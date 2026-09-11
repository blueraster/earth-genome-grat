"""Top-level water allocation across canals, basins and farms.

GRAT allocates each day's water available for recharge (WAFR) to the sites that
can take it, working down a priority order. `start_analysis` runs a span of
years, `process_year` runs one, and `use_sites` runs a single day.

Within a day the order is fixed: canals, then in-lieu fields, then basins, then
on-farm recharge. That whole sequence runs twice — once drawing on each
district's own (primary) sources, and again on other districts' (secondary)
sources for whatever is left.
"""

import logging
import pickle
from time import time

from grat.model.constants import DEFAULT_YEARS
from grat.model.sorters import group_sites_by_recharge_type
from grat.model.transfers import calc_transfer_limits

logger = logging.getLogger(__name__)

# TODO - these are hard-code to remove need for config.py but need to be moved OSGRAT
transfer_supply_sources = {}


def timer_func(func):
    """Log how long the decorated function took to run.

    Args:
        func: the function to time.

    Returns:
        The wrapped function, which logs its runtime at INFO level once it
        returns and then passes the result through unchanged.
    """

    def wrap_func(*args, **kwargs):
        t1 = time()
        result = func(*args, **kwargs)
        t2 = time()
        logger.info("Function %r executed in %.4fs", func.__name__, t2 - t1)
        return result

    return wrap_func


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


def sort_wafr_source_by_volume(wafr: dict, day: int):
    """Rank the WAFR sources that have a non-zero volume on a day, largest first.

    Args:
        wafr: volume available (acre-feet) per day, keyed by WAFR source name.
        day: zero-indexed day of the water year.

    Returns:
        Source names in descending order of volume. Sources sitting at exactly
        zero that day are omitted; the test is for non-zero, so a negative
        volume is kept and sorts last.
    """
    non_zero_sources = [source for source in wafr if wafr[source][day] != 0]
    return sorted(non_zero_sources, key=lambda x: wafr[x][day], reverse=True)


def check_wafr_availability(wafr, day):
    """Report whether any WAFR source has water left on a day.

    Used to skip the remaining allocation work once the day's water is spent.

    Args:
        wafr: volume available (acre-feet) per day, keyed by WAFR source name.
        day: zero-indexed day of the water year.

    Returns:
        `True` if any source has water that day, `False` otherwise.
    """
    # get the day's volume by looping over the wafr dictionary and summing the total
    total_volume = sum([v[day] for k, v in wafr.items()])
    return total_volume > 0


