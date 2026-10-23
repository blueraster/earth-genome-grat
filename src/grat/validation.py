"""Checks input data for problems before it reaches `build_sites` or `run_grat`.

Meant to be run from a notebook right after loading your own data, so problems show up
as a readable report instead of a stack trace (or worse, a silently wrong run) partway
through the model::

    from grat.loaders.get_sites import load_sites
    from grat.loaders.get_wafr import load_wafr
    from grat.loaders.get_ccc import get_crop_calendar
    from grat.validation import validate_grat_inputs

    sites = load_sites("my_sites.csv")
    wafr = load_wafr("my_wafr.csv")
    crop_calendar = get_crop_calendar("my_ccc.csv")

    report = validate_grat_inputs(sites, wafr, crop_calendar=crop_calendar)
    report  # prints a summary in a notebook cell

    if not report.ok:
        raise SystemExit("fix the data before running the model")

Every check function here takes the same objects `build_sites` and `run_grat` take
(the loader output), not raw file paths, so it works regardless of where your data
came from or how messy the source file was - csv, shapefile, geodatabase, or something
assembled by hand.
"""

import math
from collections import Counter
from dataclasses import dataclass, field
from numbers import Number

from grat.loaders.get_ccc import ccc_valid_crops, ccc_valid_soil_types
from grat.loaders.get_sites import parse_bottleneck_ids, parse_compatible_sources
from grat.model.constants import DAYS_PER_WATER_YEAR


def _is_number(value):
    """True if `value` is an actual number (not a numeric-looking string) and not NaN.

    A numeric string such as `"10"` is deliberately rejected: callers compare the
    value against zero, and the loaders never coerce stray strings to numbers, so a
    string that merely looks numeric would behave no better in the model than one
    that doesn't.
    """
    if isinstance(value, bool) or not isinstance(value, Number):
        return False
    try:
        return not math.isnan(value)
    except TypeError:
        return True  # non-float numeric types (e.g. int) are never NaN


