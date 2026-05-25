from data_ingestion.schemas import CanonicalAddressRecord
from data_ingestion.validators import validate_and_deduplicate


def test_validate_and_deduplicate():
    records = [
        CanonicalAddressRecord(source_file="x.csv", raw_address="1603 LAFAYETTE ST", normalized_key="1603 LAFAYETTE ST"),
        CanonicalAddressRecord(source_file="x.csv", raw_address="1603 LAFAYETTE ST", normalized_key="1603 LAFAYETTE ST"),
        CanonicalAddressRecord(source_file="x.csv", raw_address=None),
    ]

    summary = validate_and_deduplicate(records)

    assert summary.valid_count == 1
    assert summary.duplicate_count == 1
    assert summary.invalid_count == 1
