"""Extract SPG producers from the commercialization xlsx into per-producer JSON files."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections import OrderedDict
from pathlib import Path

NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
A_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

REPO_ROOT = Path(__file__).resolve().parent.parent
XLSX_PATH = REPO_ROOT / "data" / "25-8 Listado Comercilizacion.xlsx"
OUT_DIR = REPO_ROOT / "data" / "spg" / "producers"
SHEET_PATH = "xl/worksheets/sheet3.xml"  # SPG sheet, per workbook rels

PRODUCER_COLUMNS = {
    "B": "country",
    "C": "city",
    "D": "name",
    "E": "contact",
    "F": "whatsapp",
    "G": "email",
}

FIELD_COLUMNS = [
    ("H", "organic_certification", "string"),
    ("I", "bd_certification", "string"),
    ("J", "product", "string"),
    ("K", "variety", "string"),
    ("L", "surface", "number"),
    ("M", "surface_unit", "string"),
    ("N", "production", "number"),
    ("O", "production_unit", "string"),
    ("P", "market", "string"),
    ("Q", "observations", "string"),
]

DATA_START_ROW = 4  # xlsx 1-indexed; rows 1-3 are title/blank/header


def load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    out = []
    for si in root.findall("a:si", NS):
        out.append("".join(t.text or "" for t in si.iter(f"{A_NS}t")))
    return out


def cell_text(c: ET.Element, shared: list[str]) -> str | None:
    t_attr = c.attrib.get("t")
    v = c.find("a:v", NS)
    if v is None:
        is_el = c.find("a:is", NS)
        if is_el is not None:
            return "".join(t.text or "" for t in is_el.iter(f"{A_NS}t"))
        return None
    if t_attr == "s":
        return shared[int(v.text)]
    return v.text


def col_letters(ref: str) -> str:
    return "".join(ch for ch in ref if ch.isalpha())


def row_number(ref: str) -> int:
    return int("".join(ch for ch in ref if ch.isdigit()))


def parse_rows(zf: zipfile.ZipFile, shared: list[str]) -> list[dict[str, str]]:
    sheet = ET.fromstring(zf.read(SHEET_PATH))
    rows = []
    for row in sheet.findall(".//a:sheetData/a:row", NS):
        rd: dict[str, str] = {}
        for c in row.findall("a:c", NS):
            ref = c.attrib.get("r", "")
            val = cell_text(c, shared)
            if val is None:
                continue
            stripped = val.strip()
            if not stripped:
                continue
            rd[col_letters(ref)] = stripped
        if not rd:
            continue
        first_ref = row.attrib.get("r")
        rd["__row"] = int(first_ref) if first_ref else row_number(
            row.find("a:c", NS).attrib["r"]
        )
        rows.append(rd)
    return rows


def slugify(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = ascii_only.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "unnamed"


def parse_number(raw: str) -> float | int | str:
    try:
        n = float(raw)
    except ValueError:
        return raw
    if n.is_integer():
        return int(n)
    return n


def to_field_value(raw: str | None, kind: str):
    if raw is None:
        return None
    if kind == "number":
        return parse_number(raw)
    return raw


def pick_canonical(values: list[str]) -> str:
    # Distinct trimmed values; pick the longest (handles "Harry Lee" vs
    # "Harry Lee /Carmen RuizTagle" cases) and trim.
    distinct = list(OrderedDict.fromkeys(v.strip() for v in values if v.strip()))
    if not distinct:
        return ""
    return max(distinct, key=len)


def build_producer(producer_id: str, rows: list[dict[str, str]]) -> dict:
    producer: dict = {"id": parse_number(producer_id)}
    for col, key in PRODUCER_COLUMNS.items():
        canonical = pick_canonical([r.get(col, "") for r in rows])
        producer[key] = canonical or None

    parcels = []
    for r in rows:
        entry = {}
        for col, key, kind in FIELD_COLUMNS:
            entry[key] = to_field_value(r.get(col), kind)
        parcels.append(entry)
    producer["parcels"] = parcels
    return producer


def main() -> int:
    if not XLSX_PATH.exists():
        print(f"Source xlsx not found: {XLSX_PATH}", file=sys.stderr)
        return 1

    with zipfile.ZipFile(XLSX_PATH) as zf:
        shared = load_shared_strings(zf)
        rows = parse_rows(zf, shared)

    data_rows = [r for r in rows if r["__row"] >= DATA_START_ROW and r.get("A")]

    by_producer: dict[str, list[dict[str, str]]] = OrderedDict()
    for r in data_rows:
        by_producer.setdefault(r["A"], []).append(r)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    used_slugs: dict[str, str] = {}
    written = 0
    total_parcels = 0
    for pid, prows in by_producer.items():
        producer = build_producer(pid, prows)
        name = producer.get("name") or f"producer-{pid}"
        slug = slugify(name)
        if slug in used_slugs and used_slugs[slug] != pid:
            slug = f"{slug}-{pid}"
        used_slugs[slug] = pid

        out_path = OUT_DIR / f"{slug}.json"
        out_path.write_text(
            json.dumps(producer, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written += 1
        total_parcels += len(producer["parcels"])
        print(f"  {pid:>3}  {slug:<40} {len(producer['parcels'])} parcels")

    print(f"\nWrote {written} producer files ({total_parcels} total parcels) to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
