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

    def test_negative_acres_is_a_warning(self):
        report = ValidationReport()
        check_sites(report, [{**GOOD_SITE, "acres": -5}])
        assert any("negative acres" in i.message for i in report.warnings)

    def test_unknown_recharge_type_is_a_warning(self):
        report = ValidationReport()
        check_sites(report, [{**GOOD_SITE, "recharge_type": "Farm"}])
        assert any("recharge_type" in i.message for i in report.warnings)

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


class TestCheckPrecip:
    def test_good_data_has_no_issues(self):
        report = ValidationReport()
        check_precip(report, {2000: {1102: [0.0] * 365}})
        assert report.ok


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
        assert any("instead of 365 or 366" in i.message for i in report.errors)


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
