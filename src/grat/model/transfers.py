import logging


def calc_transfer_limits(wafr, transfer_wafr_source_list, district_transfer_goals=None):
    """
    Calculates the district/sustainability zone transfer limits based on water available for transfer
    and the user's defined transfer settings

    Args:
        wafr: wafr dictionary for a single year
        transfer_wafr_source_list: list of sources to transfer water from
        district_transfer_goals: dictionary of transfer goals for each district/zone
            - key: district or sustainability zone name
            - value: dictionary with either "PERCENT" or "ACREFEET" as keys
                - PERCENT: percentage of the total available water to transfer
                - ACREFEET: total volume to transfer
                - THRESHOLD: volume per district to determine if there is enough water to transfer

    Returns:

    """
    if district_transfer_goals is None:
        district_transfer_goals = {}

    transfer_limits_per_district = {}  # dictionary to store the transfer limits for each district/zone

    for district in district_transfer_goals:
        # check if there is a threshold defined
        if district_transfer_goals[district].get("THRESHOLD") is None:
            logging.warning("Transfer threshold is None - no transfer limits will be set")
            transfer_limits_per_district[district] = 0
            continue

        # sum up the total wafr with the sources that match the district
        # remap the district to the wafr source name
        source = transfer_wafr_source_list.get(district)
        if source not in wafr:
            logging.warning(f"Source {source} not found in WAFR data for {district}")
            transfer_limits_per_district[district] = 0
            continue

        total_available_for_year = sum(wafr[source])  # the total water available for entire year

        # check if total water available is less than the district's threshold
        if total_available_for_year < district_transfer_goals[district].get("THRESHOLD", 0):
            logging.warning(
                f"Total available water for transfer {total_available_for_year} is less than"
                f" the threshold {district_transfer_goals[district].get('THRESHOLD', 0)} for {district}"
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
