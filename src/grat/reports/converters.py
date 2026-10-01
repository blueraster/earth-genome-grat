"""This module contains functions for converting day of water year to month name and summing daily values by month."""

import datetime


def get_month_name(year: int, day_of_water_year: int):
    """Get the month name from a day of the water year.

    Parameters:
        year (int): water year
        day_of_water_year (int): The day of the water year (1-365 or 1-366 for a leap year).

    Returns:
        str: The name of the month corresponding to the input day of the water year.
    """
    start_date = datetime.date(year - 1, 10, 1)
    delta = datetime.timedelta(days=day_of_water_year - 1)
    date = start_date + delta
    return date.strftime("%B")


def get_num_days_in_month(year, month_name):
    """Get the number of days in a given month of a given water year.

    Parameters:
        year (int): The year.
        month_name (str): The name of the month (e.g., "January", "February", etc.).

    Returns:
        int: The number of days in the given month of the given year.
    """
    # Get the number of days in the given month of the given year
    if month_name == "February":
        # check if it is a leap year
        if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
            return 29
        return 28
    if month_name in ["April", "June", "September", "November"]:
        return 30
    return 31


def is_leap_year(year):
    """Determine whether a year is a leap year or not.

    Parameters:
        year (int): The year to check.

    Returns:
        bool: True if the year is a leap year, False otherwise.
    """
    if year % 4 == 0:
        if year % 100 == 0:
            return year % 400 == 0
        return True
    return False


def find_wy_month_index(month_name):
    """Returns the index position of the months in the order of the water year (starts in october).

    Args:
        month_name: name of the month

    Returns: index position of the month (oct -> sept) in the water year
    """
    month_list = [
        "October",
        "November",
        "December",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
    ]
    return month_list.index(month_name.capitalize())


def sum_array_by_month(daily_values, leap_year=False):
    """Slices an array of daily values into months and sums each one.

    The months are **water-year** months, so the first entry of the returned list is
    October and the last is September. Reports 06 and 07 label these sums `1` to `12`,
    which means their column `"1"` holds October, not January.

    Args:
        daily_values: daily values ordered by day of the water year
        leap_year: whether this water year has 366 days

    Returns:
        A list of 12 monthly sums, October first
    """
    # Initialize a dictionary of month lengths for a non-leap year
    month_lengths = {
        10: 31,
        11: 30,
        12: 31,
        1: 31,
        2: 28,
        3: 31,
        4: 30,
        5: 31,
        6: 30,
        7: 31,
        8: 31,
        9: 30,
    }

    # Update the month lengths for a leap year
    if leap_year:
        month_lengths[2] = 29

    monthly_groups = []
    start_day = 0

    # Loop over each month in the year
    for _month, num_days in month_lengths.items():
        # Sum the daily values for the current month
        monthly_sum = sum(daily_values[start_day : start_day + num_days])
        monthly_groups.append(monthly_sum)

        # Update the start day for the next month
        start_day += num_days

    return monthly_groups
