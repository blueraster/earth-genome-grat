"""
Utility functions
"""

import logging
import os
import pickle
from time import time


def timer_func(func):
    # This function shows the execution time of
    # the function object passed
    def wrap_func(*args, **kwargs):
        t1 = time()
        result = func(*args, **kwargs)
        t2 = time()
        logging.info(f"Function {func.__name__!r} executed in {(t2 - t1):.4f}s")
        return result

    return wrap_func


def save_pickle(directory_path, file_name, pickle_content):
    """
    Saves a pickle to disk
    Args:
        directory_path: output folder
        file_name: name of the file 'something.pickle'
        pickle_content: stuff to write to the pickle

    Returns: path to the output file

    """
    output_file_path = os.path.join(directory_path, file_name)
    with open(output_file_path, "wb") as file:
        pickle.dump(pickle_content, file, protocol=pickle.HIGHEST_PROTOCOL)
    return output_file_path


def load_pickle(pickle_path):
    """
    Loads a pickle from disk
    Args:
        pickle_path: full path to the pickled object

    Returns: unpickled object

    """
    with open(pickle_path, "rb") as file:
        return pickle.load(file)


def sort_wafr_source_by_volume(wafr: dict, day: int):
    """
    Sorts WAFR sources names by the volume available for the date
    Args:
        wafr: dictionary of water available for recharge
        day: zero-indexed day of the water year

    Returns: names of the wafr sources in order (most volume first) with non-zero volume on the specified day

    """
    non_zero_sources = [source for source in wafr if wafr[source][day] != 0]
    return sorted(non_zero_sources, key=lambda x: wafr[x][day], reverse=True)


def check_wafr_availability(wafr, day):
    """
    Checks if water is available from ANY WAFR source
    Args:
        wafr: dictionary of water available for recharge
        day: zero-indexed day of the water year

    Returns: True is there is water, False no water from WAFR

    """

    # get the day's volume by looping over the wafr dictionary and summing the total
    total_volume = sum([v[day] for k, v in wafr.items()])
    return total_volume > 0


def get_compatible_crops_soils_for_day(crop_compatibility_calendar: dict, day: int):
    """
    Returns a list of crops that can accept water for a given day
    Args:
        crop_compatibility_calendar: crop compatibility calendar dictionary
        day: zero-indexed day of the water year

    Returns: list of crops + soil types that can accept volume for recharge. Array of tuples (crop, soil).

    """
    if crop_compatibility_calendar is None:
        return []
    return [
        (crop, soil)
        for crop, soil_types in crop_compatibility_calendar.items()
        for soil, days in soil_types.items()
        if days[day] > 0
    ]


def subset_in_lieu_can_accept_water(in_lieu_sites, wafr_source_list, crop_soil_types):
    """

    Args:
        in_lieu_sites:
        wafr_source_list:
        crop_soil_types:

    Returns:

    """

    # subset in lieu sites by the ones that can receive wafr from sources with water
    in_lieu_sites_can_accept_wafr = [
        s for s in in_lieu_sites if any(elem in s.wafr_sources for elem in wafr_source_list)
    ]

    # subset by field that have non-zero values for the day in the appropriate crop compatibility calendar
    return [s for s in in_lieu_sites_can_accept_wafr if (s.in_lieu_crop, s.soil_type) in crop_soil_types]


def subset_ofr_can_accept_water(ofr_sites, wafr_source_list, crop_soil_types):
    """

    Args:
        ofr_sites:
        wafr_source_list:
        crop_soil_types:

    Returns:

    """

    # subset in sites by the ones that can receive wafr from sources with water
    ofr_sites_can_accept_wafr = [s for s in ofr_sites if any(elem in s.wafr_sources for elem in wafr_source_list)]

    # subset by field that have non-zero values for the day in the appropriate crop compatibility calendar
    return [s for s in ofr_sites_can_accept_wafr if (s.crop, s.soil_type) in crop_soil_types]
