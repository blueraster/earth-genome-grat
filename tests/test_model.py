import copy
import logging

import pytest

from grat.model import baseSite, basins, bottlenecks, canals, farms, funcs, grat, sorters
from grat.model.transfers import calc_transfer_limits


class TestBaseSite:
    def setup_method(self) -> None:
        self.bs = baseSite.BaseSite(gratID=299, crop="Corn", acres=12.5, other="test")

    def test_setDailyRecharge(self):

        self.bs.setDailyRecharge(5, 12.13)
        self.bs.setDailyRecharge(5, 7.3)

        assert self.bs.dailyRechargeVolumes[5] == 19.43

    def test_calcPrecip(self):
        self.bs.precipGrid = "GRID444"
        precipDict = {
            "GRID123": [1.2, 0, 0.22, 1.5, 0] * int(365 / 5),
            "GRID444": [0.1] * 365,
        }

        self.bs.calcPrecip(precipDict)  # daily values should be 1.25
        assert sum(self.bs.precip) == 456.25

        self.bs.precipGrid = "GRID123"
        self.bs.calcPrecip(precipDict)
        assert sum(self.bs.precip) == 2664.5

    def test_setDailyRechargeLeapYear(self):

        self.bs.setDailyRecharge(5, 12.13)
        self.bs.setDailyRecharge(364, 1.1)
        self.bs.setDailyRecharge(365, 5.02)
        assert sum(self.bs.dailyRechargeVolumes) == 18.25

    def test_wafrLog(self):
        self.bs.setWafrLog("Unit", 12.3)
        self.bs.setWafrLog("Test", 33.2)
        self.bs.setWafrLog("Test", 55)
        assert self.bs.wafrLog == {"Unit": 12.3, "Test": 88.2}


class TestBasin:
    def setup_method(self) -> None:
        self.b = basins.Basin(
            gratID="unittest",
            crop="Perc Basin",
            acres=12.5,
            cost=12.4,
            percRate=120,
            maxCapacity=50,
            cost_unused=1.25,
            bottleneckIDs=[2],
        )

    def test_updateDailyValues(self):

        self.b.currentCapacity = 200.2  # default on init is zero
        self.b.updateDailyValues(0)

        assert self.b.currentCapacity == pytest.approx(80.2, abs=0.005)

        self.b.updateDailyValues(1)

        assert self.b.currentCapacity == 0

        assert [round(elm, 2) for elm in list(self.b.dailyRechargeVolumes)[0:2]] == [
            120,
            80.2,
        ]

    def test_getSiteVolume(self):
        self.b.currentCapacity = 89.12
        self.b.precip[10] = 20
        assert self.b.getBasinVolumeAvailable(10) == pytest.approx(60.88, abs=0.005)

    def test_setUsedVolume(self):
        self.b.currentCapacity = 77.1
        self.b.setUsedVolume(14, 12.89)
        assert self.b.usedVolume[14] == 12.89
        assert self.b.currentCapacity == 89.99

    def test_useBasin(self):
        self.b.wafrSourcesPrimary = ["B"]

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 9.2, 1]}

        # need bottleneck obj to mock
        bottleneckList = [
            bottlenecks.Bottleneck(
                bottleneckID=2,
                name="canal name",
                capacity=5.949,
                wafrSources=["B"],
            )
        ]

        self.b.useBasin(1, wafr, bottleneckList)
        wafrApplied = 5.949

        assert self.b.usedVolume[1] == pytest.approx(wafrApplied)
        assert wafr["B"][1] == pytest.approx(9.2 - wafrApplied)

    def test_useBasinMultipleWAFR(self):
        self.b.wafrSourcesPrimary = ["B", "A", "C"]
        self.b.precip[1] = 2.5
        wafr = {"A": [1.3, 200, 3.5], "B": [4.2, 9.2, 1], "C": [4.2, 9.2, 1]}

        # need bottleneck obj to mock
        bottleneckList = [
            bottlenecks.Bottleneck(
                bottleneckID=2,
                name="canal name",
                capacity=5.949,
                wafrSources=["B"],
            )
        ]

        self.b.useBasin(1, wafr, bottleneckList)
        wafrApplied = 167.5

        assert self.b.usedVolume[1] == pytest.approx(wafrApplied)

    def test_useBasin_transferLimitExhausted(self):
        self.b.wafrSourcesPrimary = ["B"]
        self.b.district = "D1"

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 9.2, 1]}

        bottleneckList = [
            bottlenecks.Bottleneck(
                bottleneckID=2,
                name="canal name",
                capacity=5.949,
                wafrSources=["B"],
            )
        ]

        transferLimits = {"D1": 0, "transfer_wafr_sources": {"D1": "B"}}

        self.b.useBasin(1, wafr, bottleneckList, transferLimits=transferLimits)

        assert self.b.usedVolume[1] == 0
        assert wafr["B"][1] == 9.2

    def test_useBasin_transferLimitNotExhausted(self):
        self.b.wafrSourcesPrimary = ["B"]
        self.b.district = "D1"

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 9.2, 1]}

        bottleneckList = [
            bottlenecks.Bottleneck(
                bottleneckID=2,
                name="canal name",
                capacity=5.949,
                wafrSources=["B"],
            )
        ]

        transferLimits = {"D1": 100, "transfer_wafr_sources": {"D1": "B"}}

        self.b.useBasin(1, wafr, bottleneckList, transferLimits=transferLimits)
        wafrApplied = 5.949

        assert self.b.usedVolume[1] == pytest.approx(wafrApplied)
        assert wafr["B"][1] == pytest.approx(9.2 - wafrApplied)
        assert transferLimits["D1"] == pytest.approx(100 - wafrApplied)


