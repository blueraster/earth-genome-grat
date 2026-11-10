# `grat.reports`

Turns a model run's results into report dataframes — and into the handful of
json-ready series the frontend charts off of.

## The catalog (`catalog.py`)

Reports are asked for **by name**, not by calling functions directly. Every name is a
key of `writers.REPORT_FILES`.

- `ALL_REPORTS` — every report name that can be requested (`CSV_REPORTS |
  FRONTEND_SERIES`).
- `CSV_REPORTS` — reports written to csv inside the run's output folder.
- `FRONTEND_SERIES` — reports returned as json-ready dicts instead, for the frontend
  visualizations.
- `expand(names)` — the function that resolves a request: adds in whatever a
  requested report is built from (see `IMPLIES`, e.g. asking for
  `yearly_recharge_volumes` also produces `annual_summary_recharge`), and raises
  `KeyError` for any name that isn't in `ALL_REPORTS`.

Requesting a smaller list than `ALL_REPORTS` means only the intermediates those
reports actually need get built — the catalog's `NEEDS_*` sets are what
`selector.report_picker` and `selector.post_process` check to decide that.

Two model inputs are optional, and the reports that depend on them are silently
skipped (with a log line) rather than failing the run when it's missing:

- No bottlenecks → `NEEDS_BOTTLENECKS` reports are skipped.
- No transfer list → `NEEDS_TRANSFERS` reports are skipped.

## How a run produces reports (`selector.py`)

Two entry points, called once each per run:

- **`report_picker(names, output_folder, year, sites, year_raw_wafr, wafr,
  bottlenecks=None, transfer_list=None)`** — called once per water year (this is what
  `run_grat` wires up as `start_analysis`'s `on_year` hook). Builds every per-year
  report and intermediate the request needs, writes the csvs (unless
  `output_folder` is `None`, in which case nothing is written and the dataframes are
  simply returned), and returns the dataframes for the reports actually in `names`.
- **`post_process(names, output_folder, produced=None)`** — called once after every
  year has run. Builds the reports that need the whole run's data at once (the
  monthly pivot, the three grouping reports, the yearly transfer rollup, the MLRP
  report) by reading back the per-year intermediates `report_picker` wrote, builds
  the frontend series, and then deletes the intermediates
  (`writers.REPORT_FILES` entries not in `CSV_REPORTS`). Returns a dict holding the
  post-run csv reports (as dataframes) and the frontend series (as json-ready dicts).

