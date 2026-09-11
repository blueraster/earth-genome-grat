"""Percolation basins."""

import math

from . import bottlenecks
from .sites import BaseSite


class Basin(BaseSite):
    """A dedicated managed recharge facility.

    Basin recharge is the practice of applying WAFR to dedicated managed
    facilities, and is reported as groundwater recharge. Basins are filled until
    WAFR is used up or every basin is full.

    Water enters a basin as standing volume (`current_capacity`) and drains to
    groundwater at `perc_rate` each day, so a basin recharges over several days
    rather than instantly.

    Attributes:
        current_capacity: volume currently standing in the basin (acre-feet).
    """

    def __init__(self, max_capacity=0, perc_rate=0, **kwargs):
        """Build a percolation basin.

        Args:
            max_capacity: basin capacity (acre-feet).
            perc_rate: percolation rate (acre-feet per day).
            **kwargs: all other `BaseSite` arguments.
        """
        super().__init__(**kwargs)
        self.current_capacity: float = 0.0
        self.perc_rate = perc_rate
        self.max_capacity = max_capacity

    def update_daily_values(self, day: int):
        """Drain a day's percolation from the basin into groundwater recharge.

        The volume recharged is the percolation rate, or the standing volume if
        that is smaller. The percolation rate is then subtracted from the standing
        volume, which never goes below zero.

        Args:
            day: zero-indexed day of the water year.
        """
        recharge_volume = min(self.perc_rate, self.current_capacity)
        self.set_daily_recharge(day, recharge_volume)
        self.current_capacity = max(self.current_capacity - self.perc_rate, 0)

    def get_basin_volume_available(self, day: int):
        """Return how much water the basin could accept on a day.

        Headroom is the basin capacity less the standing volume, plus the volume
        that will percolate away that day, less the precipitation the basin
        receives. Never negative.

        Args:
            day: zero-indexed day of the water year.

        Returns:
            Volume the basin could accept (acre-feet).
        """
        return max(
            self.max_capacity - self.current_capacity + self.perc_rate - self.precip[day],
            0,
        )

    def set_used_volume(self, day: int, new_volume: float):
        """Record water applied to the basin on a day.

        Adds the volume to both the day's used volume and the standing volume in
        the basin.

        Args:
            day: zero-indexed day of the water year.
            new_volume: volume applied (acre-feet).
        """
        self.used_volume[day] += new_volume
        self.current_capacity = self.current_capacity + new_volume
        return

    def use_basin(
        self,
        dowy: int,
        wafr: dict,
        bottleneck_list: list,
        secondary_wafr: bool = False,
        transfer_limits: dict | None = None,
    ):
        """Apply water to this basin from every source that can reach it.

        Works through the site's WAFR sources in order, taking from each the
        smallest of: the basin's remaining headroom, the volume the source still
        has that day, and the throughput its bottlenecks still allow. Stops early
        once the basin has no headroom left.

        Args:
            dowy: zero-indexed day of the water year.
            wafr: volume still available (acre-feet) per day, keyed by WAFR source
                name. **Mutated**: water applied here is subtracted from it.
            bottleneck_list: every bottleneck in the system. The ones relevant to
                this site are selected by its `bottleneck_ids`. **Mutated**: the
                throughput used is subtracted from the bottlenecks crossed.
            secondary_wafr: draw from the site's secondary (out-of-district)
                sources instead of its primary (in-district) ones.
            transfer_limits: remaining yearly transfer budget (acre-feet) per
                district. **Mutated**: volume applied is charged against the
                site's district. When a district's budget is spent, the sources
                subject to that budget are skipped for this site. `None` disables
                transfer limiting entirely.
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
    secondary_wafr: bool = False,
    transfer_limits: dict | None = None,
):
    """Apply water to every basin in turn.

    Basins are filled in list order, so earlier basins get first call on the
    available water. See `Basin.use_basin` for how each one is filled.

    Args:
        basin_list: basins to fill, in processing order.
        day: zero-indexed day of the water year.
        wafr: volume still available (acre-feet) per day, keyed by WAFR source
            name. **Mutated**: water applied is subtracted from it.
        bottleneck_list: every bottleneck in the system. **Mutated**.
        secondary_wafr: draw from secondary (out-of-district) sources instead of
            primary (in-district) ones.
        transfer_limits: remaining yearly transfer budget (acre-feet) per
            district. **Mutated**. `None` disables transfer limiting.
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
    """Drain a day's percolation from every basin into groundwater recharge.

    Call once per day after the basins have been filled. See
    `Basin.update_daily_values`.

    Args:
        basin_list: basins to drain.
        day: zero-indexed day of the water year.
    """
    for b in basin_list:
        b.update_daily_values(day)  # update daily values
    return
