"""Build a single static HTML page listing all SPG producers and their parcels."""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCERS_DIR = REPO_ROOT / "data" / "spg" / "producers"
OUT_DIR = REPO_ROOT / "site"
OUT_FILE = OUT_DIR / "index.html"

PARCEL_COLUMNS = [
    ("product", "Producto"),
    ("variety", "Variedad"),
    ("surface", "Superficie"),
    ("production", "Producción"),
    ("organic_certification", "Cert. orgánica"),
    ("bd_certification", "Cert. BD"),
    ("market", "Mercado"),
    ("observations", "Observaciones"),
]


def combined(value, unit) -> str:
    base = fmt(value)
    if unit is None or unit == "" or base == "—":
        return base
    return f"{base} {unit}"


def fmt(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:g}"
    return str(value)


def load_producers() -> list[dict]:
    producers = []
    for path in sorted(PRODUCERS_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as f:
            producers.append(json.load(f))
    producers.sort(key=lambda p: (p.get("id") if isinstance(p.get("id"), int) else 1 << 30))
    return producers


def render_parcels(parcels: list[dict]) -> str:
    if not parcels:
        return '<p class="empty">Sin parcelas registradas.</p>'
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in PARCEL_COLUMNS)
    rows = []
    for parcel in parcels:
        cells = []
        for key, _ in PARCEL_COLUMNS:
            if key == "surface":
                text = combined(parcel.get("surface"), parcel.get("surface_unit"))
            elif key == "production":
                text = combined(parcel.get("production"), parcel.get("production_unit"))
            else:
                text = fmt(parcel.get(key))
            cells.append(f"<td>{html.escape(text)}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return (
        '<div class="table-wrap"><table>'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
    )


def field(label: str, value: str) -> str:
    return (
        f'<div class="field"><span class="label">{html.escape(label)}</span>'
        f'<span class="value">{value}</span></div>'
    )


def render_producer(producer: dict) -> str:
    pid = producer.get("id")
    name = html.escape(producer.get("name") or f"Productor {pid}")
    parcels = producer.get("parcels") or []

    fields = []
    if pid is not None:
        fields.append(field("ID", html.escape(str(pid))))
    for key, label in [("country", "País"), ("city", "Ciudad"), ("contact", "Contacto")]:
        v = producer.get(key)
        if v:
            fields.append(field(label, html.escape(str(v))))
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
    fields.append(field("Parcelas", str(len(parcels))))

    return (
        '<details class="producer">'
        '<summary>'
        f'<div class="name">{name}</div>'
        f'<div class="fields">{"".join(fields)}</div>'
        '</summary>'
        '<div class="body">'
        f"{render_parcels(parcels)}"
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
  <p class="lede">{count} productores · {parcel_count} parcelas. Hace clic en un productor para ver sus parcelas.</p>
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

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        HTML_TEMPLATE.format(
            count=len(producers),
            parcel_count=parcel_count,
            producers=rendered,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUT_FILE} ({len(producers)} producers, {parcel_count} parcels)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
