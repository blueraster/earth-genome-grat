"""What reports exist, and what each one is built from.

Reports are asked for by name. The names are the keys of `writers.REPORT_FILES`, so
the filename for each is looked up there and the numeric prefixes (`02_`, `03_`, ...)
stay where they belong - in the filenames, which are the output contract.

The sets below say which reports share an expensive intermediate. `selector` guards
each intermediate on an intersection, so a run only pays for what it asked for.
"""

# ---------------------------------------------------------------------------
# What a caller can ask for
# ---------------------------------------------------------------------------

# The 20 published csv reports. Every name here is a key of writers.REPORT_FILES.
CSV_REPORTS = frozenset(
    {
        "annual_summary_recharge",
        "daily_summary_recharge",
        "daily_wafr_applied_by_site",
        "daily_recharge_by_site",
        "monthly_recharge_by_site_report",
        "monthly_recharge_by_site_report_detailed",
        "daily_farm_recharge_report",
        "yearly_aggregate_farm_recharge_report",
        "daily_wafr_report",
        "bottlenecks_capacity_limitations_report",
        "bottlenecks_daily_conveyance_limits_by_volume",
        "yearly_bottleneck_capacity_logger",
        "annual_recharge_by_sw_and_gw",
        "annual_recharge_by_district_and_gw",
        "annual_recharge_by_district_and_wafr",
        "daily_recharge_by_gw_basin",
        "acres_available_and_used",
        "daily_water_transfer_by_sustain_zone_report",
        "yearly_water_transfer_by_sustain_zone_report",
        "fields_repurposed",
    }
)

# The frontend visualisation series. These are returned as json-ready dicts rather
# than written to csv, but they are selected by name like any other report.
FRONTEND_SERIES = frozenset(
    {
        "yearly_recharge_volumes",
        "unused_wafr",
        "max_wafr_per_site",
        "recharge_by_sustainability_zone",
    }
)

ALL_REPORTS = CSV_REPORTS | FRONTEND_SERIES

# ---------------------------------------------------------------------------
# Which reports share which intermediate
# ---------------------------------------------------------------------------

# Site attribution. Needed in memory by the per-site reports, and read back after the
# run by the monthly pivot and the MLRP report.
NEEDS_SITE_INFO = frozenset(
    {
        "daily_wafr_applied_by_site",
        "daily_recharge_by_site",
        "daily_farm_recharge_report",
        "yearly_aggregate_farm_recharge_report",
        "daily_recharge_by_gw_basin",
        "monthly_recharge_by_site_report",
        "monthly_recharge_by_site_report_detailed",
        "fields_repurposed",
    }
)

# Per-site daily volume arrays, the input to every per-site report.
NEEDS_SITE_VOLUME = frozenset(
    {
        "daily_wafr_applied_by_site",
        "daily_recharge_by_site",
        "monthly_recharge_by_site_report",
        "monthly_recharge_by_site_report_detailed",
        "daily_farm_recharge_report",
        "yearly_aggregate_farm_recharge_report",
        "daily_recharge_by_gw_basin",
    }
)

NEEDS_DAILY_SUMMARY = frozenset({"annual_summary_recharge", "daily_summary_recharge"})

NEEDS_ANNUAL_GROUPING = frozenset(
    {
        "annual_recharge_by_sw_and_gw",
        "annual_recharge_by_district_and_gw",
        "annual_recharge_by_district_and_wafr",
    }
)

# Monthly values per site, accumulated per year and pivoted after the run.
NEEDS_MONTHLY = frozenset({"monthly_recharge_by_site_report", "monthly_recharge_by_site_report_detailed"})

# Intermediates feeding a single frontend series each.
NEEDS_UNUSED_WAFR = frozenset({"unused_wafr"})
NEEDS_WAFR_BY_SITE = frozenset({"max_wafr_per_site"})
NEEDS_TOTAL_BY_ZONE = frozenset({"recharge_by_sustainability_zone"})

# ---------------------------------------------------------------------------
# How and when each report is produced
# ---------------------------------------------------------------------------

# Built once, after every water year has run.
POST_RUN = (
    frozenset(
        {
            "monthly_recharge_by_site_report",
            "monthly_recharge_by_site_report_detailed",
            "annual_recharge_by_sw_and_gw",
            "annual_recharge_by_district_and_gw",
            "annual_recharge_by_district_and_wafr",
            "yearly_water_transfer_by_sustain_zone_report",
            "fields_repurposed",
        }
    )
    | FRONTEND_SERIES
)

PER_YEAR = ALL_REPORTS - POST_RUN

# Written into <output_folder>/<year>/ rather than the run root, because they carry one
# column per day of the water year and would be unreadable concatenated.
YEAR_SUBFOLDER = frozenset({"daily_wafr_applied_by_site", "daily_recharge_by_site"})

# Reports that need a model input which may legitimately be absent. When it is, the
# report is skipped with a log line rather than failing the run.
NEEDS_BOTTLENECKS = frozenset(
    {
        "bottlenecks_capacity_limitations_report",
        "bottlenecks_daily_conveyance_limits_by_volume",
        "yearly_bottleneck_capacity_logger",
    }
)

NEEDS_TRANSFERS = frozenset(
    {"daily_water_transfer_by_sustain_zone_report", "yearly_water_transfer_by_sustain_zone_report"}
)

# Reports built from another report's published csv. Asking for one of these publishes
# the report it reads as well - previously this happened silently.
IMPLIES = {
    "yearly_water_transfer_by_sustain_zone_report": frozenset({"daily_water_transfer_by_sustain_zone_report"}),
    "yearly_recharge_volumes": frozenset({"annual_summary_recharge"}),
}


def expand(names):
    """Returns the requested reports plus any report they are built from.

    Args:
        names: report names the caller asked for.

    Returns: frozenset of report names to produce

    Raises:
        KeyError: a name is not a known report.
    """
    requested = frozenset(names)

    unknown = requested - ALL_REPORTS
    if unknown:
        raise KeyError(f"unknown reports: {sorted(unknown)}")

    for name, implied in IMPLIES.items():
        if name in requested:
            requested |= implied
    return requested
