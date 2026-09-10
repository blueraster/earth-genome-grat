"""Shared helpers: timing, pickle I/O, and WAFR and crop calendar queries."""

import logging
import os
import pickle
from time import time

logger = logging.getLogger(__name__)


def timer_func(func):
    """Log how long the decorated function took to run.

    Args:
        func: the function to time.

    Returns:
        The wrapped function, which logs its runtime at INFO level once it
        returns and then passes the result through unchanged.
    """

    def wrap_func(*args, **kwargs):
        t1 = time()
        result = func(*args, **kwargs)
        t2 = time()
        logger.info("Function %r executed in %.4fs", func.__name__, t2 - t1)
        return result

    return wrap_func


def save_pickle(directory_path, file_name, pickle_content):
    """Write an object to disk as a pickle.

    Args:
        directory_path: folder to write into. Must already exist.
        file_name: name of the file, e.g. `"results.pickle"`.
        pickle_content: object to serialise.

    Returns:
        Path to the file written.
    """
    output_file_path = os.path.join(directory_path, file_name)
    with open(output_file_path, "wb") as file:
        pickle.dump(pickle_content, file, protocol=pickle.HIGHEST_PROTOCOL)
    return output_file_path


def load_pickle(pickle_path):
    """Read a pickled object back from disk.

    Warning:
        Unpickling executes arbitrary code from the file. Only use this on files
        this package wrote, never on a pickle from an untrusted source.

    Args:
        pickle_path: full path to the pickled object.

    Returns:
        The unpickled object.
    """
    with open(pickle_path, "rb") as file:
        return pickle.load(file)


def sort_wafr_source_by_volume(wafr: dict, day: int):
    """Rank the WAFR sources that have a non-zero volume on a day, largest first.

    Args:
        wafr: volume available (acre-feet) per day, keyed by WAFR source name.
        day: zero-indexed day of the water year.

    Returns:
        Source names in descending order of volume. Sources sitting at exactly
        zero that day are omitted; the test is for non-zero, so a negative
        volume is kept and sorts last.
    """
    non_zero_sources = [source for source in wafr if wafr[source][day] != 0]
    return sorted(non_zero_sources, key=lambda x: wafr[x][day], reverse=True)


def check_wafr_availability(wafr, day):
    """Report whether any WAFR source has water left on a day.

    Used to skip the remaining allocation work once the day's water is spent.

    Args:
        wafr: volume available (acre-feet) per day, keyed by WAFR source name.
        day: zero-indexed day of the water year.

    Returns:
        `True` if any source has water that day, `False` otherwise.
    """
    # get the day's volume by looping over the wafr dictionary and summing the total
    total_volume = sum([v[day] for k, v in wafr.items()])
    return total_volume > 0


def get_compatible_crops_soils_for_day(crop_compatibility_calendar: dict, day: int):
    """List the crop and soil combinations that can take water on a day.

    Args:
        crop_compatibility_calendar: accepted application rate (feet per day),
            indexed as `[crop][soil_type][day]`. `None` is treated as an empty
            calendar.
        day: zero-indexed day of the water year.

    Returns:
        `(crop, soil_type)` pairs with a non-zero accepted rate that day.
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
    """Narrow in-lieu sites to those that could take water right now.

    A site qualifies when at least one of the supplied sources can reach it and
    its crop and soil combination is accepting water.

    Args:
        in_lieu_sites: in-lieu sites to filter.
        wafr_source_list: names of the WAFR sources that currently have water.
        crop_soil_types: `(crop, soil_type)` pairs accepting water today, as
            returned by `get_compatible_crops_soils_for_day`.

    Returns:
        The subset of sites that could take water.
    """
    # subset in lieu sites by the ones that can receive wafr from sources with water
    in_lieu_sites_can_accept_wafr = [
        s for s in in_lieu_sites if any(elem in s.wafr_sources for elem in wafr_source_list)
    ]

    # subset by field that have non-zero values for the day in the appropriate crop compatibility calendar
    return [s for s in in_lieu_sites_can_accept_wafr if (s.in_lieu_crop, s.soil_type) in crop_soil_types]


def subset_ofr_can_accept_water(ofr_sites, wafr_source_list, crop_soil_types):
    """Narrow on-farm sites to those that could take water right now.

    A site qualifies when at least one of the supplied sources can reach it and
    its crop and soil combination is accepting water.

    Args:
        ofr_sites: on-farm recharge sites to filter.
        wafr_source_list: names of the WAFR sources that currently have water.
        crop_soil_types: `(crop, soil_type)` pairs accepting water today, as
            returned by `get_compatible_crops_soils_for_day`.

    Returns:
        The subset of sites that could take water.
    """
    # subset in sites by the ones that can receive wafr from sources with water
    ofr_sites_can_accept_wafr = [s for s in ofr_sites if any(elem in s.wafr_sources for elem in wafr_source_list)]

    # subset by field that have non-zero values for the day in the appropriate crop compatibility calendar
    return [s for s in ofr_sites_can_accept_wafr if (s.crop, s.soil_type) in crop_soil_types]
