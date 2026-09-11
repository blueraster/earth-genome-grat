import copy
import logging

import pytest

from grat.model import bottlenecks, constants, engine, sites, sorters, utils
from grat.model.transfers import calc_transfer_limits


class TestBaseSite:
    def setup_method(self) -> None:
        self.bs = sites.BaseSite(grat_id=299, crop="Corn", acres=12.5, other="test")

    def test_set_daily_recharge(self):

        self.bs.set_daily_recharge(5, 12.13)
        self.bs.set_daily_recharge(5, 7.3)

        assert self.bs.daily_recharge_volumes[5] == 19.43

    def test_calc_precip(self):
        self.bs.precip_grid = "GRID444"
        precip_dict = {
            "GRID123": [1.2, 0, 0.22, 1.5, 0] * int(365 / 5),
            "GRID444": [0.1] * 365,
        }

        self.bs.calc_precip(precip_dict)  # daily values should be 1.25
        assert sum(self.bs.precip) == 456.25

        self.bs.precip_grid = "GRID123"
        self.bs.calc_precip(precip_dict)
        assert sum(self.bs.precip) == 2664.5

    def test_set_daily_recharge_leap_year(self):

        self.bs.set_daily_recharge(5, 12.13)
        self.bs.set_daily_recharge(364, 1.1)
        self.bs.set_daily_recharge(365, 5.02)
        assert sum(self.bs.daily_recharge_volumes) == 18.25

    def test_wafr_log(self):
        self.bs.set_wafr_log("Unit", 12.3)
        self.bs.set_wafr_log("Test", 33.2)
        self.bs.set_wafr_log("Test", 55)
        assert self.bs.wafr_log == {"Unit": 12.3, "Test": 88.2}


class TestBasin:
    def setup_method(self) -> None:
        self.b = sites.Basin(
            grat_id="unittest",
            crop="Perc Basin",
            acres=12.5,
            cost=12.4,
            perc_rate=120,
            max_capacity=50,
            cost_unused=1.25,
            bottleneck_ids=[2],
        )

    def test_update_daily_values(self):

        self.b.current_capacity = 200.2  # default on init is zero
        self.b.update_daily_values(0)

        assert self.b.current_capacity == pytest.approx(80.2, abs=0.005)

        self.b.update_daily_values(1)

        assert self.b.current_capacity == 0

        assert [round(elm, 2) for elm in list(self.b.daily_recharge_volumes)[0:2]] == [
            120,
            80.2,
        ]

    def test_get_site_volume(self):
        self.b.current_capacity = 89.12
        self.b.precip[10] = 20
        assert self.b.get_basin_volume_available(10) == pytest.approx(60.88, abs=0.005)

    def test_set_used_volume(self):
        self.b.current_capacity = 77.1
        self.b.set_used_volume(14, 12.89)
        assert self.b.used_volume[14] == 12.89
        assert self.b.current_capacity == 89.99

    def test_use_basin(self):
        self.b.wafr_sources_primary = ["B"]

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 9.2, 1]}

        # need bottleneck obj to mock
        bottleneck_list = [
            bottlenecks.Bottleneck(
                bottleneck_id=2,
                name="canal name",
                capacity=5.949,
                wafr_sources=["B"],
            )
        ]

        self.b.use_basin(1, wafr, bottleneck_list)
        wafr_applied = 5.949

        assert self.b.used_volume[1] == pytest.approx(wafr_applied)
        assert wafr["B"][1] == pytest.approx(9.2 - wafr_applied)

    def test_use_basin_multiple_wafr(self):
        self.b.wafr_sources_primary = ["B", "A", "C"]
        self.b.precip[1] = 2.5
        wafr = {"A": [1.3, 200, 3.5], "B": [4.2, 9.2, 1], "C": [4.2, 9.2, 1]}

        # need bottleneck obj to mock
        bottleneck_list = [
            bottlenecks.Bottleneck(
                bottleneck_id=2,
                name="canal name",
                capacity=5.949,
                wafr_sources=["B"],
            )
        ]

        self.b.use_basin(1, wafr, bottleneck_list)
        wafr_applied = 167.5

        assert self.b.used_volume[1] == pytest.approx(wafr_applied)

    def test_use_basin_transfer_limit_exhausted(self):
        self.b.wafr_sources_primary = ["B"]
        self.b.district = "D1"

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 9.2, 1]}

        bottleneck_list = [
            bottlenecks.Bottleneck(
                bottleneck_id=2,
                name="canal name",
                capacity=5.949,
                wafr_sources=["B"],
            )
        ]

        transfer_limits = {"D1": 0, "transfer_wafr_sources": {"D1": "B"}}

        self.b.use_basin(1, wafr, bottleneck_list, transfer_limits=transfer_limits)

        assert self.b.used_volume[1] == 0
        assert wafr["B"][1] == 9.2

    def test_use_basin_transfer_limit_not_exhausted(self):
        self.b.wafr_sources_primary = ["B"]
        self.b.district = "D1"

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 9.2, 1]}

        bottleneck_list = [
            bottlenecks.Bottleneck(
                bottleneck_id=2,
                name="canal name",
                capacity=5.949,
                wafr_sources=["B"],
            )
        ]

        transfer_limits = {"D1": 100, "transfer_wafr_sources": {"D1": "B"}}

        self.b.use_basin(1, wafr, bottleneck_list, transfer_limits=transfer_limits)
        wafr_applied = 5.949

        assert self.b.used_volume[1] == pytest.approx(wafr_applied)
        assert wafr["B"][1] == pytest.approx(9.2 - wafr_applied)
        assert transfer_limits["D1"] == pytest.approx(100 - wafr_applied)


