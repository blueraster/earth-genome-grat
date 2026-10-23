from grat.loaders.get_ccc import get_crop_calendar
from grat.loaders.get_sites import load_sites
from grat.loaders.get_wafr import load_wafr
from grat.validation import (
    ValidationReport,
    check_bottlenecks,
    check_crop_calendar,
    check_precip,
    check_sites,
    check_wafr,
    validate_grat_inputs,
)

GOOD_SITE = {
    "grat_id": 1,
    "recharge_type": "OFR",
    "acres": 10,
    "crop": "Almonds",
    "soil_type": "Good",
    "wafr_sources_primary": "Folsom Lake",
    "bottleneck_ids": "1",
    "precip_grid": 1102,
}


class TestValidationReport:
    def test_ok_with_no_issues(self):
        report = ValidationReport()
        assert report.ok
        assert bool(report)
        assert report.errors == []
        assert report.warnings == []

    def test_not_ok_with_an_error(self):
        report = ValidationReport()
        report.error("sites", "no rows")
        assert not report.ok
        assert not bool(report)
        assert len(report.errors) == 1

    def test_ok_with_only_a_warning(self):
        report = ValidationReport()
        report.warning("sites", "looks odd")
        assert report.ok
        assert len(report.warnings) == 1


class TestCheckSites:
    def test_no_sites_is_an_error(self):
        report = ValidationReport()
        check_sites(report, [])
        assert len(report.errors) == 1

    def test_valid_site_has_no_issues(self):
        report = ValidationReport()
        check_sites(report, [dict(GOOD_SITE)])
        assert report.ok
        assert not report.warnings

    def test_missing_grat_id_is_an_error(self):
        report = ValidationReport()
        check_sites(report, [{**GOOD_SITE, "grat_id": None}])
        assert any("missing grat_id" in i.message for i in report.errors)

    def test_duplicate_grat_id_is_a_warning(self):
        report = ValidationReport()
        check_sites(report, [dict(GOOD_SITE), dict(GOOD_SITE)])
        assert any("duplicated" in i.message for i in report.warnings)

    def test_non_numeric_acres_is_an_error(self):
        report = ValidationReport()
        check_sites(report, [{**GOOD_SITE, "acres": "ten"}])
        assert any("non-numeric acres" in i.message for i in report.errors)

    def test_numeric_looking_string_acres_is_an_error_not_a_crash(self):
        # a string "10" must not slip past _is_number only to blow up the next
        # comparison against zero.
        report = ValidationReport()
        check_sites(report, [{**GOOD_SITE, "acres": "10"}])
        assert any("non-numeric acres" in i.message for i in report.errors)

    def test_negative_acres_is_a_warning(self):
        report = ValidationReport()
        check_sites(report, [{**GOOD_SITE, "acres": -5}])
        assert any("negative acres" in i.message for i in report.warnings)

    def test_unknown_recharge_type_is_a_warning(self):
        report = ValidationReport()
        check_sites(report, [{**GOOD_SITE, "recharge_type": "Farm"}])
        assert any("silently dropped" in i.message for i in report.warnings)

    def test_canal_recharge_type_is_a_warning(self):
        # build_sites never constructs a Canal from a sites row - only load_canals does -
        # so a "Canal" row here is dropped just like any other unrecognized type.
        report = ValidationReport()
        check_sites(report, [{**GOOD_SITE, "recharge_type": "Canal"}])
        assert any("silently dropped" in i.message for i in report.warnings)

    def test_none_recharge_type_without_in_lieu_crop_is_a_warning(self):
        report = ValidationReport()
        check_sites(report, [{**GOOD_SITE, "recharge_type": None, "crop": None}])
        assert any("silently dropped" in i.message for i in report.warnings)

    def test_none_recharge_type_with_in_lieu_crop_has_no_issue(self):
        # build_sites keeps this case - it's the one way an in-lieu-only site is built.
        report = ValidationReport()
        check_sites(report, [{**GOOD_SITE, "recharge_type": None, "crop": None, "in_lieu_crop": "Almonds"}])
        assert not any("silently dropped" in i.message for i in report.warnings)

    def test_ofr_site_without_crop_or_in_lieu_crop_is_a_warning(self):
        report = ValidationReport()
        check_sites(report, [{**GOOD_SITE, "crop": None}])
        assert any("neither crop nor in_lieu_crop" in i.message for i in report.warnings)

    def test_unknown_crop_is_a_warning(self):
        report = ValidationReport()
        check_sites(report, [dict(GOOD_SITE)], valid_crops=["Alfalfa"])
        assert any("Crop type" in i.message for i in report.warnings)

    def test_unknown_wafr_source_is_a_warning(self):
        report = ValidationReport()
        check_sites(report, [dict(GOOD_SITE)], known_wafr_sources=["Yolo Creek"])
        assert any("WAFR source" in i.message for i in report.warnings)

    def test_unknown_bottleneck_id_is_a_warning(self):
        report = ValidationReport()
        check_sites(report, [dict(GOOD_SITE)], known_bottleneck_ids=[2])
        assert any("Bottleneck id" in i.message for i in report.warnings)

    def test_unknown_precip_grid_is_a_warning(self):
        report = ValidationReport()
        check_sites(report, [dict(GOOD_SITE)], known_precip_grids=[9999])
        assert any("Precip grid" in i.message for i in report.warnings)

    def test_missing_and_unknown_soil_types_dont_crash_the_sort(self):
        # sorted() on a set mixing None with strings raises TypeError - soil_type isn't
        # required to be set the way crop is, so None has to be handled explicitly.
        report = ValidationReport()
        check_sites(
            report,
            [
                {**GOOD_SITE, "grat_id": 1, "soil_type": None},
                {**GOOD_SITE, "grat_id": 2, "soil_type": "Bad"},
            ],
            valid_soil_types=["Good"],
        )
        assert any("Soil type" in i.message for i in report.warnings)

    def test_unparseable_bottleneck_ids_is_an_error_not_a_crash(self):
        # parse_bottleneck_ids raises ValueError on "unknown" - build_sites would hit the
        # same exception, so this has to be reported rather than propagate.
        report = ValidationReport()
        check_sites(report, [{**GOOD_SITE, "bottleneck_ids": "1,unknown"}])
        assert any("unparseable bottleneck_ids" in i.message for i in report.errors)

    def test_unparseable_bottleneck_ids_checked_even_without_bottleneck_data(self):
        report = ValidationReport()
        check_sites(report, [{**GOOD_SITE, "bottleneck_ids": "not-a-number"}], known_bottleneck_ids=None)
        assert any("unparseable bottleneck_ids" in i.message for i in report.errors)

    def test_crop_in_calendar_but_wrong_soil_is_an_error(self):
        # the crop exists in the calendar, just not for this soil type - Farm.get_site_volume
        # would KeyError on this exact combination.
        report = ValidationReport()
        check_sites(
            report,
            [dict(GOOD_SITE)],  # crop="Almonds", soil_type="Good"
            crop_calendar={"Almonds": {"Poor": [0.1] * 366}},
        )
        assert any("Crop/soil_type combination" in i.message for i in report.errors)

    def test_crop_missing_entirely_is_not_double_reported_as_a_pair_error(self):
        report = ValidationReport()
        check_sites(
            report, [dict(GOOD_SITE)], valid_crops=["Alfalfa"], crop_calendar={"Alfalfa": {"Good": [0.1] * 366}}
        )
        assert any("Crop type" in i.message for i in report.warnings)
        assert not any("Crop/soil_type combination" in i.message for i in report.errors)

    def test_in_lieu_crop_and_region_pair_mismatch_is_an_error(self):
        report = ValidationReport()
        check_sites(
            report,
            [{**GOOD_SITE, "crop": None, "in_lieu_crop": "Almonds", "region_number": 8}],
            crop_calendar_in_lieu={"Almonds": {"10": [0.1] * 366}},
        )
        assert any("In_lieu_crop/region_number combination" in i.message for i in report.errors)

    def test_in_lieu_region_number_normalized_like_build_sites(self):
        # region_number=8.0 (a float with no fractional part) must match calendar key "8",
        # the same way build_sites normalizes it before Farm.get_site_volume looks it up.
        report = ValidationReport()
        check_sites(
            report,
            [{**GOOD_SITE, "crop": None, "in_lieu_crop": "Almonds", "region_number": 8.0}],
            crop_calendar_in_lieu={"Almonds": {"8": [0.1] * 366}},
        )
        assert not any("In_lieu_crop/region_number combination" in i.message for i in report.errors)


