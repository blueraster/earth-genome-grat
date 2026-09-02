"""
Conveyance system
"""

import numpy as np

from .basins import Basin
from .funcs import sortWafrSourceByVolume


class Canal(Basin):
    def __init__(
        self,
        irrigationDays=None,
        **kwargs,
    ):
        """
        Canal class. Expands the basin class with some additional behavior and logic.
        Max capacity is an array of daily values (n=365) to account for changes in volume due to operations

        Conveyance refers to the built (canals, sloughs, etc) and natural structures (rivers, streams, etc.)
        that transport WAFR from its source to identified areas or fields within each district

        Attributes:
            irrigationDays (list): list of days (zero index day of water year) that use the irrigation season
            capacity rate.
        """
        super().__init__(**kwargs)

        self.rechargeType = "Canal"
        self.maxCapacity = self._calculateDailyCapacity(
            self.maxCapacity, irrigationDays if irrigationDays is not None else []
        )  # array supersedes the basin variable to account for changes in volume due to operations

    def _calculateDailyCapacity(self, maxCapacity, irrigationDays=None):

        if irrigationDays is None:
            irrigationDays = []

        capacityArray = np.full(366, fill_value=0.0)  # init empty array
        for d in range(0, 366):
            if d in irrigationDays:
                capacityArray[d] = 0.0
            else:
                capacityArray[d] = maxCapacity

        return capacityArray

    def getCanalVolumeAvailable(self, day: int):
        """
        Canal volume available is the max capacity minus the current capacity plus the perc rate

        Args:
            day: zero-indexed day of the water year

        Returns: volume that could be added to the canal in acre-feet

        """

        if self.maxCapacity[day] == 0:
            return 0  # no capacity on this day (irrigation season). Assumed full (perc accounted in different model)
        else:
            return max(self.maxCapacity[day] - self.currentCapacity + self.percRate, 0)

    def useCanal(self, day: int, wafr: dict, source: str, usableVolFromSource: float):
        """
        Apply water to the canal on a specific day using a proportionally allocated volume from a specific WAFR source

        Args:
            day: zero-index day of the water year
            wafr: water available for recharge dictionary
            source: name of the source that is supplying water
            usableVolFromSource: usable volume from the WAFR source
        """
        volumeAvailableFromWafr = wafr[source][day]
        if volumeAvailableFromWafr > 0 and usableVolFromSource > 0:
            wafrApplied = min(self.getCanalVolumeAvailable(day), usableVolFromSource)
            self.setUsedVolume(day, wafrApplied)
            wafr[source][day] -= wafrApplied
            self.setWafrLog(source, wafrApplied)

    def __repr__(self):
        return f"{self.__dict__}"


def proportionallyFill(
    day: int,
    canalList: list,
    wafr: dict,
    selectedWafr: str,
    secondaryWAFR: bool = False,
):
    """
    Proportionally fills canals with water from a specific WAFR source

    Filters canal list to just the ones that can receive water from the selected WAFR source, sums up
    the total volume remaining in the canals. If this number is larger than the volume
    from the source, then the available volume gets split proportionally (using the ratio of the volume each canal
    could accept) and applied into the canal system. If there is enough water available, all the canals get filled

    Args:
        day: zero-indexed day of the water year
        canalList: list of canal objects
        wafr: dictionary of WAFR organized by source and day
        selectedWafr: name of the WAFR source to proportionally fill canals
        secondaryWAFR: controls which list of sources should be used


    Returns:

    """

    volumeAvailableFromWafr = wafr[selectedWafr][day]  # volume available from this WAFR source

    if volumeAvailableFromWafr > 0:
        if secondaryWAFR is True:
            # select the canals that are supplied by the secondary WAFR source
            compatibleCanals = [c for c in canalList if selectedWafr in c.wafrSourcesSecondary]
        else:
            # select the canals that are supplied by the selected WAFR source
            compatibleCanals = [c for c in canalList if selectedWafr in c.wafrSourcesPrimary]

        # sum of the volume available for the list of compatible canals that can receive water from this source
        sumCanalVolumeAvailable = sum([c.getCanalVolumeAvailable(day) for c in compatibleCanals])

        # proportionally fill canals using fraction of volume available at site divided by the sum all volume available.
        if sumCanalVolumeAvailable > 0:
            for c in compatibleCanals:
                proportionalVolume = c.getCanalVolumeAvailable(day) / sumCanalVolumeAvailable * volumeAvailableFromWafr
                fillVolume = min(c.getCanalVolumeAvailable(day), proportionalVolume)
                c.useCanal(day, wafr, selectedWafr, usableVolFromSource=fillVolume)

    return


def fillCanals(canalList: list, day: int, wafr: dict, secondaryWAFR: bool = False):
    """
    Loops through each of the WAFR sources and applies water to the canals

    Args:
        canalList: list of canal object
        day: zero-indexed day of the water year
        wafr: dictionary of water available for recharge
        secondaryWAFR: controls which list of sources should be used

    Returns:

    """

    wafrOrder = sortWafrSourceByVolume(wafr, day)  # sort WAFR sources by volume currently available

    for wafrSource in wafrOrder:
        proportionallyFill(day, canalList, wafr, wafrSource, secondaryWAFR=secondaryWAFR)

    return


def canalsUpdateDailyValues(canalList: list, day: int):
    """
    Loops through the canals in the list and calls the updateDailyValues method to move percRate volume to
        groundwater recharge

    Args:
        canalList: list of canal objects
        day: zero-indexed day of the water year

    Returns:

    """
    for c in canalList:
        c.updateDailyValues(day)  # update daily values
    return
