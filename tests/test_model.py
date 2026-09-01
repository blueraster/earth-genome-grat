import copy
import unittest

from model import baseSite, basins, bottlenecks, canals, farms, funcs, grat
from model.transfers import calc_transfer_limits


class BaseSiteTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.bs = baseSite.BaseSite(gratID=299, crop="Corn", acres=12.5, other="test")

    def test_setDailyRecharge(self):

        self.bs.setDailyRecharge(5, 12.13)
        self.bs.setDailyRecharge(5, 7.3)

        self.assertEqual(19.43, self.bs.dailyRechargeVolumes[5])

    def test_calcPrecip(self):
        self.bs.precipGrid = "GRID444"
        precipDict = {
            "GRID123": [1.2, 0, 0.22, 1.5, 0] * int(365 / 5),
            "GRID444": [0.1] * 365,
        }

        self.bs.calcPrecip(precipDict)  # daily values should be 1.25
        self.assertEqual(456.25, sum(self.bs.precip))

        self.bs.precipGrid = "GRID123"
        self.bs.calcPrecip(precipDict)
        self.assertEqual(2664.5, sum(self.bs.precip))

    def test_setDailyRechargeLeapYear(self):

        self.bs.setDailyRecharge(5, 12.13)
        self.bs.setDailyRecharge(364, 1.1)
        self.bs.setDailyRecharge(365, 5.02)
        self.assertEqual(sum(self.bs.dailyRechargeVolumes), 18.25)

    def test_wafrLog(self):
        self.bs.setWafrLog("Unit", 12.3)
        self.bs.setWafrLog("Test", 33.2)
        self.bs.setWafrLog("Test", 55)
        self.assertEqual(self.bs.wafrLog, {"Unit": 12.3, "Test": 88.2})


class BasinTestCase(unittest.TestCase):
    def setUp(self) -> None:
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

        self.assertAlmostEqual(80.2, self.b.currentCapacity, places=2)

        self.b.updateDailyValues(1)

        self.assertEqual(0, self.b.currentCapacity)

        self.assertEqual(
            [120, 80.2],
            [round(elm, 2) for elm in list(self.b.dailyRechargeVolumes)[0:2]],
        )

    def test_getSiteVolume(self):
        self.b.currentCapacity = 89.12
        self.b.precip[10] = 20
        self.assertAlmostEqual(60.88, self.b.getBasinVolumeAvailable(10), places=2)

    def test_setUsedVolume(self):
        self.b.currentCapacity = 77.1
        self.b.setUsedVolume(14, 12.89)
        self.assertEqual(12.89, self.b.usedVolume[14])
        self.assertEqual(89.99, self.b.currentCapacity)

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

        self.assertAlmostEqual(wafrApplied, self.b.usedVolume[1])
        self.assertAlmostEqual(9.2 - wafrApplied, wafr["B"][1])

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

        self.assertAlmostEqual(wafrApplied, self.b.usedVolume[1])


