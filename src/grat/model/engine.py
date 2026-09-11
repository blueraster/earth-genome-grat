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

from grat.model.basins import basins_update_daily_values, fill_basins
from grat.model.canals import canals_update_daily_values, fill_canals
from grat.model.constants import DEFAULT_YEARS
from grat.model.farms import use_farms
from grat.model.sorters import group_sites_by_recharge_type
from grat.model.transfers import calc_transfer_limits
from grat.model.utils import check_wafr_availability, timer_func

logger = logging.getLogger(__name__)

# TODO - these are hard-code to remove need for config.py but need to be moved OSGRAT
transfer_supply_sources = {}


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
