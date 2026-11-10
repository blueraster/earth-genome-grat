# grat

GRAT is a groundwater recharge assessment tool. It models how water available for
recharge is allocated, day by day across a span of water years, to canals, basins and
farm fields, and reports the resulting groundwater recharge.

## Installation

```bash
pip install grat
```

## Quick start

```python
from grat import read_report, run_grat

result = run_grat(
    sites, wafr, bottlenecks, crop_calendar, precip, reports=["annual_summary_recharge", "acres_available_and_used"]
)

result["zip_path"]  # the results archive
result["reports"]  # the report names that were produced

df = read_report(result["output_folder"], "annual_summary_recharge")
```

## Where to go next

- [Model guide](model.md) — sites, allocation order, bottlenecks, transfers, and
  running the year loop yourself.
- [Reports guide](reports.md) — the report catalog, what each report contains, and
  how to read one back.
- **API reference** (left-hand menu) — generated from the docstrings in `src/grat`
  on every push to `main`.