def _as_list(value, parser):
    """Normalizes a raw site field that may be a string, a list, or missing.

    Args:
        value: raw field value - a comma-delimited string, a list/tuple, or None.
        parser: function to split a string into a list (e.g. `parse_compatible_sources`).

    Returns:
        list of values
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return parser(value)


def _sort_key(value):
    """Sort key that tolerates `None` and mixed types, unlike the default `sorted`."""
    return (value is None, str(value))


def _safe_sorted(values):
    """`sorted`, but safe for a collection that may mix `None` with strings, numbers, or tuples."""
    return sorted(values, key=_sort_key)


def _site_bottleneck_ids(site):
    """Parses one site's `bottleneck_ids` field the same way `build_sites` does.

    Args:
        site: a site dictionary, as returned by `load_sites`.

    Returns:
        `(ids, error_message)` - `ids` is a list (possibly empty), and `error_message`
        is `None` unless the field couldn't be parsed, in which case `ids` is empty.
    """
    raw = site.get("bottleneck_ids")
    if isinstance(raw, (list, tuple, set)):
        return list(raw), None
    try:
        return parse_bottleneck_ids(raw) or [], None
    except (TypeError, ValueError):
        return [], f"site {site.get('grat_id')!r} has an unparseable bottleneck_ids value: {raw!r}."


def _in_lieu_region_key(region_number):
    """Returns the in-lieu crop calendar lookup key for a region number, or `None`.

    Mirrors the normalization `build_sites` applies before `Farm.get_site_volume` looks
    the region number up in the in-lieu calendar (`str(region_number)`, with whole
    numbers first stripped of a trailing `.0`) - `region_number=8.0` and
    `region_number="8"` must resolve to the same key, `"8"`.

    Args:
        region_number: a site's raw `region_number` value.

    Returns:
        The calendar lookup key, or `None` if there is no region number (in which case
        the model skips the in-lieu lookup entirely rather than using a key).
    """
    if region_number is None:
        return None
    if isinstance(region_number, Number) and not isinstance(region_number, bool) and region_number % 1 == 0:
        return str(int(region_number))
    return str(region_number)


def _would_build(site):
    """True if `build_sites` would keep this site rather than silently dropping it.

    Mirrors `grat.loaders.get_sites.build_sites`'s branching exactly: only
    `recharge_type` of `"OFR"` or `"Basin"` survive outright, and `recharge_type=None`
    survives only alongside an `in_lieu_crop`. Any other `recharge_type` - including
    `"Canal"`, which is never built from a sites row - is dropped, in_lieu_crop or not.

    Args:
        site: a site dictionary, as returned by `load_sites`.

    Returns:
        True if `build_sites` would construct a `Farm` or `Basin` from this row.
    """
    recharge_type = site.get("recharge_type")
    if recharge_type in ("OFR", "Basin"):
        return True
    return recharge_type is None and site.get("in_lieu_crop") is not None


@dataclass
class Issue:
    """One problem found in the input data."""

    level: str  # "error" or "warning"
    source: str  # which input the issue came from, e.g. "sites", "wafr"
    message: str

    def __str__(self):
        """Render as `[x] source: message` (errors) or `[!] source: message` (warnings)."""
        marker = "x" if self.level == "error" else "!"
        return f"[{marker}] {self.source}: {self.message}"


@dataclass
class ValidationReport:
    """Collects issues found across one or more checks.

    Attributes:
        issues: every issue found, in the order the checks ran.
    """

    issues: list = field(default_factory=list)

    def error(self, source, message):
        """Records a problem that will likely break the run or silently drop data."""
        self.issues.append(Issue("error", source, message))

    def warning(self, source, message):
        """Records a problem that is worth checking but won't stop the model from running."""
        self.issues.append(Issue("warning", source, message))

    @property
    def errors(self):
        """Issues at the "error" level."""
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self):
        """Issues at the "warning" level."""
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self):
        """True when nothing at the "error" level was found. Warnings may still be worth reading."""
        return not self.errors

    def __bool__(self):
        """Same as `ok`, so `if report:` reads naturally."""
        return self.ok

    def __repr__(self):
        """Readable summary, shown automatically when a report is the last line of a notebook cell."""
        if not self.issues:
            return "ValidationReport: no issues found."

        lines = [f"ValidationReport: {len(self.errors)} error(s), {len(self.warnings)} warning(s)"]
        lines += [f"  {issue}" for issue in self.issues]
        return "\n".join(lines)


