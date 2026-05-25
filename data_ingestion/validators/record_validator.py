from __future__ import annotations

from dataclasses import dataclass, field

from data_ingestion.schemas import CanonicalAddressRecord


@dataclass
class ValidationSummary:
    valid_records: list[CanonicalAddressRecord] = field(default_factory=list)
    invalid_records: list[CanonicalAddressRecord] = field(default_factory=list)
    duplicate_records: list[CanonicalAddressRecord] = field(default_factory=list)

    @property
    def valid_count(self) -> int:
        return len(self.valid_records)

    @property
    def invalid_count(self) -> int:
        return len(self.invalid_records)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicate_records)


def validate_record(record: CanonicalAddressRecord) -> CanonicalAddressRecord:
    """Apply POC validation rules.

    This intentionally avoids provider-specific USPS/Smarty/Melissa checks.
    """
    record.validation_errors.clear()
    record.validation_warnings.clear()

    if not record.raw_address:
        record.validation_errors.append("missing_raw_address")

    if record.latitude is None or record.longitude is None:
        record.validation_warnings.append("missing_coordinates")
    else:
        if not -90 <= record.latitude <= 90:
            record.validation_errors.append("invalid_latitude")
        if not -180 <= record.longitude <= 180:
            record.validation_errors.append("invalid_longitude")

    if not record.normalized_key and record.raw_address:
        record.validation_warnings.append("missing_normalized_key")

    return record


def validate_and_deduplicate(records: list[CanonicalAddressRecord]) -> ValidationSummary:
    summary = ValidationSummary()
    seen_keys: set[str] = set()

    for record in records:
        record = validate_record(record)
        if record.validation_errors:
            summary.invalid_records.append(record)
            continue

        duplicate_key = record.normalized_key
        if duplicate_key and duplicate_key in seen_keys:
            record.validation_warnings.append("duplicate_in_job")
            summary.duplicate_records.append(record)
            continue

        if duplicate_key:
            seen_keys.add(duplicate_key)

        summary.valid_records.append(record)

    return summary