class TestBottleneck:
    def setup_method(self) -> None:

        self.bottleneck_a = bottlenecks.Bottleneck(
            1, "test canal", 6.84135, wafr_sources=["SourceA"]
        )  # 6.84135 af per day
        self.bottleneck_b = bottlenecks.Bottleneck(
            2,
            "second canal",
            2.39943,
            capacity_irrigation=100,
            irrigation_days=[200, 201, 203, 204],
            wafr_sources=["SourceB"],
        )  # 2.39943 af per day

        self.bottleneck_list = [self.bottleneck_a, self.bottleneck_b]

    def test_update_usage(self):
        # init value is the acre-feet per day limit
        assert self.bottleneck_a.available_throughput[10] == pytest.approx(6.84, abs=0.005)

        # update usage
        self.bottleneck_a.update_usage(10, 2.22)
        assert self.bottleneck_a.available_throughput[10] == pytest.approx(4.62, abs=0.005)

    def test_get_available_throughput(self):
        t = self.bottleneck_a.get_available_throughput(15)
        assert t == pytest.approx(6.84, abs=0.005)

    def test_get_available_throughput_capacity_hit(self):
        # update usage
        self.bottleneck_a.update_usage(15, 19.1)
        t = self.bottleneck_a.get_available_throughput(15)
        assert t == 0

    def test_get_bottleneck_from_id_wafr(self):
        should_be_a = bottlenecks.get_bottlenecks(self.bottleneck_list, [1], "SourceA")[0]
        assert should_be_a.name == "test canal"

    def test_get_bottleneck_from_id_wafr2(self):
        should_be_b = bottlenecks.get_bottlenecks(self.bottleneck_list, [1, 2], "SourceB")[0]
        assert should_be_b.name == "second canal"

    def test_get_bottleneck_from_id_wafr_none(self):
        should_be_none = bottlenecks.get_bottlenecks(self.bottleneck_list, [2], "SourceA")
        assert should_be_none == []

    def test_bottleneck_capacity_log(self):
        self.bottleneck_a.update_usage(15, 19.1)
        self.bottleneck_a.update_usage(20, 50)
        self.bottleneck_b.update_usage(20, 20)
        self.bottleneck_b.update_usage(1, 50)

        cap_log = bottlenecks.bottleneck_capacity_logger(self.bottleneck_list)
        assert cap_log[15] == [1]
        assert cap_log[20] == [1, 2]
        assert cap_log[50] == []

    def test_get_available_throughput_irrigation_date(self):
        non_irr = self.bottleneck_b.get_available_throughput(199)
        assert non_irr == pytest.approx(2.39943, abs=0.005)
        irr = self.bottleneck_b.get_available_throughput(200)
        assert irr == pytest.approx(100, abs=0.005)


class TestCanalObject:
    def setup_method(self) -> None:

        self.c = sites.Canal(
            grat_id="Example 1",
            max_capacity=10000,
            perc_rate=600,
            wafr_sources=["SourceB"],
        )

    def test_canal_init(self):
        assert self.c.max_capacity[0] == 10000
        assert self.c.perc_rate == 600
        assert self.c.current_capacity == 0

    def test_set_daily_recharge(self):

        # test variables
        i = 18  # index day
        new_vol = 12.234

        # get current recharge volume (should be zero)
        assert self.c.daily_recharge_volumes[i] == 0

        # set to a new volume
        self.c.set_daily_recharge(i, new_vol)

        # check the new daily recharge volume
        assert self.c.daily_recharge_volumes[i] == new_vol

    def test_update_daily_recharge(self):

        # sets daily recharge to the min of the perc rate or current capacity
        # default perc rate = 600, curr_capacity = 0, so does this always return zero???
        i = 29  # index day

        # set daily recharge to a different value
        self.c.set_daily_recharge(i, 124.1931)

        # set curr capacity to a non-zero number
        self.c.current_capacity = 23.123
        self.c.update_daily_values(i)

        # check the new daily recharge volume
        assert self.c.daily_recharge_volumes[i] == 147.3161

    def test_update_usage(self):

        i = 48  # index day
        v = 19902.12  # value

        self.c.set_used_volume(i, v)

        # check the new daily recharge volume
        assert self.c.used_volume[i] == v

        # check the updated current capacity
        assert self.c.current_capacity == v

    def test_use_canal_below_cap(self):

        # not sure the structure of WAFR
        wafr = {"test_source": [3.4, 1.3, 9.23, 8.9, 999999]}

        self.c.wafr_sources = ["test_source"]

        # use canal when below cap
        i = 2
        self.c.use_canal(i, wafr, "test_source", 9.23)

        assert self.c.used_volume[i] == 9.23

    def test_use_canal_above_cap(self):

        # not sure the structure of WAFR
        wafr = {"test_source": [3.4, 1.3, 9.23, 8.9, 999999]}

        self.c.wafr_sources = ["test_source"]

        # use canal above cap
        i = 4
        self.c.use_canal(i, wafr, "test_source", 100000)
        assert self.c.used_volume[i] == 10600


class TestMockCanal:
    def setup_method(self) -> None:
        self.c = sites.Canal(
            grat_id="unit test canal",
            wafr_sources_primary=["source_A", "source_B"],
            max_capacity=10000,
            perc_rate=600,
        )

        self.wafr = {
            "source_A": [91.2, 74.1, 1.23, 192.3, 12023.2, 9.3, 8.12, 12.3],
            "source_B": [87.2, 6.23, 9.51, 891.3, 789, 5.3, 98.1, 5.6],
        }
        self.canal_list = [self.c]

    def test_use_canal(self):

        # loop through the days
        for i in range(0, 7):
            sites.fill_canals(self.canal_list, i, self.wafr)
            sites.canals_update_daily_values(self.canal_list, i)

        # use canal again
        sites.fill_canals(self.canal_list, 7, self.wafr)
        sites.canals_update_daily_values(self.canal_list, 7)

        assert list(self.c.used_volume)[0:8] == [
            178.4,
            80.33,
            10.74,
            1083.6,
            10116.4,
            14.600000000000001,
            106.22,
            17.9,
        ]
        assert list(self.c.daily_recharge_volumes)[0:8] == [
            178.4,
            80.33,
            10.74,
            600.0,
            600.0,
            600.0,
            600.0,
            600.0,
        ]


