import os

import numpy as np

from grat.reports import converters

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
