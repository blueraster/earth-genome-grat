"""Data loader helper functions."""

import datetime


def water_year(year: int, month: int) -> int:
    """October 1st is the start of the water year. IE Oct 1st, 2022 is in Water Year 2023.

    Args:
        year: calendar year
        month: calendar month

    Returns:
        water year
    """
    return int(year + 1) if month >= 10 else int(year)


def day_of_water_year(year: int, month: int, day: int) -> int:
    """Calculate the day of the water year (DOWY) based on the given calendar year, month, and day.

    The water year starts on October 1st, so for example, October 1st, 2022 is in Water Year 2023.

    Args:
        year: Calendar year
        month: Calendar month
        day: Calendar day

    Returns:
        Day of the water year (DOWY)
    """
    start_wy_date = datetime.date(year=year if month >= 10 else year - 1, month=10, day=1)
    current_date = datetime.date(year=year, month=month, day=day)
    days_since_start = (current_date - start_wy_date).days + 1
    return int(days_since_start)


def rename_dictionary_keys(d: dict, keymap: dict) -> dict:
    """Replaces keys in a dictionary with new names.

    Args:
        d: input dictionary
        keymap: key values to rename ({'from-key': 'to-key'})

    Returns:
        dictionary
    """
    return {keymap.get(key, key): value for key, value in d.items()}


def split_multivalues(string):
    """Split a string of comma separated values into a list.

    Args:
        string: string of comma separated values

    Returns:
        list of values
    """
    if string is None:
        return []
    return string.split(",")


def single_value_as_string(list_of_values):
    """If the list has a single value, return it as a string. Otherwise return the list.

    Args:
        list_of_values: list of values

    Returns:
        string or list
    """
    if len(list_of_values) == 1:
        return list_of_values[0]
    return list_of_values
