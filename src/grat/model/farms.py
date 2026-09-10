"""
Agriculture recharge
"""

import math

import numpy as np

from . import bottlenecks
from .base_site import BaseSite


def turnout_limit_conversion(cfs_rate):
    """
    Converts turnout limit in cubic-feet per second to acre-feet per day
    Args:
        cfs_rate: flow rate in cubic feet per second

    Returns: volume in acre-feet per day
    """
    return cfs_rate * 1.983


class Farm(BaseSite):
    def __init__(self, soil_type, cfs_limit, crop=None, in_lieu_crop=None, **kwargs):
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
            soil_type: soil classification from SAGBI
            cfs_limit: rate water can be applied to site (cubic-feet per second)
            **kwargs: all other BaseSite args
        """
        super().__init__(**kwargs)
        self.crop = crop

        self.soil_type = soil_type
        self.cfs_limit = (
            cfs_limit if cfs_limit is not None else 15
        )  # default rate of water that can be applied to a site
        self.flow_limit = np.full(366, float(turnout_limit_conversion(self.cfs_limit)))

        # # in lieu recharge attributes
        self.in_lieu_crop = in_lieu_crop
        self.in_lieu_unused_volume = np.full(366, 0.0)
        self.in_lieu_used_volume = np.full(366, 0.0)
        self.in_lieu_daily_recharge_volumes = np.full(366, 0.0)

        self.ofr_unused_volume = np.full(366, 0.0)
        self.ofr_used_volume = np.full(366, 0.0)
        self.ofr_daily_recharge_volumes = np.full(366, 0.0)

        self.used_precip = np.full(366, 0.0)  # empty array to store precip that gets "used"

    def get_site_volume(self, day: int, crop_calendar: dict, in_lieu: bool = False):
        """
        Return the potential volume of water a site could receive on a given day

        Args:
            day: zero-indexed day of the water year
            crop_calendar: dictionary that contains info for the amount of water that can be applied to a specific crop
        Returns: site volume in acre-feet (minimum of flow limit or crop accepted rate)

        """
        if in_lieu:
            if self.region_number is not None:
                crop_accepted_rate = (
                    crop_calendar[self.in_lieu_crop][str(self.region_number)][day] * self.acres
                    - self.in_lieu_used_volume[day]
                )
            else:
                crop_accepted_rate = 0
        else:
            crop_accepted_rate = crop_calendar[self.crop][self.soil_type][day] * self.acres - self.ofr_used_volume[day]

        return (
            crop_accepted_rate
            - self.precip[day]  # removes volume from the daily precip
            + self.used_precip[day]  # avoids double counting precip
        )

    def set_unused(self, day: int, volume: float, in_lieu: bool = False):
        """
        Sets the unused volume (acre-feet) of a site for a specific day
        Args:
            day: zero-index day of the water year
            volume: amount to set for unused_volume for a specific date
            in_lieu: boolean to control if the update is for in-lieu recharge or OFR

        """
        if in_lieu:
            self.in_lieu_unused_volume[day] = volume
        else:
            self.ofr_unused_volume[day] = volume

    def set_used_volume(self, day: int, new_volume: float, in_lieu: bool = False):
        """
        Adds the water applied (acre-feet) to the existing used_volume array value for the date
        Args:
            day: index date
            new_volume: volume that was applied (acre-feet)
            in_lieu: boolean to control if the update is for in-lieu recharge or OFR

        """
        if in_lieu:
            self.in_lieu_used_volume[day] += new_volume
        else:
            self.ofr_used_volume[day] += new_volume

        return

    def set_daily_recharge(self, day: int, new_volume: float, in_lieu: bool = False):
        """
        Update the daily recharge by adding the new volume to the existing value
        Args:
            day: array index to update
            new_volume: volume to add (acre-feet)
            in_lieu: boolean to control if the update is for in-lieu recharge or OFR
        """
        if in_lieu:
            self.in_lieu_daily_recharge_volumes[day] += new_volume
        else:
            self.ofr_daily_recharge_volumes[day] += new_volume

    def use_site(
        self,
        dowy: int,
        wafr: dict,
        bottleneck_list: list,
        crop_calendar: dict,
        in_lieu: bool = False,
        secondary_wafr: bool = False,
        transfer_limits: dict = None,
    ):
        """
        Add water to the site as on-farm-recharge or in-lieu recharge.
        Args:
            dowy: zero indexed day of the water year
            wafr: water available for recharge. The current availability of water (in acre-feet) by water source.
            bottleneck_list: list of bottleneck objects
            crop_calendar: crop / soil combo to determine if field can take water.
            in_lieu: water applied in lieu of pumping groundwater
            secondary_wafr: controls which list of sources should be used
            transfer_limits: dictionary of district-level yearly transfer limits

        """

        wafr_source_list = self.wafr_sources_secondary if secondary_wafr else self.wafr_sources_primary

        # check if the transfer limit has been exceeded for the district if applicable
        if transfer_limits is not None and self.district in transfer_limits and transfer_limits[self.district] <= 0:
            # no water can be applied to the site from the sources subject to the transfer limit
            transfer_sources_for_district = transfer_limits.get("transfer_wafr_sources", {}).get(self.district, [])
            if isinstance(transfer_sources_for_district, str):
                transfer_sources_for_district = [transfer_sources_for_district]

            wafr_source_list = [item for item in wafr_source_list if item not in transfer_sources_for_district]

        # loop through each of the compatible sources that can supply water to the site
        for wafrsrc in wafr_source_list:
            # calculate the amount of water that can come from WAFR
            try:
                volume_available_from_wafr = wafr[wafrsrc][dowy]
            except KeyError:
                volume_available_from_wafr = 0

            # if volume from WAFR == zero skip
            # no water is available from source so nothing can be applied to the site
            if volume_available_from_wafr > 0:
                # how much water can be applied to the crop type for this day?
                available_site_volume = max(self.get_site_volume(dowy, crop_calendar, in_lieu=in_lieu), 0)

                if available_site_volume <= 0:
                    break

                # determine how much water can be delivered through the bottlenecks
                # get the bottlepoint object for the wafr source that restrict delivery to this site
                bottleneck_points = bottlenecks.get_bottlenecks(bottleneck_list, self.bottleneck_ids, wafrsrc)

                if len(bottleneck_points) > 0:
                    # get the minimum available throughput from the bottlenecks
                    available_throughput = min([bp.get_available_throughput(dowy) for bp in bottleneck_points])
                else:
                    available_throughput = math.inf

                # water applied for groundwater recharge
                wafr_applied = min(
                    available_site_volume,
                    volume_available_from_wafr,
                    available_throughput,
                    self.flow_limit[dowy],
                )
                # update values only if water is applied
                if wafr_applied > 0:
                    # update the used volume array
                    self.set_used_volume(dowy, wafr_applied, in_lieu=in_lieu)

                    # update the unused volume array
                    unused_vol = available_site_volume - wafr_applied

                    self.set_unused(dowy, unused_vol, in_lieu=in_lieu)

                    # set daily recharge array
                    self.set_daily_recharge(dowy, wafr_applied, in_lieu=in_lieu)

                    # subtract water applied from wafr so it is unavailable
                    wafr[wafrsrc][dowy] -= wafr_applied

                    # subtract water from the flow_limit
                    self.flow_limit[dowy] -= wafr_applied

                    # update wafr source log
                    self.set_wafr_log(wafrsrc, wafr_applied)

                    # updated used_precip
                    self.used_precip[dowy] = self.precip[dowy]

                    # update bottlenecks usage
                    if len(bottleneck_points) > 0:
                        for bp in bottleneck_points:
                            bp.update_usage(dowy, wafr_applied)

                    # update transfer limits
                    if transfer_limits is not None and self.district in transfer_limits:
                        transfer_limits[self.district] -= wafr_applied
        return

    def __repr__(self):
        return f"{self.__dict__}"


def use_farms(
    site_list,
    day,
    wafr,
    bottleneck_list,
    crop_calendar,
    in_lieu=False,
    secondary_wafr=False,
    transfer_limits=None,
):
    """
    Loop through the list of sites and try to use the site
    Args:
        site_list: list of sites (OFR & in lieu)
        day: zero-indexed day of the water year
        wafr: water available for recharge dictionary
        bottleneck_list: list of bottlenecks
        crop_calendar: dictionary of the crop compatibility calendar
        in_lieu: boolean - is water applied in lieu of groundwater pumping
        secondary_wafr: controls which list of sources should be used
        transfer_limits: dictionary of district-level yearly transfer limits

    Returns:

    """
    for s in site_list:
        s.use_site(
            day,
            wafr,
            bottleneck_list,
            crop_calendar,
            in_lieu=in_lieu,
            secondary_wafr=secondary_wafr,
            transfer_limits=transfer_limits,
        )
    return