class TestBottleneck:
    def setup_method(self) -> None:

        self.bottleneckA = bottlenecks.Bottleneck(
            1, "test canal", 6.84135, wafrSources=["SourceA"]
        )  # 6.84135 af per day
        self.bottleneckB = bottlenecks.Bottleneck(
            2,
            "second canal",
            2.39943,
            capacityIrrigation=100,
            irrigationDays=[200, 201, 203, 204],
            wafrSources=["SourceB"],
        )  # 2.39943 af per day

        self.bottleneckList = [self.bottleneckA, self.bottleneckB]

    def test_updateUsage(self):
        # init value is the acre-feet per day limit
        assert self.bottleneckA.availableThroughput[10] == pytest.approx(6.84, abs=0.005)

        # update usage
        self.bottleneckA.updateUsage(10, 2.22)
        assert self.bottleneckA.availableThroughput[10] == pytest.approx(4.62, abs=0.005)

    def test_getAvailableThroughput(self):
        t = self.bottleneckA.getAvailableThroughput(15)
        assert t == pytest.approx(6.84, abs=0.005)

    def test_getAvailableThroughputCapacityHit(self):
        # update usage
        self.bottleneckA.updateUsage(15, 19.1)
        t = self.bottleneckA.getAvailableThroughput(15)
        assert t == 0

    def test_getBottleneckFromIDWafr(self):
        shouldBeA = bottlenecks.getBottlenecks(self.bottleneckList, [1], "SourceA")[0]
        assert shouldBeA.name == "test canal"

    def test_getBottleneckFromIDWaf2(self):
        shouldBeB = bottlenecks.getBottlenecks(self.bottleneckList, [1, 2], "SourceB")[0]
        assert shouldBeB.name == "second canal"

    def test_getBottleneckFromIDWafrNone(self):
        shouldBeNone = bottlenecks.getBottlenecks(self.bottleneckList, [2], "SourceA")
        assert shouldBeNone == []

    def test_bottleneckCapacityLogger(self):
        self.bottleneckA.updateUsage(15, 19.1)
        self.bottleneckA.updateUsage(20, 50)
        self.bottleneckB.updateUsage(20, 20)
        self.bottleneckB.updateUsage(1, 50)

        capLogger = bottlenecks.bottleneckCapacityLogger(self.bottleneckList)
        assert capLogger[15] == [1]
        assert capLogger[20] == [1, 2]
        assert capLogger[50] == []

    def test_getAvailableThroughputIrrigationDate(self):
        nonIrr = self.bottleneckB.getAvailableThroughput(199)
        assert nonIrr == pytest.approx(2.39943, abs=0.005)
        irr = self.bottleneckB.getAvailableThroughput(200)
        assert irr == pytest.approx(100, abs=0.005)


class TestCanalObject:
    def setup_method(self) -> None:

        self.c = canals.Canal(
            gratID="Example 1",
            maxCapacity=10000,
            percRate=600,
            wafrSources=["SourceB"],
        )

    def test_canal_init(self):
        assert self.c.maxCapacity[0] == 10000
        assert self.c.percRate == 600
        assert self.c.currentCapacity == 0

    def test_set_daily_recharge(self):

        # test variables
        i = 18  # index day
        new_vol = 12.234

        # get current recharge volume (should be zero)
        assert self.c.dailyRechargeVolumes[i] == 0

        # set to a new volume
        self.c.setDailyRecharge(i, new_vol)

        # check the new daily recharge volume
        assert self.c.dailyRechargeVolumes[i] == new_vol

    def test_update_daily_recharge(self):

        # sets daily recharge to the min of the perc rate or current capacity
        # default perc rate = 600, curr_capacity = 0, so does this always return zero???
        i = 29  # index day

        # set daily recharge to a different value
        self.c.setDailyRecharge(i, 124.1931)

        # set curr capacity to a non-zero number
        self.c.currentCapacity = 23.123
        self.c.updateDailyValues(i)

        # check the new daily recharge volume
        assert self.c.dailyRechargeVolumes[i] == 147.3161

    def test_update_usage(self):

        i = 48  # index day
        v = 19902.12  # value

        self.c.setUsedVolume(i, v)

        # check the new daily recharge volume
        assert self.c.usedVolume[i] == v

        # check the updated current capacity
        assert self.c.currentCapacity == v

    def test_use_canal_below_cap(self):

        # not sure the structure of WAFR
        wafr = {"test_source": [3.4, 1.3, 9.23, 8.9, 999999]}

        self.c.wafrSources = ["test_source"]

        # use canal when below cap
        i = 2
        self.c.useCanal(i, wafr, "test_source", 9.23)

        assert self.c.usedVolume[i] == 9.23

    def test_use_canal_above_cap(self):

        # not sure the structure of WAFR
        wafr = {"test_source": [3.4, 1.3, 9.23, 8.9, 999999]}

        self.c.wafrSources = ["test_source"]

        # use canal above cap
        i = 4
        self.c.useCanal(i, wafr, "test_source", 100000)
        assert self.c.usedVolume[i] == 10600


