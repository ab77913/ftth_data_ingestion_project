from __future__ import annotations

from typing import Any

from data_ingestion.schemas import CanonicalAddressRecord, RawExtractedRecord
from data_ingestion.utils.strings import (
    clean_value,
    normalize_address_key,
    normalize_header,
    parse_kml_coordinate,
    safe_float,
)


FIELD_ALIASES: dict[str, set[str]] = {
    "raw_address": {
        "address",
        "address 1",
        "address line 1",
        "addr1",
        "street address",
        "service address",
        "raw address",
        "full address",
        "location address",
        "placemark name",
        "name2",
        "rawaddress",
        "secondary number",
        "secondarynumber",
    },
    "city": {"city", "city name", "municipality", "town"},
    "state": {"state", "st", "state code"},
    "zip_code": {"zip", "zip code", "zipcode", "postal code", "zip5"},
    "latitude": {"lat", "latitude", "y", "y coordinate"},
    "longitude": {"lon", "lng", "long", "longitude", "x", "x coordinate"},
    "network_node": {
        "node",
        "network node",
        "fiber node",
        "serving area",
        "service area",
        "hub",
        "pon",
    },
    "terminal_id": {
        "terminal",
        "terminal id",
        "terminal_id",
        "terminalid",
        "terminal number",
        "terminalnumber",
        "tap",
        "mst",
        "fat",
    },
    "address_id": {
        "address id",
        "address_id",
        "addressid",
        "addr id",
        "customer id",
        "cust id",
        "location id",
        "id",
    },
    "coordinates": {"coordinates", "coords", "coordinate"},
}


class CanonicalMapper:
    """Map extractor-specific raw rows/features into the canonical FTTH schema."""

    def map_record(
        self,
        raw_record: RawExtractedRecord,
        *,
        customer_id: str | None = None,
    ) -> CanonicalAddressRecord:
        raw = raw_record.raw_data
        normalized_lookup = self._build_normalized_lookup(raw)

        raw_address = self._first_value(normalized_lookup, "raw_address")
        if raw_address is None:
            raw_address = clean_value(raw.get("placemark_name") or raw.get("name"))

        coordinates = self._first_value(normalized_lookup, "coordinates")
        latitude = safe_float(self._first_value(normalized_lookup, "latitude"))
        longitude = safe_float(self._first_value(normalized_lookup, "longitude"))

        if (latitude is None or longitude is None) and coordinates:
            latitude, longitude = parse_kml_coordinate(coordinates)

        record = CanonicalAddressRecord(
            raw_address=raw_address,
            city=self._first_value(normalized_lookup, "city"),
            state=self._first_value(normalized_lookup, "state"),
            zip_code=self._first_value(normalized_lookup, "zip_code"),
            latitude=latitude,
            longitude=longitude,
            network_node=self._first_value(normalized_lookup, "network_node"),
            terminal_id=self._first_value(normalized_lookup, "terminal_id"),
            address_id=self._first_value(normalized_lookup, "address_id"),
            customer_id=customer_id,
            source_file=raw_record.source_file,
            source_sheet=raw_record.source_sheet,
            source_layer=raw_record.source_layer,
            source_row_number=raw_record.row_number,
            raw_metadata=raw,
        )
        record.normalized_key = self._build_duplicate_key(record)
        return record

    def map_records(
        self,
        raw_records: list[RawExtractedRecord],
        *,
        customer_id: str | None = None,
    ) -> list[CanonicalAddressRecord]:
        return [self.map_record(record, customer_id=customer_id) for record in raw_records]

    def _build_normalized_lookup(self, raw: dict[str, Any]) -> dict[str, Any]:
        lookup: dict[str, Any] = {}
        for key, value in raw.items():
            norm_key = normalize_header(key)
            if not norm_key:
                continue
            lookup[norm_key] = clean_value(value)
        return lookup

    def _first_value(self, normalized_lookup: dict[str, Any], canonical_field: str) -> Any:
        accepted = FIELD_ALIASES[canonical_field]
        for key, value in normalized_lookup.items():
            if key in accepted and value is not None:
                return value
        return None

    def _build_duplicate_key(self, record: CanonicalAddressRecord) -> str | None:
        address_key = normalize_address_key(record.raw_address)
        if not address_key:
            return None
        parts = [address_key]
        if record.zip_code:
            parts.append(str(record.zip_code))
        elif record.city and record.state:
            parts.append(str(record.city).upper())
            parts.append(str(record.state).upper())
        return "|".join(parts)