class BottleneckTestCase(unittest.TestCase):
    def setUp(self) -> None:

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
        self.assertAlmostEqual(6.84, self.bottleneckA.availableThroughput[10], places=2)

        # update usage
        self.bottleneckA.updateUsage(10, 2.22)
        self.assertAlmostEqual(4.62, self.bottleneckA.availableThroughput[10], places=2)

    def test_getAvailableThroughput(self):
        t = self.bottleneckA.getAvailableThroughput(15)
        self.assertAlmostEqual(6.84, t, places=2)

    def test_getAvailableThroughputCapacityHit(self):
        # update usage
        self.bottleneckA.updateUsage(15, 19.1)
        t = self.bottleneckA.getAvailableThroughput(15)
        self.assertEqual(0, t)

    def test_getBottleneckFromIDWafr(self):
        shouldBeA = bottlenecks.getBottlenecks(self.bottleneckList, [1], "SourceA")[0]
        self.assertEqual("test canal", shouldBeA.name)

    def test_getBottleneckFromIDWaf2(self):
        shouldBeB = bottlenecks.getBottlenecks(self.bottleneckList, [1, 2], "SourceB")[
            0
        ]
        self.assertEqual("second canal", shouldBeB.name)

    def test_getBottleneckFromIDWafrNone(self):
        shouldBeNone = bottlenecks.getBottlenecks(self.bottleneckList, [2], "SourceA")
        self.assertEqual([], shouldBeNone)

    def test_bottleneckCapacityLogger(self):
        self.bottleneckA.updateUsage(15, 19.1)
        self.bottleneckA.updateUsage(20, 50)
        self.bottleneckB.updateUsage(20, 20)
        self.bottleneckB.updateUsage(1, 50)

        capLogger = bottlenecks.bottleneckCapacityLogger(self.bottleneckList)
        self.assertEqual([1], capLogger[15])
        self.assertEqual([1, 2], capLogger[20])
        self.assertEqual([], capLogger[50])

    def test_getAvailableThroughputIrrigationDate(self):
        nonIrr = self.bottleneckB.getAvailableThroughput(199)
        self.assertAlmostEqual(2.39943, nonIrr, places=2)
        irr = self.bottleneckB.getAvailableThroughput(200)
        self.assertAlmostEqual(100, irr, places=2)


class CanalObjectTestCase(unittest.TestCase):
    def setUp(self) -> None:

        self.c = canals.Canal(
            gratID="Example 1",
            maxCapacity=10000,
            percRate=600,
            wafrSources=["SourceB"],
        )

    def test_canal_init(self):
        self.assertEqual(10000, self.c.maxCapacity[0])
        self.assertEqual(600, self.c.percRate)
        self.assertEqual(0, self.c.currentCapacity)

    def test_set_daily_recharge(self):

        # test variables
        i = 18  # index day
        new_vol = 12.234

        # get current recharge volume (should be zero)
        self.assertEqual(0, self.c.dailyRechargeVolumes[i])

        # set to a new volume
        self.c.setDailyRecharge(i, new_vol)

        # check the new daily recharge volume
        self.assertEqual(new_vol, self.c.dailyRechargeVolumes[i])

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
        self.assertEqual(147.3161, self.c.dailyRechargeVolumes[i])

    def test_update_usage(self):

        i = 48  # index day
        v = 19902.12  # value

        self.c.setUsedVolume(i, v)

        # check the new daily recharge volume
        self.assertEqual(v, self.c.usedVolume[i])

        # check the updated current capacity
        self.assertEqual(v, self.c.currentCapacity)

    def test_use_canal_below_cap(self):

        # not sure the structure of WAFR
        wafr = {"test_source": [3.4, 1.3, 9.23, 8.9, 999999]}

        self.c.wafrSources = ["test_source"]

        # use canal when below cap
        i = 2
        self.c.useCanal(i, wafr, "test_source", 9.23)

        self.assertEqual(9.23, self.c.usedVolume[i])

    def test_use_canal_above_cap(self):

        # not sure the structure of WAFR
        wafr = {"test_source": [3.4, 1.3, 9.23, 8.9, 999999]}

        self.c.wafrSources = ["test_source"]

        # use canal above cap
        i = 4
        self.c.useCanal(i, wafr, "test_source", 100000)
        self.assertEqual(10600, self.c.usedVolume[i])


class MockCanalTestCase(unittest.TestCase):
    def setUp(self) -> None:
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

        self.assertEqual(
            [
                178.4,
                80.33,
                10.74,
                1083.6,
                10116.4,
                14.600000000000001,
                106.22,
                17.9,
            ],
            list(self.c.usedVolume)[0:8],
        )
        self.assertEqual(
            [178.4, 80.33, 10.74, 600.0, 600.0, 600.0, 600.0, 600.0],
            list(self.c.dailyRechargeVolumes)[0:8],
        )