class TestMockCanal:
    def setup_method(self) -> None:
        self.c = canals.Canal(
            gratID="unit test canal",
            wafrSourcesPrimary=["source_A", "source_B"],
            maxCapacity=10000,
            percRate=600,
        )

        self.wafr = {
            "source_A": [91.2, 74.1, 1.23, 192.3, 12023.2, 9.3, 8.12, 12.3],
            "source_B": [87.2, 6.23, 9.51, 891.3, 789, 5.3, 98.1, 5.6],
        }
        self.canalList = [self.c]

    def test_use_canal(self):

        # loop through the days
        for i in range(0, 7):
            canals.fillCanals(self.canalList, i, self.wafr)
            canals.canalsUpdateDailyValues(self.canalList, i)

        # use canal again
        canals.fillCanals(self.canalList, 7, self.wafr)
        canals.canalsUpdateDailyValues(self.canalList, 7)

        assert list(self.c.usedVolume)[0:8] == [
            178.4,
            80.33,
            10.74,
            1083.6,
            10116.4,
            14.600000000000001,
            106.22,
            17.9,
        ]
        assert list(self.c.dailyRechargeVolumes)[0:8] == [
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
        self.A = canals.Canal(
            gratID="canal A",
            wafrSourcesPrimary=["Blue Lake"],
            maxCapacity=1000,
            percRate=600,
        )

        self.B = canals.Canal(
            gratID="canal B",
            wafrSourcesPrimary=["Blue Lake", "Green Lake"],
            maxCapacity=800,
            percRate=200,
        )

        self.C = canals.Canal(
            gratID="canal C",
            wafrSourcesPrimary=["Blue Lake", "Green Lake"],
            maxCapacity=1500,
            percRate=800,
        )

        self.wafr = {
            "Blue Lake": [2000, 4000, 10000, 0, 0, 0, 3000],
            "Green Lake": [0, 0, 0, 0, 0, 1600, 1600],
        }

        self.canalList = [self.A, self.B, self.C]

        # loop through the days
        for i in range(0, 7):
            canals.fillCanals(self.canalList, i, self.wafr)
            canals.canalsUpdateDailyValues(self.canalList, i)

    def test_use_canal_wafr(self):

        assert self.wafr == {
            "Blue Lake": [0.0, 0.0, 7900.000000000001, 0, 0, 0, 0.0],
            "Green Lake": [0, 0, 0, 0, 0, 0.0, 1069.2307692307693],
        }

    def test_use_canal_usedVolume(self):

        assert sum(self.A.usedVolume[0:7]) == pytest.approx(4030.77, abs=0.005)
        assert sum(self.B.usedVolume[0:7]) == pytest.approx(2200.0, abs=0.005)
        assert sum(self.C.usedVolume[0:7]) == pytest.approx(7000.0, abs=0.005)

    def test_use_canal_dailyRechargeVol(self):

        assert sum(self.A.dailyRechargeVolumes[0:7]) == pytest.approx(3400, abs=0.005)
        assert sum(self.B.dailyRechargeVolumes[0:7]) == pytest.approx(1400, abs=0.005)
        assert sum(self.C.dailyRechargeVolumes[0:7]) == pytest.approx(5500.0, abs=0.005)

    def test_use_canal_currentCapacity(self):

        assert self.A.currentCapacity == pytest.approx(630.77, abs=0.005)
        assert self.B.currentCapacity == pytest.approx(800, abs=0.005)
        assert self.C.currentCapacity == pytest.approx(1500.0, abs=0.005)


class TestMockCanalProportional:
    def setup_method(self) -> None:
        self.A = canals.Canal(
            gratID="canal A",
            wafrSourcesPrimary=["Blue Lake"],
            maxCapacity=10,
            percRate=5,
        )
        self.B = canals.Canal(
            gratID="canal B",
            wafrSourcesPrimary=["Blue Lake", "Red Lake"],
            maxCapacity=10,
            percRate=5,
        )
        self.C = canals.Canal(
            gratID="canal C",
            wafrSourcesPrimary=["Red Lake"],
            maxCapacity=10,
            percRate=5,
        )

        self.wafr = {
            "Blue Lake": [100, 0, 0, 0, 0, 0, 0, 0],
            "Red Lake": [8, 10, 0, 0, 0, 0, 0, 0],
        }

        self.canalList = [self.A, self.B, self.C]

        # loop through the days
        for i in range(0, 2):
            canals.fillCanals(self.canalList, i, self.wafr)
            canals.canalsUpdateDailyValues(self.canalList, i)

    def test_use_canal_day1(self):

        assert self.A.usedVolume[0] == pytest.approx(15, abs=0.005)
        assert self.B.usedVolume[0] == pytest.approx(15, abs=0.005)
        assert self.C.usedVolume[0] == pytest.approx(8, abs=0.005)

        assert self.A.dailyRechargeVolumes[0] == pytest.approx(5, abs=0.005)
        assert self.B.dailyRechargeVolumes[0] == pytest.approx(5, abs=0.005)
        assert self.C.dailyRechargeVolumes[0] == pytest.approx(5, abs=0.005)

        assert self.wafr["Blue Lake"][0] == pytest.approx(70, abs=0.005)
        assert self.wafr["Red Lake"][0] == pytest.approx(0, abs=0.005)

    def test_use_canal_day2(self):
        assert self.A.usedVolume[1] == pytest.approx(0, abs=0.005)
        assert self.B.usedVolume[1] == pytest.approx(2.94, abs=0.005)
        assert self.C.usedVolume[1] == pytest.approx(7.06, abs=0.005)

        assert self.A.dailyRechargeVolumes[1] == pytest.approx(5, abs=0.005)
        assert self.B.dailyRechargeVolumes[1] == pytest.approx(5, abs=0.005)
        assert self.C.dailyRechargeVolumes[1] == pytest.approx(5, abs=0.005)

        assert self.wafr["Blue Lake"][1] == pytest.approx(0, abs=0.005)
        assert self.wafr["Red Lake"][1] == pytest.approx(0, abs=0.005)

    def test_canalFeedBy(self):
        assert self.A.wafrLog["Blue Lake"] == 15
        assert self.B.wafrLog["Red Lake"] == 2.9411764705882355
        assert self.B.wafrLog["Blue Lake"] == 15
        assert self.C.wafrLog["Red Lake"] == 8.0 + 7.058823529411765


class TestMockCanalProportionalWafrOrder:
    def setup_method(self) -> None:
        self.A = canals.Canal(
            gratID="canal A",
            wafrSourcesPrimary=["Blue Lake"],
            maxCapacity=10,
            percRate=5,
        )
        self.B = canals.Canal(
            gratID="canal B",
            wafrSourcesPrimary=["Blue Lake", "Red Lake"],
            maxCapacity=10,
            percRate=5,
        )
        self.C = canals.Canal(
            gratID="canal C",
            wafrSourcesPrimary=["Red Lake"],
            maxCapacity=10,
            percRate=5,
        )

        self.wafr = {
            "Blue Lake": [100, 0, 0, 0, 0, 0, 0, 0],
            "Red Lake": [8, 10, 0, 0, 0, 0, 0, 0],
        }

        self.canalList = [self.A, self.B, self.C]

        # loop through the days
        for i in range(0, 2):
            canals.fillCanals(self.canalList, i, self.wafr)
            canals.canalsUpdateDailyValues(self.canalList, i)

    def test_use_canal_day1(self):

        assert self.A.usedVolume[0] == pytest.approx(15, abs=0.005)
        assert self.B.usedVolume[0] == pytest.approx(15, abs=0.005)
        assert self.C.usedVolume[0] == pytest.approx(8, abs=0.005)

        assert self.A.dailyRechargeVolumes[0] == pytest.approx(5, abs=0.005)
        assert self.B.dailyRechargeVolumes[0] == pytest.approx(5, abs=0.005)
        assert self.C.dailyRechargeVolumes[0] == pytest.approx(5, abs=0.005)

    def test_use_canal_day2(self):
        assert self.A.usedVolume[1] == pytest.approx(0, abs=0.005)
        assert self.B.usedVolume[1] == pytest.approx(2.941, abs=0.005)
        assert self.C.usedVolume[1] == pytest.approx(7.058, abs=0.005)

        assert self.A.dailyRechargeVolumes[1] == pytest.approx(5, abs=0.005)
        assert self.B.dailyRechargeVolumes[1] == pytest.approx(5, abs=0.005)
        assert self.C.dailyRechargeVolumes[1] == pytest.approx(5, abs=0.005)


class TestOFR:
    def setup_method(self) -> None:
        self.ofr = farms.Farm(
            gratID="Unittest",
            crop="Corn",
            acres=10.2,
            soilType="Good",
            cfsLimit=100,
            bottleneckIDs=[2],
        )
        self.cropCalendar = {"Corn": {"Good": [4.12, 4.12]}}

        self.bottleneckList = [
            bottlenecks.Bottleneck(
                bottleneckID=2,
                name="canal name",
                capacity=5.949,
                wafrSources=["B"],
            )
        ]

    def test_getSiteVolume(self):

        assert self.ofr.getSiteVolume(0, self.cropCalendar) == 42.024

    def test_useSite(self):

        self.ofr.wafrSourcesPrimary = ["B"]

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 9.2, 1]}

        self.ofr.precip[1] = 2.1

        self.ofr.useSite(
            1,
            wafr,
            self.bottleneckList,
            cropCalendar=self.cropCalendar,
        )
        wafrApplied = 5.949

        assert self.ofr.ofrUsedVolume[1] == pytest.approx(wafrApplied)
        assert self.ofr.ofrUnusedVolume[1] == pytest.approx(33.975)
        assert wafr["B"][1] == pytest.approx(9.2 - wafrApplied)

    def test_useSite_transferLimitExhausted(self):
        self.ofr.wafrSourcesPrimary = ["B"]
        self.ofr.district = "D1"

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 9.2, 1]}
        self.ofr.precip[1] = 2.1

        transferLimits = {"D1": 0, "transfer_wafr_sources": {"D1": "B"}}

        self.ofr.useSite(
            1,
            wafr,
            self.bottleneckList,
            cropCalendar=self.cropCalendar,
            transferLimits=transferLimits,
        )

        assert self.ofr.ofrUsedVolume[1] == 0
        assert wafr["B"][1] == 9.2

    def test_useSite_transferLimitNotExhausted(self):
        self.ofr.wafrSourcesPrimary = ["B"]
        self.ofr.district = "D1"

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 9.2, 1]}
        self.ofr.precip[1] = 2.1

        transferLimits = {"D1": 100, "transfer_wafr_sources": {"D1": "B"}}

        self.ofr.useSite(
            1,
            wafr,
            self.bottleneckList,
            cropCalendar=self.cropCalendar,
            transferLimits=transferLimits,
        )
        wafrApplied = 5.949

        assert self.ofr.ofrUsedVolume[1] == pytest.approx(wafrApplied)
        assert wafr["B"][1] == pytest.approx(9.2 - wafrApplied)
        assert transferLimits["D1"] == pytest.approx(100 - wafrApplied)


