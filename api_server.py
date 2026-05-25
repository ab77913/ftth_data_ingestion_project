"""
FastAPI backend for the FTTH Data Ingestion frontend.

Endpoints:
  POST /api/upload       — Upload a file, ingest it, return job summary
  GET  /api/jobs         — List all ingestion jobs
  GET  /api/jobs/{id}    — Get a single job detail
  GET  /api/records      — Paginated, filterable address records
  GET  /api/records/{id} — Single record detail
  GET  /api/columns      — Dynamic column metadata based on ingested data
  POST /api/jobs/{id}/process — Start agent processing for a job
  GET  /api/jobs/{id}/progress — SSE stream of agent progress
  GET  /api/jobs/{id}/agents — Get agent status for a job

Run: python api_server.py
"""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import String, func, select, text

from data_ingestion.config.settings import get_settings
from data_ingestion.database.db import get_engine, get_session_factory, init_db, session_scope
from data_ingestion.database.models import Address, DispatchQueue, IngestionJob
from data_ingestion.database.repositories import IngestionRepository
from data_ingestion.ingestion_service import IngestionService
from data_ingestion.schemas import IngestionStatus

app = FastAPI(title="FTTH Data Ingestion API", version="1.0.0")

# Allow the React dev server (port 5173) to hit this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173", "http://127.0.0.1:5174", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def serve_frontend():
    """Serve the single-page frontend."""
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


# ─── Response models ────────────────────────────────────────────────────────────

class JobResponse(BaseModel):
    id: str
    customer_id: str | None
    source_file: str
    row_count: int
    status: str
    error_message: str | None
    created_at: str
    updated_at: str


class RecordResponse(BaseModel):
    id: int
    record_uuid: str
    job_id: str
    customer_id: str | None
    raw_address: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    latitude: float | None
    longitude: float | None
    network_node: str | None
    terminal_id: str | None
    address_id: str | None
    normalized_key: str | None
    source_file: str
    source_sheet: str | None
    source_layer: str | None
    source_row_number: int | None
    validation_errors: Any | None
    validation_warnings: Any | None
    raw_metadata: Any | None
    created_at: str
    # Flattened raw data for table display
    raw_data: dict[str, Any] | None = None