class TestMockCanalProportionalFill:
    def setup_method(self) -> None:
        self.A = sites.Canal(
            grat_id="canal A",
            wafr_sources_primary=["Blue Lake"],
            max_capacity=1000,
            perc_rate=600,
        )

        self.B = sites.Canal(
            grat_id="canal B",
            wafr_sources_primary=["Blue Lake", "Green Lake"],
            max_capacity=800,
            perc_rate=200,
        )

        self.C = sites.Canal(
            grat_id="canal C",
            wafr_sources_primary=["Blue Lake", "Green Lake"],
            max_capacity=1500,
            perc_rate=800,
        )

        self.wafr = {
            "Blue Lake": [2000, 4000, 10000, 0, 0, 0, 3000],
            "Green Lake": [0, 0, 0, 0, 0, 1600, 1600],
        }

        self.canal_list = [self.A, self.B, self.C]

        # loop through the days
        for i in range(0, 7):
            sites.fill_canals(self.canal_list, i, self.wafr)
            sites.canals_update_daily_values(self.canal_list, i)

    def test_use_canal_wafr(self):

        assert self.wafr == {
            "Blue Lake": [0.0, 0.0, 7900.000000000001, 0, 0, 0, 0.0],
            "Green Lake": [0, 0, 0, 0, 0, 0.0, 1069.2307692307693],
        }

    def test_use_canal_used_volume(self):

        assert sum(self.A.used_volume[0:7]) == pytest.approx(4030.77, abs=0.005)
        assert sum(self.B.used_volume[0:7]) == pytest.approx(2200.0, abs=0.005)
        assert sum(self.C.used_volume[0:7]) == pytest.approx(7000.0, abs=0.005)

    def test_use_canal_daily_recharge_volume(self):

        assert sum(self.A.daily_recharge_volumes[0:7]) == pytest.approx(3400, abs=0.005)
        assert sum(self.B.daily_recharge_volumes[0:7]) == pytest.approx(1400, abs=0.005)
        assert sum(self.C.daily_recharge_volumes[0:7]) == pytest.approx(5500.0, abs=0.005)

    def test_use_canal_current_capacity(self):

        assert self.A.current_capacity == pytest.approx(630.77, abs=0.005)
        assert self.B.current_capacity == pytest.approx(800, abs=0.005)
        assert self.C.current_capacity == pytest.approx(1500.0, abs=0.005)


class TestMockCanalProportional:
    def setup_method(self) -> None:
        self.A = sites.Canal(
            grat_id="canal A",
            wafr_sources_primary=["Blue Lake"],
            max_capacity=10,
            perc_rate=5,
        )
        self.B = sites.Canal(
            grat_id="canal B",
            wafr_sources_primary=["Blue Lake", "Red Lake"],
            max_capacity=10,
            perc_rate=5,
        )
        self.C = sites.Canal(
            grat_id="canal C",
            wafr_sources_primary=["Red Lake"],
            max_capacity=10,
            perc_rate=5,
        )

        self.wafr = {
            "Blue Lake": [100, 0, 0, 0, 0, 0, 0, 0],
            "Red Lake": [8, 10, 0, 0, 0, 0, 0, 0],
        }

        self.canal_list = [self.A, self.B, self.C]

        # loop through the days
        for i in range(0, 2):
            sites.fill_canals(self.canal_list, i, self.wafr)
            sites.canals_update_daily_values(self.canal_list, i)

    def test_use_canal_day1(self):

        assert self.A.used_volume[0] == pytest.approx(15, abs=0.005)
        assert self.B.used_volume[0] == pytest.approx(15, abs=0.005)
        assert self.C.used_volume[0] == pytest.approx(8, abs=0.005)

        assert self.A.daily_recharge_volumes[0] == pytest.approx(5, abs=0.005)
        assert self.B.daily_recharge_volumes[0] == pytest.approx(5, abs=0.005)
        assert self.C.daily_recharge_volumes[0] == pytest.approx(5, abs=0.005)

        assert self.wafr["Blue Lake"][0] == pytest.approx(70, abs=0.005)
        assert self.wafr["Red Lake"][0] == pytest.approx(0, abs=0.005)

    def test_use_canal_day2(self):
        assert self.A.used_volume[1] == pytest.approx(0, abs=0.005)
        assert self.B.used_volume[1] == pytest.approx(2.94, abs=0.005)
        assert self.C.used_volume[1] == pytest.approx(7.06, abs=0.005)

        assert self.A.daily_recharge_volumes[1] == pytest.approx(5, abs=0.005)
        assert self.B.daily_recharge_volumes[1] == pytest.approx(5, abs=0.005)
        assert self.C.daily_recharge_volumes[1] == pytest.approx(5, abs=0.005)

        assert self.wafr["Blue Lake"][1] == pytest.approx(0, abs=0.005)
        assert self.wafr["Red Lake"][1] == pytest.approx(0, abs=0.005)

    def test_canal_fed_by(self):
        assert self.A.wafr_log["Blue Lake"] == 15
        assert self.B.wafr_log["Red Lake"] == 2.9411764705882355
        assert self.B.wafr_log["Blue Lake"] == 15
        assert self.C.wafr_log["Red Lake"] == 8.0 + 7.058823529411765