def check_sites(
    report,
    sites,
    *,
    known_wafr_sources=None,
    known_bottleneck_ids=None,
    known_precip_grids=None,
    valid_crops=None,
    valid_il_crops=None,
    valid_soil_types=None,
    crop_calendar=None,
    crop_calendar_in_lieu=None,
):
    """Checks the site dictionaries returned by `load_sites`, before `build_sites` runs.

    Flags conditions that `build_sites` and `drop_invalid_sites` would otherwise handle
    by silently dropping the site, so a bad input file doesn't just quietly shrink the
    site count.

    Args:
        report: `ValidationReport` to add issues to.
        sites: list of site attribute dictionaries, as returned by `load_sites`.
        known_wafr_sources: WAFR source names present in the WAFR input, to catch sites
            that reference a source the WAFR file doesn't have.
        known_bottleneck_ids: bottleneck ids present in the bottleneck input.
        known_precip_grids: precipitation grid ids present in the precip input.
        valid_crops: crop types present in the on-farm crop compatibility calendar.
        valid_il_crops: crop types present in the in-lieu crop compatibility calendar.
        valid_soil_types: soil types present in the crop compatibility calendar.
        crop_calendar: the on-farm crop compatibility calendar itself (`{crop: {soil_type:
            [...]}}`), to check each site's actual crop/soil_type pair rather than just
            whether each half is individually known.
        crop_calendar_in_lieu: the in-lieu crop compatibility calendar itself
            (`{crop: {region_number: [...]}}`), to check each site's actual
            in_lieu_crop/region_number pair.
    """
    if not sites:
        report.error("sites", "No site rows were loaded - check the file path, layer name and where clause.")
        return

    ids = [s.get("grat_id") for s in sites]
    missing_ids = sum(1 for i in ids if i is None or (isinstance(i, str) and not i.strip()))
    if missing_ids:
        report.error("sites", f"{missing_ids} of {len(sites)} site(s) have a missing grat_id.")

    duplicate_ids = _safe_sorted(gid for gid, n in Counter(i for i in ids if i is not None).items() if n > 1)
    if duplicate_ids:
        report.warning("sites", f"grat_id is duplicated for {len(duplicate_ids)} site(s), e.g. {duplicate_ids[:5]}.")

    dropped = [s.get("grat_id") for s in sites if not _would_build(s)]
    if dropped:
        report.warning(
            "sites",
            f"{len(dropped)} site(s) will be silently dropped by build_sites - recharge_type must be "
            f'"OFR", "Basin", or None with an in_lieu_crop set, e.g. ids {dropped[:5]}.',
        )

    non_numeric_acres = [s.get("grat_id") for s in sites if not _is_number(s.get("acres"))]
    if non_numeric_acres:
        report.error(
            "sites",
            f"{len(non_numeric_acres)} site(s) have a missing or non-numeric acres, e.g. ids {non_numeric_acres[:5]}.",
        )

    negative_acres = [s.get("grat_id") for s in sites if _is_number(s.get("acres")) and s["acres"] < 0]
    if negative_acres:
        report.warning("sites", f"{len(negative_acres)} site(s) have negative acres, e.g. ids {negative_acres[:5]}.")

    zero_acres = [s.get("grat_id") for s in sites if _is_number(s.get("acres")) and s["acres"] == 0]
    if zero_acres:
        report.warning(
            "sites",
            f"{len(zero_acres)} site(s) have zero acres and can never receive or recharge water, "
            f"e.g. ids {zero_acres[:5]}.",
        )

    ofr_sites = [s for s in sites if s.get("recharge_type") == "OFR"]

    neither_crop = [s.get("grat_id") for s in ofr_sites if not s.get("crop") and not s.get("in_lieu_crop")]
    if neither_crop:
        report.warning(
            "sites",
            f"{len(neither_crop)} OFR site(s) have neither crop nor in_lieu_crop set and will be dropped by "
            f"drop_invalid_sites, e.g. ids {neither_crop[:5]}.",
        )

    if valid_crops is not None:
        bad_crops = _safe_sorted({s["crop"] for s in ofr_sites if s.get("crop") and s["crop"] not in valid_crops})
        if bad_crops:
            report.warning("sites", f"Crop type(s) not found in the on-farm crop compatibility calendar: {bad_crops}.")

    if valid_il_crops is not None:
        bad_il_crops = _safe_sorted(
            {s["in_lieu_crop"] for s in sites if s.get("in_lieu_crop") and s["in_lieu_crop"] not in valid_il_crops}
        )
        if bad_il_crops:
            report.warning(
                "sites", f"In-lieu crop type(s) not found in the in-lieu crop compatibility calendar: {bad_il_crops}."
            )

    if valid_soil_types is not None:
        bad_soils = _safe_sorted(
            {s.get("soil_type") for s in ofr_sites if s.get("crop") and s.get("soil_type") not in valid_soil_types}
        )
        if bad_soils:
            report.warning("sites", f"Soil type(s) not found in the crop compatibility calendar: {bad_soils}.")

    if crop_calendar is not None:
        # only for crops the calendar actually has - a crop missing entirely is already
        # covered by the warning above, and checking it here would just double-report it.
        missing_pairs = _safe_sorted(
            {
                (s["crop"], s.get("soil_type"))
                for s in ofr_sites
                if s.get("crop") in crop_calendar and s.get("soil_type") not in crop_calendar[s["crop"]]
            }
        )
        if missing_pairs:
            report.error(
                "sites",
                f"Crop/soil_type combination(s) not found in the on-farm crop compatibility calendar - "
                f"Farm.get_site_volume will raise a KeyError for these: {missing_pairs}.",
            )

    if crop_calendar_in_lieu is not None:
        missing_il_pairs = _safe_sorted(
            {
                (s["in_lieu_crop"], _in_lieu_region_key(s.get("region_number")))
                for s in sites
                if s.get("in_lieu_crop") in crop_calendar_in_lieu
                and s.get("region_number") is not None
                and _in_lieu_region_key(s["region_number"]) not in crop_calendar_in_lieu[s["in_lieu_crop"]]
            }
        )
        if missing_il_pairs:
            report.error(
                "sites",
                f"In_lieu_crop/region_number combination(s) not found in the in-lieu crop compatibility "
                f"calendar - Farm.get_site_volume will raise a KeyError for these: {missing_il_pairs}.",
            )

    if known_wafr_sources is not None:
        used_sources = {
            src
            for s in sites
            for src in _as_list(s.get("wafr_sources_primary"), parse_compatible_sources)
            + _as_list(s.get("wafr_sources_secondary"), parse_compatible_sources)
        }
        unknown_sources = _safe_sorted(used_sources - set(known_wafr_sources))
        if unknown_sources:
            report.warning(
                "sites", f"WAFR source(s) referenced by sites but not present in the WAFR data: {unknown_sources}."
            )

    # build_sites calls parse_bottleneck_ids too, so an unparseable value breaks the
    # model whether or not bottleneck data was supplied here - always check it.
    used_bottleneck_ids = set()
    bad_bottleneck_fields = []
    for s in sites:
        parsed_ids, error_message = _site_bottleneck_ids(s)
        used_bottleneck_ids.update(parsed_ids)
        if error_message:
            bad_bottleneck_fields.append(error_message)

    if bad_bottleneck_fields:
        shown = bad_bottleneck_fields[:5]
        remainder = f" (+{len(bad_bottleneck_fields) - 5} more)" if len(bad_bottleneck_fields) > 5 else ""
        report.error("sites", " ".join(shown) + remainder)

    if known_bottleneck_ids is not None:
        unknown_bottleneck_ids = _safe_sorted(used_bottleneck_ids - set(known_bottleneck_ids))
        if unknown_bottleneck_ids:
            report.warning(
                "sites",
                f"Bottleneck id(s) referenced by sites but not present in the bottleneck "
                f"data: {unknown_bottleneck_ids}.",
            )

    if known_precip_grids is not None:
        used_grids = {s["precip_grid"] for s in sites if s.get("precip_grid") is not None}
        unknown_grids = _safe_sorted(used_grids - set(known_precip_grids))
        if unknown_grids:
            report.warning(
                "sites", f"Precip grid id(s) referenced by sites but not present in the precip data: {unknown_grids}."
            )