class TestModelMainRun:
    def setup_method(self) -> None:
        self.canal1 = canals.Canal(
            gratID="test",
            wafrSourcesPrimary=["A", "B"],
            maxCapacity=10000,
            percRate=600,
            rechargeType="Canal",
        )
        self.site1 = farms.Farm(
            gratID=299,
            crop="Corn",
            acres=12.5,
            rechargeType="On-Farm Recharge",
            soilType="Good",
            cfsLimit=5 / 1.983,
            bottleneckIDs=[2],
            wafrSourcesPrimary=["B"],
        )
        self.site2 = farms.Farm(
            gratID=9,
            crop="Wheat",
            acres=2.5,
            rechargeType="On-Farm Recharge",
            soilType="Good",
            cfsLimit=5 / 1.983,
            bottleneckIDs=[2],
            wafrSourcesPrimary=["A"],
        )
        self.site3 = basins.Basin(
            gratID=33,
            acres=2.5,
            rechargeType="Basin",
            percRate=1.2,
            maxCapacity=100,
            bottleneckIDs=[1],
            wafrSourcesPrimary=["A"],
        )
        self.site_list = [self.canal1, self.site3, self.site1, self.site2]

        self.wafr = {"A": [20000.3, 20000, 20000], "B": [4.2, 9.2, 1]}

        # need bottleneck obj to mock

        self.bottleneckList = [
            bottlenecks.Bottleneck(
                bottleneckID=1,
                name="canal name",
                capacity=595.037759907,
                wafrSources=["A"],
            ),
            bottlenecks.Bottleneck(
                bottleneckID=2,
                name="canal name",
                capacity=595.037759907,
                wafrSources=["B"],
            ),
        ]

        self.cropCalendar = {
            "Corn": {"Good": {0: 4.12, 1: 4.12, 2: 4.12}},
            "Wheat": {"Good": {0: 4.12, 1: 4.12, 2: 4.12}},
        }

    def test_runGRAT_wafr(self):
        r = grat.processYear(
            self.site_list,
            self.bottleneckList,
            self.wafr,
            self.cropCalendar,
            precip=None,
        )

        assert r["wafr"] == {
            "A": [9294.099999999999, 19393.8, 19393.8],
            "B": [0.0, 4.199999999999999, 0],
        }

    def test_runGRAT_canals(self):
        r = grat.processYear(
            self.site_list,
            self.bottleneckList,
            self.wafr,
            self.cropCalendar,
            precip=None,
        )

        assert sum(r["sites"][0].dailyRechargeVolumes) == 1800.0

    def test_runGRAT_sites(self):
        r = grat.processYear(
            self.site_list,
            self.bottleneckList,
            self.wafr,
            self.cropCalendar,
            precip=None,
        )

        # basin 1.2 perc rate x 3 days
        assert sum(r["sites"][1].dailyRechargeVolumes) == pytest.approx(3.6)
        # site 1 [4.2, 5. , 1.]
        assert sum(r["sites"][2].ofrDailyRechargeVolumes) == pytest.approx(10.2)


