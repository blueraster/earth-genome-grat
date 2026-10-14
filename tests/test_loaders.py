import pytest

from grat.loaders import (
    get_bottlenecks,
    get_canals,
    get_ccc,
    get_sites,
    get_wafr,
    helpers,
)

CCC_CROPS = [
    "Alfalfa",
    "Almonds",
    "Cotton",
    "Fallow",
    "Grapes",
    "Pasture",
    "Pistachios",
    "ShorebirdApr",
    "ShorebirdMar",
    "Sweet Potato",
    "Tomatoes",
    "Walnuts",
]


class TestGetWAFR:
    @pytest.fixture(scope="class")
    @classmethod
    def d(cls, oak_valley):
        # avoid loading the dataset for each test
        return get_wafr.load_wafr(oak_valley / "WAFR_optimistic.csv")

    def test_get_wafr_type(self, d):
        assert isinstance(d, dict)

    def test_get_wafr_keys(self, d):
        assert list(d.keys()) == list(range(1969, 2019))

    def test_get_wafr_offset_years(self, oak_valley):
        d = get_wafr.load_wafr(oak_valley / "WAFR_pessimistic.csv", offset_years=100)
        assert list(d.keys()) == list(range(2069, 2119))

    def test_get_wafr_single_year_keys(self, d):
        assert sorted(d[2017].keys()) == ["Folsom Lake", "Yolo Creek"]

    def test_get_wafr_length_yearly_array(self, d):
        assert len(d[2017]["Folsom Lake"]) == 365
        assert len(d[1972]["Folsom Lake"]) == 366  # leap year

    def test_get_wafr_first_value(self, d):
        # first day with water in the sample is day 105 of water year 1969
        assert d[1969]["Folsom Lake"][103] == 0
        assert d[1969]["Folsom Lake"][104] == 416.509

    def test_get_wafr_length_yearly_array_max_min(self, d):
        year_array = d[2017]["Folsom Lake"]
        assert min(year_array) == 0
        assert max(year_array) == 984.313
        assert sum(year_array) / len(year_array) == pytest.approx(78.42520821917809, abs=1e-6)


# class TestGetPrecip:
#     @classmethod
#     def setup_class(cls):
#         # avoid loading the dataset for each test
#         cls.precip_data = get_precip.get_precip(input_precip_file=DATA_DIR / "precip_100DP_0DT_00EX_110yr.csv")
#
#     def test_get_precip_keys(self):
#         assert set(range(2100, 2200)).issubset(self.precip_data.keys())
#
#     def test_get_precip_length(self):
#         assert len(self.precip_data[2103][1102]) == 365
#         assert len(self.precip_data[2104][1510]) == 366


class TestHelpers:
    def test_wy(self):
        assert helpers.water_year(2022, 9) == 2022
        assert helpers.water_year(2021, 10) == 2022

    def test_dowy(self):
        assert helpers.day_of_water_year(2021, 10, 1) == 1
        assert helpers.day_of_water_year(2022, 9, 30) == 365
        assert helpers.day_of_water_year(2020, 9, 30) == 366  # extra day for leap year

    def test_rename(self):
        d = {"a": 1, "b": 2, "c": 3, "d": 4}

        d_renamed = helpers.rename_dictionary_keys(d, {"a": "z", "b": "y", "c": "x"})
        assert d_renamed.get("y") == 2
        assert d_renamed.get("d") == 4

    def test_split_multivalues(self):
        assert helpers.split_multivalues("Folsom Lake,Yolo Creek") == ["Folsom Lake", "Yolo Creek"]
        assert helpers.split_multivalues(None) == []

    def test_split_multivalues_strips_spaces(self):
        assert helpers.split_multivalues("Folsom Lake, Yolo Creek ") == ["Folsom Lake", "Yolo Creek"]

    def test_split_multivalues_drops_empty_values(self):
        assert helpers.split_multivalues("Folsom Lake,,Yolo Creek,") == ["Folsom Lake", "Yolo Creek"]
        assert helpers.split_multivalues("") == []