`run_grat` (in `grat.run`) is the normal way to invoke both of these — see the
top-level [quick start](index.md#quick-start) for the one-call version. Calling
`report_picker`/`post_process` directly is for driving the model's year loop
yourself, as shown in [model.md](model.md#running-the-model).

## Reading reports back (`writers.py`)

- `write_report(df, output_folder, key)` / `read_report(output_folder, key, year=None,
  dtype=None)` — write or read a single report by its catalog name. `year` is only
  needed for the two reports written into a per-year subfolder (see below).
- `REPORT_FILES` — maps every report name (plus the internal intermediates) to the
  csv filename it's written as, and whether that file is appended to across water
  years (`append=True`, the default) or written fresh each time.
- `construct_output_folder_name(path_to_folder)` — creates a uniquely-named,
  timestamped results folder (what `run_grat` calls to build `output_folder`).
- `zip_output_folder(result_folder_path, custom_name=None)` — zips a finished results
  folder.

```python
from grat.reports import read_report

read_report(result["output_folder"], "annual_summary_recharge")
read_report(result["output_folder"], "daily_recharge_by_site", year=2047)  # per-year report
```

## The reports

CSV reports, in the order their filenames are numbered. All are indexed by water year
except the two marked *(per-year subfolder)*, which carry one column per day and are
written into `<output_folder>/<year>/` instead of the run root.

| # | Report name | File | What it is |
| --- | --- | --- | --- |
| 02 | `annual_summary_recharge` | `02_Annual Summary Recharge and WAFR.csv` | Recharge and WAFR volumes totalled per water year, by site type. |
| 03 | `daily_summary_recharge` | `03_Daily Summary Recharge.csv` | The same totals as 02, broken out per day of the water year. |
| 04 | `daily_wafr_applied_by_site` *(per-year subfolder)* | `04_Daily WAFR Applied by Site.csv` | Daily volume applied to each site, one column per day, joined to site attribution. |
| 05 | `daily_recharge_by_site` *(per-year subfolder)* | `05_Daily Detailed Recharge Applied by Site.csv` | Daily volume that reached groundwater at each site, one column per day. |
| 06 | `monthly_recharge_by_site_report` | `06_Monthly Recharge by Site.csv` | Monthly recharge totals per site, summarized. |
| 07 | `monthly_recharge_by_site_report_detailed` | `07_Monthly Detailed Recharge by Site.csv` | The same monthly pivot, unsummarized. |
| 08 | `daily_farm_recharge_report` | `08_Daily OFR by Crop and Soil Type.csv` | On-farm recharge volumes grouped by crop and soil type, per day. |
| 09 | `yearly_aggregate_farm_recharge_report` | `09_Annual OFR by Crop and Soil Type.csv` | The same grouping, rolled up per year. |
| 10 | `daily_wafr_report` | `10_Daily Unused WAFR by Source.csv` | Unused WAFR by source, per day. |
| 11 | `bottlenecks_capacity_limitations_report` | `11_Annual Conveyance Bottleneck Count.csv` | Count of days each bottleneck ran out of capacity, per year. |
| 12 | `bottlenecks_daily_conveyance_limits_by_volume` | `12_Daily Conveyance Limits by Volume.csv` | Remaining throughput per bottleneck, per day. |
| 13 | `yearly_bottleneck_capacity_logger` | `13_Daily Conveyance Bottleneck IDs.csv` | Which bottlenecks hit their limit, per day. |
| 15 | `annual_recharge_by_sw_and_gw` | `15_Annual Recharge by SW Source and GW Basin.csv` | Annual recharge grouped by surface-water source and groundwater basin. |
| 16 | `annual_recharge_by_district_and_gw` | `16_Annual District Recharge by GW Basin.csv` | Annual recharge grouped by district and groundwater basin. |
| 17 | `annual_recharge_by_district_and_wafr` | `17_Annual District Recharge by SW Source.csv` | Annual recharge grouped by district and WAFR source. |
| 18 | `daily_recharge_by_gw_basin` | `18_Daily Recharge by GW Basin.csv` | Daily recharge grouped by groundwater basin. |
| 19 | `acres_available_and_used` | `19_Acres Available and Used.csv` | Acreage available vs. used, by recharge type and category, per year. |
| 20 | `daily_water_transfer_by_sustain_zone_report` | `20_Daily Water Transfer by Sustainability Zone.csv` | Daily water transferred in, by sustainability zone. |
| 21 | `yearly_water_transfer_by_sustain_zone_report` | `21_Yearly Water Transfer by Sustainability Zone.csv` | Report 20 rolled up to a yearly total per zone. |
| 22 | `fields_repurposed` | `22_Fields Repurposed.csv` | Sites that `sorters.mlrp_sorter` converted to the MLRP crop. |

Frontend series (returned as dicts, not written to csv):

| Series name | What it is |
| --- | --- |
| `yearly_recharge_volumes` | Recharge by type (canals/basins/in-lieu/on-farm) per year, plus a run total. Built from report 02. |
| `unused_wafr` | Input vs. unused WAFR volume, summed by source across the whole run. |
| `max_wafr_per_site` | The largest single-year volume each site used, keyed by `gratID`. |
| `recharge_by_sustainability_zone` | Total recharge per sustainability zone, across the whole run. |

## Other modules

- `builders.py` — the functions that build each report dataframe from site objects,
  WAFR dicts and bottleneck lists. `report_picker`/`post_process` are the supported
  way to call these; the individual functions are documented inline for anyone
  building a new report or a custom pipeline.
- `converters.py` — small date/calendar helpers used by the builders:
  `get_month_name`, `get_num_days_in_month`, `is_leap_year`, `find_wy_month_index`,
  and `sum_array_by_month` (which sums a daily array into water-year months —
  October first, so column `"1"` in reports 06/07 is October, not January).
