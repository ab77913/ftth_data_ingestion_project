"""
Agent 1 — Address Validation (Smarty + Melissa)
================================================
Called from api_server.py when the user presses "Process" for a job.

Flow:
  1. Read addresses from the `addresses` table for the given job_id
  2. Build a RawAddressRecord for each row
  3. Canonicalize → check cache
       CACHE HIT  → restore result from cache, skip API calls
       CACHE MISS → run Smarty + Melissa → arbitrate → score → write cache
  4. Upsert results into `agent1_results`
  5. Back-fill lat/lon on the `addresses` row if it was missing
  6. Save cache once at the end of the run
"""
from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# ── add agent's src/ to path so we can import its modules ──────────────────────
AGENT_SRC = Path(__file__).resolve().parents[2] / (
    "ftth_address_validation_agent_1"
    + os.sep
    + "ftth_address_validation_agent_1"
)
if str(AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_SRC))

# Load the agent's .env so SMARTY_AUTH_ID / MELISSA_LICENSE_KEY are available
_agent_env = AGENT_SRC / ".env"
if _agent_env.exists():
    from dotenv import load_dotenv as _ld
    _ld(_agent_env, override=False)

from src.models.schemas import RawAddressRecord          # noqa: E402
from src.core.address_parser import canonicalize         # noqa: E402
from src.providers.smarty_adapter import SmartyProvider  # noqa: E402
from src.providers.melissa_adapter import MelissaProvider  # noqa: E402
from src.core.compare import compare_results             # noqa: E402
from src.core.scoring import choose_result, structure_hint, validation_status  # noqa: E402
from src.core.provider_arbitration import provider_arbitration  # noqa: E402
from src.providers.cache_lookup import AddressCache, generate_cache_key  # noqa: E402

_CACHE_FILE = AGENT_SRC / "cache" / "cache.json"

from sqlalchemy.orm.attributes import flag_modified

from data_ingestion.database.db import get_session_factory
from data_ingestion.database.models import Address, Agent1Result

logger = logging.getLogger(__name__)


def _row_to_raw(addr: Address) -> RawAddressRecord:
    """Convert an Address ORM row to a RawAddressRecord for the agent."""
    meta = addr.raw_metadata or {}
    raw = (
        addr.raw_address
        or meta.get("raw_address")
        or meta.get("address")
        or ""
    )
    city  = addr.city  or meta.get("city")  or ""
    state = addr.state or meta.get("state") or ""
    zip_c = addr.zip_code or meta.get("zip") or meta.get("zip_code") or ""
    return RawAddressRecord(
        source_file=addr.source_file or "db",
        source_type="db",
        row_id=str(addr.source_row_number or addr.id),
        address_id=str(addr.id),
        raw_address=raw,
        city=city,
        state=state,
        zip_code=str(zip_c)[:5] if zip_c else None,
        latitude=addr.latitude,
        longitude=addr.longitude,
        network_node=addr.network_node or meta.get("network_node"),
        terminal_id=addr.terminal_id or meta.get("terminal_id"),
    )


