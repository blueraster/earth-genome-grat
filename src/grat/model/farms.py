"""
Agriculture recharge
"""

import math

import numpy as np

from . import bottlenecks
from .baseSite import BaseSite


def turnoutLimitConversion(cfsRate):
    """
    Converts turnout limit in cubic-feet per second to acre-feet per day
    Args:
        cfsRate: flow rate in cubic feet per second

    Returns: volume in acre-feet per day
    """
    afPerDay = cfsRate * 1.983
    return afPerDay


class Farm(BaseSite):
    def __init__(self, soilType, cfsLimit, crop=None, inLieuCrop=None, **kwargs):
        """
        Class for sites that are in agriculture (on-farm & in-lieu)

        In lieu recharge is a simple way to say “surface water used in lieu of pumping groundwater.” In lieu recharge
         is a method of OFR that reduces groundwater pumping by irrigating with surface water instead of groundwater
         to meet crop demand (ETc).

        Direct recharge refers to a method of OFR that reduces groundwater level decline by applying surface water in
        excess of crop demand (ETc) at levels that do not interfere with crop development. Direct recharge uses the
        CCC to determine the volume of WAFR that can be applied as OFR to existing fields under production for crops.
        Only fields with crops currently in the crop compatibility calendar are included in on-farm calculations.


        Args:
            soilType: soil classification from SAGBI
            cfsLimit: rate water can be applied to site (cubic-feet per second)
            **kwargs: all other BaseSite args
        """
        super().__init__(**kwargs)
        self.crop = crop

        self.soilType = soilType
        self.cfsLimit = cfsLimit if cfsLimit is not None else 15  # default rate of water that can be applied to a site
        self.flowLimit = np.full(366, float(turnoutLimitConversion(self.cfsLimit)))

        # # in lieu recharge attributes
        self.inLieuCrop = inLieuCrop
        self.inLieuUnusedVolume = np.full(366, 0.0)
        self.inLieuUsedVolume = np.full(366, 0.0)
        self.inLieuDailyRechargeVolumes = np.full(366, 0.0)

        self.ofrUnusedVolume = np.full(366, 0.0)
        self.ofrUsedVolume = np.full(366, 0.0)
        self.ofrDailyRechargeVolumes = np.full(366, 0.0)

        self.usedPrecip = np.full(366, 0.0)  # empty array to store precip that gets "used"

    def getSiteVolume(self, day: int, cropCalendar: dict, inlieu: bool = False):
        """
        Return the potential volume of water a site could receive on a given day

        Args:
            day: zero-indexed day of the water year
            cropCalendar: dictionary that contains info for the amount of water that can be applied to a specific crop
        Returns: site volume in acre-feet (minimum of flow limit or crop accepted rate)

        """
        if inlieu:
            if self.regionNumber is not None:
                cropAcceptedRate = (
                    cropCalendar[self.inLieuCrop][str(self.regionNumber)][day] * self.acres - self.inLieuUsedVolume[day]
                )
            else:
                cropAcceptedRate = 0
        else:
            cropAcceptedRate = cropCalendar[self.crop][self.soilType][day] * self.acres - self.ofrUsedVolume[day]

        siteVolume = (
            cropAcceptedRate
            - self.precip[day]  # removes volume from the daily precip
            + self.usedPrecip[day]  # avoids double counting precip
        )

        return siteVolume

    def setUnused(self, day: int, volume: float, inlieu: bool = False):
        """
        Sets the unused volume (acre-feet) of a site for a specific day
        Args:
            day: zero-index day of the water year
            volume: amount to set for unusedVolume for a specific date
            inlieu: boolean to control if the update is for in-lieu recharge or OFR

        """
        if inlieu:
            self.inLieuUnusedVolume[day] = volume
        else:
            self.ofrUnusedVolume[day] = volume

    def setUsedVolume(self, day: int, newVolume: float, inlieu: bool = False):
        """
        Adds the water applied (acre-feet) to the existing usedVolume array value for the date
        Args:
            day: index date
            newVolume: volume that was applied (acre-feet)
            inlieu: boolean to control if the update is for in-lieu recharge or OFR

        """
        if inlieu:
            self.inLieuUsedVolume[day] += newVolume
        else:
            self.ofrUsedVolume[day] += newVolume

        return

    def setDailyRecharge(self, day: int, newVolume: float, inlieu: bool = False):
        """
        Update the daily recharge by adding the new volume to the existing value
        Args:
            day: array index to update
            newVolume: volume to add (acre-feet)
            inlieu: boolean to control if the update is for in-lieu recharge or OFR
        """
        if inlieu:
            self.inLieuDailyRechargeVolumes[day] += newVolume
        else:
            self.ofrDailyRechargeVolumes[day] += newVolume

    def useSite(
        self,
        dowy: int,
        wafr: dict,
        bottleneckList: list,
        cropCalendar: dict,
        inLieu: bool = False,
        secondaryWAFR: bool = False,
        transferLimits: dict = None,
    ):
        """
        Add water to the site as on-farm-recharge or in-lieu recharge.
        Args:
            dowy: zero indexed day of the water year
            wafr: water available for recharge. The current availability of water (in acre-feet) by water source.
            bottleneckList: list of bottleneck objects
            cropCalendar: crop / soil combo to determine if field can take water.
            inLieu: water applied in lieu of pumping groundwater
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

        # loop through each of the compatible sources that can supply water to the site
        for wafrsrc in wafrSourceList:
            # calculate the amount of water that can come from WAFR
            try:
                volumeAvailableFromWafr = wafr[wafrsrc][dowy]
            except Exception:
                volumeAvailableFromWafr = 0

            # if volume from WAFR == zero skip
            # no water is available from source so nothing can be applied to the site
            if volumeAvailableFromWafr > 0:
                # how much water can be applied to the crop type for this day?
                availableSiteVolume = max(self.getSiteVolume(dowy, cropCalendar, inlieu=inLieu), 0)

                if availableSiteVolume <= 0:
                    break

                # determine how much water can be delivered through the bottlenecks
                # get the bottlepoint object for the wafr source that restrict delivery to this site
                bottlePoints = bottlenecks.getBottlenecks(bottleneckList, self.bottleneckIDs, wafrsrc)

                if len(bottlePoints) > 0:
                    # get the minimum available throughput from the bottlenecks
                    availableThroughput = min([bp.getAvailableThroughput(dowy) for bp in bottlePoints])
                else:
                    availableThroughput = math.inf

                # water applied for groundwater recharge
                wafrApplied = min(
                    availableSiteVolume,
                    volumeAvailableFromWafr,
                    availableThroughput,
                    self.flowLimit[dowy],
                )
                # update values only if water is applied
                if wafrApplied > 0:
                    # update the used volume array
                    self.setUsedVolume(dowy, wafrApplied, inlieu=inLieu)

                    # update the unused volume array
                    unused_vol = availableSiteVolume - wafrApplied

                    self.setUnused(dowy, unused_vol, inlieu=inLieu)

                    # set daily recharge array
                    self.setDailyRecharge(dowy, wafrApplied, inlieu=inLieu)

                    # subtract water applied from wafr so it is unavailable
                    wafr[wafrsrc][dowy] -= wafrApplied

                    # subtract water from the flowLimit
                    self.flowLimit[dowy] -= wafrApplied

                    # update wafr source log
                    self.setWafrLog(wafrsrc, wafrApplied)

                    # updated usedPrecip
                    self.usedPrecip[dowy] = self.precip[dowy]

                    # update bottlenecks usage
                    if len(bottlePoints) > 0:
                        for bp in bottlePoints:
                            bp.updateUsage(dowy, wafrApplied)

                    # update transfer limits
                    if transferLimits is not None and self.district in transferLimits:
                        transferLimits[self.district] -= wafrApplied
        return

    def __repr__(self):
        return f"{self.__dict__}"


def useFarms(
    siteList,
    day,
    wafr,
    bottleneckList,
    cropCalendar,
    inLieu=False,
    secondaryWAFR=False,
    transferLimits=None,
):
    """
    Loop through the list of sites and try to use the site
    Args:
        siteList: list of sites (OFR & in lieu)
        day: zero-indexed day of the water year
        wafr: water available for recharge dictionary
        bottleneckList: list of bottlenecks
        cropCalendar: dictionary of the crop compatibility calendar
        inLieu: boolean - is water applied in lieu of groundwater pumping
        secondaryWAFR: controls which list of sources should be used
        transferLimits: dictionary of district-level yearly transfer limits

    Returns:

    """
    for s in siteList:
        s.useSite(
            day,
            wafr,
            bottleneckList,
            cropCalendar,
            inLieu=inLieu,
            secondaryWAFR=secondaryWAFR,
            transferLimits=transferLimits,
        )
    return