class MockCanalProportionalFill(unittest.TestCase):
    def setUp(self) -> None:
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

        self.assertEqual(
            {
                "Blue Lake": [0.0, 0.0, 7900.000000000001, 0, 0, 0, 0.0],
                "Green Lake": [0, 0, 0, 0, 0, 0.0, 1069.2307692307693],
            },
            self.wafr,
        )

    def test_use_canal_usedVolume(self):

        self.assertAlmostEqual(4030.77, sum(self.A.usedVolume[0:7]), 2)
        self.assertAlmostEqual(2200.0, sum(self.B.usedVolume[0:7]), 2)
        self.assertAlmostEqual(7000.0, sum(self.C.usedVolume[0:7]), 2)

    def test_use_canal_dailyRechargeVol(self):

        self.assertAlmostEqual(3400, sum(self.A.dailyRechargeVolumes[0:7]), 2)
        self.assertAlmostEqual(1400, sum(self.B.dailyRechargeVolumes[0:7]), 2)
        self.assertAlmostEqual(5500.0, sum(self.C.dailyRechargeVolumes[0:7]), 2)

    def test_use_canal_currentCapacity(self):

        self.assertAlmostEqual(630.77, self.A.currentCapacity, 2)
        self.assertAlmostEqual(800, self.B.currentCapacity, 2)
        self.assertAlmostEqual(1500.0, self.C.currentCapacity, 2)


class MockCanalTestCaseProportional(unittest.TestCase):
    def setUp(self) -> None:
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

        self.assertAlmostEqual(15, self.A.usedVolume[0], 2)
        self.assertAlmostEqual(15, self.B.usedVolume[0], 2)
        self.assertAlmostEqual(8, self.C.usedVolume[0], 2)

        self.assertAlmostEqual(5, self.A.dailyRechargeVolumes[0], 2)
        self.assertAlmostEqual(5, self.B.dailyRechargeVolumes[0], 2)
        self.assertAlmostEqual(5, self.C.dailyRechargeVolumes[0], 2)

        self.assertAlmostEqual(self.wafr["Blue Lake"][0], 70, 2)
        self.assertAlmostEqual(self.wafr["Red Lake"][0], 0, 2)

    def test_use_canal_day2(self):
        self.assertAlmostEqual(0, self.A.usedVolume[1], 2)
        self.assertAlmostEqual(2.94, self.B.usedVolume[1], 2)
        self.assertAlmostEqual(7.06, self.C.usedVolume[1], 2)

        self.assertAlmostEqual(5, self.A.dailyRechargeVolumes[1], 2)
        self.assertAlmostEqual(5, self.B.dailyRechargeVolumes[1], 2)
        self.assertAlmostEqual(5, self.C.dailyRechargeVolumes[1], 2)

        self.assertAlmostEqual(self.wafr["Blue Lake"][1], 0, 2)
        self.assertAlmostEqual(self.wafr["Red Lake"][1], 0, 2)

    def test_canalFeedBy(self):
        self.assertEqual(
            15,
            self.A.wafrLog["Blue Lake"],
        )
        self.assertEqual(
            2.9411764705882355,
            self.B.wafrLog["Red Lake"],
        )
        self.assertEqual(
            15,
            self.B.wafrLog["Blue Lake"],
        )
        self.assertEqual(
            8.0 + 7.058823529411765,
            self.C.wafrLog["Red Lake"],
        )


class MockCanalTestCaseProportionalWafrOrder(unittest.TestCase):
    def setUp(self) -> None:
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

        self.assertAlmostEqual(15, self.A.usedVolume[0], 2)
        self.assertAlmostEqual(15, self.B.usedVolume[0], 2)
        self.assertAlmostEqual(8, self.C.usedVolume[0], 2)

        self.assertAlmostEqual(5, self.A.dailyRechargeVolumes[0], 2)
        self.assertAlmostEqual(5, self.B.dailyRechargeVolumes[0], 2)
        self.assertAlmostEqual(5, self.C.dailyRechargeVolumes[0], 2)

    def test_use_canal_day2(self):
        self.assertAlmostEqual(0, self.A.usedVolume[1], 2)
        self.assertAlmostEqual(2.941, self.B.usedVolume[1], 2)
        self.assertAlmostEqual(7.058, self.C.usedVolume[1], 2)

        self.assertAlmostEqual(5, self.A.dailyRechargeVolumes[1], 2)
        self.assertAlmostEqual(5, self.B.dailyRechargeVolumes[1], 2)
        self.assertAlmostEqual(5, self.C.dailyRechargeVolumes[1], 2)


