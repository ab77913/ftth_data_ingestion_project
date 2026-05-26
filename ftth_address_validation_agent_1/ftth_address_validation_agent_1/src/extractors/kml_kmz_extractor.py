import re
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple
from xml.etree import ElementTree as ET
from src.models.schemas import RawAddressRecord

ADDRESS_RE = re.compile(r"\b\d{1,6}\s+[A-Za-z0-9][A-Za-z0-9 .#\-/]+\b")
COORD_RE = re.compile(r"(-?\d+\.\d+),(-?\d+\.\d+)(?:,[-?\d.]*)?")


def _read_kml_text(path: Path) -> str:
    if path.suffix.lower() == ".kmz":
        with zipfile.ZipFile(path, "r") as z:
            kml_files = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if not kml_files:
                return ""
            return z.read(kml_files[0]).decode("utf-8", errors="ignore")
    return path.read_text(encoding="utf-8", errors="ignore")


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1]


def _text(elem, child_name: str) -> Optional[str]:
    for child in list(elem):
        if _strip_ns(child.tag) == child_name:
            return (child.text or "").strip()
    return None


def _coords(elem) -> Tuple[Optional[float], Optional[float]]:
    all_text = " ".join([t.strip() for t in elem.itertext() if t and t.strip()])
    m = COORD_RE.search(all_text)
    if not m:
        return None, None
    lon, lat = float(m.group(1)), float(m.group(2))
    return lat, lon


def _extract_address_from_text(*texts: Optional[str]) -> str:
    combined = " ".join([t for t in texts if t])
    m = ADDRESS_RE.search(combined)
    return m.group(0).upper() if m else ""


def extract_kml_kmz(path: str | Path) -> List[RawAddressRecord]:
    path = Path(path)
    kml = _read_kml_text(path)
    if not kml:
        return []
    root = ET.fromstring(kml.encode("utf-8"))
    records: List[RawAddressRecord] = []
    placemarks = [e for e in root.iter() if _strip_ns(e.tag) == "Placemark"]
    for idx, pm in enumerate(placemarks):
        name = _text(pm, "name")
        desc = _text(pm, "description")
        lat, lon = _coords(pm)
        raw_address = _extract_address_from_text(name, desc)
        if not raw_address:
            continue
        records.append(
            RawAddressRecord(
                source_file=path.name,
                source_type=path.suffix.lower().replace(".", ""),
                row_id=str(idx),
                address_id=None,
                raw_address=raw_address,
                city=None,
                state=None,
                zip_code=None,
                latitude=lat,
                longitude=lon,
                extra={"placemark_name": name, "description": desc},
            )
        )
    return records
