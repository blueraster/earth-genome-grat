"""Delivery limits shared by a group of sites."""

import numpy as np

from .constants import DAYS_PER_WATER_YEAR


class Bottleneck:
    """A daily delivery limit shared by every site behind it.

    A bottleneck caps how much water can reach the sites that name it on a given
    day, no matter how much WAFR is available. Each bottleneck is associated with
    one or more WAFR sources and only limits water from those.

    Sites name the bottlenecks that restrict them via their `bottleneck_ids`. A site
    behind several bottlenecks is limited by the tightest of them.

    Capacity is tracked as a running daily budget: `available_throughput` starts at
    the day's capacity and is drawn down by `update_usage` as sites take water.

    Attributes:
        available_throughput: throughput still unused (acre-feet), one entry per day
            of the water year. Drawn down as sites take water, and may go negative.
    """

    def __init__(
        self,
        bottleneck_id: int,
        name: str | None = None,
        capacity: float | None = None,
        wafr_sources: list | None = None,
        capacity_irrigation: float | None = None,
        irrigation_days: list | None = None,
        **kwargs,
    ):
        """Build a bottleneck.

        Args:
            bottleneck_id: bottleneck identifier, matched against a site's
                `bottleneck_ids`.
            name: human-readable name of the bottleneck.
            capacity: throughput limit outside the irrigation season
                (acre-feet per day).
            wafr_sources: names of the WAFR sources this bottleneck restricts. Water
                from any other source passes unrestricted.
            capacity_irrigation: throughput limit during the irrigation season
                (acre-feet per day).
            irrigation_days: zero-indexed days of the water year that use
                `capacity_irrigation` instead of `capacity`.
            **kwargs: additional attributes, set directly on the instance.
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

    def _calculate_throughput(self, irrigation_days: list | None = None):
        """Build the daily throughput budget for the whole water year.

        Args:
            irrigation_days: zero-indexed days that use the irrigation season capacity.

        Returns:
            Throughput limit (acre-feet per day) for each day of the water year.
        """
        if irrigation_days is None:
            irrigation_days = []

        throughput_array = np.full(DAYS_PER_WATER_YEAR, fill_value=0.0)  # init empty array
        for d in range(DAYS_PER_WATER_YEAR):
            if d in irrigation_days:
                throughput_array[d] = self.capacity_irrigation
            else:
                throughput_array[d] = self.capacity

        return throughput_array

    def update_usage(self, day: int, amount: float):
        """Charge a volume against the bottleneck's remaining throughput for a day.

        Args:
            day: zero-indexed day of the water year.
            amount: volume delivered through the bottleneck (acre-feet).
        """
        self.available_throughput[day] -= amount
        return

    def get_available_throughput(self, day: int):
        """Return the volume that can still pass through the bottleneck on a day.

        Args:
            day: zero-indexed day of the water year.

        Returns:
            Remaining throughput (acre-feet). Clamped to zero, so an
            over-subscribed bottleneck reports no capacity rather than a
            negative one.
        """
        daily_throughput = self.available_throughput[day]
        if daily_throughput <= 0:
            return 0
        return daily_throughput

    def __repr__(self):
        """Return every attribute of the bottleneck, including the full daily array."""
        return f"{self.__dict__}"


# operations on list of bottlenecks
def get_bottlenecks(bottleneck_list: list, bottleneck_ids, wafr_source: str):
    """Select the bottlenecks that restrict a given site's delivery from a source.

    A bottleneck matches when its identifier is one the site names *and* it
    restricts the WAFR source in question.

    Args:
        bottleneck_list: every bottleneck in the system.
        bottleneck_ids: the identifiers named by the site. `None` means the site is
            behind no bottlenecks.
        wafr_source: name of the WAFR source supplying the water.

    Returns:
        The matching bottlenecks, empty if the site is unrestricted for this source.
    """
    if bottleneck_ids is None:
        return []
    return [b for b in bottleneck_list if b.bottleneck_id in bottleneck_ids and wafr_source in b.wafr_sources]


def bottleneck_capacity_logger(bottleneck_list: list):
    """Report which bottlenecks ran out of capacity, day by day.

    A bottleneck counts as having hit its limit on any day where its remaining
    throughput has fallen to zero or below.

    Args:
        bottleneck_list: every bottleneck in the system.

    Returns:
        One list per day of the water year, each holding the identifiers of the
        bottlenecks that hit their limit that day.
    """
    capacity_hit_log = [[] for _ in range(DAYS_PER_WATER_YEAR)]  # assumes multiple bottlenecks per day

    for b in bottleneck_list:
        # use list comprehension to get index positions where available_throughput is less than zero?
        hit_limit = [i for i, e in enumerate(b.available_throughput) if e <= 0]
        for h in hit_limit:
            capacity_hit_log[h].append(b.bottleneck_id)

    return capacity_hit_log
