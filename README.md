# grat

[![CI](https://github.com/blueraster/grat/actions/workflows/ci.yml/badge.svg)](https://github.com/blueraster/grat/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/grat.svg)](https://pypi.org/project/grat/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

One-line description of what `grat` does.

## Installation

```bash
pip install grat
```

## Usage

Run the model and produce reports in one call:

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

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
uv sync                  # install dependencies (incl. dev group) into .venv
uv run pytest            # run tests
uv run ruff check .      # lint
uv run ruff format .     # format
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