class TestMockCanalProportionalWafrOrder:
    def setup_method(self) -> None:
        self.A = sites.Canal(
            grat_id="canal A",
            wafr_sources_primary=["Blue Lake"],
            max_capacity=10,
            perc_rate=5,
        )
        self.B = sites.Canal(
            grat_id="canal B",
            wafr_sources_primary=["Blue Lake", "Red Lake"],
            max_capacity=10,
            perc_rate=5,
        )
        self.C = sites.Canal(
            grat_id="canal C",
            wafr_sources_primary=["Red Lake"],
            max_capacity=10,
            perc_rate=5,
        )

        self.wafr = {
            "Blue Lake": [100, 0, 0, 0, 0, 0, 0, 0],
            "Red Lake": [8, 10, 0, 0, 0, 0, 0, 0],
        }

        self.canal_list = [self.A, self.B, self.C]

        # loop through the days
        for i in range(0, 2):
            sites.fill_canals(self.canal_list, i, self.wafr)
            sites.canals_update_daily_values(self.canal_list, i)

    def test_use_canal_day1(self):

        assert self.A.used_volume[0] == pytest.approx(15, abs=0.005)
        assert self.B.used_volume[0] == pytest.approx(15, abs=0.005)
        assert self.C.used_volume[0] == pytest.approx(8, abs=0.005)

        assert self.A.daily_recharge_volumes[0] == pytest.approx(5, abs=0.005)
        assert self.B.daily_recharge_volumes[0] == pytest.approx(5, abs=0.005)
        assert self.C.daily_recharge_volumes[0] == pytest.approx(5, abs=0.005)

    def test_use_canal_day2(self):
        assert self.A.used_volume[1] == pytest.approx(0, abs=0.005)
        assert self.B.used_volume[1] == pytest.approx(2.941, abs=0.005)
        assert self.C.used_volume[1] == pytest.approx(7.058, abs=0.005)

        assert self.A.daily_recharge_volumes[1] == pytest.approx(5, abs=0.005)
        assert self.B.daily_recharge_volumes[1] == pytest.approx(5, abs=0.005)
        assert self.C.daily_recharge_volumes[1] == pytest.approx(5, abs=0.005)


class TestOFR:
    def setup_method(self) -> None:
        self.ofr = sites.Farm(
            grat_id="Unittest",
            crop="Corn",
            acres=10.2,
            soil_type="Good",
            cfs_limit=100,
            bottleneck_ids=[2],
        )
        self.crop_calendar = {"Corn": {"Good": [4.12, 4.12]}}

        self.bottleneck_list = [
            bottlenecks.Bottleneck(
                bottleneck_id=2,
                name="canal name",
                capacity=5.949,
                wafr_sources=["B"],
            )
        ]

    def test_get_site_volume(self):

        assert self.ofr.get_site_volume(0, self.crop_calendar) == 42.024

    def test_use_site(self):

        self.ofr.wafr_sources_primary = ["B"]

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 9.2, 1]}

        self.ofr.precip[1] = 2.1

        self.ofr.use_site(
            1,
            wafr,
            self.bottleneck_list,
            crop_calendar=self.crop_calendar,
        )
        wafr_applied = 5.949

        assert self.ofr.ofr_used_volume[1] == pytest.approx(wafr_applied)
        assert self.ofr.ofr_unused_volume[1] == pytest.approx(33.975)
        assert wafr["B"][1] == pytest.approx(9.2 - wafr_applied)

    def test_use_site_transfer_limit_exhausted(self):
        self.ofr.wafr_sources_primary = ["B"]
        self.ofr.district = "D1"

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 9.2, 1]}
        self.ofr.precip[1] = 2.1

        transfer_limits = {"D1": 0, "transfer_wafr_sources": {"D1": "B"}}

        self.ofr.use_site(
            1,
            wafr,
            self.bottleneck_list,
            crop_calendar=self.crop_calendar,
            transfer_limits=transfer_limits,
        )

        assert self.ofr.ofr_used_volume[1] == 0
        assert wafr["B"][1] == 9.2

    def test_use_site_transfer_limit_not_exhausted(self):
        self.ofr.wafr_sources_primary = ["B"]
        self.ofr.district = "D1"

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 9.2, 1]}
        self.ofr.precip[1] = 2.1

        transfer_limits = {"D1": 100, "transfer_wafr_sources": {"D1": "B"}}

        self.ofr.use_site(
            1,
            wafr,
            self.bottleneck_list,
            crop_calendar=self.crop_calendar,
            transfer_limits=transfer_limits,
        )
        wafr_applied = 5.949

        assert self.ofr.ofr_used_volume[1] == pytest.approx(wafr_applied)
        assert wafr["B"][1] == pytest.approx(9.2 - wafr_applied)
        assert transfer_limits["D1"] == pytest.approx(100 - wafr_applied)


class TestModelMainRun:
    def setup_method(self) -> None:
        self.canal1 = sites.Canal(
            grat_id="test",
            wafr_sources_primary=["A", "B"],
            max_capacity=10000,
            perc_rate=600,
            recharge_type="Canal",
        )
        self.site1 = sites.Farm(
            grat_id=299,
            crop="Corn",
            acres=12.5,
            recharge_type="On-Farm Recharge",
            soil_type="Good",
            cfs_limit=5 / 1.983,
            bottleneck_ids=[2],
            wafr_sources_primary=["B"],
        )
        self.site2 = sites.Farm(
            grat_id=9,
            crop="Wheat",
            acres=2.5,
            recharge_type="On-Farm Recharge",
            soil_type="Good",
            cfs_limit=5 / 1.983,
            bottleneck_ids=[2],
            wafr_sources_primary=["A"],
        )
        self.site3 = sites.Basin(
            grat_id=33,
            acres=2.5,
            recharge_type="Basin",
            perc_rate=1.2,
            max_capacity=100,
            bottleneck_ids=[1],
            wafr_sources_primary=["A"],
        )
        self.site_list = [self.canal1, self.site3, self.site1, self.site2]

        self.wafr = {"A": [20000.3, 20000, 20000], "B": [4.2, 9.2, 1]}

        # need bottleneck obj to mock

        self.bottleneck_list = [
            bottlenecks.Bottleneck(
                bottleneck_id=1,
                name="canal name",
                capacity=595.037759907,
                wafr_sources=["A"],
            ),
            bottlenecks.Bottleneck(
                bottleneck_id=2,
                name="canal name",
                capacity=595.037759907,
                wafr_sources=["B"],
            ),
        ]

        self.crop_calendar = {
            "Corn": {"Good": {0: 4.12, 1: 4.12, 2: 4.12}},
            "Wheat": {"Good": {0: 4.12, 1: 4.12, 2: 4.12}},
        }

    def test_run_grat_wafr(self):
        r = engine.process_year(
            self.site_list,
            self.bottleneck_list,
            self.wafr,
            self.crop_calendar,
            precip=None,
        )

        assert r["wafr"] == {
            "A": [9294.099999999999, 19393.8, 19393.8],
            "B": [0.0, 4.199999999999999, 0],
        }

    def test_run_grat_canals(self):
        r = engine.process_year(
            self.site_list,
            self.bottleneck_list,
            self.wafr,
            self.crop_calendar,
            precip=None,
        )

        assert sum(r["sites"][0].daily_recharge_volumes) == 1800.0

    def test_run_grat_sites(self):
        r = engine.process_year(
            self.site_list,
            self.bottleneck_list,
            self.wafr,
            self.crop_calendar,
            precip=None,
        )

        # basin 1.2 perc rate x 3 days
        assert sum(r["sites"][1].daily_recharge_volumes) == pytest.approx(3.6)
        # site 1 [4.2, 5. , 1.]
        assert sum(r["sites"][2].ofr_daily_recharge_volumes) == pytest.approx(10.2)