def _check_daily_series(report, source, data, label_singular, *, empty_year_is_error=False):
    """Shared checks for the `{year: {key: [daily values]}}` shape of WAFR and precip data.

    Args:
        report: `ValidationReport` to add issues to.
        source: name to tag issues with, e.g. "wafr" or "precip".
        data: dictionary of `{year: {key: [daily values]}}`.
        label_singular: name for one `key`, e.g. "source" or "grid", used in messages.
        empty_year_is_error: report a year with no entries as an error rather than a
            warning. True for WAFR: `process_year` reads the day count from its first
            source and raises `IndexError` for a year with none. Precipitation is
            optional per site, so an empty year there degrades gracefully instead.
    """
    if not data:
        report.error(source, "No data was loaded.")
        return

    for year, by_key in data.items():
        if not by_key:
            record_issue = report.error if empty_year_is_error else report.warning
            record_issue(source, f"Water year {year} has no {label_singular}s.")
            continue

        lengths = {key: len(values) for key, values in by_key.items()}
        if any(length not in (365, 366) for length in lengths.values()):
            report.error(source, f"Water year {year} has {label_singular}(s) with an unexpected day count: {lengths}.")
        elif len(set(lengths.values())) > 1:
            report.error(source, f"Water year {year} has {label_singular}s with differing day counts: {lengths}.")

        for key, values in by_key.items():
            if any(not _is_number(v) for v in values):
                report.error(source, f"Water year {year}, {label_singular} '{key}' has missing or non-numeric values.")

            negative_days = sum(1 for v in values if _is_number(v) and v < 0)
            if negative_days:
                report.warning(
                    source, f"Water year {year}, {label_singular} '{key}' has {negative_days} negative value(s)."
                )

    years = sorted(data)
    gaps = [y for y in range(years[0], years[-1] + 1) if y not in data]
    if gaps:
        report.warning(source, f"Water years are not contiguous; missing year(s): {gaps}.")