class OFRTestCase(unittest.TestCase):
    def setUp(self) -> None:
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

        self.assertEqual(
            42.024,
            self.ofr.getSiteVolume(0, self.cropCalendar),
        )

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

        self.assertAlmostEqual(wafrApplied, self.ofr.ofrUsedVolume[1])
        self.assertAlmostEqual(33.975, self.ofr.ofrUnusedVolume[1])
        self.assertAlmostEqual(9.2 - wafrApplied, wafr["B"][1])


class ModelMainRun(unittest.TestCase):
    def setUp(self) -> None:
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

        self.assertEqual(
            {
                "A": [9294.099999999999, 19393.8, 19393.8],
                "B": [0.0, 4.199999999999999, 0],
            },
            r["wafr"],
        )

    def test_runGRAT_canals(self):
        r = grat.processYear(
            self.site_list,
            self.bottleneckList,
            self.wafr,
            self.cropCalendar,
            precip=None,
        )

        self.assertEqual(1800.0, sum(r["sites"][0].dailyRechargeVolumes))

    def test_runGRAT_sites(self):
        r = grat.processYear(
            self.site_list,
            self.bottleneckList,
            self.wafr,
            self.cropCalendar,
            precip=None,
        )

        self.assertAlmostEqual(
            3.6, sum(r["sites"][1].dailyRechargeVolumes)
        )  # basin 1.2 perc rate x 3 days
        self.assertAlmostEqual(
            10.2, sum(r["sites"][2].ofrDailyRechargeVolumes)
        )  # site 1 [4.2, 5. , 1.]


class ModelMainRunMultiYear(unittest.TestCase):
    def setUp(self) -> None:
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

        year_2 = grat.processYear(
            sites2, bottleneckList2, self.wafr2, self.cropCalendar, precip=None
        )

        # years should not be equal
        self.assertNotEqual(year_1["sites"], year_2["sites"])


class ILTestCase(unittest.TestCase):
    def setUp(self) -> None:
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
            bottlenecks.Bottleneck(
                bottleneckID=2, name="canal name", capacity=1000, wafrSources=["A"]
            )
        ]

    def test_getSiteVolume(self):

        self.assertEqual(
            42.024,
            self.il.getSiteVolume(0, self.ilCropCalendar, inlieu=True),
        )

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
        self.assertAlmostEqual(0, self.il.usedVolume[1])

        # modify the in-lieu variables
        self.assertAlmostEqual(39.924, self.il.inLieuUsedVolume[1])
        self.assertAlmostEqual(0, self.il.inLieuUnusedVolume[1])

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
        self.assertAlmostEqual(39.924, self.il.inLieuUsedVolume[1])
        self.assertAlmostEqual(0, self.il.inLieuUnusedVolume[1])

        # should be not impacted by precip
        # acres x ofr ccc
        # 10.2*12.4 = 126.48
        self.assertAlmostEqual(126.48, self.il.ofrUsedVolume[1])
        self.assertAlmostEqual(0, self.il.ofrUnusedVolume[1])

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
        self.assertAlmostEqual(42.024, self.il.inLieuUsedVolume[1])
        self.assertAlmostEqual(0, self.il.inLieuUnusedVolume[1])

        self.assertAlmostEqual(100 - 42.024, self.il.ofrUsedVolume[1])
        # self.assertAlmostEqual(42.024, self.il.unusedVolume[1])


class WafrSortOrder(unittest.TestCase):
    def setUp(self) -> None:
        self.wafr = {"SourceB": [50, 12000], "SourceA": [19, 300000]}

    def test_day0(self):
        self.assertEqual(
            ["SourceB", "SourceA"], funcs.sortWafrSourceByVolume(self.wafr, 0)
        )

    def test_day1(self):
        self.assertEqual(
            ["SourceA", "SourceB"], funcs.sortWafrSourceByVolume(self.wafr, 1)
        )


