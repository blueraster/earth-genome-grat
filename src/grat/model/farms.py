"""Agriculture recharge."""

import math

import numpy as np

from . import bottlenecks
from .base_site import BaseSite


def turnout_limit_conversion(cfs_rate):
    """Convert a turnout's flow rate into the volume it can deliver in a day.

    One cubic-foot per second sustained for 24 hours is 86,400 cubic feet, which
    is roughly 1.983 acre-feet.

    Args:
        cfs_rate: flow rate (cubic-feet per second).

    Returns:
        Volume deliverable in one day (acre-feet per day).
    """
    return cfs_rate * 1.983


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
