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
    if site.recharge_type == "Canal":
        return 1
    if site.recharge_type == "Basin":
        return 2
    if site.recharge_type == "OFR":
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

    sort_by_variables([site_a(), site_b()...], (("acres", True), ("index", True))

    https://docs.python.org/3/howto/sorting.html
    Args:
        list_of_sites: site objects
        specs: tuples with the object attribute + boolean if the sort is reversed

    Returns:

    """
    for attr, reverse in reversed(specs):
        list_of_sites.sort(key=none_aware_attrgetter(attr, reverse), reverse=reverse)
    return list_of_sites


def sort_sites(sites, sort_rule=None):
    """
    Orders sites objects by various scenarios by sorting multiple object properties.
    The order the Object properties to sort by is important (most restrictive -> least).
    Always sort final list by recharge type last.

    Args:
        sites: list of unordered site object
        sort_rule: name of the scenario's sort rule

    Returns: sorted list of sites

    """

    if sort_rule is None:
        # sort by rsi score, acres and then finally by recharge type
        s = sort_by_variables(sites, (("rsi", True), ("acres", True)))
        s.sort(key=recharge_type_order)

    elif sort_rule == "A":
        # test scenario for sorting
        # sort by recharge type, scenario, index score, acres
        s = sort_by_variables(sites, (("scenario_a", True), ("rsi", True), ("acres", True)))
        s.sort(key=recharge_type_order)

    elif sort_rule == "RMA":
        # sort by RMA rank,rsi score, acres and then finally by recharge type
        s = sort_by_variables(sites, (("rma", False), ("rsi", True), ("acres", True)))
        s.sort(key=recharge_type_order)
    else:
        raise Exception("Unknown sort rule selected")

    # update sort_index parameter
    sorted_sites = []

    for i, site in enumerate(s):
        site.sort_index = i + 1
        sorted_sites.append(site)

    return sorted_sites


def group_sites_by_recharge_type(site_list, use_in_lieu=True, use_ofr=True, rma_sort=False):
    """
    Splits site_list into sublists by type (basins, in-lieu, on farm recharge)
    Args:
        site_list: list of objects (basins, farms)
        use_in_lieu: boolean if in-lieu sites should be included
        use_ofr: boolean if on farm recharge sites should be included
        rma_sort: boolean if the in-lieu sites should be sorted by rma rank
    Returns: list of basins, list of in-lieu sites, list of ofr sites, list of canals

    """
    basin_list = [s for s in site_list if s.recharge_type == "Basin"]
    canal_list = [s for s in site_list if s.recharge_type == "Canal"]

    in_lieu_sites_unordered = [
        s for s in site_list if s.recharge_type not in ["Basin", "Canal"] and s.in_lieu_crop is not None
    ]

    # Groundwater change used to sort in lieu sites. Within each RMA zone the
    # Lowest numbers (i.e most negative) have the highest priority.
    if rma_sort is True:
        logging.info("Sorting in-lieu sites by RMA rank")
        in_lieu_sites = sort_by_variables(in_lieu_sites_unordered, (("rma", False), ("groundwater_change", False)))
    else:
        logging.info("Sorting in-lieu sites by groundwater_change only")

        in_lieu_sites = sort_by_variable(in_lieu_sites_unordered, "groundwater_change", False)

    ofr_sites = [s for s in site_list if s.recharge_type not in ["Basin", "Canal"] and s.crop is not None]

    if use_in_lieu is False:
        in_lieu_sites = []

    if use_ofr is False:
        ofr_sites = []

    return basin_list, in_lieu_sites, ofr_sites, canal_list


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
    sites.sort(key=none_aware_attrgetter("mlrp_score", False))

    for site in sites:
        # get the current district
        gsa = site.agency
        if total_gsa_acreage[gsa] <= 0:
            continue
        total_gsa_acreage[gsa] -= site.acres
        site.crop = "MLRP"
        site.in_lieu_crop = None  # reset in-lieu crop if it was set
    return