class TestGetCCC:
    @pytest.fixture(autouse=True)
    def setup(self, oak_valley):
        self.ccc = get_ccc.get_crop_calendar(oak_valley / "CCC_ofr.csv")

    def test_ccc_valid_crops(self):
        assert get_ccc.ccc_valid_crops(self.ccc) == CCC_CROPS

    def test_ccc_valid_soil_types(self):
        soil_types = get_ccc.ccc_valid_soil_types(self.ccc)
        expected = ["Very Poor", "Poor", "Moderately Poor", "Moderately Good", "Good", "Excellent"]
        assert sorted(soil_types) == sorted(expected)

    def test_shorebird_soil_types(self):
        # shorebird crops only have 4 of the 6 SAGBI types in the sample
        assert len(self.ccc["ShorebirdApr"]) == 4
        assert len(self.ccc["ShorebirdMar"]) == 4

    def test_get_ccc_value(self):
        # first non-zero day for Alfalfa on Poor soil is dowy95 (index 94)
        assert self.ccc["Alfalfa"]["Poor"][93] == 0
        assert self.ccc["Alfalfa"]["Poor"][94] == pytest.approx(0.5)
        assert self.ccc["Alfalfa"]["Poor"][95] == pytest.approx(0.43)
        assert len(self.ccc["Alfalfa"]["Poor"]) == 366

    def test_add_mlrp_fallow_copied_to_mlrp(self):
        mlrp = get_ccc.add_mlrp_to_ccc(self.ccc)
        assert mlrp["MLRP"] == mlrp["Fallow"]

    def test_add_mlrp_exception_if_no_fallow(self):
        del self.ccc["Fallow"]
        with pytest.raises(KeyError, match="Fallow crop type not found"):
            get_ccc.add_mlrp_to_ccc(self.ccc)


class TestGetILCCC:
    @pytest.fixture(autouse=True)
    def setup(self, oak_valley):
        self.il_ccc = get_ccc.get_il_crop_calendar(oak_valley / "CCC_inlieu.csv")
        self.multiplier_file = oak_valley / "CCC_inlieu_multiplier.csv"

    def test_il_crops(self):
        assert len(self.il_ccc) == 19
        assert "Wheat" not in self.il_ccc

    def test_il_regions(self):
        # regions are string keys
        assert sorted(self.il_ccc["Alfalfa"].keys()) == ["11", "12", "13", "8"]

    def test_il_length_with_leap_day(self):
        # the sample ends at dowy365, so dowy366 repeats it
        alfalfa = self.il_ccc["Alfalfa"]["8"]
        assert len(alfalfa) == 366
        assert alfalfa[365] == alfalfa[364]

    def test_il_value(self):
        # first non-zero day for Alfalfa in region 8 is dowy183 (April 1st)
        assert self.il_ccc["Alfalfa"]["8"][181] == 0
        assert self.il_ccc["Alfalfa"]["8"][182] == pytest.approx(0.169940647)

    def test_il_multiplier(self):
        multiplier_df = get_ccc.load_in_lieu_climate_multiplier(self.multiplier_file, "t5")
        assert len(multiplier_df) == 80  # 20 crops x 4 regions
        assert all(len(m) == 12 for m in multiplier_df["MonthlyMultiplier"])

    def test_il_multiplier_unknown_scenario(self):
        with pytest.raises(ValueError, match="Scenario T9 not found"):
            get_ccc.load_in_lieu_climate_multiplier(self.multiplier_file, "t9")

    def test_multiply_crop_calendar(self):
        multiplier_df = get_ccc.load_in_lieu_climate_multiplier(self.multiplier_file, "t5")
        il_multi = get_ccc.multiply_crop_calendar(self.il_ccc, multiplier_df)

        # Wheat has multipliers but no calendar, so it is dropped
        assert sorted(il_multi.keys()) == sorted(self.il_ccc.keys())
        # April multiplier for Alfalfa in region 8 is 1.1519
        assert il_multi["Alfalfa"]["8"][182] == pytest.approx(0.169940647 * 1.1519)


