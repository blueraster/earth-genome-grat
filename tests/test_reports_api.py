"""Tests for selecting reports by name and getting frames back."""

import os

import pytest

from grat import read_report, run_grat
from grat.model import bottlenecks, engine, sites, sorters
from grat.reports import catalog
from grat.reports.writers import REPORT_FILES

# The numeric ids the legacy run-builder form used, and the name each one now maps to.
# The sets in `catalog` are asserted against this below, so the guards that used to be
# written as `if any(e in [4, 5, 6, 7, 8, 9, 18] ...)` stay honest.
ID_TO_NAME = {
    2: "annual_summary_recharge",
    3: "daily_summary_recharge",
    4: "daily_wafr_applied_by_site",
    5: "daily_recharge_by_site",
    6: "monthly_recharge_by_site_report",
    7: "monthly_recharge_by_site_report_detailed",
    8: "daily_farm_recharge_report",
    9: "yearly_aggregate_farm_recharge_report",
    10: "daily_wafr_report",
    11: "bottlenecks_capacity_limitations_report",
    12: "bottlenecks_daily_conveyance_limits_by_volume",
    13: "yearly_bottleneck_capacity_logger",
    15: "annual_recharge_by_sw_and_gw",
    16: "annual_recharge_by_district_and_gw",
    17: "annual_recharge_by_district_and_wafr",
    18: "daily_recharge_by_gw_basin",
    19: "acres_available_and_used",
    20: "daily_water_transfer_by_sustain_zone_report",
    21: "yearly_water_transfer_by_sustain_zone_report",
    22: "fields_repurposed",
}


def names_for(ids):
    return frozenset(ID_TO_NAME[i] for i in ids)


# --------------------------------------------------------------------------- catalog


def test_every_legacy_report_has_a_name():
    assert frozenset(ID_TO_NAME.values()) == catalog.CSV_REPORTS


def test_every_csv_report_has_a_filename():
    assert frozenset(REPORT_FILES) >= catalog.CSV_REPORTS


@pytest.mark.parametrize(
    ("group", "ids"),
    [
        ("NEEDS_DAILY_SUMMARY", [2, 3]),
        ("NEEDS_SITE_VOLUME", [4, 5, 6, 7, 8, 9, 18]),
        ("NEEDS_ANNUAL_GROUPING", [15, 16, 17]),
        ("NEEDS_MONTHLY", [6, 7]),
        ("NEEDS_BOTTLENECKS", [11, 12, 13]),
        ("NEEDS_TRANSFERS", [20, 21]),
        ("YEAR_SUBFOLDER", [4, 5]),
        # site_info had no guard at all before; these are the reports that read it
        ("NEEDS_SITE_INFO", [4, 5, 6, 7, 8, 9, 18, 22]),
    ],
)
def test_group_matches_the_legacy_id_set(group, ids):
    assert getattr(catalog, group) == names_for(ids)


def test_groups_only_name_known_reports():
    for group in (n for n in dir(catalog) if n.startswith(("NEEDS_", "POST_RUN", "YEAR_"))):
        assert getattr(catalog, group) <= catalog.ALL_REPORTS, group


def test_asking_for_the_yearly_transfer_report_pulls_in_the_daily_one():
    """Report 21 is a roll-up of report 20's csv, so 20 is published too."""
    assert "daily_water_transfer_by_sustain_zone_report" in catalog.expand(
        {"yearly_water_transfer_by_sustain_zone_report"}
    )


def test_expand_is_idempotent():
    once = catalog.expand(catalog.ALL_REPORTS)
    assert catalog.expand(once) == once


def test_expand_rejects_an_unknown_name():
    with pytest.raises(KeyError, match="nope"):
        catalog.expand({"nope"})


# ----------------------------------------------------------------------- end to end


