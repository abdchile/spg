"""Build a single static HTML page listing all SPG producers and their parcels."""

from __future__ import annotations

import html
import json
import re
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCERS_DIR = REPO_ROOT / "data" / "spg" / "producers"
OUT_DIR = REPO_ROOT / "site"
OUT_FILE = OUT_DIR / "index.html"

PRODUCT_COLUMNS = [
    ("product", "Producto"),
    ("variety", "Variedad"),
    ("parcel_count", "Parcelas"),
    ("surface", "Superficie"),
    ("production", "Producción"),
    ("season", "Temporada"),
    ("market", "Mercado"),
    ("observations", "Observaciones"),
]

UNIT_SYNONYMS = {
    "kilo": "kg", "kilos": "kg", "kg": "kg",
    "ha": "ha", "há": "ha", "hectarea": "ha", "hectáreas": "ha", "hectareas": "ha",
    "planta": "plantas", "plantas": "plantas",
    "arbol": "árboles", "arboles": "árboles", "árbol": "árboles", "árboles": "árboles",
    "arbusto": "arbustos", "arbustos": "arbustos",
    "unidad": "un", "unidades": "un", "un": "un",
}


def fmt(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:g}"
    return str(value)


def fmt_num(n: float) -> str:
    if n == int(n):
        return str(int(n))
    return f"{n:g}"


def normalize_unit(raw: str) -> tuple[str, str]:
    """Return (canonical_key, display_label) for a unit string."""
    cleaned = (raw or "").strip().lower()
    if not cleaned:
        return "", ""
    canon = UNIT_SYNONYMS.get(cleaned, cleaned)
    return canon, canon


def parse_qty(value) -> tuple[float | None, str]:
    """Parse a quantity. Returns (number, unit_string) or (None, original_text)."""
    if value is None or value == "":
        return None, ""
    if isinstance(value, (int, float)):
        return float(value), ""
    s = str(value).strip()
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s*(.*)$", s)
    if not m:
        return None, s
    num_str, rest = m.group(1), m.group(2).strip()
    if not _unit_safe(rest):
        return None, s
    try:
        return float(num_str.replace(",", ".")), rest
    except ValueError:
        return None, s


def _unit_safe(rest: str) -> bool:
    if not rest:
        return True
    for tok in rest.split():
        if re.fullmatch(r"\d+", tok):
            return False  # bare number — likely a dimension like "5 x 100"
        if re.fullmatch(r"x\d*", tok, re.IGNORECASE):
            return False
        if not re.fullmatch(r"[a-zA-Záéíóúñ0-9]+", tok):
            return False
    return True


def aggregate_qty(values) -> str:
    """Sum parseable numeric quantities by unit; list the rest verbatim."""
    by_unit: dict[str, list] = {}
    raw: list[str] = []
    for v in values:
        if v is None or v == "":
            continue
        num, unit = parse_qty(v)
        if num is None:
            raw.append(unit)
            continue
        key, label = normalize_unit(unit)
        slot = by_unit.setdefault(key, [label, 0.0])
        slot[1] += num
    parts = [f"{fmt_num(total)} {label}".strip() for label, total in by_unit.values()]
    if raw:
        parts.append("(" + ", ".join(raw) + ")" if parts else ", ".join(raw))
    return ", ".join(parts) if parts else ""


def _distinct(values) -> list[str]:
    seen: dict[str, None] = {}
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        seen.setdefault(s, None)
    return list(seen.keys())