class TestModelMainRunMultiYear:
    def setup_method(self) -> None:
        self.canal1 = sites.Canal(
            grat_id="test",
            wafr_sources=["A", "B"],
            max_capacity=10000,
            perc_rate=600,
            recharge_type="Canal",
        )

        self.site1 = sites.Farm(
            grat_id=299,
            crop="Corn",
            acres=12.5,
            recharge_type="OFR",
            soil_type="Good",
            cfs_limit=5 / 1.983,
            bottleneck_ids=2,
            wafr_sources=["B"],
        )
        self.site2 = sites.Farm(
            grat_id=9,
            crop="Wheat",
            acres=2.5,
            recharge_type="OFR",
            soil_type="Good",
            cfs_limit=5 / 1.983,
            bottleneck_ids=2,
            wafr_sources=["A"],
        )
        self.site3 = sites.Basin(
            grat_id=33,
            acres=2.5,
            recharge_type="Basin",
            perc_rate=1.2,
            max_capacity=100,
            bottleneck_ids=2,
            wafr_sources=["A"],
        )
        self.site_list = [self.canal1, self.site3, self.site1, self.site2]

        self.wafr = {"A": [20000.3, 20000, 20000], "B": [4.2, 9.2, 1]}
        self.wafr2 = {"A": [20000.3, 19.1, 20000], "B": [4.2, 9.2, 1]}

        # need bottleneck obj to mock
        self.bottleneck_list = [
            bottlenecks.Bottleneck(
                bottleneck_id=2,
                name="canal name",
                capacity=595.03775990781,
            )
        ]

        self.crop_calendar = {
            "Corn": {"Good": {0: 4.12, 1: 4.12, 2: 4.12}},
            "Wheat": {"Good": {0: 4.12, 1: 4.12, 2: 4.12}},
        }

    def test_process_year(self):

        sites2 = copy.deepcopy(self.site_list)
        bottleneck_list2 = copy.deepcopy(self.bottleneck_list)

        year_1 = engine.process_year(
            self.site_list,
            self.bottleneck_list,
            self.wafr,
            self.crop_calendar,
            precip=None,
        )

        year_2 = engine.process_year(sites2, bottleneck_list2, self.wafr2, self.crop_calendar, precip=None)

        # years should not be equal
        assert year_1["sites"] != year_2["sites"]


class TestSorters:
    def setup_method(self) -> None:
        class SorterExample:
            def __init__(self, grat_id, acres, recharge_type, rsi=0, scenario_a=None):
                self.grat_id = grat_id
                self.acres = acres
                self.recharge_type = recharge_type
                self.rsi = rsi
                self.scenario_a = scenario_a

            def __repr__(self):
                return f"{self.grat_id}"

        a = SorterExample("A", 10.2, "OFR", rsi=77, scenario_a=None)
        b = SorterExample("B", 12.2, "OFR", rsi=23, scenario_a="Z")
        c = SorterExample("C", 1.2, "Basin", rsi=50, scenario_a="A")
        d = SorterExample("D", 13.2, None, rsi=7, scenario_a="Z")
        e = SorterExample("E", 12.2, "OFR", rsi=19, scenario_a="A")

        self.listofsites = [a, b, c, d, e]

    def test_sort_by_type(self):
        s = self.listofsites.copy()
        s.sort(key=sorters.recharge_type_order)
        site_order = [o.grat_id for o in s]
        assert site_order == ["C", "A", "B", "E", "D"]

    def test_sort_by_variable(self):
        s = sorters.sort_by_variable(self.listofsites, "acres")
        site_order = [o.grat_id for o in s]
        assert site_order == ["C", "A", "B", "E", "D"]

    def test_sort_by_variable2(self):

        s = sorters.sort_by_variable(self.listofsites, "rsi", True)
        site_order = [o.grat_id for o in s]
        assert site_order == ["A", "C", "B", "E", "D"]

    def test_sort_by_multi_variable(self):

        s = sorters.sort_by_variables(self.listofsites, (("acres", True), ("rsi", True)))
        site_order = [o.grat_id for o in s]
        assert site_order == ["D", "B", "E", "A", "C"]

    def test_sort_sites_basic(self):

        s = sorters.sort_sites(self.listofsites, sort_rule=None)
        site_order = [o.grat_id for o in s]
        assert site_order == ["C", "A", "B", "E", "D"]

    def test_sort_sites_scenario_a(self):

        s = sorters.sort_sites(self.listofsites, sort_rule="A")
        site_order = [o.grat_id for o in s]
        assert site_order == ["C", "B", "E", "A", "D"]


class TestSortersCanals:
    def setup_method(self) -> None:
        class SorterExample:
            def __init__(self, grat_id, acres, recharge_type, index=0, scenario_a=None):
                self.grat_id = grat_id
                self.acres = acres
                self.recharge_type = recharge_type
                self.index = index
                self.scenario_a = scenario_a

            def __repr__(self):
                return f"{self.grat_id}"

        a = SorterExample("A", 0, "Canal", index=77, scenario_a=None)
        b = SorterExample("B", 12.2, "OFR", index=23, scenario_a="Z")
        c = SorterExample("C", 1.2, "Basin", index=50, scenario_a="A")
        d = SorterExample("D", 0, "Canal", index=50, scenario_a="A")
        e = SorterExample("E", 15, "OFR", index=50, scenario_a="A")

        self.listofsites = [a, b, c, d, e]

    def test_sort_by_type(self):
        s = self.listofsites.copy()
        s.sort(key=sorters.recharge_type_order)
        site_order = [o.grat_id for o in s]
        assert site_order == ["A", "D", "C", "B", "E"]

    def test_sort_type_by_variable(self):
        s = sorters.sort_by_variable(self.listofsites, "acres", reverse=True)
        s.sort(key=sorters.recharge_type_order)
        site_order = [o.grat_id for o in s]
        assert site_order == ["A", "D", "C", "E", "B"]


