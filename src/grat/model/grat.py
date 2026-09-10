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
    canalList,
    basinList,
    inLieuSites,
    ofrSites,
    bottlenecks,
    cropCalendar,
    cropCalendarIL,
    transferLimits,
):
    """
    Runs through canals, in-lieu, basins, ofr sites in order and calculates recharge if the site can accept it.
    Args:
        day: zero-indexed day of the water year
        wafr: dictionary of water available for recharge
        canalList: list of canal objects
        basinList: list of basins
        inLieuSites: list of in-lieu sites
        ofrSites: list of OFR sites
        bottlenecks: list of bottleneck objects
        cropCalendar: dictionary of the times of the year that determine when crops can accept water for OFR
        cropCalendarIL: dictionary of the times of the year that determine when crops can accept water for in-lieu
        transferLimits: dictionary of transfer limits for each district

    Returns:

    """
    # use primary wafr sources to fill canals first
    fill_canals(canalList, day, wafr, secondaryWAFR=False)

    # use primary wafr sources (in-district) to fill in-lieu, basins, on-farm-recharge
    if check_wafr_availability(wafr, day):
        # use in-lieu sites
        use_farms(
            inLieuSites,
            day,
            wafr,
            bottlenecks,
            cropCalendarIL,
            inLieu=True,
            transferLimits=transferLimits,
        )

        # use basins
        fill_basins(basinList, day, wafr, bottlenecks, transferLimits=transferLimits)

        # use on-farm recharge sites
        use_farms(
            ofrSites,
            day,
            wafr,
            bottlenecks,
            cropCalendar,
            inLieu=False,
            transferLimits=transferLimits,
        )

    # use secondary wafr sources to fill canals if needed
    fill_canals(canalList, day, wafr, secondaryWAFR=True)

    # use secondary wafr sources (out-off district) to fill in-lieu, basins, on-farm-recharge
    if check_wafr_availability(wafr, day):
        # use in-lieu sites
        use_farms(
            inLieuSites,
            day,
            wafr,
            bottlenecks,
            cropCalendarIL,
            inLieu=True,
            secondaryWAFR=True,
            transferLimits=transferLimits,
        )

        # use basins
        fill_basins(
            basinList,
            day,
            wafr,
            bottlenecks,
            secondaryWAFR=True,
            transferLimits=transferLimits,
        )

        # use on-farm recharge sites
        use_farms(
            ofrSites,
            day,
            wafr,
            bottlenecks,
            cropCalendar,
            inLieu=False,
            secondaryWAFR=True,
            transferLimits=transferLimits,
        )

    canals_update_daily_values(canalList, day)
    basins_update_daily_values(basinList, day)

    return


@timer_func
def process_year(
    siteList,
    bottleneckList,
    wafr,
    cropCalendar,
    precip,
    cropCalendarIL=None,
    useInLieu=True,
    useOFR=True,
    rmaSort=True,
    transferLimits=None,
):
    """
    Run GRAT for a single year. Iterate over the sites in order and apply water

    Args:
        siteList: lists of canals, basins, farms
        bottleneckList: list of bottleneck objects
        wafr: dictionary of water available for recharge
        cropCalendar: dictionary of when crops can receive water
        precip: dictionary of water from precip
        cropCalendarIL: dictionary of when crops can receive water for in-lieu
        useInLieu: boolean to use in-lieu sites
        useOFR: boolean to use on-farm-recharge sites
        rmaSort: boolean to pass through if il-lieu sites need to be sorted by RMA
        transferLimits: dictionary of transfer limits for each district

    Returns: modified siteMap, canals, bottlenecks, wafr
    """

    if transferLimits is None:
        transferLimits = {}

    # calculate number of days from the first wafr source
    num_days = len(wafr[list(wafr.keys())[0]])

    # update the precipArray for all the sites
    [s.calc_precip(precip) for s in siteList if s.rechargeType != "Canal"]

    basinList, inLieuSites, ofrSites, canalList = group_sites_by_recharge_type(
        siteList, useInLieu, useOFR, rmaSort=rmaSort
    )

    # loop through each day in the year
    for day in range(0, num_days):
        # use canals, in-lieu farms, fill basins, use on-farm-recharge
        use_sites(
            day,
            wafr,
            canalList,
            basinList,
            inLieuSites,
            ofrSites,
            bottleneckList,
            cropCalendar,
            cropCalendarIL,
            transferLimits,
        )

    return {
        "sites": siteList,
        "wafr": wafr,
        "bottlenecks": bottleneckList,
        "transferLimits": transferLimits,
    }


def start_analysis(
    rawSites,
    rawWAFR,
    rawBottlenecks,
    cropCalendar,
    precip,
    years=None,
    cropCalendarIL=None,
    outputFolder=None,
    selectedReports=None,
    useInLieu=True,
    useOFR=True,
    rmaSort=True,
    transfer_goals=None,
):
    """
    Runs analysis for multiple years

    Args:
        rawSites: list of canals, basins and farm objects that are in sequenced order
        rawWAFR: input dictionary of the water available for recharge
        rawBottlenecks: bottleneck object
        cropCalendar: dictionary of the times of the year that determine when crops can accept water
        precip: dictionary of water from precipitation
        years: lists of years to run analysis
        cropCalendarIL: dictionary of when crops can receive water for in-lieu
        outputFolder: folder to save results
        selectedReports: list of reports to generate
        useInLieu: boolean to use in-lieu sites
        useOFR: boolean to use on-farm-recharge sites
        rmaSort: boolean to pass through to enable in-lieu sites to be sorted by RMA
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
        year_rawWAFR = rawWAFR[year]

        year_precip = precip[year] if precip is not None else None

        # deep clone the objects so each year is independent
        # use pickle dumps then pickle loads -> slightly faster
        sites = pickle.loads(pickle.dumps(rawSites))
        wafr = pickle.loads(pickle.dumps(year_rawWAFR))
        bottlenecks = pickle.loads(pickle.dumps(rawBottlenecks))

        # logic for the transfer limits dictionary
        transferLimits = calc_transfer_limits(
            wafr,
            transfer_supply_sources,
            transfer_goals,
        )

        process_year(
            sites,
            bottlenecks,
            wafr,
            cropCalendar,
            year_precip,
            cropCalendarIL,
            useInLieu,
            useOFR,
            rmaSort,
            transferLimits,
        )

        # TODO - reportPicker not ported over yet to OSGRAT
        # if selectedReports is not None:
        #     selector.reportPicker(
        #         selectedReports,
        #         outputFolder,
        #         year,
        #         sites,
        #         year_rawWAFR,
        #         wafr,
        #         bottlenecks,
        #         transfer_list=transferLimits.keys() if transferLimits else None,
        #     )

        del sites, wafr, bottlenecks  # delete to reduce memory consumption

    # TODO - postProcess not ported over yet to OSGRAT
    # # post process for operations that collate multiple temp files
    # if selectedReports is not None:
    #     frontend_viz_results = selector.postProcess(selectedReports, outputFolder)
    # return frontend_viz_results

    return
