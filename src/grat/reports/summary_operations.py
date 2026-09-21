"""Aggregates model results into the summary dataframes used by the reports."""

import numpy as np
import pandas as pd

# Output column name -> attribute on the site object. The column names are part of the
# report output contract (report_generator and selector read them by these spellings),
# so they keep their original casing while the lookups follow the model's attributes.
SITE_ATTRIBUTES = {
    "rechargeType": "recharge_type",
    "acres": "acres",
    "cfsLimit": "cfs_limit",
    "precipGrid": "precip_grid",
    "bottleneckIDs": "bottleneck_ids",
    "soilType": "soil_type",
    "rsi": "rsi",
    "sortIndex": "sort_index",
    "crop": "crop",
    "inLieuCrop": "in_lieu_crop",
    "subbasin": "subbasin",
    "district": "district",
    "rma": "rma",
    "watershed": "watershed",
    "agency": "agency",
    "dac": "dac",
    "gsc": "gsc",
    "subsidence": "subsidence",
    "inbasinret": "inbasinret",
    "shorebird": "shorebird",
}


def combine_yearly_dataframes(list_of_year_df):
    """Combines a list of dataframes with the same schema together into a single dataframe.

    Args:
        list_of_year_df: paths to the pickled pandas dataframes

    Returns: a single dataframe
    """
    unpickeld = [pd.read_pickle(p) for p in list_of_year_df]
    return pd.concat(unpickeld).reset_index()


def get_site_info(site_list):
    """Pulls site attribution from the sites objects as a pandas dataframe.

    Args:
        site_list: list of sites

    Returns: dataframe
    """
    site_info = {
        s.grat_id: {column: getattr(s, attribute, None) for column, attribute in SITE_ATTRIBUTES.items()}
        for s in site_list
    }

    site_data = pd.DataFrame.from_dict(site_info, orient="index")
    site_data.index = site_data.index.set_names(["gratID"])
    return site_data.reset_index()


def daily_summary_recharge(
    year,
    sites_list,
    raw_wafr,
    wafr,
):
    """Totals recharge and WAFR volumes per day of the water year.

    Covers total recharge (AF) by type (canal, basins, in-lieu, on farm), total unused
    WAFR (AF), total WAFR applied (AF), total WAFR (AF) and precipitation (AF).

    Args:
        year: the current water year
        sites_list: list of site objects
        raw_wafr: dict of WAFR source to daily volume array, totalled into "Total WAFR (AF)"
        wafr: dict of WAFR source to daily volume array, totalled into "Total Unused WAFR (AF)"

    Returns: pandas dataframe
    """
    # use array arithmetic to add daily values
    add_up_ofr_daily_recharge_volumes = np.full(366, 0.0)
    add_up_ofr_in_lieu_daily_recharge_volumes = np.full(366, 0.0)
    add_up_basin_daily_recharge_volumes = np.full(366, 0.0)
    add_up_precip = np.full(366, 0.0)
    add_up_canal_daily_recharge_volumes = np.full(366, 0.0)
    add_up_total_wafr = np.full(366, 0.0)
    add_up_used_wafr = np.full(366, 0.0)
    add_up_basin_eoy_current_capacity = 0
    add_up_canal_eoy_current_capacity = 0

    for site in sites_list:
        if site.recharge_type == "OFR":
            add_up_ofr_daily_recharge_volumes += site.ofr_daily_recharge_volumes
            add_up_ofr_in_lieu_daily_recharge_volumes += site.in_lieu_daily_recharge_volumes
            add_up_precip += site.used_precip

        elif site.recharge_type == "Basin":
            add_up_basin_daily_recharge_volumes += site.daily_recharge_volumes
            add_up_precip += site.precip
            add_up_basin_eoy_current_capacity += site.current_capacity
        elif site.recharge_type == "Canal":
            add_up_canal_daily_recharge_volumes += site.daily_recharge_volumes
            add_up_canal_eoy_current_capacity += site.current_capacity

    for v in wafr.values():
        # force WAFR to be 366
        while len(v) < 366:
            v.append(0.0)
        add_up_used_wafr += v

    for v in raw_wafr.values():
        # force WAFR to be 366
        while len(v) < 366:
            v.append(0.0)
        add_up_total_wafr += v

    df_year = pd.DataFrame(
        {
            "Total Recharge (AF) On Farm": add_up_ofr_daily_recharge_volumes,
            "Total Recharge (AF) In-Lieu": add_up_ofr_in_lieu_daily_recharge_volumes,
            "Total Recharge (AF) Basins": add_up_basin_daily_recharge_volumes,
            "Precipitation (AF)": add_up_precip,
            "Total Recharge (AF) Canals": add_up_canal_daily_recharge_volumes,
            "Total Unused WAFR (AF)": add_up_used_wafr,
            "Total WAFR Applied (AF)": add_up_total_wafr - add_up_used_wafr,
            "Total WAFR (AF)": add_up_total_wafr,
            "Canals EOY Capacity": add_up_canal_eoy_current_capacity,
            "Basins EOY Capacity": add_up_basin_eoy_current_capacity,
        }
    )

    df_year["Year"] = year
    df_year["Day"] = df_year.index + 1

    return df_year


def site_volume_report(year, sites_list):
    """Collects the per-site daily volume arrays for a single water year.

    Args:
        year: the current water year
        sites_list: list of site objects

    Returns: dataframe with one row per Basin, Canal or OFR site
    """
    data_rows = []

    for site in sites_list:
        # volume for basins is used volume, OFR is ofrUsed + inLieuUsed
        if site.recharge_type in ("Basin", "Canal"):
            data_rows.append(
                (
                    year,
                    site.grat_id,
                    site.used_volume,
                    site.daily_recharge_volumes,
                    [],
                    [],
                    site.daily_recharge_volumes,  # work around for the daily recharge volumes report 6&7 for issue #154
                    [],
                )
            )
        elif site.recharge_type == "OFR":
            data_rows.append(
                (
                    year,
                    site.grat_id,
                    site.ofr_used_volume + site.in_lieu_used_volume,
                    site.ofr_daily_recharge_volumes + site.in_lieu_daily_recharge_volumes,
                    site.ofr_used_volume,
                    site.ofr_unused_volume,
                    site.ofr_daily_recharge_volumes,
                    site.in_lieu_daily_recharge_volumes,
                )
            )

    return pd.DataFrame(
        data_rows,
        columns=[
            "Year",
            "gratID",
            "UsedVolumeArray",
            "dailyRechargeVolumesArray",
            "ofrUsedVolumeArray",
            "ofrUnusedVolumeArray",
            "ofrDailyRechargeVolumesArray",
            "inLieuDailyRechargeVolumesArray",
        ],
    )
