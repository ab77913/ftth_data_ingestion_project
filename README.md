# FTTH Data Ingestion & Extraction Module

A reusable Python ingestion service for FTTH address/GIS inputs. It reads CSV, Excel, KML, and KMZ files; extracts structured records; maps them into a canonical FTTH schema; validates and deduplicates records; stores them in PostgreSQL/PostGIS; and dispatches normalized records sequentially to downstream verification agents.

This project is intentionally provider-agnostic. It does **not** call Smarty, Melissa, Street View, AI classifiers, or parcel enrichment services. Those belong downstream.

## What this POC includes

- File detection for `.csv`, `.xlsx`, `.xls`, `.kml`, and `.kmz`
- CSV ingestion
- Excel ingestion
- Real KML/KMZ placemark extraction
- Flattened KML/KMZ export extraction, including tables like:
  - `ns1:name2`
  - `name`
  - `ns1:value`
  - `ns1:coordinates`
- Canonical FTTH address schema
- Missing-field validation
- Coordinate validation
- In-job deduplication
- PostgreSQL/PostGIS persistence
- Sequential dispatcher stub for downstream agents
- Docker Compose for local PostGIS

## Architecture

```text
Input Files
    ↓
File Detector
    ↓
File-Type Extractors
    ↓
Canonical Mapper
    ↓
Validation / Deduplication
    ↓
PostgreSQL / PostGIS
    ↓
Sequential Dispatcher
    ↓
Downstream Verification Agents
```

## Folder structure

```text
ftth_data_ingestion_project/
├── data_ingestion/
│   ├── config/
│   ├── database/
│   ├── dispatcher/
│   ├── extractors/
│   ├── parsers/
│   ├── utils/
│   ├── validators/
│   ├── logging_config.py
│   └── schemas.py
├── examples/
├── scripts/
├── tests/
├── .env.example
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
└── run_ingestion.py
```

## Quick start

### 1. Create environment

```bash
python -m venv .venv
source .venv/bin/activate      # macOS/Linux
# .venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

### 2. Start PostgreSQL/PostGIS

```bash
docker compose up -d
```

### 3. Configure environment

```bash
cp .env.example .env
```

Default local connection:

```text
DATABASE_URL=postgresql+psycopg2://ftth:ftth@localhost:5432/ftth
```

### 4. Run ingestion

```bash
python run_ingestion.py ingest examples/sample_addresses.csv --customer-id demo_customer
```

### 5. Dispatch pending records

```bash
python run_ingestion.py dispatch --limit 50
```

## Input examples

### Simple CSV

```csv
Address,City,State,ZIP,Latitude,Longitude,Terminal ID,Node,Address ID
1603 LAFAYETTE ST,,,,-84.241345,32.086591,T-1,6BA8,A1098636881
706 KINGS WAY,,,,-84.242501,32.088068,T-1,6BA8,A1098631951
```

### Flattened KML/KMZ Excel export

The project detects repeated placemark rows like this:

| ns1:name2 | name | ns1:value | ns1:coordinates |
|---|---|---|---|
| 1603 LAFAYETTE ST | Address | 1603 LAFAYETTE ST | -84.241345,32.086591,0 |
| 1603 LAFAYETTE ST | Address ID | A1098636881 | -84.241345,32.086591,0 |
| 1603 LAFAYETTE ST | ZIP |  | -84.241345,32.086591,0 |

The extractor groups rows by placemark name and emits one raw record per address/placemark.

## Canonical record

```json
{
  "record_type": "ADDRESS",
  "raw_address": "1603 LAFAYETTE ST",
  "city": null,
  "state": null,
  "zip_code": null,
  "latitude": 32.086591,
  "longitude": -84.241345,
  "network_node": "6BA8",
  "terminal_id": "T-1",
  "address_id": "A1098636881",
  "source_file": "sample_addresses.csv",
  "source_layer": null,
  "raw_metadata": {}
}
```

## Database tables

- `ingestion_jobs`
- `addresses`
- `network_assets`
- `ingestion_logs`
- `dispatch_queue`

The `addresses.geom` column is a PostGIS `GEOMETRY(Point, 4326)` field populated when both longitude and latitude are available.

## Development commands

```bash
ruff check .
pytest
```

## Notes

- The ingestion module does not validate USPS delivery status.
- The ingestion module does not classify SFU/MDU/MXU/Anchor.
- The ingestion module does not perform Street View or parcel matching.
- Downstream agents should consume the records from `dispatch_queue` or query canonical records by `job_id`.