class TestModelMainRunMultiYear:
    def setup_method(self) -> None:
        self.canal1 = canals.Canal(
            gratID="test",
            wafrSources=["A", "B"],
            maxCapacity=10000,
            percRate=600,
            rechargeType="Canal",
        )

        self.site1 = farms.Farm(
            gratID=299,
            crop="Corn",
            acres=12.5,
            rechargeType="OFR",
            soilType="Good",
            cfsLimit=5 / 1.983,
            bottleneckIDs=2,
            wafrSources=["B"],
        )
        self.site2 = farms.Farm(
            gratID=9,
            crop="Wheat",
            acres=2.5,
            rechargeType="OFR",
            soilType="Good",
            cfsLimit=5 / 1.983,
            bottleneckIDs=2,
            wafrSources=["A"],
        )
        self.site3 = basins.Basin(
            gratID=33,
            acres=2.5,
            rechargeType="Basin",
            percRate=1.2,
            maxCapacity=100,
            bottleneckIDs=2,
            wafrSources=["A"],
        )
        self.site_list = [self.canal1, self.site3, self.site1, self.site2]

        self.wafr = {"A": [20000.3, 20000, 20000], "B": [4.2, 9.2, 1]}
        self.wafr2 = {"A": [20000.3, 19.1, 20000], "B": [4.2, 9.2, 1]}

        # need bottleneck obj to mock
        self.bottleneckList = [
            bottlenecks.Bottleneck(
                bottleneckID=2,
                name="canal name",
                capacity=595.03775990781,
            )
        ]

        self.cropCalendar = {
            "Corn": {"Good": {0: 4.12, 1: 4.12, 2: 4.12}},
            "Wheat": {"Good": {0: 4.12, 1: 4.12, 2: 4.12}},
        }

    def test_processYear(self):

        sites2 = copy.deepcopy(self.site_list)
        bottleneckList2 = copy.deepcopy(self.bottleneckList)

        year_1 = grat.processYear(
            self.site_list,
            self.bottleneckList,
            self.wafr,
            self.cropCalendar,
            precip=None,
        )

        year_2 = grat.processYear(sites2, bottleneckList2, self.wafr2, self.cropCalendar, precip=None)

        # years should not be equal
        assert year_1["sites"] != year_2["sites"]


