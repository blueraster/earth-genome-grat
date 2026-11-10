# `grat.model`

The recharge assessment model. It answers one question, one day at a time, for an
entire span of water years: given the water available for recharge (WAFR) on a given
day, how much of it reaches each canal, basin and field, and how much of that
eventually reaches groundwater?


## Core concepts

- **Water year**: October 1 through September 30, represented as 366 zero-indexed
  days (`day` 0 is October 1). A non-leap year simply leaves day 365 unused —
  `DAYS_PER_WATER_YEAR` (`grat.model.constants`) is always 366 so the same code runs
  either length without reallocating arrays.
- **WAFR** (water available for recharge): volume, in acre-feet, available per day
  from a named source (e.g. a river or canal diversion). Represented as a dict of
  `source name -> daily array`. The model draws this down as it allocates water, so
  callers that need the original values should keep their own copy (`run_grat` does
  this for the reports layer, via `raw_wafr`).
- **Site**: a canal, basin or farm. Every site is built on `BaseSite` and carries both
  static attributes (area, location, which WAFR sources can reach it) and per-day
  arrays the model fills in as the year is allocated.
- **Bottleneck**: a shared daily delivery limit. A site behind a bottleneck is capped
  by whichever bottleneck restricts it most tightly, regardless of how much WAFR is
  otherwise available.
- **Transfers**: a yearly budget, per district, capping how much water transferred in
  from another district's sources that district's sites may use.
- All volumes are acre-feet and all rates are acre-feet per day unless a docstring
  says otherwise.

## Site types (`grat.model.sites`)

| Class | Recharge type | Behavior |
| --- | --- | --- |
| `BaseSite` | — | Shared foundation: static attributes, the `precip`/`wafr_log` arrays, `sort_index`. Not used directly. |
| `Canal(Basin)` | `"Canal"` | A conveyance structure (canal, slough, river). Shares water across every canal it can reach in proportion to headroom, via `proportionally_fill`, rather than filling in priority order. Capacity is a daily array, and it accepts no WAFR during the irrigation season (assumed already full for delivery). |
| `Basin` | `"Basin"` | A managed recharge facility. Water stands in the basin (`current_capacity`) and drains to groundwater at `perc_rate` acre-feet/day, so recharge happens over several days. Filled in priority order until full or the day's WAFR runs out. |
| `Farm` | `"OFR"` and/or in-lieu | A field. Supports two independent recharge methods tracked in separate arrays: **on-farm recharge** (surface water applied beyond crop demand, capped by the crop compatibility calendar) and **in-lieu recharge** (surface water substituted for pumping, capped by a separate in-lieu calendar). A farm with both a `crop` and an `in_lieu_crop` takes part in both. |

How much each site can take on a day is always the smallest of: its own headroom
(capacity, or crop-calendar rate × area), the WAFR still available from a compatible
source, and whatever its bottlenecks still allow.

## Allocation order

Within a day, `engine.use_sites` runs a fixed sequence **twice** — once against each
site's primary (in-district) WAFR sources, once against secondary (out-of-district)
sources for whatever is left:

1. **Canals** (`fill_canals` → `proportionally_fill`) — shared proportionally, largest
   WAFR source first.
2. **In-lieu fields** (`use_farms(..., in_lieu=True)`).
3. **Basins** (`fill_basins`).
4. **On-farm recharge fields** (`use_farms(..., in_lieu=False)`).

Steps 2–4 are skipped entirely once a day's WAFR is exhausted
(`check_wafr_availability`). Canals, basins and in-lieu/on-farm sites are each
processed in **list order**, so priority within a type is entirely decided by how the
site list was sorted beforehand — see `sorters.sort_sites` and
`sorters.group_sites_by_recharge_type`. The day ends by draining that day's
percolation from canals and basins into recorded groundwater recharge.

## Running the model

- `engine.process_year(...)` — runs one water year against a site list (**mutated in
  place**) and returns its results. Use this directly to drive the loop yourself and
  work with the resulting objects, without writing anything to disk.
- `engine.start_analysis(...)` — runs a span of years (default 2001–2099, see
  `constants.DEFAULT_YEARS`). Each year runs against a deep copy of the inputs, so
  years are independent and the original `raw_sites`/`raw_wafr`/`raw_bottlenecks` are
  left untouched. Nothing is returned — each year's results are handed to the
  `on_year` callback (if one was given) and then discarded, so a long run never holds
  more than one year in memory. This is the seam `grat.run.run_grat` hangs the
  reporting layer off of.

```python
from grat.model.engine import process_year, start_analysis

# one year, working with the objects directly
year = process_year(sites, bottlenecks, wafr, crop_calendar, precip)
year["sites"]  # the same site objects, now carrying the year's results
year["wafr"]  # wafr, drawn down to what was left unused


# a full span of years, doing something with each year's results as it finishes
def on_year(
    year, sites, raw_wafr, wafr, bottlenecks, transfer_limits
): ...  # e.g. hand off to grat.reports.report_picker


start_analysis(raw_sites, raw_wafr, raw_bottlenecks, crop_calendar, precip, on_year=on_year)
```

Most callers should use `grat.run.run_grat` instead, which drives `start_analysis` and
turns its output into reports in one call — see the top-level
[quick start](index.md#quick-start).

## Other modules

- `bottlenecks.py` — the `Bottleneck` class and helpers (`get_bottlenecks`,
  `bottleneck_capacity_logger`) for finding which bottlenecks restrict a site and
  reporting which ones ran out of capacity.
- `sorters.py` — `sort_sites` puts sites into processing order (by RSI score, RMA
  rank, or a test scenario, then grouped by recharge type);
  `group_sites_by_recharge_type` splits an already-sorted list into the four
  sublists the daily loop works through; `mlrp_sorter` converts top-ranked acreage
  per agency to the MLRP crop.
- `transfers.py` — `calc_transfer_limits` turns each district's transfer goal
  (a threshold plus either a percentage or a flat acre-foot volume) into its yearly
  transfer budget.
- `constants.py` — shared constants: `DAYS_PER_WATER_YEAR`, `CFS_TO_ACRE_FEET_PER_DAY`,
  `DEFAULT_CFS_LIMIT`, `DEFAULT_YEARS`, `DEFAULT_IRRIGATION_DAYS`.

## Irrigation season

`DEFAULT_IRRIGATION_DAYS` is the default irrigation season: zero-indexed days of the
water year from April 1st through October 31st (days 0-30 and 182-365). Canals accept
no WAFR on those days, and bottlenecks switch to their irrigation capacity. It is applied
when the loaders build canals and bottlenecks, so pass `irrigation_days` to a loader to
use a different season:

```python
from grat.loaders.get_bottlenecks import load_bottlenecks
from grat.loaders.get_canals import load_canals

canals = load_canals("canals.csv")  # default season
canals = load_canals("canals.csv", irrigation_days=list(range(0, 31)))  # October only
canals = load_canals("canals.csv", irrigation_days=[])  # no irrigation season

bottlenecks = load_bottlenecks("bottlenecks.csv", irrigation_days=list(range(0, 31)))
```

Use the same season for canals and bottlenecks in a run.

The model classes (`sites.Canal`, `bottlenecks.Bottleneck`) take the same argument but
default to no irrigation season when it is omitted.