class PaginatedRecords(BaseModel):
    records: list[RecordResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    columns: list[dict[str, Any]]
    display_mode: str = "raw"  # "raw" = show original file columns, "canonical" = show mapped fields


class UploadResponse(BaseModel):
    job_id: str
    source_file: str
    total_raw_records: int
    valid_records: int
    invalid_records: int
    duplicate_records: int
    stored_records: int
    queued_records: int
    status: str


class ColumnInfo(BaseModel):
    key: str
    label: str
    visible: bool = True


# ─── Startup ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    init_db()


# ─── Endpoints ──────────────────────────────────────────────────────────────────

@app.post("/api/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    customer_id: str = Query(default="demo_customer"),
):
    """Upload and ingest a CSV, Excel, KML, or KMZ file."""
    # Save uploaded file to disk
    suffix = Path(file.filename).suffix
    dest = UPLOAD_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        with session_scope() as session:
            repo = IngestionRepository(session)
            service = IngestionService(repo)
            result = service.ingest_file(dest, customer_id=customer_id)

        return UploadResponse(
            job_id=str(result.job_id),
            source_file=result.source_file,
            total_raw_records=result.total_raw_records,
            valid_records=result.valid_records,
            invalid_records=result.invalid_records,
            duplicate_records=result.duplicate_records,
            stored_records=result.stored_records,
            queued_records=result.queued_records,
            status=result.status.value,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/jobs", response_model=list[JobResponse])
def list_jobs():
    """List all ingestion jobs."""
    session = get_session_factory()()
    try:
        jobs = session.execute(
            select(IngestionJob).order_by(IngestionJob.created_at.desc())
        ).scalars().all()
        return [
            JobResponse(
                id=str(j.id),
                customer_id=j.customer_id,
                source_file=j.source_file,
                row_count=j.row_count,
                status=j.status,
                error_message=j.error_message,
                created_at=j.created_at.isoformat(),
                updated_at=j.updated_at.isoformat(),
            )
            for j in jobs
        ]
    finally:
        session.close()


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    """Get a single job by ID."""
    session = get_session_factory()()
    try:
        job = session.get(IngestionJob, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return JobResponse(
            id=str(job.id),
            customer_id=job.customer_id,
            source_file=job.source_file,
            row_count=job.row_count,
            status=job.status,
            error_message=job.error_message,
            created_at=job.created_at.isoformat(),
            updated_at=job.updated_at.isoformat(),
        )
    finally:
        session.close()


@app.get("/api/categories")
def get_categories(job_id: str | None = Query(default=None)):
    """Get distinct category values from records' raw_metadata."""
    session = get_session_factory()()
    try:
        cat_col = text("raw_metadata->>'category'")
        stmt = select(cat_col).where(
            text("raw_metadata->>'category' IS NOT NULL"),
            text("raw_metadata->>'category' != ''"),
        ).select_from(Address.__table__).distinct()

        if job_id:
            stmt = stmt.where(Address.job_id == job_id)

        rows = session.execute(stmt).scalars().all()
        categories = sorted(set(r for r in rows if r))
        return {"categories": categories}
    finally:
        session.close()


@app.get("/api/records", response_model=PaginatedRecords)
def list_records(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    job_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    category: str | None = Query(default=None),
    sort_by: str = Query(default="id"),
    sort_dir: str = Query(default="asc"),
):
    """Paginated address records with dynamic columns."""
    session = get_session_factory()()
    try:
        stmt = select(Address)
        count_stmt = select(func.count(Address.id))

        if job_id:
            stmt = stmt.where(Address.job_id == job_id)
            count_stmt = count_stmt.where(Address.job_id == job_id)

        if category:
            cat_filter = text("raw_metadata->>'category' = :cat").bindparams(cat=category)
            stmt = stmt.where(cat_filter)
            count_stmt = count_stmt.where(cat_filter)

        if search:
            like_pattern = f"%{search}%"
            search_filter = (
                Address.raw_address.ilike(like_pattern)
                | Address.city.ilike(like_pattern)
                | Address.state.ilike(like_pattern)
                | Address.zip_code.ilike(like_pattern)
                | Address.terminal_id.ilike(like_pattern)
                | Address.network_node.ilike(like_pattern)
                | Address.address_id.ilike(like_pattern)
                | func.cast(Address.raw_metadata, String).ilike(like_pattern)
            )
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        # Sorting
        sort_column = getattr(Address, sort_by, Address.id)
        if sort_dir == "desc":
            stmt = stmt.order_by(sort_column.desc())
        else:
            stmt = stmt.order_by(sort_column.asc())

        # Total count
        total = session.execute(count_stmt).scalar()

        # Pagination
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)
        addresses = session.execute(stmt).scalars().all()

        # Build dynamic columns based on raw_metadata from the first record
        columns = _get_raw_columns(session, job_id)

        records = [
            RecordResponse(
                id=a.id,
                record_uuid=str(a.record_uuid),
                job_id=str(a.job_id),
                customer_id=a.customer_id,
                raw_address=a.raw_address,
                city=a.city,
                state=a.state,
                zip_code=a.zip_code,
                latitude=a.latitude,
                longitude=a.longitude,
                network_node=a.network_node,
                terminal_id=a.terminal_id,
                address_id=a.address_id,
                normalized_key=a.normalized_key,
                source_file=a.source_file,
                source_sheet=a.source_sheet,
                source_layer=a.source_layer,
                source_row_number=a.source_row_number,
                validation_errors=a.validation_errors,
                validation_warnings=a.validation_warnings,
                raw_metadata=a.raw_metadata,
                created_at=a.created_at.isoformat(),
                raw_data=a.raw_metadata if a.raw_metadata else None,
            )
            for a in addresses
        ]

        total_pages = max(1, (total + page_size - 1) // page_size)

        return PaginatedRecords(
            records=records,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            columns=columns,
            display_mode="raw" if columns and columns[0].get("source") == "raw" else "canonical",
        )
    finally:
        session.close()


@app.get("/api/records/geo")
def get_geo_records(
    job_id: str | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=50000),
):
    """Get records with coordinates for map display (lightweight GeoJSON-like response)."""
    session = get_session_factory()()
    try:
        stmt = select(
            Address.id,
            Address.latitude,
            Address.longitude,
            Address.raw_address,
            Address.city,
            Address.state,
            Address.network_node,
            Address.terminal_id,
            Address.source_file,
            Address.source_row_number,
            Address.raw_metadata,
        ).where(
            Address.latitude.isnot(None),
            Address.longitude.isnot(None),
        )

        if job_id:
            stmt = stmt.where(Address.job_id == job_id)

        stmt = stmt.limit(limit)
        rows = session.execute(stmt).all()

        features = []
        for row in rows:
            meta = row.raw_metadata or {}
            style_color = meta.get("style_color", "")
            # Ensure style_color has # prefix for CSS
            if style_color and not style_color.startswith("#"):
                style_color = "#" + style_color

            feat = {
                "id": row.id,
                "lat": row.latitude,
                "lon": row.longitude,
                "address": row.raw_address or meta.get("placemark_name", ""),
                "city": row.city or "",
                "state": row.state or "",
                "network_node": row.network_node or "",
                "terminal_id": row.terminal_id or "",
                "source_file": row.source_file or "",
                "row_number": row.source_row_number,
                "category": meta.get("category", ""),
                "geometry_type": meta.get("geometry_type", ""),
                "folder_path": meta.get("folder_path", ""),
                "style_color": style_color,
                "placemark_name": meta.get("placemark_name", ""),
            }
            # Parse and include coordinates for polygons and linestrings
            geom_type = meta.get("geometry_type", "")
            if geom_type in ("Polygon", "LineString") and meta.get("coordinates"):
                parsed = _parse_kml_coordinates(meta["coordinates"], geom_type)
                if parsed:
                    feat["coordinates"] = parsed
            features.append(feat)

        return {"features": features, "count": len(features)}
    finally:
        session.close()


def _parse_kml_coordinates(coords_raw, geom_type: str):
    """Parse KML coordinate string into array format for frontend.

    KML format: 'lon,lat,alt\\nlon,lat,alt\\n...'
    Returns: [[lon, lat], ...] for LineString or [[[lon, lat], ...]] for Polygon
    """
    if isinstance(coords_raw, list):
        # Already parsed
        return coords_raw

    if not isinstance(coords_raw, str):
        return None

    try:
        # Split by whitespace/newlines and parse each coordinate tuple
        parts = coords_raw.strip().split()
        # If single-space-separated didn't work, try newline
        if len(parts) <= 1:
            parts = [p.strip() for p in coords_raw.strip().splitlines() if p.strip()]

        coords = []
        for part in parts:
            # Each part is "lon,lat,alt" or "lon,lat"
            components = part.strip().rstrip(",").split(",")
            if len(components) >= 2:
                lon = float(components[0])
                lat = float(components[1])
                coords.append([lon, lat])

        if not coords:
            return None

        if geom_type == "Polygon":
            return [coords]  # Polygon needs array of rings
        return coords  # LineString is flat array of coords
    except (ValueError, TypeError):
        return None


@app.get("/api/records/{record_id}", response_model=RecordResponse)
def get_record(record_id: int):
    """Get a single address record."""
    session = get_session_factory()()
    try:
        a = session.get(Address, record_id)
        if not a:
            raise HTTPException(status_code=404, detail="Record not found")
        return RecordResponse(
            id=a.id,
            record_uuid=str(a.record_uuid),
            job_id=str(a.job_id),
            customer_id=a.customer_id,
            raw_address=a.raw_address,
            city=a.city,
            state=a.state,
            zip_code=a.zip_code,
            latitude=a.latitude,
            longitude=a.longitude,
            network_node=a.network_node,
            terminal_id=a.terminal_id,
            address_id=a.address_id,
            normalized_key=a.normalized_key,
            source_file=a.source_file,
            source_sheet=a.source_sheet,
            source_layer=a.source_layer,
            source_row_number=a.source_row_number,
            validation_errors=a.validation_errors,
            validation_warnings=a.validation_warnings,
            raw_metadata=a.raw_metadata,
            created_at=a.created_at.isoformat(),
        )
    finally:
        session.close()


@app.get("/api/columns", response_model=list[ColumnInfo])
def get_columns(job_id: str | None = Query(default=None)):
    """Get dynamic column definitions based on data in the database."""
    session = get_session_factory()()
    try:
        columns = _get_raw_columns(session, job_id)
        return [ColumnInfo(**{k: v for k, v in c.items() if k in ("key", "label", "visible")}) for c in columns]
    finally:
        session.close()


@app.get("/api/stats")
def get_stats(job_id: str | None = Query(default=None)):
    """Get summary statistics for the dashboard."""
    session = get_session_factory()()
    try:
        base_filter = Address.job_id == job_id if job_id else True

        total = session.execute(select(func.count(Address.id)).where(base_filter)).scalar() or 0
        with_coords = session.execute(
            select(func.count(Address.id)).where(
                base_filter, Address.latitude.isnot(None), Address.longitude.isnot(None)
            )
        ).scalar() or 0
        without_coords = total - with_coords

        jobs_count = session.execute(select(func.count(IngestionJob.id))).scalar() or 0

        return {
            "total_records": total,
            "with_coordinates": with_coords,
            "without_coordinates": without_coords,
            "total_jobs": jobs_count,
        }
    finally:
        session.close()


# ─── Helpers ────────────────────────────────────────────────────────────────────

def _get_raw_columns(session, job_id: str | None) -> list[dict[str, Any]]:
    """Determine columns from raw_metadata of the first record for this job."""
    base_filter = Address.job_id == job_id if job_id else True

    # Get the first record to inspect its raw_metadata keys
    first_record = session.execute(
        select(Address.raw_metadata).where(base_filter, Address.raw_metadata.isnot(None)).limit(1)
    ).scalar()

    if first_record and isinstance(first_record, dict) and len(first_record) > 0:
        # Use raw file columns as the primary display
        columns = [{"key": "source_row_number", "label": "#", "visible": True, "source": "raw"}]
        for raw_key in first_record.keys():
            label = raw_key.replace("_", " ").title()
            columns.append({"key": raw_key, "label": label, "visible": True, "source": "raw"})
        return columns

    # Fallback: use canonical fields if no raw_metadata
    return _get_canonical_columns(session, job_id)


def _get_canonical_columns(session, job_id: str | None) -> list[dict[str, Any]]:
    """Fallback: determine which canonical columns have data."""
    base_filter = Address.job_id == job_id if job_id else True

    checks = {
        "city": Address.city,
        "state": Address.state,
        "zip_code": Address.zip_code,
        "latitude": Address.latitude,
        "longitude": Address.longitude,
        "network_node": Address.network_node,
        "terminal_id": Address.terminal_id,
        "address_id": Address.address_id,
        "source_sheet": Address.source_sheet,
        "source_layer": Address.source_layer,
    }

    has_data = {}
    for key, col in checks.items():
        count = session.execute(
            select(func.count(Address.id)).where(base_filter, col.isnot(None))
        ).scalar() or 0
        has_data[key] = count > 0

    columns = [
        {"key": "id", "label": "#", "visible": True, "source": "canonical"},
        {"key": "raw_address", "label": "Address", "visible": True, "source": "canonical"},
    ]

    if has_data.get("city"):
        columns.append({"key": "city", "label": "City", "visible": True, "source": "canonical"})
    if has_data.get("state"):
        columns.append({"key": "state", "label": "State", "visible": True, "source": "canonical"})
    if has_data.get("zip_code"):
        columns.append({"key": "zip_code", "label": "ZIP", "visible": True, "source": "canonical"})
    if has_data.get("latitude"):
        columns.append({"key": "latitude", "label": "Latitude", "visible": True, "source": "canonical"})
    if has_data.get("longitude"):
        columns.append({"key": "longitude", "label": "Longitude", "visible": True, "source": "canonical"})
    if has_data.get("network_node"):
        columns.append({"key": "network_node", "label": "Node", "visible": True, "source": "canonical"})
    if has_data.get("terminal_id"):
        columns.append({"key": "terminal_id", "label": "Terminal ID", "visible": True, "source": "canonical"})
    if has_data.get("address_id"):
        columns.append({"key": "address_id", "label": "Address ID", "visible": True, "source": "canonical"})
    if has_data.get("source_sheet"):
        columns.append({"key": "source_sheet", "label": "Sheet", "visible": True, "source": "canonical"})
    if has_data.get("source_layer"):
        columns.append({"key": "source_layer", "label": "Layer", "visible": True, "source": "canonical"})

    columns.append({"key": "source_file", "label": "Source File", "visible": True, "source": "canonical"})
    columns.append({"key": "source_row_number", "label": "Row #", "visible": True, "source": "canonical"})

    return columns


# ─── Agent Processing Infrastructure ───────────────────────────────────────────

# In-memory store for agent progress (production would use Redis/DB)
_agent_progress: dict[str, dict] = {}

AGENT_DEFINITIONS = [
    {"id": "address_parser", "name": "Address Parser", "description": "Parses raw address into structured components"},
    {"id": "smarty_geocoder", "name": "Smarty Geocoder", "description": "Geocodes addresses using SmartyStreets API"},
    {"id": "melissa_validator", "name": "Melissa Validator", "description": "Validates and enriches address data via Melissa"},
    {"id": "coordinate_extractor", "name": "Coordinate Extractor", "description": "Extracts lat/lon from address or network data"},
    {"id": "network_mapper", "name": "Network Mapper", "description": "Maps addresses to network nodes and terminals"},
    {"id": "data_enricher", "name": "Data Enricher", "description": "Fills missing fields from external data sources"},
    {"id": "kmz_generator", "name": "KMZ Generator", "description": "Generates KMZ file from processed coordinates"},
]


class AgentStatus(BaseModel):
    agent_id: str
    agent_name: str
    description: str
    status: str  # pending, running, completed, failed
    progress: int  # 0-100
    records_processed: int
    records_total: int
    started_at: str | None = None
    completed_at: str | None = None
    errors: list[str] = []


class JobProgress(BaseModel):
    job_id: str
    overall_progress: int  # 0-100
    status: str  # pending, processing, completed, failed
    agents: list[AgentStatus]
    current_agent: str | None = None
    output_csv: str | None = None
    output_kmz: str | None = None


@app.post("/api/jobs/{job_id}/process")
async def start_processing(job_id: str):
    """Start agent processing for a job. Returns immediately, progress via SSE."""
    session = get_session_factory()()
    try:
        job = session.get(IngestionJob, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Initialize progress tracking
        _agent_progress[job_id] = {
            "status": "processing",
            "overall_progress": 0,
            "current_agent_idx": 0,
            "total_records": job.row_count,
            "agents": [
                {
                    "agent_id": a["id"],
                    "agent_name": a["name"],
                    "description": a["description"],
                    "status": "pending",
                    "progress": 0,
                    "records_processed": 0,
                    "records_total": job.row_count,
                    "started_at": None,
                    "completed_at": None,
                    "errors": [],
                }
                for a in AGENT_DEFINITIONS
            ],
            "output_csv": None,
            "output_kmz": None,
        }

        # Start background processing
        asyncio.create_task(_run_agents(job_id, job.row_count))

        return {"message": "Processing started", "job_id": job_id}
    finally:
        session.close()


async def _run_agents(job_id: str, total_records: int):
    """Simulate agent processing pipeline (replace with real agent calls)."""
    progress = _agent_progress.get(job_id)
    if not progress:
        return

    for idx, agent_def in enumerate(AGENT_DEFINITIONS):
        if job_id not in _agent_progress:
            return  # Job was cancelled

        progress["current_agent_idx"] = idx
        agent = progress["agents"][idx]
        agent["status"] = "running"
        agent["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Simulate processing records in batches
        batch_size = max(1, total_records // 10)
        processed = 0
        while processed < total_records:
            await asyncio.sleep(0.5)  # Simulate work
            processed = min(processed + batch_size, total_records)
            agent["records_processed"] = processed
            agent["progress"] = int((processed / total_records) * 100)
            # Update overall progress
            completed_agents = sum(1 for a in progress["agents"] if a["status"] == "completed")
            current_progress = agent["progress"] / 100
            progress["overall_progress"] = int(
                ((completed_agents + current_progress) / len(AGENT_DEFINITIONS)) * 100
            )

        agent["status"] = "completed"
        agent["progress"] = 100
        agent["records_processed"] = total_records
        agent["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # All agents done
    progress["status"] = "completed"
    progress["overall_progress"] = 100
    progress["output_csv"] = f"/outputs/{job_id}_enriched.csv"
    progress["output_kmz"] = f"/outputs/{job_id}_output.kmz"


@app.get("/api/jobs/{job_id}/progress")
async def get_job_progress_sse(job_id: str):
    """SSE endpoint streaming real-time agent progress updates."""

    async def event_generator():
        last_sent = None
        while True:
            progress = _agent_progress.get(job_id)
            if not progress:
                yield f"data: {json.dumps({'error': 'No processing found for this job'})}\n\n"
                return

            # Build response
            current_agent = None
            if progress["status"] == "processing":
                idx = progress.get("current_agent_idx", 0)
                if idx < len(progress["agents"]):
                    current_agent = progress["agents"][idx]["agent_id"]

            payload = {
                "job_id": job_id,
                "overall_progress": progress["overall_progress"],
                "status": progress["status"],
                "current_agent": current_agent,
                "agents": progress["agents"],
                "output_csv": progress.get("output_csv"),
                "output_kmz": progress.get("output_kmz"),
            }

            payload_str = json.dumps(payload)
            if payload_str != last_sent:
                yield f"data: {payload_str}\n\n"
                last_sent = payload_str

            if progress["status"] in ("completed", "failed"):
                yield f"data: {json.dumps({'done': True})}\n\n"
                return

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/api/jobs/{job_id}/agents")
def get_job_agents(job_id: str):
    """Get current agent status for a job."""
    progress = _agent_progress.get(job_id)
    if not progress:
        # Return default pending state
        return {
            "job_id": job_id,
            "overall_progress": 0,
            "status": "pending",
            "agents": [
                {
                    "agent_id": a["id"],
                    "agent_name": a["name"],
                    "description": a["description"],
                    "status": "pending",
                    "progress": 0,
                    "records_processed": 0,
                    "records_total": 0,
                }
                for a in AGENT_DEFINITIONS
            ],
        }

    current_agent = None
    if progress["status"] == "processing":
        idx = progress.get("current_agent_idx", 0)
        if idx < len(progress["agents"]):
            current_agent = progress["agents"][idx]["agent_id"]

    return {
        "job_id": job_id,
        "overall_progress": progress["overall_progress"],
        "status": progress["status"],
        "current_agent": current_agent,
        "agents": progress["agents"],
        "output_csv": progress.get("output_csv"),
        "output_kmz": progress.get("output_kmz"),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
