"""Ordering rules that decide which sites get water first.

The model allocates water strictly in list order, so the sort applied here
determines priority: a site earlier in the list takes what it can before later
sites are offered anything.
"""

import logging
import operator


def recharge_type_order(site):
    """Return the rank used to group sites by recharge type when sorting.

    Ranks canals 1, basins 2, on-farm recharge 3, and anything else 4. Applied
    last in `sort_sites` so that sites of the same type stay together.

    Note that this ordering is not what decides which type is watered first —
    `grat.use_sites` fixes that order independently, and it differs.

    Args:
        site: any site with a `recharge_type` attribute.

    Returns:
        Rank from 1 to 4.
    """
    if site.recharge_type == "Canal":
        return 1
    if site.recharge_type == "Basin":
        return 2
    if site.recharge_type == "OFR":
        return 3
    return 4


def none_aware_attrgetter(attr, reverse=False):
    """Build a sort key for an attribute that may be `None` on some sites.

    Sorting on an attribute that is `None` for some sites raises a `TypeError`,
    because `None` cannot be compared with a number. This wraps the attribute in
    a tuple whose first element sorts the `None`s as a group, so they always come
    last regardless of sort direction, and the real values are compared only
    against each other.

    Adapted from https://stackoverflow.com/questions/61452346

    Args:
        attr: name of the attribute to sort on.
        reverse: whether the caller will pass `reverse=True` to `sorted`/`sort`.
            Needed so that `None` values stay at the end either way.

    Returns:
        A key function suitable for `sorted` or `list.sort`.
    """
    getter = operator.attrgetter(attr)

    def key_func(item):
        value = getter(item)
        if reverse is True:
            return (value is not None, value)
        return (value is None, value)

    return key_func


def sort_by_variable(list_of_sites, variable, reverse=False):
    """Sort sites by a single attribute.

    Sites whose value is `None` are placed last in either direction. Use
    `sort_by_variables` to sort on more than one attribute.

    Args:
        list_of_sites: sites to sort.
        variable: name of the attribute to sort on.
        reverse: sort descending rather than ascending.

    Returns:
        A new sorted list; the input is left unchanged.
    """
    return sorted(list_of_sites, key=none_aware_attrgetter(variable, reverse), reverse=reverse)


def sort_by_variables(list_of_sites, specs):
    """Sort sites by several attributes at once.

    Works by sorting repeatedly, least significant attribute first, relying on
    Python's sort being stable. List the attributes in the order you want them
    applied — most significant first::

        sort_by_variables(sites, (("acres", True), ("index", True)))

    See https://docs.python.org/3/howto/sorting.html

    Args:
        list_of_sites: sites to sort. **Mutated**: sorted in place.
        specs: `(attribute_name, reverse)` pairs, most significant first.

    Returns:
        The same list, sorted.
    """
    for attr, reverse in reversed(specs):
        list_of_sites.sort(key=none_aware_attrgetter(attr, reverse), reverse=reverse)
    return list_of_sites


def sort_sites(sites, sort_rule=None):
    """Put sites into the order the model will process them.

    Applies the chosen scenario's tie-breakers first, then sorts by recharge type
    last so it dominates: sites are grouped by type, with the scenario deciding
    the order within each group.

    Each site's `sort_index` is set to its one-based position in the result.

    Args:
        sites: sites to order. **Mutated**: sorted in place, and each site's
            `sort_index` is assigned.
        sort_rule: which scenario to apply. `None` ranks by RSI score
            then area. `"RMA"` ranks by RMA rank first. `"A"` is a
            test scenario that ranks by the `scenario_a` attribute first.

    Returns:
        The sites in processing order.

    Raises:
        Exception: if `sort_rule` is not one of the supported values.
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
    """Split the sites into the four lists the daily loop works through.

    A farm can appear in both the in-lieu and on-farm lists if it has both a
    `crop` and an `in_lieu_crop`; the two recharge methods are tracked separately
    on the site, so it can receive water as each.

    In-lieu sites are re-sorted here rather than left in the order `sort_sites`
    produced: they are ordered by groundwater change, lowest first.

    Args:
        site_list: all sites, already in processing order.
        use_in_lieu: include in-lieu sites. When `False` the in-lieu list comes
            back empty and no in-lieu recharge happens.
        use_ofr: include on-farm sites. When `False` the on-farm list comes back
            empty.
        rma_sort: order in-lieu sites by RMA rank first, then by groundwater
            change within each rank. When `False`, order by
            groundwater change alone.

    Returns:
        Four lists: basins, in-lieu sites, on-farm sites, canals.
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
    """Convert the best-ranked land in each agency to the MLRP crop.

    Works through each agency's sites best-ranked first, switching each to the
    "MLRP" crop until that agency's target acreage is used up. Converted sites
    have their in-lieu crop cleared, so they take part in on-farm recharge only.

    Args:
        sites: sites to consider. **Mutated**: sorted in place, and the `crop` and
            `in_lieu_crop` of the converted sites are reassigned.
        gsa_target_percentage: share of each agency's total acreage to convert,
            keyed by agency, e.g. `{"gsa1": 0.5, "gsa2": 0.3}`. An agency absent
            from the mapping converts nothing.
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
