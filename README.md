# grat

[![CI](https://github.com/blueraster/earth-genome-grat/actions/workflows/ci.yml/badge.svg)](https://github.com/blueraster/earth-genome-grat/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/grat.svg)](https://pypi.org/project/grat/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

GRAT is a groundwater recharge assessment tool. It models how water available for
recharge is allocated, day by day across a span of water years, to canals, basins and
farm fields, and reports the resulting groundwater recharge.

## Installation

```bash
pip install grat
```

## Usage

Load the sites layer from a shapefile, file geodatabase, geopackage, geojson or csv.
ArcGIS is not needed; only the attribute table is read.

```python
from grat.loaders.get_sites import load_sites

rows = load_sites("OakValley/oakvalley.shp")
rows = load_sites("project.gdb", layer="sites", where="R_TYPE = 'OFR'")
rows = load_sites("sites.csv", attribute_renamer={"GRATID": "grat_id", "R_TYPE": "recharge_type"})
```

Run the model and produce reports:

```python
from grat import read_report, run_grat

result = run_grat(sites, wafr, bottlenecks, crop_calendar, precip)

result["zip_path"]  # the results archive
result["reports"]  # the report names that were produced
result["series"]["unused_wafr"]  # the frontend visualisation data
```

`run_grat` returns a plain dict. To look at any report it produced, read it back by
name as a pandas dataframe:

```python
df = read_report(result["output_folder"], "annual_summary_recharge")
df = read_report(result["output_folder"], "daily_recharge_by_site", year=2001)
```

Reports are asked for by name, and a run only builds what those reports need:

```python
result = run_grat(..., reports=["annual_summary_recharge", "acres_available_and_used"])
```

`grat.reports.catalog.ALL_REPORTS` lists everything available.

To drive the year loop yourself and work with the dataframes directly, without writing
any csv files, pass `None` as the output folder:

```python
from grat.model.engine import process_year
from grat.reports import report_picker

year = process_year(sites, bottlenecks, wafr, crop_calendar, precip)
reports = report_picker(
    ["annual_summary_recharge"], None, 2001, year["sites"], raw_wafr, year["wafr"], year["bottlenecks"]
)
reports["annual_summary_recharge"]
```

## Documentation

Full docs, including an API reference generated from the docstrings, are published at
<https://blueraster.github.io/earth-genome-grat/>. To preview them locally:

```bash
uv sync --group docs
uv run mkdocs serve
```

- [docs/model.md](docs/model.md) — `grat.model`: sites, allocation order, bottlenecks,
  transfers, and running the year loop yourself.
- [docs/reports.md](docs/reports.md) — `grat.reports`: the report catalog, what each
  report contains, and how to read one back.

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
uv sync                  # install dependencies (incl. dev group) into .venv
uv run pytest            # run tests
uv run ruff check .      # lint
uv run ruff format .     # format
```

## License

MIT — see [LICENSE](LICENSE).