def use_sites(
    day,
    wafr,
    canal_list,
    basin_list,
    in_lieu_sites,
    ofr_sites,
    bottlenecks,
    crop_calendar,
    crop_calendar_in_lieu,
    transfer_limits,
):
    """Allocate a single day's water across every site that can take it.

    Runs the priority order twice: first against each district's own primary
    sources, then against secondary sources from other districts for whatever
    water is left. Within each pass the order is canals, in-lieu fields, basins,
    on-farm recharge. The three site types after canals are skipped entirely if
    the day's water is already spent.

    Ends by draining the day's percolation from the canals and basins into
    groundwater recharge.

    Args:
        day: zero-indexed day of the water year.
        wafr: volume still available (acre-feet) per day, keyed by WAFR source
            name. **Mutated**: water applied is subtracted from it.
        canal_list: canals, in processing order.
        basin_list: basins, in processing order.
        in_lieu_sites: in-lieu fields, in processing order.
        ofr_sites: on-farm recharge fields, in processing order.
        bottlenecks: every bottleneck in the system. **Mutated**.
        crop_calendar: accepted application rate (feet per day) for on-farm
            recharge, indexed as `[crop][soil_type][day]`.
        crop_calendar_in_lieu: accepted application rate (feet per day) for
            in-lieu recharge, indexed as `[crop][region_number][day]`.
        transfer_limits: remaining yearly transfer budget (acre-feet) per
            district. **Mutated**.
    """
    # use primary wafr sources to fill canals first
    fill_canals(canal_list, day, wafr, secondary_wafr=False)

    # use primary wafr sources (in-district) to fill in-lieu, basins, on-farm-recharge
    if check_wafr_availability(wafr, day):
        # use in-lieu sites
        use_farms(
            in_lieu_sites,
            day,
            wafr,
            bottlenecks,
            crop_calendar_in_lieu,
            in_lieu=True,
            transfer_limits=transfer_limits,
        )

        # use basins
        fill_basins(basin_list, day, wafr, bottlenecks, transfer_limits=transfer_limits)

        # use on-farm recharge sites
        use_farms(
            ofr_sites,
            day,
            wafr,
            bottlenecks,
            crop_calendar,
            in_lieu=False,
            transfer_limits=transfer_limits,
        )

    # use secondary wafr sources to fill canals if needed
    fill_canals(canal_list, day, wafr, secondary_wafr=True)

    # use secondary wafr sources (out-off district) to fill in-lieu, basins, on-farm-recharge
    if check_wafr_availability(wafr, day):
        # use in-lieu sites
        use_farms(
            in_lieu_sites,
            day,
            wafr,
            bottlenecks,
            crop_calendar_in_lieu,
            in_lieu=True,
            secondary_wafr=True,
            transfer_limits=transfer_limits,
        )

        # use basins
        fill_basins(
            basin_list,
            day,
            wafr,
            bottlenecks,
            secondary_wafr=True,
            transfer_limits=transfer_limits,
        )

        # use on-farm recharge sites
        use_farms(
            ofr_sites,
            day,
            wafr,
            bottlenecks,
            crop_calendar,
            in_lieu=False,
            secondary_wafr=True,
            transfer_limits=transfer_limits,
        )

    canals_update_daily_values(canal_list, day)
    basins_update_daily_values(basin_list, day)

    return


@timer_func
def process_year(
    site_list,
    bottleneck_list,
    wafr,
    crop_calendar,
    precip,
    crop_calendar_in_lieu=None,
    use_in_lieu=True,
    use_ofr=True,
    rma_sort=True,
    transfer_limits=None,
):
    """Run GRAT for a single water year.

    Applies precipitation to every site except canals, groups the sites by
    recharge type, then walks the year one day at a time allocating water. The
    length of the year is taken from the WAFR series, so a 366-entry series runs
    a leap year.

    Args:
        site_list: every canal, basin and farm, already in processing order.
            **Mutated**: the sites accumulate the year's results.
        bottleneck_list: every bottleneck in the system. **Mutated**.
        wafr: volume available (acre-feet) per day, keyed by WAFR source name.
            **Mutated**: drawn down to zero as the year is allocated.
        crop_calendar: accepted application rate (feet per day) for on-farm
            recharge, indexed as `[crop][soil_type][day]`.
        precip: daily precipitation depth (decimal-feet) for the water year,
            keyed by precipitation grid identifier. `None` skips precipitation.
        crop_calendar_in_lieu: accepted application rate (feet per day) for
            in-lieu recharge, indexed as `[crop][region_number][day]`.
        use_in_lieu: include in-lieu recharge.
        use_ofr: include on-farm recharge.
        rma_sort: order in-lieu sites by RMA rank first.
        transfer_limits: yearly transfer budget (acre-feet) per district, from
            `transfers.calc_transfer_limits`. **Mutated**: drawn down as
            transfers are made. `None` disables transfer limiting.

    Returns:
        The year's results, holding the modified `sites`, `wafr`, `bottlenecks`
        and `transfer_limits`.
    """
    if transfer_limits is None:
        transfer_limits = {}

    # calculate number of days from the first wafr source
    num_days = len(wafr[list(wafr.keys())[0]])

    # update the precip array for all the sites
    for site in site_list:
        if site.recharge_type != "Canal":
            site.calc_precip(precip)

    basin_list, in_lieu_sites, ofr_sites, canal_list = group_sites_by_recharge_type(
        site_list, use_in_lieu, use_ofr, rma_sort=rma_sort
    )

    # loop through each day in the year
    for day in range(0, num_days):
        # use canals, in-lieu farms, fill basins, use on-farm-recharge
        use_sites(
            day,
            wafr,
            canal_list,
            basin_list,
            in_lieu_sites,
            ofr_sites,
            bottleneck_list,
            crop_calendar,
            crop_calendar_in_lieu,
            transfer_limits,
        )

    return {
        "sites": site_list,
        "wafr": wafr,
        "bottlenecks": bottleneck_list,
        "transfer_limits": transfer_limits,
    }