class TestGetCanals:
    @pytest.fixture(autouse=True)
    def setup(self, oak_valley):
        self.canal_csv = oak_valley / "canals.csv"
        self.canal_list = get_canals.load_canals(self.canal_csv)

    def test_number_of_canals(self):
        assert len(self.canal_list) == 1

    def test_perc_rate(self):
        assert self.canal_list[0].perc_rate == 8

    def test_name(self):
        assert self.canal_list[0].grat_id == "Oak Valley"
        assert self.canal_list[0].district == "Oak Valley"

    def test_subbasin(self):
        assert self.canal_list[0].subbasin == "North American"

    def test_wafr_sources(self):
        # WAFRSOURCE2 is empty in the sample
        assert self.canal_list[0].wafr_sources_primary == ["Folsom Lake"]
        assert self.canal_list[0].wafr_sources_secondary == []
        assert self.canal_list[0].wafr_sources == ["Folsom Lake"]

    def test_max_capacity(self):
        assert self.canal_list[0].max_capacity[0] == 0
        assert self.canal_list[0].max_capacity[30] == 0
        assert self.canal_list[0].max_capacity[31] == 300
        assert self.canal_list[0].max_capacity[170] == 300
        assert self.canal_list[0].max_capacity[182] == 0

    def test_custom_irrigation_days(self):
        canal_list = get_canals.load_canals(self.canal_csv, irrigation_days=[31])
        assert canal_list[0].max_capacity[0] == 300
        assert canal_list[0].max_capacity[31] == 0


class TestGetBottlenecks:
    @pytest.fixture(autouse=True)
    def setup(self, oak_valley):
        self.bottlenecks = get_bottlenecks.load_bottlenecks(oak_valley / "bottlenecks.csv")
        self.turlock = next(b for b in self.bottlenecks if b.name == "Turlock Main Canal")

    def test_get_bn(self):
        assert len(self.bottlenecks) == 19

    def test_ids(self):
        assert [b.bottleneck_id for b in self.bottlenecks] == list(range(19))

    def test_capacity(self):
        assert self.turlock.capacity == pytest.approx(356.94)  # 180 cfs x 1.983 acre-feet per day
        assert self.turlock.capacity_irrigation == pytest.approx(192.351)  # 97 cfs x 1.983 acre-feet per day

    def test_wafr_sources(self):
        canal_1 = next(b for b in self.bottlenecks if b.name == "Canal 1")
        assert self.turlock.wafr_sources == ["Folsom Lake"]
        assert canal_1.wafr_sources == ["Folsom Lake", "Yolo Creek"]

    def test_wafr_sources_match_wafr(self, oak_valley):
        # every bottleneck source must be a source in the WAFR sample
        wafr = get_wafr.load_wafr(oak_valley / "WAFR_optimistic.csv")
        wafr_sources = set(wafr[1969].keys())
        assert {s for b in self.bottlenecks for s in b.wafr_sources} <= wafr_sources

    def test_available_throughput_array(self):
        assert self.turlock.available_throughput[0] == pytest.approx(192.351)
        assert self.turlock.available_throughput[30] == pytest.approx(192.351)
        assert self.turlock.available_throughput[31] == pytest.approx(356.94)
        assert self.turlock.available_throughput[182] == pytest.approx(192.351)


class TestLoadSites:
    @pytest.fixture(autouse=True)
    def setup(self, oak_valley):
        self.shp = oak_valley / "oakvalley.shp"
        self.sites = get_sites.load_sites(self.shp)

    def test_number_of_sites(self):
        assert len(self.sites) == 685

    def test_fields(self):
        assert self.sites[0]["GRATID"] is not None
        assert "R_TYPE" in self.sites[0]

    def test_where(self):
        sites = get_sites.load_sites(self.shp, where="R_TYPE = 'OFR'")
        assert len(sites) == 682
        assert all(s["R_TYPE"] == "OFR" for s in sites)

    def test_ignore_and_rename_fields(self):
        sites = get_sites.load_sites(self.shp, ignore_fields=["Shape_Leng"], attribute_renamer={"GRATID": "grat_id"})
        assert "Shape_Leng" not in sites[0]
        assert "grat_id" in sites[0]
        assert "GRATID" not in sites[0]

    def test_csv_matches_shapefile(self, tmp_path):
        csv = tmp_path / "sites.csv"
        get_sites.read_attributes(self.shp).to_csv(csv, index=False)
        sites = get_sites.load_sites(csv)
        assert len(sites) == 685
        assert sites[0]["GRATID"] == self.sites[0]["GRATID"]

    def test_csv_where_error(self, tmp_path):
        with pytest.raises(ValueError, match="where is not supported for csv input"):
            get_sites.load_sites(tmp_path / "sites.csv", where="1=1")