class TestSortersInLieu:
    def setup_method(self) -> None:
        class SorterExample:
            def __init__(
                self,
                grat_id,
                acres,
                recharge_type,
                index=0,
                scenario_a=None,
                groundwater_change=0,
                crop=None,
                in_lieu_crop=None,
                rma=None,
            ):
                self.grat_id = grat_id
                self.acres = acres
                self.recharge_type = recharge_type
                self.index = index
                self.scenario_a = scenario_a
                self.groundwater_change = groundwater_change
                self.crop = crop
                self.in_lieu_crop = in_lieu_crop
                self.rma = rma

            def __repr__(self):
                return f"{self.grat_id}"

        a = SorterExample(
            "A",
            0,
            "OFR",
            index=77,
            groundwater_change=10,
            in_lieu_crop="Corn",
            crop="Apple",
            rma=2,
        )
        b = SorterExample("B", 12.2, "OFR", index=23, groundwater_change=5, crop="Apple", rma=1)
        c = SorterExample("C", 1.2, "OFR", index=50, groundwater_change=-10, in_lieu_crop="Corn", rma=1)
        d = SorterExample(
            "D",
            0,
            "OFR",
            index=50,
            groundwater_change=-5,
            in_lieu_crop="Corn",
            crop="Apple",
            rma=2,
        )
        e = SorterExample("E", 15, "OFR", index=50, groundwater_change=2, in_lieu_crop="Corn")

        self.listofsites = [a, b, c, d, e]

    def test_sort_in_lieu(self):
        _, sites_il, _, _ = sorters.group_sites_by_recharge_type(self.listofsites, rma_sort=False)
        site_order = [o.grat_id for o in sites_il]
        assert site_order == ["C", "D", "E", "A"]

    def test_sort_in_lieu_rma(self):
        _, sites_il, _, _ = sorters.group_sites_by_recharge_type(self.listofsites, rma_sort=True)
        site_order = [o.grat_id for o in sites_il]
        assert site_order == ["C", "D", "A", "E"]


class TestIL:
    def setup_method(self) -> None:
        self.il = sites.Farm(
            grat_id="Unittest",
            crop="Corn",
            acres=10.2,
            soil_type="Good",
            cfs_limit=100 / 1.983,
            bottleneck_ids=[2],
            in_lieu_crop="Grapes",
            region_number=1,
        )
        self.crop_calendar = {
            "Corn": {"Good": [55.1, 12.4]},
        }

        self.in_lieu_crop_calendar = {
            "Grapes": {"1": [4.12, 4.12]},
        }

        self.bottleneck_list = [
            bottlenecks.Bottleneck(bottleneck_id=2, name="canal name", capacity=1000, wafr_sources=["A"])
        ]

    def test_get_site_volume(self):

        assert self.il.get_site_volume(0, self.in_lieu_crop_calendar, in_lieu=True) == 42.024

    def test_use_site(self):

        self.il.wafr_sources_primary = ["B"]

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 1000, 1]}
        self.il.precip[1] = 2.1
        self.il.use_site(
            1,
            wafr,
            self.bottleneck_list,
            crop_calendar=self.in_lieu_crop_calendar,
            in_lieu=True,
        )

        # should not modify used/unused volume
        assert self.il.used_volume[1] == pytest.approx(0)

        # modify the in-lieu variables
        assert self.il.in_lieu_used_volume[1] == pytest.approx(39.924)
        assert self.il.in_lieu_unused_volume[1] == pytest.approx(0)

    def test_use_site_twice(self):

        self.il.wafr_sources_primary = ["B"]
        self.il.flow_limit = [1000, 1000]

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 1000, 1]}

        self.il.precip[0] = 2.1
        self.il.precip[1] = 2.1

        self.il.use_site(
            1,
            wafr,
            self.bottleneck_list,
            crop_calendar=self.in_lieu_crop_calendar,
            in_lieu=True,
        )

        self.il.use_site(
            1,
            wafr,
            self.bottleneck_list,
            crop_calendar=self.crop_calendar,
            in_lieu=False,
        )

        # check the in-lieu variables
        # in_lieu potential
        # acres x il ccc - precip
        # (10.2 x 4.12) - 2.1
        assert self.il.in_lieu_used_volume[1] == pytest.approx(39.924)
        assert self.il.in_lieu_unused_volume[1] == pytest.approx(0)

        # should be not impacted by precip
        # acres x ofr ccc
        # 10.2*12.4 = 126.48
        assert self.il.ofr_used_volume[1] == pytest.approx(126.48)
        assert self.il.ofr_unused_volume[1] == pytest.approx(0)

    def test_use_site_twice_turnout(self):

        self.il.wafr_sources_primary = ["B"]

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 1000, 1]}

        self.il.precip[1] = 0

        self.il.use_site(
            1,
            wafr,
            self.bottleneck_list,
            crop_calendar=self.in_lieu_crop_calendar,
            in_lieu=True,
        )

        self.il.use_site(
            1,
            wafr,
            self.bottleneck_list,
            crop_calendar=self.crop_calendar,
            in_lieu=False,
        )

        # check the in-lieu variables
        assert self.il.in_lieu_used_volume[1] == pytest.approx(42.024)
        assert self.il.in_lieu_unused_volume[1] == pytest.approx(0)

        assert self.il.ofr_used_volume[1] == pytest.approx(100 - 42.024)
        # assert self.il.unused_volume[1] == pytest.approx(42.024)


