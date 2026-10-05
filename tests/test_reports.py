import os
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from grat.reports import builders, catalog, converters, selector, writers

wd = os.path.abspath(os.path.dirname(__file__))


def test_is_leap_year():
    assert converters.is_leap_year(2000) is True
    assert converters.is_leap_year(2001) is False
    assert converters.is_leap_year(2002) is False
    assert converters.is_leap_year(2003) is False
    assert converters.is_leap_year(2004) is True
    assert converters.is_leap_year(2048) is True
    assert converters.is_leap_year(2100) is False
    assert converters.is_leap_year(2096) is True


def test_month_name_from_dowy():
    assert converters.get_month_name(2000, 1) == "October"
    assert converters.get_month_name(2000, 31) == "October"
    assert converters.get_month_name(2000, 32) == "November"
    assert converters.get_month_name(2000, 32) == "November"
    assert converters.get_month_name(2000, 152) == "February"  # leap year
    assert converters.get_month_name(2001, 152) == "March"  # non leap year
    assert converters.get_month_name(2000, 366) == "September"  # leap year
    assert converters.get_month_name(2001, 366) == "October"  # non leap year (isn't valid value)


def test_num_days_in_month():
    assert converters.get_num_days_in_month(2000, "February") == 29  # leap year
    assert converters.get_num_days_in_month(2001, "February") == 28
    assert converters.get_num_days_in_month(2001, "March") == 31
    assert converters.get_num_days_in_month(2001, "April") == 30
    assert converters.get_num_days_in_month(2001, "October") == 31


def test_wy_month_index():
    assert converters.find_wy_month_index("February") == 4
    assert converters.find_wy_month_index("September") == 11


def test_sum_array_by_month():
    d = np.full(366, 1.0)
    assert converters.sum_array_by_month(d) == [
        31.0,
        30.0,
        31.0,
        31.0,
        28.0,
        31.0,
        30.0,
        31.0,
        30.0,
        31.0,
        31.0,
        30.0,
    ]
    assert converters.sum_array_by_month(d, True) == [
        31.0,
        30.0,
        31.0,
        31.0,
        29.0,
        31.0,
        30.0,
        31.0,
        30.0,
        31.0,
        31.0,
        30.0,
    ]


def test_wy_month_index_ignores_case():
    assert converters.find_wy_month_index("october") == 0
    assert converters.find_wy_month_index("SEPTEMBER") == 11


def test_sum_array_by_month_short_array():
    # a partial year sums what is there and leaves the remaining months at zero
    assert converters.sum_array_by_month([1.0] * 31) == [31.0] + [0] * 11


def test_expand():
    assert catalog.expand([]) == frozenset()
    assert catalog.expand(["daily_wafr_report"]) == {"daily_wafr_report"}
    # reports built from another report's csv pull that report in
    assert catalog.expand(["yearly_recharge_volumes"]) == {"yearly_recharge_volumes", "annual_summary_recharge"}
    with pytest.raises(KeyError):
        catalog.expand(["daily_wafr_report", "not_a_report"])


def test_every_csv_report_has_a_filename():
    assert frozenset(writers.REPORT_FILES) >= catalog.CSV_REPORTS


def test_daily_summary_recharge_pads_short_wafr():
    raw_wafr = {"River": [5.0] * 365}
    wafr = {"River": [2.0] * 365}

    df = builders.daily_summary_recharge(2001, [], raw_wafr, wafr)

    assert len(df) == 366
    assert df["Total WAFR (AF)"].sum() == 1825.0
    assert df["Total Unused WAFR (AF)"].sum() == 730.0
    assert df["Total WAFR Applied (AF)"].sum() == 1095.0
    # the caller's lists are read again later, so they must not be padded in place
    assert len(raw_wafr["River"]) == 365
    assert len(wafr["River"]) == 365


def test_annual_summary_recharge_number_of_days():
    daily = pd.concat(
        [
            builders.daily_summary_recharge(2000, [], {}, {}),  # leap year
            builders.daily_summary_recharge(2001, [], {}, {}),
        ]
    )
    df = builders.annual_summary_recharge(daily)
    assert df["Year"].tolist() == [2000, 2001]
    assert df["Number of Days"].tolist() == [366, 365]


def test_daily_wafr_report_drops_day_366():
    wafr = {"River": [1.0] * 366, "Canal": [2.0] * 366}

    df = builders.daily_wafr_report(2001, wafr)
    assert len(df) == 365
    assert df.columns.tolist() == ["Year", "Day", "Canal", "River"]  # sources sorted

    df = builders.daily_wafr_report(2000, wafr)  # leap year
    assert len(df) == 366


