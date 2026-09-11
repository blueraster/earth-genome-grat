"""Base class used for all recharge types."""

import logging
import math

import numpy as np

from . import bottlenecks
from .constants import CFS_TO_ACRE_FEET_PER_DAY, DAYS_PER_WATER_YEAR, DEFAULT_CFS_LIMIT
from .utils import sort_wafr_source_by_volume

logger = logging.getLogger(__name__)


class BaseSite:
    """Foundation for every recharge site (basins, canals and farms).

    A site holds the static attributes that describe a parcel (area, location,
    which WAFR sources can reach it) plus the per-day arrays that the model
    fills in as it allocates water across the water year. All volumes are in
    acre-feet unless stated otherwise, and all day indexes are zero-indexed
    days of the water year.

    Attributes:
        wafr_sources: combined primary and secondary WAFR source names, built at
            construction time from `wafr_sources_primary` + `wafr_sources_secondary`.
        used_volume: daily volume applied to the site (acre-feet), one entry per day.
            Populated for basins and canals only — `Farm` overrides
            `set_used_volume` and records into its own arrays, leaving this at zero.
        daily_recharge_volumes: daily volume that reached groundwater (acre-feet).
            Populated for basins and canals only — `Farm` overrides
            `set_daily_recharge` and records into its own arrays, leaving this at
            zero.
        precip: daily volume received as precipitation (acre-feet), populated by
            `calc_precip`.
        wafr_log: running total of volume supplied (acre-feet), keyed by WAFR
            source name.
        sort_index: position of the site in the processing order, assigned by
            `sorters.sort_sites`. `None` until the site has been sorted.
    """

    def __init__(
        self,
        grat_id,
        acres=0,
        recharge_type=None,
        bottleneck_ids=None,
        wafr_sources_primary=None,
        wafr_sources_secondary=None,
        precip_grid=0,
        district=None,
        subbasin=None,
        watershed=None,
        agency=None,
        nondistrict=None,
        inbasinret=None,
        dac=None,
        gsc=None,
        streamretu=None,
        subsidence=None,
        shorebird=None,
        rsi=None,
        groundwater_change=None,
        rma=None,
        region_number=None,
        mlrp_score=None,
        projects=None,
        sustainability_zone=None,
        depth_to_groundwater=None,
        **kwargs,
    ):
        """Build a site.

        Args:
            grat_id: internal unique identifier for the site.
            acres: polygon area in acres.
            recharge_type: type of recharge at the site, e.g. "Canal", "Basin" or "OFR".
                Determines which sublist the site is grouped into by
                `sorters.group_sites_by_recharge_type`.
            bottleneck_ids: identifiers of the bottlenecks that restrict flow to this
                site. A single identifier is accepted and wrapped in a list.
            wafr_sources_primary: names of the sources that can supply water to this
                site from within its own district.
            wafr_sources_secondary: names of the sources that can supply water to this
                site from other districts. Used only after the primary sources are spent.
            precip_grid: identifier of the precipitation grid cell covering this site.
                Used as the lookup key into the precipitation dictionary passed to
                `calc_precip`.
            district: district the site belongs to. Transfer limits are tracked per
                district, so this is the key used to charge a transfer against a budget.
            agency: agency the site belongs to, referred to as the GSA elsewhere in
                the model. Used by `sorters.mlrp_sorter` to pool acreage per agency.
            rsi: RSI score. Higher scores are processed first by the default sort rule.
            rma: RMA rank. Lower ranks are processed first by the "RMA" sort rule.
            groundwater_change: change in groundwater level. Lower (more negative)
                values are prioritised when ordering in-lieu sites.
            region_number: climate region number. Used as the crop calendar lookup key
                for in-lieu recharge, where accepted rates vary by region.
            mlrp_score: MLRP rank. Lower ranks are converted to the "MLRP" crop first
                by `sorters.mlrp_sorter`.
            sustainability_zone: sustainability zone name. Coerced to a string when set.
            subbasin: groundwater subbasin containing the site.
            watershed: watershed containing the site.
            depth_to_groundwater: depth to groundwater at the site.
            projects: projects associated with the site.
            nondistrict: site attribute carried through the model. Meaning not
                documented in this codebase.
            inbasinret: site attribute carried through the model. Meaning not
                documented in this codebase.
            dac: site attribute carried through the model. Meaning not documented in
                this codebase.
            gsc: site attribute carried through the model. Meaning not documented in
                this codebase.
            streamretu: site attribute carried through the model. Meaning not
                documented in this codebase.
            subsidence: site attribute carried through the model. Meaning not
                documented in this codebase.
            shorebird: site attribute carried through the model. Meaning not
                documented in this codebase.
            **kwargs: additional site attributes. `wafr_sources` is accepted here as an
                alias for `wafr_sources_primary`; anything else is ignored.

        Note:
            `subbasin`, `watershed`, `depth_to_groundwater`, `projects`, `nondistrict`,
            `inbasinret`, `dac`, `gsc`, `streamretu`, `subsidence`, `shorebird` and
            `sustainability_zone` are stored on the site but are not read by any model
            calculation. They are carried through so the reporting layer can group and
            filter results.
        """
        # site info
        self.grat_id = grat_id
        self.acres = acres
        self.recharge_type = recharge_type
        if wafr_sources_primary is None and "wafr_sources" in kwargs:
            wafr_sources_primary = kwargs["wafr_sources"]
        self.wafr_sources_primary = wafr_sources_primary
        self.wafr_sources_secondary = wafr_sources_secondary

        if bottleneck_ids is not None and not isinstance(bottleneck_ids, (list, tuple, set)):
            bottleneck_ids = [bottleneck_ids]
        self.bottleneck_ids = bottleneck_ids

        # init empty default values
        self.used_volume = np.full(DAYS_PER_WATER_YEAR, 0.0)
        self.daily_recharge_volumes = np.full(DAYS_PER_WATER_YEAR, 0.0)
        self.precip = np.full(DAYS_PER_WATER_YEAR, 0.0)
        self.wafr_log = {}

        # sort index (order sites are processed)
        self.precip_grid = precip_grid
        self.sort_index = None
        self.rsi = rsi
        self.subbasin = subbasin
        self.district = district
        self.watershed = watershed
        self.agency = agency
        self.nondistrict = nondistrict
        self.inbasinret = inbasinret
        self.dac = dac
        self.gsc = gsc
        self.streamretu = streamretu
        self.subsidence = subsidence
        self.shorebird = shorebird
        self.rma = rma
        self.groundwater_change = groundwater_change
        self.region_number = region_number  # climate region number
        self.sustainability_zone = None if sustainability_zone is None else str(sustainability_zone)
        if self.wafr_sources_primary is None:
            self.wafr_sources_primary = []
        if self.wafr_sources_secondary is None:
            self.wafr_sources_secondary = []

        self.wafr_sources = self.wafr_sources_primary + self.wafr_sources_secondary

        self.mlrp_score = mlrp_score
        self.projects = projects
        self.depth_to_groundwater = depth_to_groundwater

    def calc_precip(self, precip_dictionary: dict):
        """Populate the site's daily precipitation volumes.

        Multiplies the site area (acres) by the depth received at the site's
        precipitation grid cell (decimal-feet) to give a volume in acre-feet, and
        writes the result into `self.precip`.

        Does nothing if the site has no precipitation grid or no dictionary is
        supplied. Logs a warning and leaves `self.precip` untouched if the site's
        grid is missing from the dictionary.

        Args:
            precip_dictionary: daily precipitation depth (decimal-feet) for the water
                year, keyed by precipitation grid identifier.
        """
        if self.precip_grid is not None and precip_dictionary is not None:
            if self.precip_grid not in precip_dictionary:
                logger.warning(
                    "Site %s has precip_grid %s which is not found in the precip_dictionary",
                    self.grat_id,
                    self.precip_grid,
                )
                return

            precip_values = [g * self.acres for g in precip_dictionary[self.precip_grid]]
            for idx, v in enumerate(precip_values):
                self.precip[idx] = v
        return

    def set_daily_recharge(self, day: int, new_volume: float):
        """Add volume to the site's groundwater recharge for a day.

        Args:
            day: zero-indexed day of the water year.
            new_volume: volume to add (acre-feet).
        """
        self.daily_recharge_volumes[day] += new_volume

    def set_wafr_log(self, wafr_source: str, volume: float):
        """Record volume supplied to this site by a WAFR source.

        Accumulates across the whole water year rather than per day: repeated calls
        for the same source add to its running total.

        Args:
            wafr_source: name of the WAFR source that supplied water to this site.
            volume: volume supplied by that source (acre-feet).
        """
        # check if the wafr src is already in the dictionary, if so then just add the volume
        current_value = self.wafr_log.get(wafr_source, None)  # will return none if the key doesn't exist
        if current_value is None:
            self.wafr_log[wafr_source] = volume
        else:
            self.wafr_log[wafr_source] = current_value + volume  # add the new volume to the existing value

    def __repr__(self):
        """Return every attribute of the site, including the full daily arrays."""
        return f"{self.__dict__}"


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