class TestWafrSortOrder:
    def setup_method(self) -> None:
        self.wafr = {"SourceB": [50, 12000], "SourceA": [19, 300000]}

    def test_day0(self):
        assert utils.sort_wafr_source_by_volume(self.wafr, 0) == ["SourceB", "SourceA"]

    def test_day1(self):
        assert utils.sort_wafr_source_by_volume(self.wafr, 1) == ["SourceA", "SourceB"]


class TestWafrAvailability:
    def setup_method(self) -> None:
        self.wafr = {"SourceB": [50, 12000, 0, 0], "SourceA": [19, 300000, 0, 1]}

    def test_day0(self):
        assert utils.check_wafr_availability(self.wafr, 0)

    def test_day2(self):
        assert not utils.check_wafr_availability(self.wafr, 2)


class TestGetCompatibleCrops:
    def setup_method(self) -> None:
        self.ccc = {
            "Corn": {"Poor": [0, 1.2, 3, 0], "Good": [3, 0, 1, 0]},
            "Rice": {"Great": [0, 0, 1.2, 0], "Good": [0, 2.1, 0, 0]},
        }

    def test_day0(self):
        assert utils.get_compatible_crops_soils_for_day(self.ccc, 0) == [("Corn", "Good")]

    def test_day1(self):
        assert utils.get_compatible_crops_soils_for_day(self.ccc, 1) == [
            ("Corn", "Poor"),
            ("Rice", "Good"),
        ]

    def test_day2(self):
        assert utils.get_compatible_crops_soils_for_day(self.ccc, 2) == [
            ("Corn", "Poor"),
            ("Corn", "Good"),
            ("Rice", "Great"),
        ]

    def test_day3(self):
        assert utils.get_compatible_crops_soils_for_day(self.ccc, 3) == []

    def test_none_sort_rule(self):
        assert utils.get_compatible_crops_soils_for_day(None, 2) == []


class TestModelMainRunSecondaryWafr:
    def setup_method(self) -> None:
        self.canal1 = sites.Canal(
            grat_id="test",
            wafr_sources_primary=["A", "B"],
            max_capacity=10000,
            perc_rate=600,
            recharge_type="Canal",
        )
        self.site1 = sites.Farm(
            grat_id=299,
            crop="Corn",
            acres=12.5,
            recharge_type="On-Farm Recharge",
            soil_type="Good",
            cfs_limit=5 / 1.983,
            bottleneck_ids=[2],
            wafr_sources_primary=["B"],
            wafr_sources_secondary=["A"],
        )
        self.site2 = sites.Farm(
            grat_id=9,
            crop="Wheat",
            acres=2.5,
            recharge_type="On-Farm Recharge",
            soil_type="Good",
            cfs_limit=5 / 1.983,
            bottleneck_ids=[2],
            wafr_sources_primary=["A"],
            wafr_sources_secondary=["B"],
        )
        self.site3 = sites.Basin(
            grat_id=33,
            acres=2.5,
            recharge_type="Basin",
            perc_rate=1.2,
            max_capacity=100,
            bottleneck_ids=[2],
            wafr_sources_primary=["A"],
            wafr_sources_secondary=["B"],
        )
        self.site_list = [self.canal1, self.site3, self.site1, self.site2]
        self.wafr = {"A": [20000.3, 20000, 20000], "B": [4.2, 9.2, 1]}

        # need bottleneck obj to mock
        self.bottleneck_list = [
            bottlenecks.Bottleneck(
                bottleneck_id=2,
                name="canal name",
                capacity=595.037759907,
                wafr_sources=["A"],
            ),
            bottlenecks.Bottleneck(
                bottleneck_id=2,
                name="canal name",
                capacity=595.037759907,
                wafr_sources=["B"],
            ),
        ]

        self.crop_calendar = {
            "Corn": {"Good": {0: 4.12, 1: 4.12, 2: 4.12}},
            "Wheat": {"Good": {0: 4.12, 1: 4.12, 2: 4.12}},
        }

    def test_run_grat_wafr(self):
        r = engine.process_year(
            self.site_list,
            self.bottleneck_list,
            self.wafr,
            self.crop_calendar,
            precip=None,
        )

        assert r["wafr"] == {
            "A": [9294.099999999999 - 0.8, 19393.8, 19393.8 - 4],
            "B": [0.0, 4.199999999999999, 0],
        }

    def test_run_grat_canals(self):
        r = engine.process_year(
            self.site_list,
            self.bottleneck_list,
            self.wafr,
            self.crop_calendar,
            precip=None,
        )

        assert sum(r["sites"][0].daily_recharge_volumes) == 1800.0

    def test_run_grat_sites(self):
        r = engine.process_year(
            self.site_list,
            self.bottleneck_list,
            self.wafr,
            self.crop_calendar,
            precip=None,
        )

        # basin 1.2 perc rate x 3 days
        assert sum(r["sites"][1].daily_recharge_volumes) == pytest.approx(3.6)
        # site 1 [4.2, 5. , 1.]
        assert sum(r["sites"][2].ofr_daily_recharge_volumes) == pytest.approx(15)


class TestSubsetSiteList:
    def setup_method(self) -> None:
        self.wafr = {
            "CalDuck": [10, 0, 0, 0, 10, 20, 10, 0],
            "Calaveras": [
                0,
                0,
                0,
                0,
                150,
                300,
                150,
                0,
            ],
            "Duck": [0, 0, 0, 0, 66, 132, 66, 0],
        }

    def test_get_wafr_sources_with_water(self):
        assert utils.sort_wafr_source_by_volume(self.wafr, 0) == ["CalDuck"]
        assert utils.sort_wafr_source_by_volume(self.wafr, 1) == []
        assert utils.sort_wafr_source_by_volume(self.wafr, 4) == [
            "Calaveras",
            "Duck",
            "CalDuck",
        ]


class TestTurnoutLimitConversion:
    def test_cfs_to_acre_feet_per_day_with_valid_input(self):
        cfs_rate = 20
        expected_output = 39.66
        assert sites.turnout_limit_conversion(cfs_rate) == pytest.approx(expected_output, abs=0.005)


