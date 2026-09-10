"""
Conveyance system
"""

import numpy as np

from .basins import Basin
from .utils import sort_wafr_source_by_volume


class Canal(Basin):
    def __init__(
        self,
        irrigation_days=None,
        **kwargs,
    ):
        """
        Canal class. Expands the basin class with some additional behavior and logic.
        Max capacity is an array of daily values (n=365) to account for changes in volume due to operations

        Conveyance refers to the built (canals, sloughs, etc) and natural structures (rivers, streams, etc.)
        that transport WAFR from its source to identified areas or fields within each district

        Attributes:
            irrigation_days (list): list of days (zero index day of water year) that use the irrigation season
            capacity rate.
        """
        super().__init__(**kwargs)

        self.recharge_type = "Canal"
        self.max_capacity = self._calculate_daily_capacity(
            self.max_capacity, irrigation_days if irrigation_days is not None else []
        )  # array supersedes the basin variable to account for changes in volume due to operations

    def _calculate_daily_capacity(self, max_capacity, irrigation_days=None):

        if irrigation_days is None:
            irrigation_days = []

        capacity_array = np.full(366, fill_value=0.0)  # init empty array
        for d in range(0, 366):
            if d in irrigation_days:
                capacity_array[d] = 0.0
            else:
                capacity_array[d] = max_capacity

        return capacity_array

    def get_canal_volume_available(self, day: int):
        """
        Canal volume available is the max capacity minus the current capacity plus the perc rate

        Args:
            day: zero-indexed day of the water year

        Returns: volume that could be added to the canal in acre-feet

        """

        if self.max_capacity[day] == 0:
            return 0  # no capacity on this day (irrigation season). Assumed full (perc accounted in different model)
        return max(self.max_capacity[day] - self.current_capacity + self.perc_rate, 0)

    def use_canal(self, day: int, wafr: dict, source: str, usable_volume_from_source: float):
        """
        Apply water to the canal on a specific day using a proportionally allocated volume from a specific WAFR source

        Args:
            day: zero-index day of the water year
            wafr: water available for recharge dictionary
            source: name of the source that is supplying water
            usable_volume_from_source: usable volume from the WAFR source
        """
        volume_available_from_wafr = wafr[source][day]
        if volume_available_from_wafr > 0 and usable_volume_from_source > 0:
            wafr_applied = min(self.get_canal_volume_available(day), usable_volume_from_source)
            self.set_used_volume(day, wafr_applied)
            wafr[source][day] -= wafr_applied
            self.set_wafr_log(source, wafr_applied)

    def __repr__(self):
        return f"{self.__dict__}"


def proportionally_fill(
    day: int,
    canal_list: list,
    wafr: dict,
    selected_wafr: str,
    secondary_wafr: bool = False,
):
    """
    Proportionally fills canals with water from a specific WAFR source

    Filters canal list to just the ones that can receive water from the selected WAFR source, sums up
    the total volume remaining in the canals. If this number is larger than the volume
    from the source, then the available volume gets split proportionally (using the ratio of the volume each canal
    could accept) and applied into the canal system. If there is enough water available, all the canals get filled

    Args:
        day: zero-indexed day of the water year
        canal_list: list of canal objects
        wafr: dictionary of WAFR organized by source and day
        selected_wafr: name of the WAFR source to proportionally fill canals
        secondary_wafr: controls which list of sources should be used


    Returns:

    """

    volume_available_from_wafr = wafr[selected_wafr][day]  # volume available from this WAFR source

    if volume_available_from_wafr > 0:
        if secondary_wafr is True:
            # select the canals that are supplied by the secondary WAFR source
            compatible_canals = [c for c in canal_list if selected_wafr in c.wafr_sources_secondary]
        else:
            # select the canals that are supplied by the selected WAFR source
            compatible_canals = [c for c in canal_list if selected_wafr in c.wafr_sources_primary]

        # sum of the volume available for the list of compatible canals that can receive water from this source
        sum_canal_volume_available = sum([c.get_canal_volume_available(day) for c in compatible_canals])

        # proportionally fill canals using fraction of volume available at site divided by the sum all volume available.
        if sum_canal_volume_available > 0:
            for c in compatible_canals:
                proportional_volume = (
                    c.get_canal_volume_available(day) / sum_canal_volume_available * volume_available_from_wafr
                )
                fill_volume = min(c.get_canal_volume_available(day), proportional_volume)
                c.use_canal(day, wafr, selected_wafr, usable_volume_from_source=fill_volume)

    return


def fill_canals(canal_list: list, day: int, wafr: dict, secondary_wafr: bool = False):
    """
    Loops through each of the WAFR sources and applies water to the canals

    Args:
        canal_list: list of canal object
        day: zero-indexed day of the water year
        wafr: dictionary of water available for recharge
        secondary_wafr: controls which list of sources should be used

    Returns:

    """

    wafr_order = sort_wafr_source_by_volume(wafr, day)  # sort WAFR sources by volume currently available

    for wafr_source in wafr_order:
        proportionally_fill(day, canal_list, wafr, wafr_source, secondary_wafr=secondary_wafr)

    return


def canals_update_daily_values(canal_list: list, day: int):
    """
    Loops through the canals in the list and calls the update_daily_values method to move perc_rate volume to
        groundwater recharge

    Args:
        canal_list: list of canal objects
        day: zero-indexed day of the water year

    Returns:

    """
    for c in canal_list:
        c.update_daily_values(day)  # update daily values
    return
