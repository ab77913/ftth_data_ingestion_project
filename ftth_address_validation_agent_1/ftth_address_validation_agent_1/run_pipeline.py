import argparse
import os
from pathlib import Path
from dotenv import load_dotenv
from src.extractors.loader import load_records
from src.core.address_parser import canonicalize
from src.providers.mock_provider import MockSmartyProvider, MockMelissaProvider
from src.providers.smarty_adapter import SmartyProvider
from src.providers.melissa_adapter import MelissaProvider
from src.core.compare import compare_results
from src.core.scoring import choose_result, structure_hint, validation_status
from src.core.output import write_outputs
from src.models.schemas import FinalValidationRecord
from src.utils.logging import get_logger

from src.providers.cache_lookup import (
    generate_cache_key,
    get_cached_result,
    save_cached_result
)

from src.core.provider_arbitration import (
    provider_arbitration
)

logger = get_logger(__name__)


def build_providers(use_mock: bool):
    if use_mock:
        return MockSmartyProvider(), MockMelissaProvider()
    return SmartyProvider(), MelissaProvider()


def run(input_path: str, output_path: str, limit: int | None = None, use_mock: bool = True):
    logger.info("Loading input records from %s", input_path)
    raw_records = load_records(input_path)
    if limit:
        raw_records = raw_records[:limit]
    logger.info("Loaded %d candidate address records", len(raw_records))

    smarty_provider, melissa_provider = build_providers(use_mock)
    final_records = []

    # for raw in raw_records:
    #     canonical = canonicalize(raw)
    #     smarty = smarty_provider.validate(canonical)
        # melissa = melissa_provider.validate(canonical)

    for raw in raw_records:

        smarty = None
        melissa = None
        chosen = None
        score = 0
        comparison = None

        canonical = canonicalize(raw)

        print("\n========== CANONICAL ==========")
        print(vars(canonical))

        print("\n==============================")
        print("RAW ADDRESS:")
        print(canonical.raw_address)

        print("\nCANONICAL OBJECT:")
        print(vars(canonical))

        # smarty = smarty_provider.validate(canonical)

        # print("\n========== SMARTY ==========")
        # print(vars(smarty))

        # print("\nSMARTY RESPONSE:")
        # print(vars(smarty))

        # melissa = melissa_provider.validate(canonical)

        # print("\nMELISSA RESPONSE:")
        # print(vars(melissa))
        
        # comparison = compare_results(smarty, melissa)
        # chosen, score = choose_result(smarty, melissa, comparison)


        cache_key = generate_cache_key(canonical)

        cached_result = get_cached_result(cache_key)

        # =========================
        # CACHE HIT
        # =========================
        if cached_result:

            print("\n========== CACHE HIT ==========")

            final_records.append(
                FinalValidationRecord(
                    source_file=canonical.source_file,
                    row_id=canonical.row_id,
                    address_id=canonical.address_id,
                    raw_address=canonical.raw_address,
                    canonical_address=canonical.normalized_full_address,

                    smarty_standardized_address=None,
                    melissa_standardized_address=None,

                    chosen_standardized_address=cached_result.get(
                        "standardized_address"
                    ),

                    smarty_dpv=None,
                    melissa_dpv=None,

                    smarty_zip_plus_4=None,
                    melissa_zip_plus_4=None,

                    smarty_vacant=None,
                    melissa_vacant=None,

                    smarty_record_type=None,
                    melissa_record_type=None,

                    chosen_provider=cached_result.get(
                        "provider"
                    ),

                    structure_hint="CACHE_HIT",

                    confidence_score=cached_result.get(
                        "score", 0
                    ),

                    # validation_status="AUTO_ACCEPT",
                    validation_status=(
                        "AUTO_ACCEPT"
                        if cached_result.get("score", 0) >= 80
                        else "MANUAL_REVIEW"
                        if cached_result.get("score", 0) >= 40
                        else "REJECT"
                    ),

                    exception_reason=None,

                    comparison_reason="Loaded from cache"
                )
            )

            continue

        # =========================
        # CACHE MISS
        # =========================
        print("\n========== CACHE MISS ==========")

        smarty = smarty_provider.validate(canonical)

        print("\n========== SMARTY ==========")
        print(vars(smarty))

        melissa = melissa_provider.validate(canonical)

        print("\n========== MELISSA ==========")
        print(vars(melissa))

        # =========================
        # COMPARISON
        # =========================
        if smarty.success and melissa.success:

            comparison = compare_results(
                smarty,
                melissa
            )

        else:

            comparison = None

        # =========================
        # PROVIDER ARBITRATION
        # =========================
        chosen, score = provider_arbitration(
            smarty,
            melissa
        )

        # =========================
        # SAVE CACHE
        # =========================
        save_cached_result(
            cache_key,
            {
                "provider": chosen.provider,
                "score": score,
                "standardized_address": chosen.standardized_address
            }
        )

        hint = structure_hint(chosen, canonical.normalized_full_address)
        status, exception_reason = validation_status(score, chosen, comparison)
        final_records.append(FinalValidationRecord(
            source_file=canonical.source_file,
            row_id=canonical.row_id,
            address_id=canonical.address_id,
            raw_address=canonical.raw_address,
            canonical_address=canonical.normalized_full_address,
            smarty_standardized_address=smarty.standardized_address,
            melissa_standardized_address=melissa.standardized_address,
            chosen_standardized_address=chosen.standardized_address,
            smarty_dpv=smarty.dpv_match,
            melissa_dpv=melissa.dpv_match,
            smarty_zip_plus_4=smarty.zip_plus_4,
            melissa_zip_plus_4=melissa.zip_plus_4,
            smarty_vacant=smarty.vacant,
            melissa_vacant=melissa.vacant,
            smarty_record_type=smarty.record_type,
            melissa_record_type=melissa.record_type,
            chosen_provider=chosen.provider,
            structure_hint=hint,
            confidence_score=score,
            validation_status=status,
            exception_reason=exception_reason,
            # comparison_reason=f"{comparison.conflict_level}: {comparison.reason}",
            comparison_reason=(
                f"{comparison.conflict_level}: {comparison.reason}"
                if comparison
                else "Both providers failed"
            ),
        ))
    paths = write_outputs(final_records, output_path)
    logger.info("Output generated: %s", paths)
    return paths


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser(description="FTTH Smarty + Melissa Address Validation Agent")
    parser.add_argument("--input", default=os.getenv("INPUT_PATH", "data/input"), help="Input file or folder")
    parser.add_argument("--output", default=os.getenv("OUTPUT_PATH", "outputs"), help="Output folder")
    parser.add_argument("--limit", type=int, default=None, help="Limit records for POC testing")
    parser.add_argument("--real-apis", action="store_true", help="Use real Smarty/Melissa APIs instead of mock mode")
    args = parser.parse_args()
    use_mock = os.getenv("USE_MOCK_PROVIDERS", "true").lower() == "true"
    if args.real_apis:
        use_mock = False
    run(args.input, args.output, args.limit, use_mock)