class TestCheckWAFR:
    def test_empty_is_an_error(self):
        report = ValidationReport()
        check_wafr(report, {})
        assert len(report.errors) == 1

    def test_good_data_has_no_issues(self):
        report = ValidationReport()
        check_wafr(report, {2000: {"Folsom Lake": [1.0] * 366}})
        assert report.ok
        assert not report.warnings

    def test_wrong_day_count_is_an_error(self):
        report = ValidationReport()
        check_wafr(report, {2000: {"Folsom Lake": [1.0] * 10}})
        assert any("day count" in i.message for i in report.errors)

    def test_missing_value_is_an_error(self):
        report = ValidationReport()
        check_wafr(report, {2000: {"Folsom Lake": [1.0] * 365 + [None]}})
        assert any("missing or non-numeric" in i.message for i in report.errors)

    def test_negative_value_is_a_warning(self):
        report = ValidationReport()
        check_wafr(report, {2000: {"Folsom Lake": [-1.0] + [1.0] * 365}})
        assert any("negative" in i.message for i in report.warnings)

    def test_year_gap_is_a_warning(self):
        report = ValidationReport()
        check_wafr(report, {2000: {"Folsom Lake": [1.0] * 366}, 2002: {"Folsom Lake": [1.0] * 365}})
        assert any("not contiguous" in i.message for i in report.warnings)

    def test_year_with_no_sources_is_an_error(self):
        # process_year reads the day count from the first WAFR source and raises
        # IndexError for a year with none - report.ok must not stay true for this.
        report = ValidationReport()
        check_wafr(report, {2000: {}})
        assert any("has no sources" in i.message for i in report.errors)
        assert not report.ok


