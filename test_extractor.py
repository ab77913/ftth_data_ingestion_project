"""Test the improved KML extractor on the real KMZ file."""
import zipfile
from pathlib import Path
from data_ingestion.extractors.kml_extractor import KMLExtractor

kmz_path = Path(r"c:\Users\ab77913\SEFH16756 - EWR24675 LEXINGTON (1)\SEFH16756 - EWR24675 LEXINGTON.kmz")

# Extract KML from KMZ
with zipfile.ZipFile(kmz_path) as z:
    kml_files = [n for n in z.namelist() if n.endswith('.kml')]
    content = z.read(kml_files[0])

extractor = KMLExtractor()
records = extractor.extract_from_bytes(content, source_file=kmz_path.name)

print(f"Total records extracted: {len(records)}")
print()

# Show category breakdown
from collections import Counter
categories = Counter(r.raw_data.get("category", "(none)") for r in records)
geom_types = Counter(r.raw_data.get("geometry_type", "?") for r in records)

print("Categories:")
for cat, count in categories.most_common():
    print(f"  {cat:20s}: {count}")

print("\nGeometry types:")
for gt, count in geom_types.most_common():
    print(f"  {gt:12s}: {count}")

print("\nSample records (1 per category):")
seen = set()
for r in records:
    cat = r.raw_data.get("category", "")
    if cat not in seen:
        seen.add(cat)
        print(f"\n  [{cat}] row={r.row_number} layer={r.source_layer}")
        for k, v in r.raw_data.items():
            val = str(v)[:80]
            print(f"    {k}: {val}")

print(f"\nKeys in first record: {list(records[0].raw_data.keys())}")
print(f"Keys count: {len(records[0].raw_data.keys())}")