class WafrAvailability(unittest.TestCase):
    def setUp(self) -> None:
        self.wafr = {"SourceB": [50, 12000, 0, 0], "SourceA": [19, 300000, 0, 1]}

    def test_day0(self):
        self.assertTrue(funcs.checkWafrAvailability(self.wafr, 0))

    def test_day2(self):
        self.assertFalse(funcs.checkWafrAvailability(self.wafr, 2))


class GetCompatibleCrops(unittest.TestCase):
    def setUp(self) -> None:
        self.ccc = {
            "Corn": {"Poor": [0, 1.2, 3, 0], "Good": [3, 0, 1, 0]},
            "Rice": {"Great": [0, 0, 1.2, 0], "Good": [0, 2.1, 0, 0]},
        }

    def test_day0(self):
        self.assertEqual(
            [("Corn", "Good")], funcs.getCompatibleCropsSoilsForDay(self.ccc, 0)
        )

    def test_day1(self):
        self.assertEqual(
            [("Corn", "Poor"), ("Rice", "Good")],
            funcs.getCompatibleCropsSoilsForDay(self.ccc, 1),
        )

    def test_day2(self):
        self.assertEqual(
            [("Corn", "Poor"), ("Corn", "Good"), ("Rice", "Great")],
            funcs.getCompatibleCropsSoilsForDay(self.ccc, 2),
        )

    def test_day3(self):
        self.assertEqual(
            [],
            funcs.getCompatibleCropsSoilsForDay(self.ccc, 3),
        )

    def test_None(self):
        self.assertEqual(
            [],
            funcs.getCompatibleCropsSoilsForDay(None, 2),
        )