# TODO move this to operations.py or similar
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


def turnout_limit_conversion(cfs_rate):
    """Convert a turnout's flow rate into the volume it can deliver in a day.

    See `constants.CFS_TO_ACRE_FEET_PER_DAY` for the conversion factor.

    Args:
        cfs_rate: flow rate (cubic-feet per second).

    Returns:
        Volume deliverable in one day (acre-feet per day).
    """
    return cfs_rate * CFS_TO_ACRE_FEET_PER_DAY


class Farm(BaseSite):
    """A field in agricultural production, used for on-farm or in-lieu recharge.

    A farm supports two distinct recharge methods, tracked in separate sets of
    arrays so they can be reported independently:

    **On-farm recharge (OFR)**, or direct recharge, reduces groundwater level
    decline by applying surface water in excess of crop demand (ETc), at levels
    that do not interfere with crop development. The crop compatibility calendar
    (CCC) determines how much WAFR a field under a given crop can take. Only crops
    present in the calendar are included in on-farm calculations.

    **In-lieu recharge** is surface water used in lieu of pumping groundwater. It
    reduces pumping by meeting crop demand (ETc) with surface water instead of
    groundwater. Accepted rates vary by climate region rather than by soil.

    How much a field can take on a day is capped by the crop calendar, by the
    turnout's flow limit, and by any bottlenecks between it and the source.
    Precipitation counts against the field's capacity, since rain has already met
    part of the demand.

    Attributes:
        flow_limit: volume the turnout can still deliver (acre-feet), one entry per
            day. Drawn down as water is applied.
        ofr_used_volume: daily volume applied as on-farm recharge (acre-feet).
        ofr_unused_volume: daily volume the field could have taken but did not
            receive (acre-feet), whether limited by available water, a bottleneck
            or the turnout.
        ofr_daily_recharge_volumes: daily volume reaching groundwater via on-farm
            recharge (acre-feet).
        in_lieu_used_volume: daily volume applied as in-lieu recharge (acre-feet).
        in_lieu_unused_volume: daily in-lieu volume the field could have taken but
            did not receive (acre-feet).
        in_lieu_daily_recharge_volumes: daily volume attributed to in-lieu recharge
            (acre-feet).
        used_precip: precipitation already counted against the field's capacity
            (acre-feet), tracked to avoid deducting the same rain twice.
    """

    def __init__(self, soil_type, cfs_limit, crop=None, in_lieu_crop=None, **kwargs):
        """Build a farm site.

        Args:
            soil_type: soil classification from SAGBI, used with `crop` to look up
                accepted rates in the on-farm crop calendar.
            cfs_limit: rate at which water can be applied to the site
                (cubic-feet per second). Defaults to 15 when `None`.
            crop: crop grown on the field, used for on-farm recharge. A field with
                no crop is excluded from on-farm calculations.
            in_lieu_crop: crop used for in-lieu recharge lookups. A field with no
                in-lieu crop is excluded from in-lieu calculations.
            **kwargs: all other `BaseSite` arguments.
        """
        super().__init__(**kwargs)
        self.crop = crop

        self.soil_type = soil_type
        self.cfs_limit = (
            cfs_limit if cfs_limit is not None else DEFAULT_CFS_LIMIT
        )  # default rate of water that can be applied to a site
        self.flow_limit = np.full(DAYS_PER_WATER_YEAR, float(turnout_limit_conversion(self.cfs_limit)))

        # # in lieu recharge attributes
        self.in_lieu_crop = in_lieu_crop
        self.in_lieu_unused_volume = np.full(DAYS_PER_WATER_YEAR, 0.0)
        self.in_lieu_used_volume = np.full(DAYS_PER_WATER_YEAR, 0.0)
        self.in_lieu_daily_recharge_volumes = np.full(DAYS_PER_WATER_YEAR, 0.0)

        self.ofr_unused_volume = np.full(DAYS_PER_WATER_YEAR, 0.0)
        self.ofr_used_volume = np.full(DAYS_PER_WATER_YEAR, 0.0)
        self.ofr_daily_recharge_volumes = np.full(DAYS_PER_WATER_YEAR, 0.0)

        self.used_precip = np.full(DAYS_PER_WATER_YEAR, 0.0)  # empty array to store precip that gets "used"

    def get_site_volume(self, day: int, crop_calendar: dict, in_lieu: bool = False):
        """Return how much water the field could still take on a day.

        Starts from the rate the crop calendar allows for this field, scaled by its
        area, less whatever has already been applied that day. Precipitation is then
        deducted, since rain has already met part of the demand — net of any rain
        already accounted for on a previous pass.

        The result may be negative when precipitation exceeds what the crop can
        take; callers clamp it at zero.

        Args:
            day: zero-indexed day of the water year.
            crop_calendar: accepted application rate (feet per day) by crop. Indexed
                as `[crop][soil_type][day]` for on-farm recharge, and as
                `[in_lieu_crop][region_number][day]` for in-lieu — the two calendars
                have different shapes and are not interchangeable.
            in_lieu: read the in-lieu calendar and in-lieu volumes rather than the
                on-farm ones.

        Returns:
            Volume the field could accept (acre-feet). For in-lieu recharge on a
            field with no climate region number the crop's accepted rate is taken
            as zero, so the result is the precipitation adjustment alone.
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
        """Record the volume the field could have taken but did not receive.

        Replaces the day's value rather than accumulating.

        Args:
            day: zero-indexed day of the water year.
            volume: unmet capacity (acre-feet).
            in_lieu: record against in-lieu recharge rather than on-farm.
        """
        if in_lieu:
            self.in_lieu_unused_volume[day] = volume
        else:
            self.ofr_unused_volume[day] = volume

    def set_used_volume(self, day: int, new_volume: float, in_lieu: bool = False):
        """Record water applied to the field on a day.

        Args:
            day: zero-indexed day of the water year.
            new_volume: volume applied (acre-feet).
            in_lieu: record against in-lieu recharge rather than on-farm.
        """
        if in_lieu:
            self.in_lieu_used_volume[day] += new_volume
        else:
            self.ofr_used_volume[day] += new_volume

        return

    def set_daily_recharge(self, day: int, new_volume: float, in_lieu: bool = False):
        """Add volume to the field's groundwater recharge for a day.

        Overrides `BaseSite.set_daily_recharge` to keep on-farm and in-lieu
        recharge in separate arrays.

        Args:
            day: zero-indexed day of the water year.
            new_volume: volume to add (acre-feet).
            in_lieu: record against in-lieu recharge rather than on-farm.
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
        transfer_limits: dict | None = None,
    ):
        """Apply water to this field as on-farm or in-lieu recharge.

        Works through the site's WAFR sources in order, taking from each the
        smallest of: what the crop can still accept, what the source has left that
        day, what the bottlenecks still allow, and what the turnout can deliver.
        Stops early once the crop can take no more.

        Args:
            dowy: zero-indexed day of the water year.
            wafr: volume still available (acre-feet) per day, keyed by WAFR source
                name. **Mutated**: water applied here is subtracted from it. A
                source the site names but the dictionary does not hold is treated
                as having no water.
            bottleneck_list: every bottleneck in the system. **Mutated**: the
                throughput used is subtracted from the bottlenecks crossed.
            crop_calendar: accepted application rate (feet per day) by crop. See
                `get_site_volume` for the two indexing shapes.
            in_lieu: apply as in-lieu recharge rather than on-farm.
            secondary_wafr: draw from the site's secondary (out-of-district)
                sources instead of its primary (in-district) ones.
            transfer_limits: remaining yearly transfer budget (acre-feet) per
                district. **Mutated**. `None` disables transfer limiting.
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
        """Return every attribute of the farm, including the full daily arrays."""
        return f"{self.__dict__}"


def use_farms(
    site_list: list,
    day: int,
    wafr: dict,
    bottleneck_list: list,
    crop_calendar: dict,
    in_lieu: bool = False,
    secondary_wafr: bool = False,
    transfer_limits: dict | None = None,
):
    """Apply water to every field in turn.

    Fields are served in list order, so earlier fields get first call on the
    available water. See `Farm.use_site` for how each one is filled.

    Args:
        site_list: fields to water, in processing order. Callers pass either the
            on-farm sites or the in-lieu sites, matched to `in_lieu`.
        day: zero-indexed day of the water year.
        wafr: volume still available (acre-feet) per day, keyed by WAFR source
            name. **Mutated**: water applied is subtracted from it.
        bottleneck_list: every bottleneck in the system. **Mutated**.
        crop_calendar: accepted application rate (feet per day) by crop. Must match
            `in_lieu` — see `Farm.get_site_volume`.
        in_lieu: apply as in-lieu recharge rather than on-farm.
        secondary_wafr: draw from secondary (out-of-district) sources instead of
            primary (in-district) ones.
        transfer_limits: remaining yearly transfer budget (acre-feet) per district.
            **Mutated**. `None` disables transfer limiting.
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