class TestSorters:
    def setup_method(self) -> None:
        class SorterExample:
            def __init__(self, gratID, acres, rechargeType, rsi=0, scenarioA=None):
                self.gratID = gratID
                self.acres = acres
                self.rechargeType = rechargeType
                self.rsi = rsi
                self.scenarioA = scenarioA

            def __repr__(self):
                return f"{self.gratID}"

        a = SorterExample("A", 10.2, "OFR", rsi=77, scenarioA=None)
        b = SorterExample("B", 12.2, "OFR", rsi=23, scenarioA="Z")
        c = SorterExample("C", 1.2, "Basin", rsi=50, scenarioA="A")
        d = SorterExample("D", 13.2, None, rsi=7, scenarioA="Z")
        e = SorterExample("E", 12.2, "OFR", rsi=19, scenarioA="A")

        self.listofsites = [a, b, c, d, e]

    def test_sortByType(self):
        s = self.listofsites.copy()
        s.sort(key=sorters.rechargeTypeOrder)
        site_order = [o.gratID for o in s]
        assert site_order == ["C", "A", "B", "E", "D"]

    def test_sortByVariable(self):
        s = sorters.sort_by_variable(self.listofsites, "acres")
        site_order = [o.gratID for o in s]
        assert site_order == ["C", "A", "B", "E", "D"]

    def test_sortByVariable2(self):

        s = sorters.sort_by_variable(self.listofsites, "rsi", True)
        site_order = [o.gratID for o in s]
        assert site_order == ["A", "C", "B", "E", "D"]

    def test_sortByMultiVariable(self):

        s = sorters.sort_by_variables(self.listofsites, (("acres", True), ("rsi", True)))
        site_order = [o.gratID for o in s]
        assert site_order == ["D", "B", "E", "A", "C"]

    def test_sortSitesBasic(self):

        s = sorters.sortSites(self.listofsites, sortRule=None)
        site_order = [o.gratID for o in s]
        assert site_order == ["C", "A", "B", "E", "D"]

    def test_sortSitesScenarioA(self):

        s = sorters.sortSites(self.listofsites, sortRule="A")
        site_order = [o.gratID for o in s]
        assert site_order == ["C", "B", "E", "A", "D"]


class TestSortersCanals:
    def setup_method(self) -> None:
        class SorterExample:
            def __init__(self, gratID, acres, rechargeType, index=0, scenarioA=None):
                self.gratID = gratID
                self.acres = acres
                self.rechargeType = rechargeType
                self.index = index
                self.scenarioA = scenarioA

            def __repr__(self):
                return f"{self.gratID}"

        a = SorterExample("A", 0, "Canal", index=77, scenarioA=None)
        b = SorterExample("B", 12.2, "OFR", index=23, scenarioA="Z")
        c = SorterExample("C", 1.2, "Basin", index=50, scenarioA="A")
        d = SorterExample("D", 0, "Canal", index=50, scenarioA="A")
        e = SorterExample("E", 15, "OFR", index=50, scenarioA="A")

        self.listofsites = [a, b, c, d, e]

    def test_sortByType(self):
        s = self.listofsites.copy()
        s.sort(key=sorters.rechargeTypeOrder)
        site_order = [o.gratID for o in s]
        assert site_order == ["A", "D", "C", "B", "E"]

    def test_sortTypeByVariable(self):
        s = sorters.sort_by_variable(self.listofsites, "acres", reverse=True)
        s.sort(key=sorters.rechargeTypeOrder)
        site_order = [o.gratID for o in s]
        assert site_order == ["A", "D", "C", "E", "B"]