def run_agent1_for_job(job_id: str, progress_callback=None) -> dict:
    """
    Run Agent 1 for all addresses in `job_id`.
    progress_callback(done, total) is called after each record if provided.
    Returns summary dict.
    """
    session = get_session_factory()()
    smarty   = SmartyProvider()
    melissa  = MelissaProvider()

    # Load cache once — avoids per-address disk I/O
    cache = AddressCache(cache_file=_CACHE_FILE).load()
    logger.info("Agent1: cache loaded — %d existing entries", cache.stats()["total_entries"])

    summary = {"total": 0, "auto_accept": 0, "manual_review": 0,
               "reject": 0, "errored": 0, "cache_hits": 0, "cache_misses": 0}
    try:
        from sqlalchemy import select as _sel
        addresses = session.scalars(
            _sel(Address).where(Address.job_id == job_id).order_by(Address.id)
        ).all()

        total = len(addresses)
        summary["total"] = total
        logger.info("Agent1: processing %d addresses for job %s", total, job_id)

        for idx, addr in enumerate(addresses, 1):
            try:
                raw_rec   = _row_to_raw(addr)
                canonical = canonicalize(raw_rec)

                cache_key = generate_cache_key(canonical)
                cached    = cache.get(cache_key)

                # ── Upsert skeleton ───────────────────────────────────────────
                existing = session.scalar(
                    _sel(Agent1Result).where(Agent1Result.address_id == addr.id)
                )
                now = datetime.utcnow()
                if existing:
                    row = existing
                    row.updated_at = now
                else:
                    row = Agent1Result(job_id=job_id, address_id=addr.id,
                                      created_at=now, updated_at=now)
                    session.add(row)

                row.raw_address       = canonical.raw_address
                row.canonical_address = canonical.normalized_full_address

                if cached:
                    # ── CACHE HIT — restore from cache, no API calls ──────────
                    logger.debug("Agent1 cache hit: %s", canonical.normalized_full_address)
                    summary["cache_hits"] += 1

                    score  = cached.get("confidence_score", cached.get("score", 0))
                    status = cached.get("validation_status") or (
                        "AUTO_ACCEPT"   if score >= 80 else
                        "MANUAL_REVIEW" if score >= 40 else
                        "REJECT"
                    )

                    row.smarty_standardized_address  = cached.get("smarty_standardized_address")
                    row.smarty_dpv                   = cached.get("smarty_dpv")
                    row.smarty_zip_plus_4            = cached.get("smarty_zip_plus_4")
                    row.smarty_vacant                = cached.get("smarty_vacant")
                    row.smarty_record_type           = cached.get("smarty_record_type")
                    row.smarty_lat                   = cached.get("smarty_lat")
                    row.smarty_lon                   = cached.get("smarty_lon")
                    row.melissa_standardized_address = cached.get("melissa_standardized_address")
                    row.melissa_dpv                  = cached.get("melissa_dpv")
                    row.melissa_zip_plus_4           = cached.get("melissa_zip_plus_4")
                    row.melissa_vacant               = cached.get("melissa_vacant")
                    row.melissa_record_type          = cached.get("melissa_record_type")
                    row.chosen_standardized_address  = (
                        cached.get("chosen_standardized_address")
                        or cached.get("standardized_address")
                    )
                    row.chosen_provider              = cached.get("chosen_provider", cached.get("provider", "cache"))
                    row.structure_hint               = cached.get("structure_hint", "CACHE_HIT")
                    row.confidence_score             = score
                    row.validation_status            = status
                    row.exception_reason             = cached.get("exception_reason")
                    row.comparison_reason            = "Loaded from cache"

                    smarty_lat = cached.get("smarty_lat")
                    smarty_lon = cached.get("smarty_lon")
                    smarty_zip = cached.get("smarty_zip_plus_4")

                else:
                    # ── CACHE MISS — call APIs ────────────────────────────────
                    logger.debug("Agent1 cache miss: %s", canonical.normalized_full_address)
                    summary["cache_misses"] += 1

                    smarty_result  = smarty.validate(canonical)
                    melissa_result = melissa.validate(canonical)

                    comparison = None
                    if smarty_result.success and melissa_result.success:
                        try:
                            comparison = compare_results(smarty_result, melissa_result)
                        except Exception:
                            comparison = None

                    chosen, score = provider_arbitration(smarty_result, melissa_result)
                    hint   = structure_hint(chosen, canonical.normalized_full_address)
                    status, exc_reason = validation_status(score, chosen, comparison)
                    comparison_reason = (
                        f"{comparison.conflict_level}: {comparison.reason}"
                        if comparison
                        else ("smarty_only" if smarty_result.success else
                              "melissa_only" if melissa_result.success else
                              "both_failed")
                    )

                    row.smarty_standardized_address  = smarty_result.standardized_address
                    row.smarty_dpv                   = smarty_result.dpv_match
                    row.smarty_zip_plus_4            = smarty_result.zip_plus_4
                    row.smarty_vacant                = smarty_result.vacant
                    row.smarty_record_type           = smarty_result.record_type
                    row.smarty_lat                   = smarty_result.latitude
                    row.smarty_lon                   = smarty_result.longitude
                    row.melissa_standardized_address = melissa_result.standardized_address
                    row.melissa_dpv                  = melissa_result.dpv_match
                    row.melissa_zip_plus_4           = melissa_result.zip_plus_4
                    row.melissa_vacant               = melissa_result.vacant
                    row.melissa_record_type          = melissa_result.record_type
                    row.chosen_standardized_address  = chosen.standardized_address
                    row.chosen_provider              = chosen.provider
                    row.structure_hint               = hint
                    row.confidence_score             = score
                    row.validation_status            = status
                    row.exception_reason             = exc_reason
                    row.comparison_reason            = comparison_reason

                    smarty_lat = smarty_result.latitude
                    smarty_lon = smarty_result.longitude
                    smarty_zip = smarty_result.zip_plus_4

                    # ── Write full result to cache ────────────────────────────
                    cache.set(cache_key, {
                        "normalized_full_address":       canonical.normalized_full_address,
                        "chosen_provider":               chosen.provider,
                        "chosen_standardized_address":   chosen.standardized_address,
                        "confidence_score":              score,
                        "validation_status":             status,
                        "structure_hint":                hint,
                        "exception_reason":              exc_reason,
                        "smarty_standardized_address":   smarty_result.standardized_address,
                        "smarty_dpv":                    smarty_result.dpv_match,
                        "smarty_zip_plus_4":             smarty_result.zip_plus_4,
                        "smarty_vacant":                 smarty_result.vacant,
                        "smarty_record_type":            smarty_result.record_type,
                        "smarty_lat":                    smarty_result.latitude,
                        "smarty_lon":                    smarty_result.longitude,
                        "smarty_geocode_precision":      smarty_result.geocode_precision,
                        "melissa_standardized_address":  melissa_result.standardized_address,
                        "melissa_dpv":                   melissa_result.dpv_match,
                        "melissa_zip_plus_4":            melissa_result.zip_plus_4,
                        "melissa_vacant":                melissa_result.vacant,
                        "melissa_record_type":           melissa_result.record_type,
                        "melissa_lat":                   melissa_result.latitude,
                        "melissa_lon":                   melissa_result.longitude,
                    })

                # ── Back-fill lat/lon on addresses row if missing or zero ─────
                if smarty_lat and (not addr.latitude or addr.latitude == 0):
                    addr.latitude  = smarty_lat
                    addr.longitude = smarty_lon

                # ── Also write into raw_metadata so table displays correct values
                if smarty_lat:
                    meta = dict(addr.raw_metadata or {})
                    for k in list(meta.keys()):
                        kl = k.lower().replace(" ", "_")
                        if kl == "network_node_latitude":
                            meta[k] = smarty_lat
                        elif kl == "network_node_longitude":
                            meta[k] = smarty_lon
                    addr.raw_metadata = meta
                    flag_modified(addr, "raw_metadata")

                # ── Back-fill zip+4 on addresses row if missing ────────────
                if not addr.zip_code and smarty_zip:
                    addr.zip_code = smarty_zip

                session.flush()

                if row.validation_status == "AUTO_ACCEPT":
                    summary["auto_accept"] += 1
                elif row.validation_status == "MANUAL_REVIEW":
                    summary["manual_review"] += 1
                else:
                    summary["reject"] += 1

            except Exception as e:
                logger.warning("Agent1: error on address_id=%s: %s", addr.id, e)
                summary["errored"] += 1

            if progress_callback:
                progress_callback(idx, total)

        session.commit()

        # Save cache once — efficient, no per-address file writes
        cache.save()
        logger.info("Agent1: cache saved — %d total entries", cache.stats()["total_entries"])
        logger.info("Agent1 complete: %s", summary)
        return summary

    except Exception as e:
        session.rollback()
        logger.error("Agent1 run failed for job %s: %s", job_id, e)
        raise
    finally:
        session.close()