class TestCCCMultiplier:
    def setup_method(self) -> None:
        # example on farm crop compatibility calendar
        self.e = [
            0.0601,
            0.0291,
            0.0273,
            0.0231,
            0.0223,
            0.003,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0037,
            0.0116,
            0.0141,
            0.0158,
            0.0181,
            0.0203,
            0.0208,
            0.0176,
            0.0185,
            0.0357,
            0.044,
            0.0457,
            0.0482,
            0.0617,
            0.1084,
            0.108,
            0.105,
            0.1017,
            0.1194,
            0.1241,
            0.1174,
            0.1139,
            0.1008,
            0.0821,
            0.0745,
            0.0714,
            0.0601,
            0.0291,
            0.0273,
            0.0231,
            0.0223,
            0.003,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0037,
            0.0116,
            0.0141,
            0.0158,
            0.0181,
            0.0203,
            0.0208,
            0.0176,
            0.0185,
            0.0357,
            0.044,
            0.0457,
            0.0482,
            0.0617,
            0.1084,
            0.108,
            0.105,
            0.1017,
            0.1194,
            0.1241,
            0.1174,
            0.1139,
            0.1008,
            0.0821,
            0.0745,
            0.0714,
            0.0601,
            0.0291,
            0.0273,
            0.0231,
            0.0223,
            0.003,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0037,
            0.0116,
            0.0141,
            0.0158,
            0.0181,
            0.0203,
            0.0208,
            0.0176,
            0.0185,
            0.0357,
            0.044,
            0.0457,
            0.0482,
            0.0617,
            0.1084,
            0.108,
            0.105,
            0.1017,
            0.1194,
            0.1241,
            0.1174,
            0.1139,
            0.1008,
            0.0821,
            0.0745,
            0.0714,
            0.0601,
            0.0291,
            0.0273,
            0.0231,
            0.0223,
            0.003,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0037,
            0.0116,
            0.0141,
            0.0158,
            0.0181,
            0.0203,
            0.0208,
            0.0176,
            0.0185,
            0.0357,
            0.044,
            0.0457,
            0.0482,
            0.0617,
            0.1084,
            0.108,
            0.105,
            0.1017,
            0.1194,
            0.1241,
            0.1174,
            0.1139,
            0.1008,
            0.0821,
            0.0745,
            0.0714,
            0.0601,
            0.0291,
            0.0273,
            0.0231,
            0.0223,
            0.003,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0037,
            0.0116,
            0.0141,
            0.0158,
            0.0181,
            0.0203,
            0.0208,
            0.0176,
            0.0185,
            0.0357,
            0.044,
            0.0457,
            0.0482,
            0.0617,
            0.1084,
            0.108,
            0.105,
            0.1017,
            0.1194,
            0.1241,
            0.1174,
            0.1139,
            0.1008,
            0.0821,
            0.0745,
            0.0714,
            0.0601,
            0.0291,
            0.0273,
            0.0231,
            0.0223,
            0.003,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0037,
            0.0116,
            0.0141,
            0.0158,
            0.0181,
            0.0203,
            0.0208,
            0.0176,
            0.0185,
            0.0357,
            0.044,
            0.0457,
            0.0482,
            0.0617,
            0.1084,
            0.108,
            0.105,
            0.1017,
            0.1194,
            0.1241,
            0.1174,
            0.1139,
            0.1008,
            0.0821,
            0.0745,
            0.0714,
            0.0601,
            0.0291,
            0.0273,
            0.0231,
            0.0223,
            0.003,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0037,
            0.0116,
            0.0141,
            0.0158,
            0.0181,
            0.0203,
            0.0208,
            0.0176,
            0.0185,
            0.0357,
            0.044,
            0.0457,
            0.0482,
            0.0617,
            0.1084,
            0.108,
            0.105,
            0.1017,
            0.1194,
            0.1241,
            0.1241,
        ]
        self.f = [1, 2, 3, 2, 1, 0, -1, 0, 1, 10, 20, 1]

    def test_multiply_month(self):
        m = get_ccc.multiply_by_monthly_factor(self.e, self.f)
        out = [
            0.601,
            0.29100000000000004,
            0.273,
            0.23099999999999998,
            0.223,
            0.03,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.037000000000000005,
            0.11599999999999999,
            0.141,
            0.15800000000000003,
            0.36200000000000004,
            0.40599999999999997,
            0.416,
            0.35200000000000004,
            0.37,
            0.7140000000000001,
            0.8799999999999999,
            0.9139999999999999,
            0.964,
            1.234,
            2.168,
            2.16,
            2.1,
            2.034,
            2.388,
            2.482,
            2.348,
            2.278,
            2.016,
            1.6420000000000001,
            1.49,
            1.4280000000000002,
            1.202,
            0.5820000000000001,
            0.546,
            0.46199999999999997,
            0.446,
            0.06,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0037,
            0.0116,
            0.0141,
            0.0158,
            0.0181,
            0.0203,
            0.0208,
            0.0176,
            0.0185,
            0.0357,
            0.044,
            0.0457,
            0.0482,
            0.0617,
            0.1084,
            0.108,
            0.105,
            0.1017,
            0.1194,
            0.1241,
            0.1174,
            0.1139,
            0.1008,
            0.0821,
            0.0745,
            0.0714,
            0.0601,
            0.0291,
            0.0273,
            0.0231,
            0.0223,
            0.003,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0074,
            0.0232,
            0.0282,
            0.0316,
            0.0362,
            0.0406,
            0.0416,
            0.0352,
            0.037,
            0.0714,
            0.088,
            0.0914,
            0.0964,
            0.1234,
            0.2168,
            0.216,
            0.21,
            0.2034,
            0.3582,
            0.3723,
            0.3522,
            0.3417,
            0.3024,
            0.24630000000000002,
            0.22349999999999998,
            0.2142,
            0.18030000000000002,
            0.0873,
            0.0819,
            0.0693,
            0.0669,
            0.009000000000000001,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0074,
            0.0232,
            0.0282,
            0.0316,
            0.0362,
            0.0406,
            0.0416,
            0.0352,
            0.037,
            0.0714,
            0.088,
            0.0914,
            0.0964,
            0.1234,
            0.2168,
            0.216,
            0.21,
            0.2034,
            0.2388,
            0.2482,
            0.2348,
            0.2278,
            0.2016,
            0.1642,
            0.149,
            0.1428,
            0.0601,
            0.0291,
            0.0273,
            0.0231,
            0.0223,
            0.003,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0037,
            0.0116,
            0.0141,
            0.0158,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0,
            -0.0037,
            -0.0116,
            -0.0141,
            -0.0158,
            -0.0181,
            -0.0203,
            -0.0208,
            -0.0176,
            -0.0185,
            -0.0357,
            -0.044,
            -0.0457,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0037,
            0.0116,
            0.0141,
            0.0158,
            0.0181,
            0.0203,
            0.0208,
            0.0176,
            0.0185,
            0.0357,
            0.044,
            0.0457,
            0.0482,
            0.0617,
            0.1084,
            0.108,
            0.105,
            0.1017,
            0.1194,
            0.1241,
            0.1241,
        ]

        assert m == out

    def test_multiply_month_error(self):
        with pytest.raises(ValueError, match="Length of monthly multipliers must be 12"):
            get_ccc.multiply_by_monthly_factor(self.e, [0, 1, 2])