def aggregate_by_product(parcels: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for parcel in parcels:
        key = (parcel.get("product") or "").strip().lower() or "—"
        groups.setdefault(key, []).append(parcel)

    rows = []
    for items in groups.values():
        product = next((it["product"] for it in items if it.get("product")), "—")
        rows.append({
            "product": product,
            "variety": ", ".join(_distinct(it.get("variety") for it in items)),
            "parcel_count": len(items),
            "surface": aggregate_qty(it.get("surface") for it in items),
            "production": aggregate_qty(it.get("production") for it in items),
            "season": ", ".join(_distinct(it.get("production_unit") for it in items)),
            "market": ", ".join(_distinct(it.get("market") for it in items)),
            "observations": "; ".join(_distinct(it.get("observations") for it in items)),
        })
    rows.sort(key=lambda r: _sort_key(r["product"]))
    return rows


def _sort_key(s: str) -> str:
    decomposed = unicodedata.normalize("NFKD", s.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def load_producers() -> list[dict]:
    producers = []
    for path in sorted(PRODUCERS_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as f:
            producers.append(json.load(f))
    producers.sort(key=lambda p: (p.get("id") if isinstance(p.get("id"), int) else 1 << 30))
    return producers


def render_products(parcels: list[dict]) -> str:
    if not parcels:
        return '<p class="empty">Sin parcelas registradas.</p>'
    rows_data = aggregate_by_product(parcels)
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in PRODUCT_COLUMNS)
    body_rows = []
    for row in rows_data:
        cells = []
        for key, _ in PRODUCT_COLUMNS:
            value = row.get(key)
            text = fmt(value) if value not in (None, "") else "—"
            cells.append(f"<td>{html.escape(text)}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return (
        '<div class="table-wrap"><table>'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )


def field(label: str, value: str) -> str:
    return (
        f'<div class="field"><span class="label">{html.escape(label)}</span>'
        f'<span class="value">{value}</span></div>'
    )


CASE_FIELDS = {
    "country": str.title,
    "city": str.title,
    "contact": str.title,
}


def render_producer(producer: dict) -> str:
    pid = producer.get("id")
    raw_name = producer.get("name") or f"Productor {pid}"
    name = html.escape(raw_name.upper())
    parcels = producer.get("parcels") or []

    fields = []
    if pid is not None:
        fields.append(field("ID", html.escape(str(pid))))
    for key, label in [("country", "País"), ("city", "Ciudad"), ("contact", "Contacto")]:
        v = producer.get(key)
        if v:
            transform = CASE_FIELDS.get(key)
            display = transform(str(v)) if transform else str(v)
            fields.append(field(label, html.escape(display)))
    email = producer.get("email")
    if email:
        e = html.escape(str(email))
        fields.append(field("Email", f'<a href="mailto:{e}">{e}</a>'))
    whatsapp = producer.get("whatsapp")
    if whatsapp:
        digits = "".join(ch for ch in str(whatsapp) if ch.isdigit())
        w = html.escape(str(whatsapp))
        fields.append(
            field("WhatsApp", f'<a href="https://wa.me/{digits}">{w}</a>')
        )
    for key, label in [("organic_certification", "Cert. orgánica"), ("bd_certification", "Cert. BD")]:
        v = producer.get(key)
        if v:
            fields.append(field(label, html.escape(str(v))))
    product_count = len({(p.get("product") or "").strip().lower() for p in parcels if p.get("product")})
    fields.append(field("Productos", str(product_count)))

    return (
        '<details class="producer">'
        '<summary>'
        f'<div class="name">{name}</div>'
        f'<div class="fields">{"".join(fields)}</div>'
        '</summary>'
        '<div class="body">'
        f"{render_products(parcels)}"
        "</div>"
        "</details>"
    )


HTML_TEMPLATE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Productores SPG</title>
<style>
  :root {{
    --fg: #1a1a1a;
    --muted: #666;
    --bg: #f7f7f5;
    --card: #fff;
    --border: #e2e2dc;
    --accent: #2f6f3e;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font: 16px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    color: var(--fg);
    background: var(--bg);
    margin: 0;
    padding: 2rem 1rem 4rem;
  }}
  main {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ margin: 0 0 .25rem; font-size: 1.6rem; }}
  .lede {{ color: var(--muted); margin: 0 0 1.5rem; }}
  .controls {{ margin: 0 0 1rem; }}
  .controls input {{
    width: 100%; padding: .55rem .75rem; font-size: 1rem;
    border: 1px solid var(--border); border-radius: 6px; background: var(--card);
  }}
  .producer {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: .5rem;
    overflow: hidden;
  }}
  .producer > summary {{
    list-style: none;
    cursor: pointer;
    padding: .9rem 1rem;
    display: block;
    text-align: left;
  }}
  .producer > summary::-webkit-details-marker {{ display: none; }}
  .producer > summary::before {{
    content: "▸"; color: var(--muted); margin-right: .5rem;
    transition: transform .15s ease;
    display: inline-block;
  }}
  .producer[open] > summary::before {{ transform: rotate(90deg); }}
  .name {{ font-weight: 600; display: inline; }}
  .fields {{
    margin-top: .4rem;
    margin-left: 1.2rem;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: .25rem 1rem;
    font-size: .88rem;
  }}
  .field {{ display: flex; gap: .35rem; min-width: 0; }}
  .field .label {{ color: var(--muted); flex-shrink: 0; }}
  .field .value {{ color: var(--fg); overflow: hidden; text-overflow: ellipsis; }}
  .field a {{ color: var(--accent); text-decoration: none; }}
  .field a:hover {{ text-decoration: underline; }}
  .body {{
    padding: 0 1rem 1rem;
    border-top: 1px solid var(--border);
  }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .88rem; }}
  th, td {{
    text-align: left; padding: .45rem .6rem;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }}
  th {{
    background: var(--bg);
    font-weight: 600;
    position: sticky; top: 0;
  }}
  tbody tr:hover {{ background: #fafaf7; }}
  .empty {{ color: var(--muted); font-style: italic; padding: .75rem 0; }}
  .footer {{ color: var(--muted); font-size: .8rem; margin-top: 2rem; text-align: center; }}
  @media (max-width: 600px) {{
    .fields {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<main>
  <h1>Productores SPG</h1>
  <p class="lede">{count} productores · {product_count} productos · {parcel_count} parcelas. Hace clic en un productor para ver sus productos.</p>
  <div class="controls">
    <input type="search" id="filter" placeholder="Filtrar por nombre, ciudad o producto…" autocomplete="off">
  </div>
  <div id="list">
{producers}
  </div>
  <p class="footer">Generado desde <code>data/spg/producers/</code>.</p>
</main>
<script>
  const input = document.getElementById('filter');
  const items = Array.from(document.querySelectorAll('.producer'));
  const haystacks = items.map(el => el.textContent.toLowerCase());
  input.addEventListener('input', () => {{
    const q = input.value.trim().toLowerCase();
    items.forEach((el, i) => {{
      el.style.display = !q || haystacks[i].includes(q) ? '' : 'none';
    }});
  }});
</script>
</body>
</html>
"""


def main() -> int:
    if not PRODUCERS_DIR.exists():
        print(f"Producers directory not found: {PRODUCERS_DIR}", file=sys.stderr)
        return 1

    producers = load_producers()
    if not producers:
        print("No producer JSON files found.", file=sys.stderr)
        return 1

    rendered = "\n".join(render_producer(p) for p in producers)
    parcel_count = sum(len(p.get("parcels") or []) for p in producers)
    product_count = sum(
        len({(parcel.get("product") or "").strip().lower()
             for parcel in (p.get("parcels") or []) if parcel.get("product")})
        for p in producers
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        HTML_TEMPLATE.format(
            count=len(producers),
            product_count=product_count,
            parcel_count=parcel_count,
            producers=rendered,
        ),
        encoding="utf-8",
    )
    print(
        f"Wrote {OUT_FILE} ({len(producers)} producers, "
        f"{product_count} products, {parcel_count} parcels)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
