"""Conveyance system."""

import numpy as np

from .basins import Basin
from .constants import DAYS_PER_WATER_YEAR
from .utils import sort_wafr_source_by_volume


class Canal(Basin):
    """A conveyance structure that recharges groundwater through its bed.

    Conveyance refers to the built structures (canals, sloughs) and natural ones
    (rivers, streams) that transport WAFR from its source to fields within each
    district. They are modelled as recharge sites in their own right, percolating
    to groundwater the same way a basin does.

    A canal extends `Basin` with two differences:

    - `max_capacity` is a daily array rather than a single number, so capacity can
      vary across the year with operations.
    - During the irrigation season the canal is assumed already full for delivery,
      so its capacity is set to zero and it accepts no WAFR. That season's
      percolation is accounted for in a separate model.

    Note:
        `get_canal_volume_available` is deliberately separate from the inherited
        `Basin.get_basin_volume_available` rather than overriding it: the two use
        different capacity calculations, and `Basin.use_basin` must keep calling
        the basin one.
    """

    def __init__(
        self,
        irrigation_days=None,
        **kwargs,
    ):
        """Build a canal.

        Args:
            irrigation_days: zero-indexed days of the water year in the irrigation
                season, during which the canal accepts no WAFR.
            **kwargs: all other `Basin` and `BaseSite` arguments. `max_capacity` is
                given as a single value (acre-feet) and expanded into a daily array.
        """
        super().__init__(**kwargs)

        self.recharge_type = "Canal"
        self.max_capacity = self._calculate_daily_capacity(
            self.max_capacity, irrigation_days if irrigation_days is not None else []
        )  # array supersedes the basin variable to account for changes in volume due to operations

    def _calculate_daily_capacity(self, max_capacity, irrigation_days: list | None = None):
        """Expand a single capacity figure into a daily array for the water year.

        Irrigation-season days are set to zero capacity, so the canal accepts no
        WAFR on those days.

        Args:
            max_capacity: canal capacity outside the irrigation season (acre-feet).
            irrigation_days: zero-indexed days in the irrigation season.

        Returns:
            Capacity (acre-feet) for each day of the water year.
        """
        if irrigation_days is None:
            irrigation_days = []

        capacity_array = np.full(DAYS_PER_WATER_YEAR, fill_value=0.0)  # init empty array
        for d in range(DAYS_PER_WATER_YEAR):
            if d in irrigation_days:
                capacity_array[d] = 0.0
            else:
                capacity_array[d] = max_capacity

        return capacity_array

    def get_canal_volume_available(self, day: int):
        """Return how much water the canal could accept on a day.

        Headroom is the day's capacity less the standing volume, plus the volume
        that will percolate away that day. Never negative.

        Args:
            day: zero-indexed day of the water year.

        Returns:
            Volume the canal could accept (acre-feet). Zero during the irrigation
            season, when the canal is assumed already full for delivery.
        """
        if self.max_capacity[day] == 0:
            return 0  # no capacity on this day (irrigation season). Assumed full (perc accounted in different model)
        return max(self.max_capacity[day] - self.current_capacity + self.perc_rate, 0)

    def use_canal(self, day: int, wafr: dict, source: str, usable_volume_from_source: float):
        """Apply an already-allocated volume from one WAFR source to this canal.

        The allocation is decided by `proportionally_fill`; this method applies the
        smaller of that allocation and the canal's own headroom.

        Args:
            day: zero-indexed day of the water year.
            wafr: volume still available (acre-feet) per day, keyed by WAFR source
                name. **Mutated**: water applied here is subtracted from it.
            source: name of the source supplying the water.
            usable_volume_from_source: volume this canal has been allocated from
                that source (acre-feet).
        """
        volume_available_from_wafr = wafr[source][day]
        if volume_available_from_wafr > 0 and usable_volume_from_source > 0:
            wafr_applied = min(self.get_canal_volume_available(day), usable_volume_from_source)
            self.set_used_volume(day, wafr_applied)
            wafr[source][day] -= wafr_applied
            self.set_wafr_log(source, wafr_applied)

    def __repr__(self):
        """Return every attribute of the canal, including the full daily arrays."""
        return f"{self.__dict__}"


def proportionally_fill(
    day: int,
    canal_list: list,
    wafr: dict,
    selected_wafr: str,
    secondary_wafr: bool = False,
):
    """Share one WAFR source's water across the canals it can reach.

    Unlike basins and farms, which are filled in priority order until the water
    runs out, canals are filled together: each one receives a share of the source's
    volume in proportion to how much headroom it has. If the source has enough
    water for everyone, every canal fills.

    Args:
        day: zero-indexed day of the water year.
        canal_list: canals to consider. Those the source cannot reach are skipped.
        wafr: volume still available (acre-feet) per day, keyed by WAFR source
            name. **Mutated**: water applied is subtracted from it.
        selected_wafr: name of the WAFR source being shared out.
        secondary_wafr: match canals on their secondary (out-of-district) sources
            instead of their primary (in-district) ones.
    """
    volume_available_from_wafr = wafr[selected_wafr][day]  # volume available from this WAFR source

    if volume_available_from_wafr > 0:
        if secondary_wafr:
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
    """Fill the canals from every WAFR source that has water.

    Sources are worked through largest first, so the most plentiful source is
    shared out before the scarcer ones. Each is distributed by
    `proportionally_fill`.

    Args:
        canal_list: canals to fill.
        day: zero-indexed day of the water year.
        wafr: volume still available (acre-feet) per day, keyed by WAFR source
            name. **Mutated**: water applied is subtracted from it.
        secondary_wafr: match canals on their secondary (out-of-district) sources
            instead of their primary (in-district) ones.
    """
    wafr_order = sort_wafr_source_by_volume(wafr, day)  # sort WAFR sources by volume currently available

    for wafr_source in wafr_order:
        proportionally_fill(day, canal_list, wafr, wafr_source, secondary_wafr=secondary_wafr)

    return


def canals_update_daily_values(canal_list: list, day: int):
    """Drain a day's percolation from every canal into groundwater recharge.

    Call once per day after the canals have been filled. See
    `Basin.update_daily_values`, which canals inherit.

    Args:
        canal_list: canals to drain.
        day: zero-indexed day of the water year.
    """
    for c in canal_list:
        c.update_daily_values(day)  # update daily values
    return
