"""Quick test: ingest KMZ file."""
from pathlib import Path
from data_ingestion.database.db import session_scope
from data_ingestion.database.repositories import IngestionRepository
from data_ingestion.ingestion_service import IngestionService

with session_scope() as s:
    repo = IngestionRepository(s)
    svc = IngestionService(repo)
    result = svc.ingest_file(
        Path(r"c:\Users\ab77913\SEFH16756 - EWR24675 LEXINGTON (1)\SEFH16756 - EWR24675 LEXINGTON.kmz")
    )
    print(f"KMZ: total={result.total_raw_records}, valid={result.valid_records}, stored={result.stored_records}, status={result.status}")