def start_analysis(
    raw_sites,
    raw_wafr,
    raw_bottlenecks,
    crop_calendar,
    precip,
    years=None,
    crop_calendar_in_lieu=None,
    output_folder=None,
    selected_reports=None,
    use_in_lieu=True,
    use_ofr=True,
    rma_sort=True,
    transfer_goals=None,
):
    """Run GRAT across a span of water years.

    Each year is run against a deep copy of the inputs, so the sites, WAFR and
    bottlenecks start every year in their original state and the years stay
    independent of one another. The copies are discarded once the year is done.

    Args:
        raw_sites: every canal, basin and farm, in processing order. Copied per
            year, so this list is not modified.
        raw_wafr: volume available (acre-feet) per day, keyed by WAFR source
            name, for each year — indexed as `[year][source][day]`.
        raw_bottlenecks: every bottleneck in the system. Copied per year.
        crop_calendar: accepted application rate (feet per day) for on-farm
            recharge, indexed as `[crop][soil_type][day]`.
        precip: daily precipitation depth (decimal-feet) for each year, indexed
            as `[year][precip_grid][day]`. `None` skips precipitation.
        years: water years to run. Defaults to 2001-2099.
        crop_calendar_in_lieu: accepted application rate (feet per day) for
            in-lieu recharge, indexed as `[crop][region_number][day]`.
        output_folder: folder to write reports into. Not yet used — the
            reporting layer has not been ported.
        selected_reports: reports to generate. Not yet used — the reporting
            layer has not been ported.
        use_in_lieu: include in-lieu recharge.
        use_ofr: include on-farm recharge.
        rma_sort: order in-lieu sites by RMA rank first.
        transfer_goals: transfer goal per district or sustainability zone, used
            to derive each year's transfer budgets. See
            `transfers.calc_transfer_limits`.

    Note:
        Returns nothing at present. Each year's results are computed and then
        discarded, because the reporting layer that consumed them has not been
        ported yet. Call `process_year` directly to get a year's results back.
    """
    if transfer_goals is None:
        transfer_goals = {}

    if years is None:
        years = DEFAULT_YEARS

    for year in years:
        logger.info("Running GRAT for %s", year)

        # select just the current water year from the WAFR input
        year_raw_wafr = raw_wafr[year]

        year_precip = precip[year] if precip is not None else None

        # deep clone the objects so each year is independent
        # use pickle dumps then pickle loads -> slightly faster
        sites = pickle.loads(pickle.dumps(raw_sites))
        wafr = pickle.loads(pickle.dumps(year_raw_wafr))
        bottlenecks = pickle.loads(pickle.dumps(raw_bottlenecks))

        # logic for the transfer limits dictionary
        transfer_limits = calc_transfer_limits(
            wafr,
            transfer_supply_sources,
            transfer_goals,
        )

        process_year(
            sites,
            bottlenecks,
            wafr,
            crop_calendar,
            year_precip,
            crop_calendar_in_lieu,
            use_in_lieu,
            use_ofr,
            rma_sort,
            transfer_limits,
        )

        # TODO - reportPicker not ported over yet to OSGRAT
        # if selected_reports is not None:
        #     selector.reportPicker(
        #         selected_reports,
        #         output_folder,
        #         year,
        #         sites,
        #         year_raw_wafr,
        #         wafr,
        #         bottlenecks,
        #         transfer_list=transfer_limits.keys() if transfer_limits else None,
        #     )

        del sites, wafr, bottlenecks  # delete to reduce memory consumption

    # TODO - postProcess not ported over yet to OSGRAT
    # # post process for operations that collate multiple temp files
    # if selected_reports is not None:
    #     frontend_viz_results = selector.postProcess(selected_reports, output_folder)
    # return frontend_viz_results

    return