class TestUnpackBottlenecks:
    def setup_method(self):
        self.bottleneck_info = [
            {
                "bid": 62,
                "name": "Planada Canal",
                "capacity_cfs": 250,
                "capacity_irr_cfs": 135,
                "wafrsource": "MercedRiver,UCC,UCC_L,Fahren,Bear",
            },
            {
                "bid": 63,
                "name": "Fairfield Canal",
                "capacity_cfs": 500,
                "capacity_irr_cfs": 287,
                "wafrsource": "MercedRiver,UCC,UCC_L,Fahren,Bear",
            },
        ]

    def test_unpack_bottlenecks(self):
        bottlenecks = get_bottlenecks.unpack_bottlenecks(self.bottleneck_info)
        assert len(bottlenecks) == 2
        assert bottlenecks[0].bottleneck_id == 62
        assert bottlenecks[1].bottleneck_id == 63
        assert bottlenecks[0].name == "Planada Canal"
        assert bottlenecks[1].name == "Fairfield Canal"

    def test_unpack_bottlenecks_capacity(self):
        bottlenecks = get_bottlenecks.unpack_bottlenecks(self.bottleneck_info)
        assert bottlenecks[0].capacity == 250 * 1.983
        assert bottlenecks[1].capacity == 500 * 1.983
        assert bottlenecks[0].capacity_irrigation == 135 * 1.983
        assert bottlenecks[1].capacity_irrigation == 287 * 1.983