class ModelMainRunSecondaryWafr(unittest.TestCase):
    def setUp(self) -> None:
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
            wafrSourcesSecondary=["A"],
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
            wafrSourcesSecondary=["B"],
        )
        self.site3 = basins.Basin(
            gratID=33,
            acres=2.5,
            rechargeType="Basin",
            percRate=1.2,
            maxCapacity=100,
            bottleneckIDs=[2],
            wafrSourcesPrimary=["A"],
            wafrSourcesSecondary=["B"],
        )
        self.site_list = [self.canal1, self.site3, self.site1, self.site2]
        self.wafr = {"A": [20000.3, 20000, 20000], "B": [4.2, 9.2, 1]}

        # need bottleneck obj to mock
        self.bottleneckList = [
            bottlenecks.Bottleneck(
                bottleneckID=2,
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

        self.assertEqual(
            {
                "A": [9294.099999999999 - 0.8, 19393.8, 19393.8 - 4],
                "B": [0.0, 4.199999999999999, 0],
            },
            r["wafr"],
        )

    def test_runGRAT_canals(self):
        r = grat.processYear(
            self.site_list,
            self.bottleneckList,
            self.wafr,
            self.cropCalendar,
            precip=None,
        )

        self.assertEqual(1800.0, sum(r["sites"][0].dailyRechargeVolumes))

    def test_runGRAT_sites(self):
        r = grat.processYear(
            self.site_list,
            self.bottleneckList,
            self.wafr,
            self.cropCalendar,
            precip=None,
        )

        self.assertAlmostEqual(
            3.6, sum(r["sites"][1].dailyRechargeVolumes)
        )  # basin 1.2 perc rate x 3 days

        self.assertAlmostEqual(
            15, sum(r["sites"][2].ofrDailyRechargeVolumes)
        )  # site 1 [4.2, 5. , 1.]


class SubsetSiteList(unittest.TestCase):
    def setUp(self) -> None:
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
        self.assertEqual(["CalDuck"], funcs.sortWafrSourceByVolume(self.wafr, 0))
        self.assertEqual([], funcs.sortWafrSourceByVolume(self.wafr, 1))
        self.assertEqual(
            ["Calaveras", "Duck", "CalDuck"], funcs.sortWafrSourceByVolume(self.wafr, 4)
        )


class TestTurnoutLimitConversion(unittest.TestCase):
    def test_turnoutLimitConversion_with_valid_input(self):
        cfsRate = 20
        expected_output = 39.66
        self.assertAlmostEqual(
            farms.turnoutLimitConversion(cfsRate), expected_output, places=2
        )


class CalcTransferLimitsTestCase(unittest.TestCase):
    def setUp(self) -> None:
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
        self.assertEqual(30.0, result["District1"])

    def test_acrefeet_used_when_percent_not_set(self):
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {"District1": {"ACREFEET": 15, "THRESHOLD": 10}},
        )
        self.assertEqual(15, result["District1"])

    def test_acrefeet_used_when_percent_none(self):
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {"District1": {"ACREFEET": 15, "PERCENT": None, "THRESHOLD": 10}},
        )
        self.assertEqual(15, result["District1"])

    def test_acrefeet_defaults_to_zero_when_missing(self):
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {"District1": {"THRESHOLD": 10}},
        )
        self.assertEqual(0, result["District1"])

    def test_multiple_districts(self):
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {
                "District1": {"PERCENT": 0.5, "THRESHOLD": 10},
                "District2": {"ACREFEET": 5, "THRESHOLD": 2},
            },
        )
        self.assertEqual(30.0, result["District1"])
        self.assertEqual(5, result["District2"])

    def test_below_threshold_sets_zero(self):
        with self.assertLogs(level="WARNING"):
            result = calc_transfer_limits(
                self.wafr,
                self.transfer_sources,
                {"District1": {"PERCENT": 0.5, "THRESHOLD": 1000}},
            )
        self.assertEqual(0, result["District1"])

    def test_transfer_wafr_sources_included_in_output(self):
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {"District1": {"PERCENT": 0.5, "THRESHOLD": 10}},
        )
        self.assertEqual(self.transfer_sources, result["transfer_wafr_sources"])

    def test_threshold_missing_sets_zero_and_logs(self):
        with self.assertLogs(level="WARNING"):
            result = calc_transfer_limits(
                self.wafr,
                self.transfer_sources,
                {"District1": {"PERCENT": 0.5}},
            )
        self.assertEqual(0, result["District1"])

    def test_threshold_missing_does_not_block_other_districts(self):
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {
                "District1": {"PERCENT": 0.5},  # no THRESHOLD
                "District2": {"ACREFEET": 5, "THRESHOLD": 2},
            },
        )
        self.assertEqual(0, result["District1"])
        self.assertEqual(5, result["District2"])

    def test_threshold_equal_to_total_is_not_below_threshold(self):
        # sum(A) == 60, so a THRESHOLD of exactly 60 should not zero it out
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {"District1": {"PERCENT": 0.5, "THRESHOLD": 60}},
        )
        self.assertEqual(30.0, result["District1"])

    def test_percent_zero_is_not_treated_as_missing(self):
        result = calc_transfer_limits(
            self.wafr,
            self.transfer_sources,
            {"District1": {"PERCENT": 0, "ACREFEET": 99, "THRESHOLD": 10}},
        )
        self.assertEqual(0, result["District1"])

    def test_source_missing_from_wafr_sets_zero_and_logs(self):
        transfer_sources = {"District1": "MissingSource"}
        with self.assertLogs(level="WARNING"):
            result = calc_transfer_limits(
                self.wafr,
                transfer_sources,
                {"District1": {"PERCENT": 0.5, "THRESHOLD": 10}},
            )
        self.assertEqual(0, result["District1"])

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
        self.assertEqual(30.0, result["District1"])
        self.assertEqual(5, result["District2"])

    def test_no_district_goals_returns_only_sources(self):
        result = calc_transfer_limits(self.wafr, self.transfer_sources, {})
        self.assertEqual({"transfer_wafr_sources": self.transfer_sources}, result)

    def test_district_transfer_goals_defaults_to_empty_when_omitted(self):
        result = calc_transfer_limits(self.wafr, self.transfer_sources)
        self.assertEqual({"transfer_wafr_sources": self.transfer_sources}, result)


if __name__ == "__main__":
    unittest.main()