def build_sites():
    """A canal, a basin and two farms, one of them repurposed to MLRP."""
    common = {"precip_grid": 1, "district": "D1", "subbasin": "SB1", "sustainability_zone": "1"}
    return sorters.sort_sites(
        [
            sites.Canal(
                grat_id="C1",
                wafr_sources_primary=["A"],
                max_capacity=10000,
                perc_rate=600,
                recharge_type="Canal",
                **common,
            ),
            sites.Basin(
                grat_id="B1",
                acres=2.5,
                recharge_type="Basin",
                perc_rate=1.2,
                max_capacity=100,
                bottleneck_ids=[1],
                wafr_sources_primary=["A"],
                **common,
            ),
            sites.Farm(
                grat_id="F1",
                crop="Corn",
                acres=12.5,
                recharge_type="OFR",
                soil_type="Good",
                cfs_limit=5 / 1.983,
                bottleneck_ids=[1],
                wafr_sources_primary=["A"],
                **common,
            ),
            sites.Farm(
                grat_id="F2",
                crop="MLRP",
                acres=4.0,
                recharge_type="OFR",
                soil_type="Good",
                cfs_limit=5 / 1.983,
                bottleneck_ids=[1],
                wafr_sources_primary=["A"],
                **common,
            ),
        ]
    )


def run(tmp_path, reports, *, transfers=True):
    """Runs two water years into `tmp_path` and returns the result dict."""
    engine.transfer_supply_sources = {"1": "A"} if transfers else {}
    return run_grat(
        build_sites(),
        {2001: {"A": [500.0] * 366}, 2002: {"A": [500.0] * 366}},
        [bottlenecks.Bottleneck(bottleneck_id=1, max_capacity=500, wafr_sources=["A"])],
        {"Corn": {"Good": [1.0] * 366}, "MLRP": {"Good": [0.5] * 366}},
        {2001: {1: [0.01] * 366}, 2002: {1: [0.01] * 366}},
        reports=reports,
        output_parent=str(tmp_path),
        years=[2001, 2002],
        transfer_goals={"1": {"THRESHOLD": 1.0, "ACREFEET": 100.0}} if transfers else None,
    )


def test_a_full_run_produces_every_report(tmp_path):
    result = run(tmp_path, catalog.ALL_REPORTS)
    assert set(result["reports"]) == catalog.CSV_REPORTS
    assert set(result["series"]) == set(catalog.FRONTEND_SERIES)
    assert os.path.exists(result["zip_path"])


def test_every_produced_report_can_be_read_back(tmp_path):
    result = run(tmp_path, catalog.ALL_REPORTS)
    for name in sorted(result["reports"]):
        year = 2001 if name in catalog.YEAR_SUBFOLDER else None
        assert not read_report(result["output_folder"], name, year=year).empty, name


def test_reading_back_a_report_that_was_not_requested_raises(tmp_path):
    """The error names the missing file, which is the report that was not asked for."""
    result = run(tmp_path, ["daily_wafr_report"])
    with pytest.raises(FileNotFoundError, match="19_Acres Available and Used"):
        read_report(result["output_folder"], "acres_available_and_used")


def test_reading_back_an_unknown_report_name_raises(tmp_path):
    result = run(tmp_path, ["daily_wafr_report"])
    with pytest.raises(KeyError, match="not_a_report"):
        read_report(result["output_folder"], "not_a_report")


def test_a_narrow_request_writes_only_that_report(tmp_path):
    """The point of the change: a run pays only for what it asked for."""
    result = run(tmp_path, ["daily_wafr_report"])
    produced = sorted(f for f in os.listdir(result["output_folder"]) if f.endswith(".csv"))
    assert produced == [REPORT_FILES["daily_wafr_report"].filename]


def test_no_working_files_are_left_behind(tmp_path):
    result = run(tmp_path, catalog.ALL_REPORTS)
    leftovers = [f for f in os.listdir(result["output_folder"]) if f.startswith("temp_")]
    assert not leftovers
    assert not os.path.exists(os.path.join(result["output_folder"], "annualRechargeByGrouping.csv"))


def test_per_year_reports_go_into_a_year_subfolder(tmp_path):
    result = run(tmp_path, ["daily_recharge_by_site"])
    for year in (2001, 2002):
        assert os.path.exists(
            os.path.join(result["output_folder"], str(year), REPORT_FILES["daily_recharge_by_site"].filename)
        )


def test_reports_needing_transfers_are_skipped_when_there_are_none(tmp_path):
    """A missing model input drops the report rather than failing the run."""
    result = run(tmp_path, catalog.ALL_REPORTS, transfers=False)
    assert not set(result["reports"]) & catalog.NEEDS_TRANSFERS
    assert set(result["reports"]) == catalog.CSV_REPORTS - catalog.NEEDS_TRANSFERS
