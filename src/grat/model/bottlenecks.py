"""
Delivery limits to collection of sites
"""

import numpy as np


class Bottleneck:
    def __init__(
        self,
        bottleneckID: int,
        name: str = None,
        capacity: float = None,
        wafrSources: list = None,
        capacityIrrigation: float = None,
        irrigationDays: list = None,
        **kwargs,
    ):
        """
        Defines the bottleneck object that restricts daily flow to groups of sites. Each bottleneck is associated
        with one or more WAFR sources. When provided, irrigationDays + capacityIrrigation modifies the
        default daily bottleneck rate value during the days that are in the irrigation season.

        Args:
            bottleneckID:  bottleneck identifier
            name: name of bottleneck (optional)
            capacity: default limit in acre-feet per day.
            wafrSources: name of the WAFR sources that supply water
            capacityIrrigation: limit in acre-feet per day during irrigation season.
            irrigationDays: list of days (zero index day of water year) that use the irrigation season capacity rate.
            **kwargs: Optional additional parameters

        """
        # catch all extra kwargs provided to class instance
        self.__dict__.update(kwargs)  # catch all for all unknown kwargs

        self.bottleneckID = bottleneckID
        self.name = name
        self.wafrSources = wafrSources if wafrSources is not None else []  # names of the WAFR sources
        self.capacity = capacity
        self.capacityIrrigation = capacityIrrigation
        self.availableThroughput = self._calculate_throughput(
            irrigationDays if irrigationDays is not None else []
        )  # volume in acre-feet per day

    def _calculate_throughput(self, irrigationDays=None):

        if irrigationDays is None:
            irrigationDays = []

        throughPutArray = np.full(366, fill_value=0.0)  # init empty array
        for d in range(0, 366):
            if d in irrigationDays:
                throughPutArray[d] = self.capacityIrrigation
            else:
                throughPutArray[d] = self.capacity

        return throughPutArray

    def update_usage(self, day: int, amount: float):
        """
        Updates the bottleneck available throughput by subtracting the volume used by the site

        Args:
            day: zero-indexed day of the water year
            amount: usage volume (AF) to subtract
        """
        self.availableThroughput[day] -= amount
        return

    def get_available_throughput(self, day: int):
        """
        Volume available to pass through the bottleneck

        Args:
            day: zero-indexed day of the water year

        Returns:
            dailyThroughput: throughput volume (AF) for a given bottleneck and day
        """
        dailyThroughput = self.availableThroughput[day]
        if dailyThroughput <= 0:
            return 0
        return dailyThroughput

    def __repr__(self):
        return f"{self.__dict__}"


# operations on list of bottlenecks
def get_bottlenecks(bottleneckList, bottleneckIDs, wafrSource):
    """
    Returns the object that matches the specific bottleneckID and WAFR source
    Args:
        bottleneckList: list of bottleneck objects
        bottleneckIDs: identifier for the bottlenecks
        wafrSource: name of the WAFR source that supplies water through the bottleneck

    Returns: list of bottleneck objects that match the conditions

    """
    try:
        return [b for b in bottleneckList if b.bottleneckID in bottleneckIDs and wafrSource in b.wafrSources]
    except KeyError:
        return []


def bottleneck_capacity_logger(bottleneckList):
    """
    Daily array of the bottlenecks that reached capacity
    Args:
        bottleneckList: list of bottleneck objects

    Returns: array containing the list of bottleneck ids that reached capacity per day

    """

    capacityHitLogger = [[] for _ in range(365)]  # assumes multiple bottlenecks per day

    for b in bottleneckList:
        # use list comprehension to get index positions where availableThroughPut is less than zero?
        hitLimit = [i for i, e in enumerate(b.availableThroughput) if e <= 0]
        for h in hitLimit:
            capacityHitLogger[h].append(b.bottleneckID)

    return capacityHitLogger