def check_wafr(report, wafr):
    """Checks the water-available-for-recharge dictionary returned by `load_wafr`.

    Args:
        report: `ValidationReport` to add issues to.
        wafr: dictionary of `{year: {source: [daily values]}}`.
    """
    _check_daily_series(report, "wafr", wafr, "source", empty_year_is_error=True)


def check_precip(report, precip):
    """Checks the precipitation dictionary returned by `get_precip`.

    Args:
        report: `ValidationReport` to add issues to.
        precip: dictionary of `{year: {grid: [daily values]}}`.
    """
    _check_daily_series(report, "precip", precip, "grid")


def check_bottlenecks(report, bottleneck_rows):
    """Checks raw bottleneck rows, before they're turned into `Bottleneck` objects.

    Args:
        report: `ValidationReport` to add issues to.
        bottleneck_rows: iterable of mappings with `bid`, `capacity_cfs` and
            `capacity_irr_cfs` keys, e.g. `load_bottlenecks`' csv rows read with
            `pandas.DataFrame.to_dict("records")`, or the JSON list `unpack_bottlenecks` takes.
    """
    rows = list(bottleneck_rows)
    if not rows:
        report.warning("bottlenecks", "No bottleneck rows were loaded.")
        return

    for required in ("bid", "capacity_cfs", "capacity_irr_cfs"):
        if any(required not in row for row in rows):
            report.error("bottlenecks", f"Not every row has a '{required}' value.")
            return  # the checks below assume every row has these keys

    duplicate_ids = sorted(bid for bid, n in Counter(row["bid"] for row in rows).items() if n > 1)
    if duplicate_ids:
        report.error("bottlenecks", f"Duplicate bottleneck id(s): {duplicate_ids}.")

    for field_name in ("capacity_cfs", "capacity_irr_cfs"):
        bad = [row["bid"] for row in rows if not _is_number(row[field_name])]
        if bad:
            report.error(
                "bottlenecks", f"{len(bad)} row(s) have a missing or non-numeric {field_name}, e.g. ids {bad[:5]}."
            )

        negative = [row["bid"] for row in rows if _is_number(row[field_name]) and row[field_name] < 0]
        if negative:
            report.warning(
                "bottlenecks", f"{len(negative)} row(s) have negative {field_name}, e.g. ids {negative[:5]}."
            )

    exceeds = [
        row["bid"]
        for row in rows
        if _is_number(row["capacity_cfs"])
        and _is_number(row["capacity_irr_cfs"])
        and row["capacity_irr_cfs"] > row["capacity_cfs"]
    ]
    if exceeds:
        report.warning(
            "bottlenecks",
            f"{len(exceeds)} row(s) have capacity_irr_cfs greater than capacity_cfs, e.g. ids {exceeds[:5]}.",
        )


