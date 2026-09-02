"""
Percolation basins
"""

import math

from . import bottlenecks
from .baseSite import BaseSite


class Basin(BaseSite):
    def __init__(self, maxCapacity=0, percRate=0, **kwargs):
        """
        Class for percolation basins. Basin recharge is the practice of applying WAFR to dedicated managed facilities
        and is reported as groundwater recharge. Basins are filled until WAFR is used up or all basins are filled.

        Args:
            maxCapacity: basin capacity in acre-feet
            percRate: percolation rate in acre-feet per day
            **kwargs: all other BaseSite arguments
        """

        super().__init__(**kwargs)
        self.currentCapacity: float = 0.0
        self.percRate = percRate
        self.maxCapacity = maxCapacity

    def updateDailyValues(self, day: int):
        """
        Sets the daily recharge volume. The volume that goes to recharge is the perc rate or the current capacity if
         the capacity is less than the perc rate volume. The perc rate is then subtracted from the current capacity.

        Args:
            day: zero-indexed day of the water year
        """
        rechargeVolume = min(self.percRate, self.currentCapacity)
        self.setDailyRecharge(day, rechargeVolume)
        self.currentCapacity = max(self.currentCapacity - self.percRate, 0)

    def getBasinVolumeAvailable(self, day: int):
        """
        Basin volume (acre-feet) available is the capacity minus the current capacity plus the perc rate minus precip
        """
        return max(
            self.maxCapacity - self.currentCapacity + self.percRate - self.precip[day],
            0,
        )

    def setUsedVolume(self, day: int, newVolume: float):
        """
        Set used volume for a specific date

        Args:
            day: zero-indexed day of the water year
            newVolume: value to add to the used volume for the day and to the overall currentCapacity
        """
        self.usedVolume[day] += newVolume
        self.currentCapacity = self.currentCapacity + newVolume
        return

    def useBasin(
        self,
        dowy: int,
        wafr: dict,
        bottleneckList,
        secondaryWAFR: bool = False,
        transferLimits: dict = None,
    ):
        """
        Use the basin for groundwater recharge

        Args:
            dowy: zero indexed day of the water year
            wafr: water available for recharge
            bottleneckList: list of bottleneck objects
            secondaryWAFR: controls which list of sources should be used
            transferLimits: dictionary of district-level yearly transfer limits
        """

        wafrSourceList = self.wafrSourcesSecondary if secondaryWAFR else self.wafrSourcesPrimary

        # check if the transfer limit has been exceeded for the district if applicable
        if transferLimits is not None and self.district in transferLimits and transferLimits[self.district] <= 0:
            # no water can be applied to the site from the sources subject to the transfer limit
            transfer_sources_for_district = transferLimits.get("transfer_wafr_sources", {}).get(self.district, [])
            if isinstance(transfer_sources_for_district, str):
                transfer_sources_for_district = [transfer_sources_for_district]

            wafrSourceList = [item for item in wafrSourceList if item not in transfer_sources_for_district]

        # loop through the sources that can provide water to the site
        for wafrsrc in wafrSourceList:
            # determine the volume of currently water available from the source
            volumeAvailableFromWafr = wafr[wafrsrc][dowy]

            if volumeAvailableFromWafr > 0:
                if self.getBasinVolumeAvailable(dowy) <= 0:
                    break  # exit loop if no water can be applied to the basin

                # Determine how much water is available through the system bottlenecks
                # get the bottlepoint object for the wafr source that restrict delivery to this site
                bottlePoints = bottlenecks.getBottlenecks(bottleneckList, self.bottleneckIDs, wafrsrc)

                if len(bottlePoints) > 0:
                    # get the minimum available throughput from the bottlenecks
                    availableThroughput = min([bp.getAvailableThroughput(dowy) for bp in bottlePoints])

                else:
                    availableThroughput = math.inf

                # how much volume could get added to the site? (the minimum value of limiting factors).
                wafrApplied = min(
                    self.getBasinVolumeAvailable(dowy),
                    volumeAvailableFromWafr,
                    availableThroughput,
                )

                if wafrApplied > 0:
                    # set used volume to the amount of water applied to the basin
                    self.setUsedVolume(dowy, wafrApplied)

                    # subtract the water used from the overall WAFR
                    wafr[wafrsrc][dowy] -= wafrApplied

                    # update wafr source log
                    self.setWafrLog(wafrsrc, wafrApplied)

                    # update bottlenecks usage
                    if len(bottlePoints) > 0:
                        for bp in bottlePoints:
                            bp.updateUsage(dowy, wafrApplied)

                    # update transfer limits
                    if transferLimits is not None and self.district in transferLimits:
                        transferLimits[self.district] -= wafrApplied
        return


def fillBasins(
    basinList: list,
    day: int,
    wafr: dict,
    bottleneckList: list,
    secondaryWAFR=False,
    transferLimits: dict = None,
):
    """
    Loops through all the basins in order and applies water from the compatible WAFR sources
    Args:
        basinList: list of basin objects
        day: zero-indexed day of the water year
        wafr: dictionary of water available for recharge
        bottleneckList: list of bottleneck objects
        secondaryWAFR: boolean to control which list of sources to use
        transferLimits: dictionary of district-level yearly transfer limits

    Returns:

    """

    for b in basinList:
        b.useBasin(
            day,
            wafr,
            bottleneckList,
            secondaryWAFR=secondaryWAFR,
            transferLimits=transferLimits,
        )

    return


def basinsUpdateDailyValues(basinList: list, day: int):
    """
    Loops through the basins in the list and calls the updateDailyValues method to move percRate volume to
     groundwater recharge
    Args:
        basinList: list of basin objects
        day: zero-indexed day of the water year
    Returns:

    """
    for b in basinList:
        b.updateDailyValues(day)  # update daily values
    return
