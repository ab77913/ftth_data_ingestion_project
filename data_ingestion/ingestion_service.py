from __future__ import annotations

import logging
from pathlib import Path

from data_ingestion.database.repositories import IngestionRepository
from data_ingestion.extractors import CSVExtractor, ExcelExtractor, KMLExtractor, KMZExtractor
from data_ingestion.extractors.base import BaseExtractor
from data_ingestion.parsers import CanonicalMapper
from data_ingestion.schemas import IngestionResult, IngestionStatus
from data_ingestion.utils.file_detection import FileType, detect_file_type
from data_ingestion.validators import validate_and_deduplicate

logger = logging.getLogger(__name__)


class IngestionService:
    """End-to-end orchestration for the ingestion pipeline."""

    def __init__(self, repository: IngestionRepository):
        self.repository = repository
        self.mapper = CanonicalMapper()

    def ingest_file(self, file_path: str | Path, *, customer_id: str | None = None) -> IngestionResult:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Input file does not exist: {path}")

        logger.info("Starting ingestion for %s", path)
        extractor = self._get_extractor(path)
        raw_records = extractor.extract(path)
        job = self.repository.create_job(
            customer_id=customer_id,
            source_file=path.name,
            row_count=len(raw_records),
        )

        try:
            canonical_records = self.mapper.map_records(raw_records, customer_id=customer_id)
            for record in canonical_records:
                record.job_id = job.id

            validation_summary = validate_and_deduplicate(canonical_records)

            # Store ALL records (valid + invalid + duplicate) so they appear in the UI
            # Clear normalized_key on duplicates/invalid to avoid unique constraint violations
            for rec in validation_summary.duplicate_records:
                rec.normalized_key = None
            for rec in validation_summary.invalid_records:
                rec.normalized_key = None
            all_records = (
                validation_summary.valid_records
                + validation_summary.invalid_records
                + validation_summary.duplicate_records
            )
            saved_addresses = self.repository.save_addresses(all_records)
            # Only enqueue valid records for downstream dispatch
            valid_saved = saved_addresses[:validation_summary.valid_count]
            queued_count = self.repository.enqueue_addresses(valid_saved)

            status = IngestionStatus.COMPLETED
            if validation_summary.invalid_count > 0 or validation_summary.duplicate_count > 0:
                status = IngestionStatus.PARTIAL

            self.repository.update_job_status(job.id, status)
            self.repository.create_log(
                job_id=job.id,
                source_file=path.name,
                records_processed=len(raw_records),
                records_valid=validation_summary.valid_count,
                records_invalid=validation_summary.invalid_count,
                records_duplicate=validation_summary.duplicate_count,
                status=status,
            )

            return IngestionResult(
                job_id=job.id,
                source_file=path.name,
                total_raw_records=len(raw_records),
                valid_records=validation_summary.valid_count,
                invalid_records=validation_summary.invalid_count,
                duplicate_records=validation_summary.duplicate_count,
                stored_records=len(all_records),
                queued_records=queued_count,
                status=status,
            )
        except Exception as exc:  # noqa: BLE001 - capture failure in job log
            logger.exception("Ingestion failed for %s", path)
            self.repository.update_job_status(job.id, IngestionStatus.FAILED, error_message=str(exc))
            self.repository.create_log(
                job_id=job.id,
                source_file=path.name,
                records_processed=len(raw_records),
                records_valid=0,
                records_invalid=0,
                records_duplicate=0,
                status=IngestionStatus.FAILED,
                message=str(exc),
            )
            raise

    def _get_extractor(self, path: Path) -> BaseExtractor:
        file_type = detect_file_type(path)
        if file_type == FileType.CSV:
            return CSVExtractor()
        if file_type == FileType.EXCEL:
            return ExcelExtractor()
        if file_type == FileType.KML:
            return KMLExtractor()
        if file_type == FileType.KMZ:
            return KMZExtractor()
        raise ValueError(f"No extractor available for file type: {file_type}")