def check_crop_calendar(report, crop_calendar, *, source="crop calendar"):
    """Checks a crop calendar dictionary from `get_crop_calendar` or `get_il_crop_calendar`.

    Args:
        report: `ValidationReport` to add issues to.
        crop_calendar: dictionary of `{crop: {key: [daily values]}}` (`key` is a soil
            type for the on-farm calendar, or a region number for the in-lieu one).
        source: name to tag issues with.
    """
    if not crop_calendar:
        report.warning(source, "No crop calendar data was loaded.")
        return

    for crop, by_key in crop_calendar.items():
        for key, values in by_key.items():
            # the loaders always pad a calendar to DAYS_PER_WATER_YEAR entries (the last
            # day of a 365-day calendar is repeated as day 366), and Farm.get_site_volume
            # indexes up to the length of whichever water year's WAFR is currently
            # running - up to 365 for a non-leap year - so a shorter calendar here can
            # raise IndexError on a leap year even though no single WAFR year would.
            if len(values) != DAYS_PER_WATER_YEAR:
                report.error(source, f"{crop} / {key} has {len(values)} day(s) instead of {DAYS_PER_WATER_YEAR}.")

            if any(not _is_number(v) for v in values):
                report.error(source, f"{crop} / {key} has missing or non-numeric accepted-rate value(s).")

            if any(_is_number(v) and v < 0 for v in values):
                report.warning(source, f"{crop} / {key} has negative accepted-rate value(s).")


def validate_grat_inputs(
    sites,
    wafr,
    *,
    bottleneck_rows=None,
    crop_calendar=None,
    crop_calendar_in_lieu=None,
    precip=None,
):
    """Runs every check that applies to the inputs provided, and returns the combined report.

    Call this with whatever you've already loaded - only `sites` and `wafr` are
    required, matching what `build_sites` and `run_grat` need at a minimum. Nothing
    passed in is modified.

    Args:
        sites: list of site attribute dictionaries, as returned by `load_sites`.
        wafr: dictionary of `{year: {source: [daily values]}}`, as returned by `load_wafr`.
        bottleneck_rows: raw bottleneck rows (before `load_bottlenecks` builds objects),
            e.g. `pandas.read_csv(path).to_dict("records")`.
        crop_calendar: on-farm crop compatibility calendar, as returned by `get_crop_calendar`.
        crop_calendar_in_lieu: in-lieu crop compatibility calendar, as returned by `get_il_crop_calendar`.
        precip: dictionary of `{year: {grid: [daily values]}}`, as returned by `get_precip`.

    Returns:
        `ValidationReport`. Prints as a readable summary in a notebook cell; `report.ok`
        is True when no errors were found, and `report.errors` / `report.warnings` give
        the issues found at each level.
    """
    report = ValidationReport()

    # materialize once - an iterator/generator would otherwise be exhausted building
    # known_bottleneck_ids below, leaving nothing for check_bottlenecks to see.
    if bottleneck_rows is not None:
        bottleneck_rows = list(bottleneck_rows)

    valid_crops = ccc_valid_crops(crop_calendar) if crop_calendar else None
    valid_soil_types = ccc_valid_soil_types(crop_calendar) if crop_calendar else None
    valid_il_crops = ccc_valid_crops(crop_calendar_in_lieu) if crop_calendar_in_lieu else None

    known_wafr_sources = {src for by_source in wafr.values() for src in by_source} if wafr else None
    known_precip_grids = {grid for by_grid in precip.values() for grid in by_grid} if precip else None
    known_bottleneck_ids = {row["bid"] for row in bottleneck_rows if "bid" in row} if bottleneck_rows else None

    check_sites(
        report,
        sites,
        known_wafr_sources=known_wafr_sources,
        known_bottleneck_ids=known_bottleneck_ids,
        known_precip_grids=known_precip_grids,
        valid_crops=valid_crops,
        valid_il_crops=valid_il_crops,
        valid_soil_types=valid_soil_types,
        crop_calendar=crop_calendar,
        crop_calendar_in_lieu=crop_calendar_in_lieu,
    )
    check_wafr(report, wafr)

    if precip is not None:
        check_precip(report, precip)
    if bottleneck_rows is not None:
        check_bottlenecks(report, bottleneck_rows)
    if crop_calendar is not None:
        check_crop_calendar(report, crop_calendar, source="on-farm crop calendar")
    if crop_calendar_in_lieu is not None:
        check_crop_calendar(report, crop_calendar_in_lieu, source="in-lieu crop calendar")

    return report
