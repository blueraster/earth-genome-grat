"""
Delivery limits to collection of sites
"""

import numpy as np


class Bottleneck:
    def __init__(
        self,
        bottleneck_id: int,
        name: str = None,
        capacity: float = None,
        wafr_sources: list = None,
        capacity_irrigation: float = None,
        irrigation_days: list = None,
        **kwargs,
    ):
        """
        Defines the bottleneck object that restricts daily flow to groups of sites. Each bottleneck is associated
        with one or more WAFR sources. When provided, irrigation_days + capacity_irrigation modifies the
        default daily bottleneck rate value during the days that are in the irrigation season.

        Args:
            bottleneck_id:  bottleneck identifier
            name: name of bottleneck (optional)
            capacity: default limit in acre-feet per day.
            wafr_sources: name of the WAFR sources that supply water
            capacity_irrigation: limit in acre-feet per day during irrigation season.
            irrigation_days: list of days (zero index day of water year) that use the irrigation season capacity rate.
            **kwargs: Optional additional parameters

        """
        # catch all extra kwargs provided to class instance
        self.__dict__.update(kwargs)  # catch all for all unknown kwargs

        self.bottleneck_id = bottleneck_id
        self.name = name
        self.wafr_sources = wafr_sources if wafr_sources is not None else []  # names of the WAFR sources
        self.capacity = capacity
        self.capacity_irrigation = capacity_irrigation
        self.available_throughput = self._calculate_throughput(
            irrigation_days if irrigation_days is not None else []
        )  # volume in acre-feet per day

    def _calculate_throughput(self, irrigation_days=None):

        if irrigation_days is None:
            irrigation_days = []

        throughput_array = np.full(366, fill_value=0.0)  # init empty array
        for d in range(0, 366):
            if d in irrigation_days:
                throughput_array[d] = self.capacity_irrigation
            else:
                throughput_array[d] = self.capacity

        return throughput_array

    def update_usage(self, day: int, amount: float):
        """
        Updates the bottleneck available throughput by subtracting the volume used by the site

        Args:
            day: zero-indexed day of the water year
            amount: usage volume (AF) to subtract
        """
        self.available_throughput[day] -= amount
        return

    def get_available_throughput(self, day: int):
        """
        Volume available to pass through the bottleneck

        Args:
            day: zero-indexed day of the water year

        Returns:
            daily_throughput: throughput volume (AF) for a given bottleneck and day
        """
        daily_throughput = self.available_throughput[day]
        if daily_throughput <= 0:
            return 0
        return daily_throughput

    def __repr__(self):
        return f"{self.__dict__}"


# operations on list of bottlenecks
def get_bottlenecks(bottleneck_list, bottleneck_ids, wafr_source):
    """
    Returns the object that matches the specific bottleneck_id and WAFR source
    Args:
        bottleneck_list: list of bottleneck objects
        bottleneck_ids: identifier for the bottlenecks
        wafr_source: name of the WAFR source that supplies water through the bottleneck

    Returns: list of bottleneck objects that match the conditions

    """
    try:
        return [b for b in bottleneck_list if b.bottleneck_id in bottleneck_ids and wafr_source in b.wafr_sources]
    except KeyError:
        return []


def bottleneck_capacity_logger(bottleneck_list):
    """
    Daily array of the bottlenecks that reached capacity
    Args:
        bottleneck_list: list of bottleneck objects

    Returns: array containing the list of bottleneck ids that reached capacity per day

    """

    capacity_hit_log = [[] for _ in range(365)]  # assumes multiple bottlenecks per day

    for b in bottleneck_list:
        # use list comprehension to get index positions where available_throughput is less than zero?
        hit_limit = [i for i, e in enumerate(b.available_throughput) if e <= 0]
        for h in hit_limit:
            capacity_hit_log[h].append(b.bottleneck_id)

    return capacity_hit_log