class TestCheckPrecip:
    def test_good_data_has_no_issues(self):
        report = ValidationReport()
        check_precip(report, {2000: {1102: [0.0] * 365}})
        assert report.ok

    def test_year_with_no_grids_is_only_a_warning(self):
        # unlike WAFR, an empty precip year degrades gracefully (calc_precip just skips
        # sites whose grid is missing) rather than crashing the run.
        report = ValidationReport()
        check_precip(report, {2000: {}})
        assert report.ok
        assert any("has no grids" in i.message for i in report.warnings)


class TestCheckBottlenecks:
    GOOD_ROW = {"bid": 1, "capacity_cfs": 100, "capacity_irr_cfs": 50}

    def test_good_rows_have_no_issues(self):
        report = ValidationReport()
        check_bottlenecks(report, [dict(self.GOOD_ROW)])
        assert report.ok

    def test_duplicate_bid_is_an_error(self):
        report = ValidationReport()
        check_bottlenecks(report, [dict(self.GOOD_ROW), dict(self.GOOD_ROW)])
        assert any("Duplicate bottleneck id" in i.message for i in report.errors)

    def test_irrigation_capacity_above_full_capacity_is_a_warning(self):
        report = ValidationReport()
        check_bottlenecks(report, [{**self.GOOD_ROW, "capacity_irr_cfs": 200}])
        assert any("capacity_irr_cfs greater than capacity_cfs" in i.message for i in report.warnings)


class TestCheckCropCalendar:
    def test_good_calendar_has_no_issues(self):
        report = ValidationReport()
        check_crop_calendar(report, {"Almonds": {"Good": [0.1] * 366}})
        assert report.ok

    def test_wrong_day_count_is_an_error(self):
        report = ValidationReport()
        check_crop_calendar(report, {"Almonds": {"Good": [0.1] * 10}})
        assert any("instead of 366" in i.message for i in report.errors)

    def test_365_days_is_also_an_error(self):
        # the loaders always pad to 366 - a 365-length calendar here is non-standard
        # input and would IndexError on a leap year.
        report = ValidationReport()
        check_crop_calendar(report, {"Almonds": {"Good": [0.1] * 365}})
        assert any("instead of 366" in i.message for i in report.errors)

    def test_missing_rate_value_is_an_error(self):
        report = ValidationReport()
        check_crop_calendar(report, {"Almonds": {"Good": [None] + [0.1] * 365}})
        assert any("missing or non-numeric" in i.message for i in report.errors)


class TestValidateGratInputs:
    def test_oak_valley_sample_data_has_no_errors(self, oak_valley):
        sites = load_sites(
            oak_valley / "oakvalley.shp",
            attribute_renamer={"GRATID": "grat_id", "R_TYPE": "recharge_type", "ACRES": "acres"},
        )
        wafr = load_wafr(oak_valley / "WAFR_optimistic.csv")
        crop_calendar = get_crop_calendar(oak_valley / "CCC_ofr.csv")

        report = validate_grat_inputs(sites, wafr, crop_calendar=crop_calendar)
        assert report.ok

    def test_requires_only_sites_and_wafr(self):
        report = validate_grat_inputs([dict(GOOD_SITE)], {2000: {"Folsom Lake": [1.0] * 366}})
        assert isinstance(report, ValidationReport)

    def test_bottleneck_rows_may_be_a_one_shot_iterator(self):
        # known_bottleneck_ids used to be built by consuming bottleneck_rows directly,
        # exhausting a generator before check_bottlenecks ever saw it.
        bottleneck_rows = iter([{"bid": 1, "capacity_cfs": 100, "capacity_irr_cfs": 50}])
        report = validate_grat_inputs(
            [dict(GOOD_SITE)], {2000: {"Folsom Lake": [1.0] * 366}}, bottleneck_rows=bottleneck_rows
        )
        assert report.ok