class TestDailyArrayLength:
    """Every daily array is sized for a leap year so no day index can overflow."""

    def test_site_arrays_cover_a_leap_year(self):
        site = sites.Farm(grat_id="f", soil_type="Good", cfs_limit=5, crop="Corn", acres=1)
        for attr in (
            "used_volume",
            "daily_recharge_volumes",
            "precip",
            "flow_limit",
            "ofr_used_volume",
            "in_lieu_used_volume",
            "used_precip",
        ):
            assert len(getattr(site, attr)) == constants.DAYS_PER_WATER_YEAR

    def test_bottleneck_throughput_covers_a_leap_year(self):
        b = bottlenecks.Bottleneck(bottleneck_id=1, capacity=10.0, wafr_sources=["A"])
        assert len(b.available_throughput) == constants.DAYS_PER_WATER_YEAR

    def test_capacity_log_covers_final_day_of_a_leap_year(self):
        """A limit hit on day 365 used to raise IndexError: the log held only 365 days."""
        b = bottlenecks.Bottleneck(bottleneck_id=7, capacity=0.0, wafr_sources=["A"])

        cap_log = bottlenecks.bottleneck_capacity_logger([b])

        assert len(cap_log) == constants.DAYS_PER_WATER_YEAR
        assert cap_log[constants.DAYS_PER_WATER_YEAR - 1] == [7]


class TestSortRuleValidation:
    def test_unknown_sort_rule_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown sort rule"):
            sorters.sort_sites([], sort_rule="not-a-rule")


class TestUseSiteMissingWafrSource:
    def test_source_absent_from_wafr_is_treated_as_empty(self):
        """A site naming a source the WAFR dictionary lacks takes no water, and does not raise."""
        site = sites.Farm(
            grat_id="f",
            soil_type="Good",
            cfs_limit=5,
            crop="Corn",
            acres=10,
            wafr_sources_primary=["Missing"],
        )
        crop_calendar = {"Corn": {"Good": {0: 4.12}}}

        site.use_site(0, {"Present": [100.0]}, [], crop_calendar)

        assert site.ofr_used_volume[0] == 0
        assert site.wafr_log == {}


class TestCalcTransferLimits:
    def setup_method(self) -> None:
        self.wafr = {"A": [10, 20, 30], "B": [1, 2, 3]}
        self.transfer_sources = {
            "District1": "A",
            "District2": "B",
        }

    def test_percent_of_single_source(self):
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {"District1": {"PERCENT": 0.5, "THRESHOLD": 10}},
        )
        assert result["District1"] == 30.0

    def test_acrefeet_used_when_percent_not_set(self):
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {"District1": {"ACREFEET": 15, "THRESHOLD": 10}},
        )
        assert result["District1"] == 15

    def test_acrefeet_used_when_percent_none(self):
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {"District1": {"ACREFEET": 15, "PERCENT": None, "THRESHOLD": 10}},
        )
        assert result["District1"] == 15

    def test_acrefeet_defaults_to_zero_when_missing(self):
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {"District1": {"THRESHOLD": 10}},
        )
        assert result["District1"] == 0

    def test_multiple_districts(self):
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {
                "District1": {"PERCENT": 0.5, "THRESHOLD": 10},
                "District2": {"ACREFEET": 5, "THRESHOLD": 2},
            },
        )
        assert result["District1"] == 30.0
        assert result["District2"] == 5

    def test_below_threshold_sets_zero(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = calc_transfer_limits(
                self.wafr,
                self.transfer_sources,
                {"District1": {"PERCENT": 0.5, "THRESHOLD": 1000}},
            )
        assert caplog.records
        assert result["District1"] == 0

    def test_transfer_wafr_sources_included_in_output(self):
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {"District1": {"PERCENT": 0.5, "THRESHOLD": 10}},
        )
        assert result["transfer_wafr_sources"] == self.transfer_sources

    def test_threshold_missing_sets_zero_and_logs(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = calc_transfer_limits(
                self.wafr,
                self.transfer_sources,
                {"District1": {"PERCENT": 0.5}},
            )
        assert caplog.records
        assert result["District1"] == 0

    def test_threshold_missing_does_not_block_other_districts(self):
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {
                "District1": {"PERCENT": 0.5},  # no THRESHOLD
                "District2": {"ACREFEET": 5, "THRESHOLD": 2},
            },
        )
        assert result["District1"] == 0
        assert result["District2"] == 5

    def test_threshold_equal_to_total_is_not_below_threshold(self):
        # sum(A) == 60, so a THRESHOLD of exactly 60 should not zero it out
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {"District1": {"PERCENT": 0.5, "THRESHOLD": 60}},
        )
        assert result["District1"] == 30.0

    def test_percent_zero_is_not_treated_as_missing(self):
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {"District1": {"PERCENT": 0, "ACREFEET": 99, "THRESHOLD": 10}},
        )
        assert result["District1"] == 0

    def test_source_missing_from_wafr_sets_zero_and_logs(self, caplog):
        transfer_sources = {"District1": "MissingSource"}
        with caplog.at_level(logging.WARNING):
            result = calc_transfer_limits(
                self.wafr,
                transfer_sources,
                {"District1": {"PERCENT": 0.5, "THRESHOLD": 10}},
            )
        assert caplog.records
        assert result["District1"] == 0

    def test_multiple_districts_share_same_source_independently(self):
        transfer_sources = {"District1": "A", "District2": "A"}
        result = calc_transfer_limits(
            self.wafr,
            transfer_sources,
            {
                "District1": {"PERCENT": 0.5, "THRESHOLD": 10},
                "District2": {"ACREFEET": 5, "THRESHOLD": 10},
            },
        )
        assert result["District1"] == 30.0
        assert result["District2"] == 5

    def test_no_district_goals_returns_only_sources(self):
        result = calc_transfer_limits(self.wafr, self.transfer_sources, {})
        assert result == {"transfer_wafr_sources": self.transfer_sources}

    def test_district_transfer_goals_defaults_to_empty_when_omitted(self):
        result = calc_transfer_limits(self.wafr, self.transfer_sources)
        assert result == {"transfer_wafr_sources": self.transfer_sources}
