# SPG · Asociación Biodinámica de Chile

Listado público de productores SPG (Sistema Participativo de Garantía) de la Asociación Biodinámica de Chile.

**Sitio publicado:** https://abdchile.github.io/spg/

## Estructura

- `data/25-8 Listado Comercilizacion.xlsx` — planilla fuente.
- `data/spg/producers/*.json` — un archivo JSON por productor, generado desde la planilla.
- `scripts/extract_spg_producers.py` — extrae los productores del xlsx a JSON.
- `scripts/build_site.py` — genera `site/index.html` a partir de los JSON.
- `.github/workflows/pages.yml` — construye y publica el sitio en GitHub Pages en cada push a `main`.

## Uso local

```bash
# Re-extraer los JSON desde el xlsx (cuando cambia la planilla)
python3 scripts/extract_spg_producers.py

# Generar el sitio estático
python3 scripts/build_site.py
open site/index.html
```

Sólo requiere Python 3 estándar — sin dependencias externas.
