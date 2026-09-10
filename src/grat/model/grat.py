"""
Main logic for water allocation for canals, basins, sites
"""

import logging
import pickle

from grat.model.basins import basins_update_daily_values, fill_basins
from grat.model.canals import canals_update_daily_values, fill_canals
from grat.model.farms import use_farms
from grat.model.sorters import group_sites_by_recharge_type
from grat.model.transfers import calc_transfer_limits
from grat.model.utils import check_wafr_availability, timer_func

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
    """
    Runs through canals, in-lieu, basins, ofr sites in order and calculates recharge if the site can accept it.
    Args:
        day: zero-indexed day of the water year
        wafr: dictionary of water available for recharge
        canal_list: list of canal objects
        basin_list: list of basins
        in_lieu_sites: list of in-lieu sites
        ofr_sites: list of OFR sites
        bottlenecks: list of bottleneck objects
        crop_calendar: dictionary of the times of the year that determine when crops can accept water for OFR
        crop_calendar_in_lieu: dictionary of the times of the year that determine when crops can accept water
            for in-lieu
        transfer_limits: dictionary of transfer limits for each district

    Returns:

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
    """
    Run GRAT for a single year. Iterate over the sites in order and apply water

    Args:
        site_list: lists of canals, basins, farms
        bottleneck_list: list of bottleneck objects
        wafr: dictionary of water available for recharge
        crop_calendar: dictionary of when crops can receive water
        precip: dictionary of water from precip
        crop_calendar_in_lieu: dictionary of when crops can receive water for in-lieu
        use_in_lieu: boolean to use in-lieu sites
        use_ofr: boolean to use on-farm-recharge sites
        rma_sort: boolean to pass through if il-lieu sites need to be sorted by RMA
        transfer_limits: dictionary of transfer limits for each district

    Returns: dictionary of the modified sites, wafr, bottlenecks and transfer_limits
    """

    if transfer_limits is None:
        transfer_limits = {}

    # calculate number of days from the first wafr source
    num_days = len(wafr[list(wafr.keys())[0]])

    # update the precip array for all the sites
    [s.calc_precip(precip) for s in site_list if s.recharge_type != "Canal"]

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
    """
    Runs analysis for multiple years

    Args:
        raw_sites: list of canals, basins and farm objects that are in sequenced order
        raw_wafr: input dictionary of the water available for recharge
        raw_bottlenecks: bottleneck object
        crop_calendar: dictionary of the times of the year that determine when crops can accept water
        precip: dictionary of water from precipitation
        years: lists of years to run analysis
        crop_calendar_in_lieu: dictionary of when crops can receive water for in-lieu
        output_folder: folder to save results
        selected_reports: list of reports to generate
        use_in_lieu: boolean to use in-lieu sites
        use_ofr: boolean to use on-farm-recharge sites
        rma_sort: boolean to pass through to enable in-lieu sites to be sorted by RMA
        transfer_goals: dictionary of transfer goals for each district or sustainability zone

    Returns: dictionary of yearly results with year as key

    """
    if transfer_goals is None:
        transfer_goals = {}

    if years is None:
        years = range(2001, 2100)

    for year in years:
        logging.info(f"Running GRAT for {year}")

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
