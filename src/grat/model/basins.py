"""
Percolation basins
"""

import math

from . import bottlenecks
from .base_site import BaseSite


class Basin(BaseSite):
    def __init__(self, max_capacity=0, perc_rate=0, **kwargs):
        """
        Class for percolation basins. Basin recharge is the practice of applying WAFR to dedicated managed facilities
        and is reported as groundwater recharge. Basins are filled until WAFR is used up or all basins are filled.

        Args:
            max_capacity: basin capacity in acre-feet
            perc_rate: percolation rate in acre-feet per day
            **kwargs: all other BaseSite arguments
        """

        super().__init__(**kwargs)
        self.current_capacity: float = 0.0
        self.perc_rate = perc_rate
        self.max_capacity = max_capacity

    def update_daily_values(self, day: int):
        """
        Sets the daily recharge volume. The volume that goes to recharge is the perc rate or the current capacity if
         the capacity is less than the perc rate volume. The perc rate is then subtracted from the current capacity.

        Args:
            day: zero-indexed day of the water year
        """
        recharge_volume = min(self.perc_rate, self.current_capacity)
        self.set_daily_recharge(day, recharge_volume)
        self.current_capacity = max(self.current_capacity - self.perc_rate, 0)

    def get_basin_volume_available(self, day: int):
        """
        Basin volume (acre-feet) available is the capacity minus the current capacity plus the perc rate minus precip
        """
        return max(
            self.max_capacity - self.current_capacity + self.perc_rate - self.precip[day],
            0,
        )

    def set_used_volume(self, day: int, new_volume: float):
        """
        Set used volume for a specific date

        Args:
            day: zero-indexed day of the water year
            new_volume: value to add to the used volume for the day and to the overall current_capacity
        """
        self.used_volume[day] += new_volume
        self.current_capacity = self.current_capacity + new_volume
        return

    def use_basin(
        self,
        dowy: int,
        wafr: dict,
        bottleneck_list,
        secondary_wafr: bool = False,
        transfer_limits: dict = None,
    ):
        """
        Use the basin for groundwater recharge

        Args:
            dowy: zero indexed day of the water year
            wafr: water available for recharge
            bottleneck_list: list of bottleneck objects
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

        # loop through the sources that can provide water to the site
        for wafrsrc in wafr_source_list:
            # determine the volume of currently water available from the source
            volume_available_from_wafr = wafr[wafrsrc][dowy]

            if volume_available_from_wafr > 0:
                if self.get_basin_volume_available(dowy) <= 0:
                    break  # exit loop if no water can be applied to the basin

                # Determine how much water is available through the system bottlenecks
                # get the bottlepoint object for the wafr source that restrict delivery to this site
                bottleneck_points = bottlenecks.get_bottlenecks(bottleneck_list, self.bottleneck_ids, wafrsrc)

                if len(bottleneck_points) > 0:
                    # get the minimum available throughput from the bottlenecks
                    available_throughput = min([bp.get_available_throughput(dowy) for bp in bottleneck_points])

                else:
                    available_throughput = math.inf

                # how much volume could get added to the site? (the minimum value of limiting factors).
                wafr_applied = min(
                    self.get_basin_volume_available(dowy),
                    volume_available_from_wafr,
                    available_throughput,
                )

                if wafr_applied > 0:
                    # set used volume to the amount of water applied to the basin
                    self.set_used_volume(dowy, wafr_applied)

                    # subtract the water used from the overall WAFR
                    wafr[wafrsrc][dowy] -= wafr_applied

                    # update wafr source log
                    self.set_wafr_log(wafrsrc, wafr_applied)

                    # update bottlenecks usage
                    if len(bottleneck_points) > 0:
                        for bp in bottleneck_points:
                            bp.update_usage(dowy, wafr_applied)

                    # update transfer limits
                    if transfer_limits is not None and self.district in transfer_limits:
                        transfer_limits[self.district] -= wafr_applied
        return


def fill_basins(
    basin_list: list,
    day: int,
    wafr: dict,
    bottleneck_list: list,
    secondary_wafr=False,
    transfer_limits: dict = None,
):
    """
    Loops through all the basins in order and applies water from the compatible WAFR sources
    Args:
        basin_list: list of basin objects
        day: zero-indexed day of the water year
        wafr: dictionary of water available for recharge
        bottleneck_list: list of bottleneck objects
        secondary_wafr: boolean to control which list of sources to use
        transfer_limits: dictionary of district-level yearly transfer limits

    Returns:

    """

    for b in basin_list:
        b.use_basin(
            day,
            wafr,
            bottleneck_list,
            secondary_wafr=secondary_wafr,
            transfer_limits=transfer_limits,
        )

    return


def basins_update_daily_values(basin_list: list, day: int):
    """
    Loops through the basins in the list and calls the update_daily_values method to move perc_rate volume to
     groundwater recharge
    Args:
        basin_list: list of basin objects
        day: zero-indexed day of the water year
    Returns:

    """
    for b in basin_list:
        b.update_daily_values(day)  # update daily values
    return