class TestSortersInLieu:
    def setup_method(self) -> None:
        class SorterExample:
            def __init__(
                self,
                gratID,
                acres,
                rechargeType,
                index=0,
                scenarioA=None,
                groundwaterChange=0,
                crop=None,
                inLieuCrop=None,
                rma=None,
            ):
                self.gratID = gratID
                self.acres = acres
                self.rechargeType = rechargeType
                self.index = index
                self.scenarioA = scenarioA
                self.groundwaterChange = groundwaterChange
                self.crop = crop
                self.inLieuCrop = inLieuCrop
                self.rma = rma

            def __repr__(self):
                return f"{self.gratID}"

        a = SorterExample(
            "A",
            0,
            "OFR",
            index=77,
            groundwaterChange=10,
            inLieuCrop="Corn",
            crop="Apple",
            rma=2,
        )
        b = SorterExample("B", 12.2, "OFR", index=23, groundwaterChange=5, crop="Apple", rma=1)
        c = SorterExample("C", 1.2, "OFR", index=50, groundwaterChange=-10, inLieuCrop="Corn", rma=1)
        d = SorterExample(
            "D",
            0,
            "OFR",
            index=50,
            groundwaterChange=-5,
            inLieuCrop="Corn",
            crop="Apple",
            rma=2,
        )
        e = SorterExample("E", 15, "OFR", index=50, groundwaterChange=2, inLieuCrop="Corn")

        self.listofsites = [a, b, c, d, e]

    def test_sortIL(self):
        _, sites_il, _, _ = sorters.groupSitesByRechargeType(self.listofsites, rmaSort=False)
        site_order = [o.gratID for o in sites_il]
        assert site_order == ["C", "D", "E", "A"]

    def test_sortIL_rma(self):
        _, sites_il, _, _ = sorters.groupSitesByRechargeType(self.listofsites, rmaSort=True)
        site_order = [o.gratID for o in sites_il]
        assert site_order == ["C", "D", "A", "E"]


class TestIL:
    def setup_method(self) -> None:
        self.il = farms.Farm(
            gratID="Unittest",
            crop="Corn",
            acres=10.2,
            soilType="Good",
            cfsLimit=100 / 1.983,
            bottleneckIDs=[2],
            inLieuCrop="Grapes",
            regionNumber=1,
        )
        self.cropCalendar = {
            "Corn": {"Good": [55.1, 12.4]},
        }

        self.ilCropCalendar = {
            "Grapes": {"1": [4.12, 4.12]},
        }

        self.bottleneckList = [
            bottlenecks.Bottleneck(bottleneckID=2, name="canal name", capacity=1000, wafrSources=["A"])
        ]

    def test_getSiteVolume(self):

        assert self.il.getSiteVolume(0, self.ilCropCalendar, inlieu=True) == 42.024

    def test_useSite(self):

        self.il.wafrSourcesPrimary = ["B"]

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 1000, 1]}
        self.il.precip[1] = 2.1
        self.il.useSite(
            1,
            wafr,
            self.bottleneckList,
            cropCalendar=self.ilCropCalendar,
            inLieu=True,
        )

        # should not modify used/unused volume
        assert self.il.usedVolume[1] == pytest.approx(0)

        # modify the in-lieu variables
        assert self.il.inLieuUsedVolume[1] == pytest.approx(39.924)
        assert self.il.inLieuUnusedVolume[1] == pytest.approx(0)

    def test_useSiteTwice(self):

        self.il.wafrSourcesPrimary = ["B"]
        self.il.flowLimit = [1000, 1000]

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 1000, 1]}

        self.il.precip[0] = 2.1
        self.il.precip[1] = 2.1

        self.il.useSite(
            1,
            wafr,
            self.bottleneckList,
            cropCalendar=self.ilCropCalendar,
            inLieu=True,
        )

        self.il.useSite(
            1,
            wafr,
            self.bottleneckList,
            cropCalendar=self.cropCalendar,
            inLieu=False,
        )

        # check the in-lieu variables
        # inlieu potential
        # acres x il ccc - precip
        # (10.2 x 4.12) - 2.1
        assert self.il.inLieuUsedVolume[1] == pytest.approx(39.924)
        assert self.il.inLieuUnusedVolume[1] == pytest.approx(0)

        # should be not impacted by precip
        # acres x ofr ccc
        # 10.2*12.4 = 126.48
        assert self.il.ofrUsedVolume[1] == pytest.approx(126.48)
        assert self.il.ofrUnusedVolume[1] == pytest.approx(0)

    def test_useSiteTwiceTurnoutTest(self):

        self.il.wafrSourcesPrimary = ["B"]

        wafr = {"A": [1.3, 4, 3.5], "B": [4.2, 1000, 1]}

        self.il.precip[1] = 0

        self.il.useSite(
            1,
            wafr,
            self.bottleneckList,
            cropCalendar=self.ilCropCalendar,
            inLieu=True,
        )

        self.il.useSite(
            1,
            wafr,
            self.bottleneckList,
            cropCalendar=self.cropCalendar,
            inLieu=False,
        )

        # check the in-lieu variables
        assert self.il.inLieuUsedVolume[1] == pytest.approx(42.024)
        assert self.il.inLieuUnusedVolume[1] == pytest.approx(0)

        assert self.il.ofrUsedVolume[1] == pytest.approx(100 - 42.024)
        # assert self.il.unusedVolume[1] == pytest.approx(42.024)


class TestWafrSortOrder:
    def setup_method(self) -> None:
        self.wafr = {"SourceB": [50, 12000], "SourceA": [19, 300000]}

    def test_day0(self):
        assert funcs.sortWafrSourceByVolume(self.wafr, 0) == ["SourceB", "SourceA"]

    def test_day1(self):
        assert funcs.sortWafrSourceByVolume(self.wafr, 1) == ["SourceA", "SourceB"]


class TestWafrAvailability:
    def setup_method(self) -> None:
        self.wafr = {"SourceB": [50, 12000, 0, 0], "SourceA": [19, 300000, 0, 1]}

    def test_day0(self):
        assert funcs.checkWafrAvailability(self.wafr, 0)

    def test_day2(self):
        assert not funcs.checkWafrAvailability(self.wafr, 2)


