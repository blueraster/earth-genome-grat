from pathlib import Path

import pytest

from grat.loaders import (
    get_bottlenecks,
    get_canals,
    get_ccc,
    get_precip,
    get_wafr,
    helpers,
)

DATA_DIR = Path(__file__).parent / "data"

CCC_CROPS = [
    "Alfalfa",
    "Almonds",
    "Apples",
    "Cherries",
    "Citrus",
    "Corn",
    "Cotton",
    "Grapes",
    "Melons",
    "Olives",
    "Onions",
    "Pasture",
    "Peaches",
    "Pistachios",
    "Plums",
    "Rice",
    "Sweet Potato",
    "Tomatoes",
    "Walnuts",
    "Wheat",
]


class TestGetWAFR:
    @classmethod
    def setup_class(cls):
        # avoid loading the dataset for each test
        cls.d = get_wafr.load_wafr_csv(DATA_DIR / "WAFR_Input_Example.csv", offset_years=100)

    def test_get_wafr_type(self):
        assert isinstance(self.d, dict)

    def test_get_wafr_keys(self):
        assert list(self.d.keys()) == list(range(2000, 2100))

    def test_get_wafr_single_year_keys(self):
        source_keys = list(self.d[2098].keys())
        expected = [
            "Merced River",
            "Upper Canal Creek",
            "Upper Canal Livingston",
            "Fahrens Creek",
            "Bear Creek",
            "Mariposa Creek",
        ]
        assert sorted(source_keys) == sorted(expected)

    def test_get_wafr_length_yearly_array(self):
        assert len(self.d[2098]["Merced River"]) == 365

    def test_get_wafr_length_yearly_array_max_min(self):
        year_array = self.d[2098]["Merced River"]
        assert min(year_array) == 0
        assert max(year_array) == 3768.595041
        assert sum(year_array) / len(year_array) == pytest.approx(159.7817685, abs=1e-6)


class TestGetPrecip:
    @classmethod
    def setup_class(cls):
        # avoid loading the dataset for each test
        cls.precip_data = get_precip.get_precip(input_precip_file=DATA_DIR / "precip_100DP_0DT_00EX_110yr.csv")

    def test_get_precip_keys(self):
        assert set(range(2100, 2200)).issubset(self.precip_data.keys())

    def test_get_precip_length(self):
        assert len(self.precip_data[2103][1102]) == 365
        assert len(self.precip_data[2104][1510]) == 366


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


class TestGetCCC:
    def setup_method(self) -> None:
        self.file = DATA_DIR / "inlieu_CCC.csv"

    def test_ccc_valid_crops(self):
        ccc = get_ccc.get_crop_calendar(self.file)
        assert get_ccc.ccc_valid_crops(ccc) == CCC_CROPS

    def test_ccc_valid_soil_types(self):
        ccc = get_ccc.get_crop_calendar(self.file)
        soil_types = get_ccc.ccc_valid_soil_types(ccc)
        expected = ["Very Poor", "Poor", "Moderately Poor", "Moderately Good", "Good", "Excellent"]
        assert sorted(soil_types) == sorted(expected)

    def test_get_ccc_value(self):
        ccc = get_ccc.get_crop_calendar(self.file)
        assert ccc["Alfalfa"]["Poor"][5] == pytest.approx(0.008, abs=1e-4)
        assert len(ccc["Alfalfa"]["Poor"]) == 366

    def test_get_il_keys(self):
        ccc = get_ccc.get_crop_calendar(self.file)
        assert list(ccc.keys()) == CCC_CROPS

    def test_add_mlrp_fallow_copied_to_mlrp(self):
        ccc = get_ccc.get_crop_calendar(self.file)
        ccc["Fallow"] = {"A": "test", "B": "VALUES"}
        mlrp = get_ccc.add_mlrp_to_ccc(ccc)

        assert mlrp["MLRP"]["A"] == "test"
        assert mlrp["MLRP"]["B"] == "VALUES"

    def test_add_mlrp_exception_if_no_fallow(self):
        ccc = get_ccc.get_crop_calendar(self.file)
        with pytest.raises(KeyError, match="Fallow crop type not found"):  # no fallow in ccc
            get_ccc.add_mlrp_to_ccc(ccc)


class TestGetCanals:
    def setup_method(self) -> None:
        self.canal_list = get_canals.load_canals(DATA_DIR / "canals_example.csv")

    def test_number_of_canals(self):
        assert len(self.canal_list) == 2

    def test_perc_rate(self):
        assert self.canal_list[0].perc_rate == 600
        assert self.canal_list[1].perc_rate == 900

    def test_name(self):
        assert self.canal_list[0].grat_id == "Example 1"
        assert self.canal_list[1].grat_id == "Example 2"

    def test_wafr_sources(self):
        assert self.canal_list[0].wafr_sources == ["SourceA", "SourceB"]
        assert self.canal_list[1].wafr_sources_primary == ["SourceB"]
        assert self.canal_list[1].wafr_sources == ["SourceB", "SourceC"]

    def test_max_capacity(self):
        assert self.canal_list[0].max_capacity[0] == 0
        assert self.canal_list[0].max_capacity[170] == 10000
        assert self.canal_list[0].max_capacity[30] == 0
        assert self.canal_list[0].max_capacity[31] == 10000

    def test_custom_irrigation_days(self):
        canal_list = get_canals.load_canals(DATA_DIR / "canals_example.csv", irrigation_days=[31])
        assert canal_list[0].max_capacity[0] == 10000
        assert canal_list[0].max_capacity[31] == 0


class TestGetBottlenecks:
    def setup_method(self) -> None:
        self.bottlenecks = get_bottlenecks.load_bottlenecks(DATA_DIR / "bottlenecks.csv")
        self.goodwin = next(b for b in self.bottlenecks if b.name == "Goodwin Tunnel")

    def test_get_bn(self):
        assert len(self.bottlenecks) == 11

    def test_capacity(self):
        assert self.goodwin.capacity == 652.407  # 329 cfs x 1.983 acre-feet per day
        assert self.goodwin.capacity_irrigation == 3.966  # 2 cfs x 1.983 acre-feet per day

    def test_available_throughput_array(self):
        assert self.goodwin.available_throughput[0] == 3.966
        assert self.goodwin.available_throughput[30] == 3.966
        assert self.goodwin.available_throughput[31] == 652.407
        assert self.goodwin.available_throughput[182] == 3.966


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