def test_bottlenecks_capacity_limitations_report():
    bottleneck_list = [
        SimpleNamespace(bottleneck_id=10, available_throughput=[0, 0, 5] + [1] * 363),
        SimpleNamespace(bottleneck_id=2, available_throughput=[1] * 366),
        SimpleNamespace(bottleneck_id=1, available_throughput=[0] * 366),
    ]

    df = builders.bottlenecks_capacity_limitations_report(2001, bottleneck_list)

    # natural sort, so 10 comes after 2
    assert df.columns.tolist() == ["Year", "BottleneckID 1", "BottleneckID 2", "BottleneckID 10"]
    assert df.iloc[0].tolist() == [2001, 366, 0, 2]


def test_annual_recharge_by_grouping():
    assert builders.annual_recharge_by_grouping(2001, []) is None

    site_list = [
        # canal volume is split evenly across its subbasins
        SimpleNamespace(subbasin=["Kings", "Kaweah"], district="D1", wafr_log={"River": 100.0}),
        SimpleNamespace(subbasin="Kings", district="D1", wafr_log={"River": 10.0}),
        # sites without a subbasin or district are left out
        SimpleNamespace(subbasin=None, district="D1", wafr_log={"River": 1000.0}),
    ]

    df = builders.annual_recharge_by_grouping(2001, site_list)

    assert df.columns.tolist() == ["Year", "subbasin", "district", "wafrsource", "value"]
    assert sorted(df.itertuples(index=False, name=None)) == [
        (2001, "Kaweah", "D1", "River", 50.0),
        (2001, "Kings", "D1", "River", 60.0),
    ]


def test_total_recharge_by_sustainability_zone_report():
    site_list = [
        SimpleNamespace(sustainability_zone="1.0", recharge_type="Basin", daily_recharge_volumes=[1.0] * 10),
        SimpleNamespace(
            sustainability_zone=1,
            recharge_type="OFR",
            ofr_daily_recharge_volumes=[1.0] * 2,
            in_lieu_daily_recharge_volumes=[1.0] * 3,
        ),
        SimpleNamespace(sustainability_zone=None, recharge_type="Canal", daily_recharge_volumes=[2.0] * 3),
        # a site whose volumes cannot be totalled is skipped rather than failing the report
        SimpleNamespace(grat_id="bad", sustainability_zone="2", recharge_type="Basin", daily_recharge_volumes=None),
    ]

    df = builders.total_recharge_by_sustainability_zone_report(2001, site_list)

    assert df.columns.tolist() == ["Year", "sustainabilityZone", "acreFeet"]
    assert dict(zip(df["sustainabilityZone"], df["acreFeet"], strict=True)) == {"1": 15.0, "No Zone": 6.0}


def test_total_recharge_by_district_report_skips_missing_districts():
    site_list = [
        SimpleNamespace(district=None, recharge_type="Basin", daily_recharge_volumes=[1.0] * 10),
        SimpleNamespace(district="<Null>", recharge_type="Basin", daily_recharge_volumes=[1.0] * 10),
        SimpleNamespace(district="5.0", recharge_type="Basin", daily_recharge_volumes=[1.0] * 10),
        SimpleNamespace(
            district=" Delta ",
            recharge_type="OFR",
            ofr_daily_recharge_volumes=[1.0] * 2,
            in_lieu_daily_recharge_volumes=[1.0] * 3,
        ),
    ]

    df = builders.total_recharge_by_district_report(2001, site_list)

    assert dict(zip(df["district"], df["acreFeet"], strict=True)) == {"5": 10.0, "Delta": 5.0}


def test_post_process_max_per_site():
    df = pd.DataFrame(
        {
            "gratID": ["a", "a", "b"],
            "Year": [2000, 2001, 2000],
            "usedVolume": [1.234, 5.678, 0.0],
        }
    )
    # sites that never used any water are omitted
    assert selector.post_process_max_per_site(df) == {"a": 5.68}


def test_post_process_recharge_by_sustain_zone():
    df = pd.DataFrame({"sustainabilityZone": ["1", "1", "No Zone"], "acreFeet": [1.004, 2.0, 3.0]})
    assert selector.post_process_recharge_by_sustain_zone(df) == {"1": 3.0, "No Zone": 3.0}

    # zones read back from csv as floats are keyed as whole numbers
    df = pd.DataFrame({"sustainabilityZone": [1.0, 2.0], "acreFeet": [1.0, 2.0]})
    assert selector.post_process_recharge_by_sustain_zone(df) == {"1": 1.0, "2": 2.0}


def test_write_csv_append(tmp_path):
    df = pd.DataFrame({"Year": [2001], "value": [1.5]})

    # appending writes the header only once
    writers.write_csv(df, str(tmp_path), "appended.csv", append=True)
    writers.write_csv(df, str(tmp_path), "appended.csv", append=True)
    appended = pd.read_csv(tmp_path / "appended.csv")
    assert appended.columns.tolist() == ["Year", "value"]
    assert len(appended) == 2

    # without append the file is replaced
    writers.write_csv(df, str(tmp_path), "replaced.csv")
    writers.write_csv(df, str(tmp_path), "replaced.csv")
    assert len(pd.read_csv(tmp_path / "replaced.csv")) == 1
