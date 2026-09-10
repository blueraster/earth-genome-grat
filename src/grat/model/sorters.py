# functions that sort a list of sites (canals, basins, farms)
import logging
import operator


def recharge_type_order(site):
    """
    Set the sort priority order depending on recharge type
    Args:
        site: individual site with recharge_type attribute

    Returns:

    """
    if site.rechargeType == "Canal":
        return 1
    if site.rechargeType == "Basin":
        return 2
    if site.rechargeType == "OFR":
        return 3
    return 4


def none_aware_attrgetter(attr, reverse=False):
    """
    https://stackoverflow.com/questions/61452346/python-attrgetter-that-handles-none-values-and-can-be-used-in-a-loop
    Args:
        attr:

    Returns:

    """
    getter = operator.attrgetter(attr)

    def key_func(item):
        value = getter(item)
        if reverse is True:
            return (value is not None, value)
        return (value is None, value)

    return key_func


def sort_by_variable(list_of_sites, variable, reverse=False):
    """
    Sorts a list of site objects by a single variable

    NOTE: use sort_by_variables() for multiples

    Args:
        list_of_sites: list of site objects
        variable: object property name to use to sort
        reverse: boolean if the order should be ascending or descending

    Returns: sorted list of objects
    """

    return sorted(list_of_sites, key=none_aware_attrgetter(variable, reverse), reverse=reverse)


def sort_by_variables(list_of_sites, specs):
    """
    Sorts list of objects by attribute properties. Specify property names in least to most restrictive order

    sort_by_variables([siteA(), siteB()...], (("acres", True), ("index", True))

    https://docs.python.org/3/howto/sorting.html
    Args:
        list_of_sites: site objects
        specs: tuples with the object attribute + boolean if the sort is reversed

    Returns:

    """
    for attr, reverse in reversed(specs):
        list_of_sites.sort(key=none_aware_attrgetter(attr, reverse), reverse=reverse)
    return list_of_sites


def sort_sites(sitesList, sortRule=None):
    """
    Orders sites objects by various scenarios by sorting multiple object properties.
    The order the Object properties to sort by is important (most restrictive -> least).
    Always sort final list by recharge type last.

    Args:
        sitesList: list of unordered site object
        sortRule: name of the scenario's sort rule

    Returns: sorted list of sites

    """

    if sortRule is None:
        # sort by rsi score, acres and then finally by recharge type
        s = sort_by_variables(sitesList, (("rsi", True), ("acres", True)))
        s.sort(key=recharge_type_order)

    elif sortRule == "A":
        # test scenario for sorting
        # sort by recharge type, scenario, index score, acres
        s = sort_by_variables(sitesList, (("scenarioA", True), ("rsi", True), ("acres", True)))
        s.sort(key=recharge_type_order)

    elif sortRule == "RMA":
        # sort by RMA rank,rsi score, acres and then finally by recharge type
        s = sort_by_variables(sitesList, (("rma", False), ("rsi", True), ("acres", True)))
        s.sort(key=recharge_type_order)
    else:
        raise Exception("Unknown sort rule selected")

    # update sortIndex parameter
    sortedSitesList = []

    for i, site in enumerate(s):
        site.sortIndex = i + 1
        sortedSitesList.append(site)

    return sortedSitesList


def group_sites_by_recharge_type(siteList, useInLieu=True, useOFR=True, rmaSort=False):
    """
    Splits siteList into sublists by type (basins, in-lieu, on farm recharge)
    Args:
        siteList: list of objects (basins, farms)
        useInLieu: boolean if in-lieu sites should be included
        useOFR: boolean if on farm recharge sites should be included
        rmaSort: boolean if the in-lieu sites should be sorted by rma rank
    Returns: list of basins, list of in-lieu sites, list of ofr sites, list of canals

    """
    basinList = [s for s in siteList if s.rechargeType == "Basin"]
    canalList = [s for s in siteList if s.rechargeType == "Canal"]

    inLieuSites_unordered = [
        s for s in siteList if s.rechargeType not in ["Basin", "Canal"] and s.inLieuCrop is not None
    ]

    # Groundwater change used to sort in lieu sites. Within each RMA zone the
    # Lowest numbers (i.e most negative) have the highest priority.
    if rmaSort is True:
        logging.info("Sorting in-lieu sites by RMA rank")
        inLieuSites = sort_by_variables(inLieuSites_unordered, (("rma", False), ("groundwaterChange", False)))
    else:
        logging.info("Sorting in-lieu sites by groundwaterChange only")

        inLieuSites = sort_by_variable(inLieuSites_unordered, "groundwaterChange", False)

    ofrSites = [s for s in siteList if s.rechargeType not in ["Basin", "Canal"] and s.crop is not None]

    if useInLieu is False:
        inLieuSites = []

    if useOFR is False:
        ofrSites = []

    return basinList, inLieuSites, ofrSites, canalList


def mlrp_sorter(sites, gsa_target_percentage=None):
    """
    Sorts sites by MLRP rank per district and changes the crop type until the acreage is met.
    Args:
        sites: list of site objects
        gsa_target_percentage: dictionary of gda MLRP target percentages {'gda': 0.5, 'gsa2': 0.3}

    Returns:

    """
    # handle the case where the gsa_target_percentage is None
    if gsa_target_percentage is None:
        gsa_target_percentage = {}

    # get the total acreage for each of the gsa in the list of sites
    total_gsa_acreage = {}
    for site in sites:
        if site.agency not in total_gsa_acreage:
            total_gsa_acreage[site.agency] = 0
        total_gsa_acreage[site.agency] += site.acres

    # calculate the target acreage for each district
    for gsa in total_gsa_acreage:
        total_gsa_acreage[gsa] = total_gsa_acreage[gsa] * gsa_target_percentage.get(gsa, 0)  # fallback is zero MLRP

    # temporarily sort sites by MLRP rank
    sites.sort(key=none_aware_attrgetter("mlrpScore", False))

    for site in sites:
        # get the current district
        gsa = site.agency
        if total_gsa_acreage[gsa] <= 0:
            continue
        total_gsa_acreage[gsa] -= site.acres
        site.crop = "MLRP"
        site.inLieuCrop = None  # reset in-lieu crop if it was set
    return
