"""Yearly caps on how much transferred water each district may receive."""

import logging

logger = logging.getLogger(__name__)


def calc_transfer_limits(wafr, transfer_wafr_source_list, district_transfer_goals=None):
    """Work out each district's transfer budget for the year.

    A transfer goal is expressed either as a share of what the district's source
    yields over the year, or as a flat volume. Either way the district must first
    clear a threshold: if its source does not carry enough water over the year,
    the district gets a budget of zero.

    The budgets returned are consumed during the run — each site charges the
    water it takes against its own district — so once a district's budget reaches
    zero its sites stop drawing from the sources that budget governs.

    Args:
        wafr: volume available (acre-feet) per day for a single year, keyed by
            WAFR source name.
        transfer_wafr_source_list: which WAFR source supplies each district,
            keyed by district or sustainability zone name. Despite the name this
            is a mapping, not a list.
        district_transfer_goals: transfer goal per district or sustainability
            zone. Each value is a mapping that may hold:

            - `"THRESHOLD"`: minimum yearly volume (acre-feet) the source must
              carry before any transfer is allowed. Required — a district
              without one gets a zero budget.
            - `"PERCENT"`: share of the source's yearly volume to transfer, as a
              fraction. Takes precedence over `"ACREFEET"`.
            - `"ACREFEET"`: flat volume to transfer (acre-feet), used when no
              percentage is given.

    Returns:
        Transfer budget (acre-feet) per district, plus a
        `"transfer_wafr_sources"` entry holding `transfer_wafr_source_list` so
        that later stages can tell which sources a district's budget governs.
    """
    if district_transfer_goals is None:
        district_transfer_goals = {}

    transfer_limits_per_district = {}  # dictionary to store the transfer limits for each district/zone

    for district in district_transfer_goals:
        # check if there is a threshold defined
        if district_transfer_goals[district].get("THRESHOLD") is None:
            logger.warning("Transfer threshold is None - no transfer limits will be set")
            transfer_limits_per_district[district] = 0
            continue

        # sum up the total wafr with the sources that match the district
        # remap the district to the wafr source name
        source = transfer_wafr_source_list.get(district)
        if source not in wafr:
            logger.warning("Source %s not found in WAFR data for %s", source, district)
            transfer_limits_per_district[district] = 0
            continue

        total_available_for_year = sum(wafr[source])  # the total water available for entire year

        # check if total water available is less than the district's threshold
        if total_available_for_year < district_transfer_goals[district].get("THRESHOLD", 0):
            logger.warning(
                "Total available water for transfer %s is less than the threshold %s for %s",
                total_available_for_year,
                district_transfer_goals[district].get("THRESHOLD", 0),
                district,
            )
            transfer_limits_per_district[district] = 0
            continue

        percentage = district_transfer_goals[district].get("PERCENT", None)
        if percentage is not None:
            transfer_limits_per_district[district] = total_available_for_year * percentage
        else:
            acrefeet = district_transfer_goals[district].get("ACREFEET")
            transfer_limits_per_district[district] = 0 if acrefeet is None else acrefeet

    # sources to the transfer limits dictionary
    transfer_limits_per_district["transfer_wafr_sources"] = transfer_wafr_source_list

    return transfer_limits_per_district