class TestGetCompatibleCrops:
    def setup_method(self) -> None:
        self.ccc = {
            "Corn": {"Poor": [0, 1.2, 3, 0], "Good": [3, 0, 1, 0]},
            "Rice": {"Great": [0, 0, 1.2, 0], "Good": [0, 2.1, 0, 0]},
        }

    def test_day0(self):
        assert funcs.getCompatibleCropsSoilsForDay(self.ccc, 0) == [("Corn", "Good")]

    def test_day1(self):
        assert funcs.getCompatibleCropsSoilsForDay(self.ccc, 1) == [
            ("Corn", "Poor"),
            ("Rice", "Good"),
        ]

    def test_day2(self):
        assert funcs.getCompatibleCropsSoilsForDay(self.ccc, 2) == [
            ("Corn", "Poor"),
            ("Corn", "Good"),
            ("Rice", "Great"),
        ]

    def test_day3(self):
        assert funcs.getCompatibleCropsSoilsForDay(self.ccc, 3) == []

    def test_None(self):
        assert funcs.getCompatibleCropsSoilsForDay(None, 2) == []


# NOTE: grat.py has not been ported to this project yet, see comment above.
#
# class TestModelMainRunSecondaryWafr:
#     def setup_method(self) -> None:
#         self.canal1 = canals.Canal(
#             gratID="test",
#             wafrSourcesPrimary=["A", "B"],
#             maxCapacity=10000,
#             percRate=600,
#             rechargeType="Canal",
#         )
#         self.site1 = farms.Farm(
#             gratID=299,
#             crop="Corn",
#             acres=12.5,
#             rechargeType="On-Farm Recharge",
#             soilType="Good",
#             cfsLimit=5 / 1.983,
#             bottleneckIDs=[2],
#             wafrSourcesPrimary=["B"],
#             wafrSourcesSecondary=["A"],
#         )
#         self.site2 = farms.Farm(
#             gratID=9,
#             crop="Wheat",
#             acres=2.5,
#             rechargeType="On-Farm Recharge",
#             soilType="Good",
#             cfsLimit=5 / 1.983,
#             bottleneckIDs=[2],
#             wafrSourcesPrimary=["A"],
#             wafrSourcesSecondary=["B"],
#         )
#         self.site3 = basins.Basin(
#             gratID=33,
#             acres=2.5,
#             rechargeType="Basin",
#             percRate=1.2,
#             maxCapacity=100,
#             bottleneckIDs=[2],
#             wafrSourcesPrimary=["A"],
#             wafrSourcesSecondary=["B"],
#         )
#         self.site_list = [self.canal1, self.site3, self.site1, self.site2]
#         self.wafr = {"A": [20000.3, 20000, 20000], "B": [4.2, 9.2, 1]}
#
#         # need bottleneck obj to mock
#         self.bottleneckList = [
#             bottlenecks.Bottleneck(
#                 bottleneckID=2,
#                 name="canal name",
#                 capacity=595.037759907,
#                 wafrSources=["A"],
#             ),
#             bottlenecks.Bottleneck(
#                 bottleneckID=2,
#                 name="canal name",
#                 capacity=595.037759907,
#                 wafrSources=["B"],
#             ),
#         ]
#
#         self.cropCalendar = {
#             "Corn": {"Good": {0: 4.12, 1: 4.12, 2: 4.12}},
#             "Wheat": {"Good": {0: 4.12, 1: 4.12, 2: 4.12}},
#         }
#
#     def test_runGRAT_wafr(self):
#         r = grat.processYear(
#             self.site_list,
#             self.bottleneckList,
#             self.wafr,
#             self.cropCalendar,
#             precip=None,
#         )
#
#         assert r["wafr"] == {
#             "A": [9294.099999999999 - 0.8, 19393.8, 19393.8 - 4],
#             "B": [0.0, 4.199999999999999, 0],
#         }
#
#     def test_runGRAT_canals(self):
#         r = grat.processYear(
#             self.site_list,
#             self.bottleneckList,
#             self.wafr,
#             self.cropCalendar,
#             precip=None,
#         )
#
#         assert sum(r["sites"][0].dailyRechargeVolumes) == 1800.0
#
#     def test_runGRAT_sites(self):
#         r = grat.processYear(
#             self.site_list,
#             self.bottleneckList,
#             self.wafr,
#             self.cropCalendar,
#             precip=None,
#         )
#
#         # basin 1.2 perc rate x 3 days
#         assert sum(r["sites"][1].dailyRechargeVolumes) == pytest.approx(3.6)
#         # site 1 [4.2, 5. , 1.]
#         assert sum(r["sites"][2].ofrDailyRechargeVolumes) == pytest.approx(15)


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

    def test_getWafrSourcesWithWater(self):
        assert funcs.sortWafrSourceByVolume(self.wafr, 0) == ["CalDuck"]
        assert funcs.sortWafrSourceByVolume(self.wafr, 1) == []
        assert funcs.sortWafrSourceByVolume(self.wafr, 4) == [
            "Calaveras",
            "Duck",
            "CalDuck",
        ]


class TestTurnoutLimitConversion:
    def test_turnoutLimitConversion_with_valid_input(self):
        cfsRate = 20
        expected_output = 39.66
        assert farms.turnoutLimitConversion(cfsRate) == pytest.approx(expected_output, abs=0.005)


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
