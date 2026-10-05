"""Generates output reports using pandas."""

import logging
import re

import numpy as np
import pandas as pd

from grat.reports.converters import is_leap_year, sum_array_by_month

logger = logging.getLogger(__name__)

# Output column name -> attribute on the site object.
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


def _padded_to_water_year(daily_values):
    """Returns `daily_values` padded with zeroes to a full 366-day water year.

    A short WAFR series is padded rather than extended in place, because these
    lists belong to the caller and are read again after this report is built.

    Args:
        daily_values: volume per day for one WAFR source

    Returns: a list of 366 values
    """
    values = list(daily_values)
    if len(values) < 366:
        values.extend([0.0] * (366 - len(values)))
    return values


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
        add_up_used_wafr += _padded_to_water_year(v)

    for v in raw_wafr.values():
        add_up_total_wafr += _padded_to_water_year(v)

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


def annual_summary_recharge(daily_summary_recharge_df):
    """Aggregates the daily summary recharge dataframe into yearly totals.

    Sums the daily values for each category, and calculates the volume of water remaining in the canals +
    basins at the end of the water year by getting the current capacity on the last day of the water year.

    Args:
        daily_summary_recharge_df: dataframe output from the daily_summary_recharge function

    Returns: pandas dataframe

    """
    # group by water year and aggregate the rows using sums (EOY capacity uses max value)

    # Define the operations for each column
    operations = {
        "Total Recharge (AF) Canals": "sum",
        "Total Recharge (AF) Basins": "sum",
        "Total Recharge (AF) In-Lieu": "sum",
        "Total Recharge (AF) On Farm": "sum",
        "Total Unused WAFR (AF)": "sum",
        "Total WAFR Applied (AF)": "sum",
        "Total WAFR (AF)": "sum",
        "Precipitation (AF)": "sum",
        "Canals EOY Capacity": "max",
        "Basins EOY Capacity": "max",
    }

    df = daily_summary_recharge_df.groupby(["Year"]).agg(operations).reset_index()

    # rename columns
    df.rename(
        columns={
            "Canals EOY Capacity": "Remaining applied WAFR in Canals At The End Of Year",
            "Basins EOY Capacity": "Remaining applied WAFR in Basins At The End Of Year",
        },
        inplace=True,
    )

    # calculate the number of days in each year
    df["Number of Days"] = df.apply(lambda row: 366 if is_leap_year(int(row["Year"])) else 365, axis=1)

    # change column order
    return df[
        [
            "Year",
            "Number of Days",
            "Total Recharge (AF) Canals",
            "Remaining applied WAFR in Canals At The End Of Year",
            "Total Recharge (AF) Basins",
            "Remaining applied WAFR in Basins At The End Of Year",
            "Total Recharge (AF) In-Lieu",
            "Total Recharge (AF) On Farm",
            "Total Unused WAFR (AF)",
            "Total WAFR Applied (AF)",
            "Total WAFR (AF)",
        ]
    ]


def daily_summary_recharge_report(df):
    """Selects the columns that report 03 publishes from the daily summary.

    The end-of-year capacity columns are dropped here rather than in the writer, so
    the frame this returns is exactly what lands in the csv.

    Args:
        df: dataframe from summary_operations.daily_summary_recharge, combined across
            every water year

    Returns: dataframe with the report 03 columns, in report order
    """
    return df[
        [
            "Year",
            "Day",
            "Total Recharge (AF) Canals",
            "Total Recharge (AF) In-Lieu",
            "Total Recharge (AF) Basins",
            "Total Recharge (AF) On Farm",
            "Total Unused WAFR (AF)",
            "Total WAFR Applied (AF)",
            "Total WAFR (AF)",
            "Precipitation (AF)",
        ]
    ]


def daily_wafr_applied_by_site(site_volume_report_df, site_info_df):
    """Splits the daily used-volume array into one column per day of water year, joined to the site info.

    Args:
        site_volume_report_df: dataframe with the site volume report values (from site_volume_report function())
        site_info_df: dataframe with the site info values (from siteInfo function())

    Returns: dataframe with daily WAFR applied by site

    """
    # get the list of years
    years = site_volume_report_df["Year"].unique()

    split = pd.DataFrame(
        site_volume_report_df["UsedVolumeArray"].to_list(),
        columns=[f"DOWY {i}" for i in range(1, 367)],
    )

    # join the split attribute back with the original
    df = pd.concat([site_volume_report_df, split], axis=1).drop(
        ["dailyRechargeVolumesArray", "UsedVolumeArray"], axis=1
    )

    # df_pivot = pd.pivot_table(df, index='gratID', columns=)
    d1 = df.set_index(["gratID", "Year"]).unstack()
    d1.columns = d1.columns.map(lambda x: "Year {} {}".format(*reversed(x)))
    d1.reset_index(inplace=True)

    # set columns in year -> date order and drop extra day for non-leap years
    # build columns names "Year 2001 DOWY 1"
    ordered_columns = ["gratID"]
    for y in years:
        if is_leap_year(y):
            for d in range(1, 367):
                ordered_columns.append(f"Year {y} DOWY {d}")
        else:
            for d in range(1, 366):
                ordered_columns.append(f"Year {y} DOWY {d}")

    d1_order = d1[ordered_columns]

    joined = site_info_df.merge(d1_order, on="gratID", how="right").sort_values("sortIndex")
    joined_transpose = joined.set_index("gratID").transpose().reset_index()
    return joined_transpose.rename(columns={"index": "gratID"})


def daily_recharge_by_site(site_volume_report_df, site_info_df):
    """Splits the daily recharge volume array into one column per day of water year, joined to the site info.

    Args:
        site_volume_report_df: dataframe with the site volume report values (from site_volume_report function())
        site_info_df: dataframe with the site info values (from siteInfo function())

    Returns: dataframe with daily recharge by site

    """
    # get the list of years
    years = site_volume_report_df["Year"].unique()

    split = pd.DataFrame(
        site_volume_report_df["dailyRechargeVolumesArray"].to_list(),
        columns=[f"DOWY {i}" for i in range(1, 367)],
    )

    # join the split attribute back with the original
    df = pd.concat([site_volume_report_df, split], axis=1).drop(
        ["dailyRechargeVolumesArray", "UsedVolumeArray"], axis=1
    )

    # df_pivot = pd.pivot_table(df, index='gratID', columns=)
    d1 = df.set_index(["gratID", "Year"]).unstack()
    d1.columns = d1.columns.map(lambda x: "Year {} {}".format(*reversed(x)))
    d1.reset_index(inplace=True)

    # set columns in year -> date order and drop extra day for non-leap years
    # build columns names "Year 2001 DOWY 1"
    ordered_columns = ["gratID"]
    for y in years:
        if is_leap_year(y):
            for d in range(1, 367):
                ordered_columns.append(f"Year {y} DOWY {d}")
        else:
            for d in range(1, 366):
                ordered_columns.append(f"Year {y} DOWY {d}")

    d1_order = d1[ordered_columns]

    joined = site_info_df.merge(d1_order, on="gratID", how="right").sort_values("sortIndex")
    joined_transpose = joined.set_index("gratID").transpose().reset_index()
    return joined_transpose.rename(columns={"index": "gratID"})


def monthly_recharge_by_site_report(site_volume_report_df):
    """Aggregates the daily recharge volume arrays into monthly totals per site and recharge volume type.

    Args:
        site_volume_report_df: dataframe with the site volume report values (from site_volume_report function())

    Returns: dataframe with monthly recharge by site

    """
    site_volume_report_df = (
        site_volume_report_df.copy()
    )  # create a copy of the data frame so original doesn't get modified

    # add column to determine if it is a leap year
    site_volume_report_df["leapYear"] = site_volume_report_df["Year"].apply(is_leap_year)

    # need to deal with OFR/INLIEU separately - see ticket # 141
    # create a copy of the site_volume_report_df
    il_site_volume_report_df = site_volume_report_df.copy()

    # OFR section

    # sum up the volume by month (array is zero-index day of the water year, needs leap years as arg)
    site_volume_report_df["ofrMonthlySums"] = site_volume_report_df.apply(
        lambda x: sum_array_by_month(x["ofrDailyRechargeVolumesArray"], x["leapYear"]),
        axis=1,
    )

    # split the monthly sums into their own columns
    month_columns = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]
    site_volume_report_df[month_columns] = pd.DataFrame(
        site_volume_report_df["ofrMonthlySums"].tolist(), index=site_volume_report_df.index
    )

    site_volume_report_df["recharge_volume_type"] = (
        "OFR/Basin/Canal"  # keep type as empty since this also contains basins/canals
    )
    monthly_numbers = site_volume_report_df[["Year", "gratID", "recharge_volume_type"] + month_columns]

    # in-lieu section
    # sum up the volume by month (array is zero-index day of the water year, needs leap years as arg)
    il_site_volume_report_df["ilMonthlySums"] = il_site_volume_report_df.apply(
        lambda x: sum_array_by_month(x["inLieuDailyRechargeVolumesArray"], x["leapYear"]),
        axis=1,
    )

    # split the monthly sums into their own columns
    month_columns = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]
    il_site_volume_report_df[month_columns] = pd.DataFrame(
        il_site_volume_report_df["ilMonthlySums"].tolist(),
        index=il_site_volume_report_df.index,
    )

    il_site_volume_report_df["recharge_volume_type"] = "In-Lieu"  # add attribute to track
    il_monthly_numbers = il_site_volume_report_df[["Year", "gratID", "recharge_volume_type"] + month_columns]

    return pd.concat([monthly_numbers, il_monthly_numbers], axis=0)


def monthly_recharge_by_site_report_post(df, site_info):
    """Pivots the monthly_recharge_by_site_report to the final format.

    Args:
        df: dataframe with the unpivoted monthly_recharge_by_site_report values
        site_info: dataframe with the site info

    Returns: dataframe with the final format of the monthly_recharge_by_site_report
    """
    years_list = sorted(df["Year"].unique())

    # pivot to wide using years
    pivot = df.pivot_table(
        index=["gratID", "recharge_volume_type"],
        columns="Year",
        values=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
    ).reset_index()

    # rename the multi-level index
    pivot.columns = [
        (f"Year {col[1]} Month {col[0]}" if col[0] not in ("gratID", "recharge_volume_type") else col[0])
        for col in pivot.columns
    ]

    # reorder the columns in order (year, month, etc.)
    desired_cols_order = ["gratID", "recharge_volume_type"]
    desired_cols_order.extend(
        [
            f"Year {y} Month {m}"
            for y in years_list
            for m in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]
        ]
    )

    pivot = pivot[desired_cols_order]

    pivot = pivot.fillna(0)

    # add site info?
    joined = site_info.merge(pivot, on="gratID", how="right").sort_values("sortIndex")
    joined["FeatureType"] = joined[
        "rechargeType"
    ]  # create a new column to hold the FeatureType since rechargeType will be modified

    # set all FeatureType row currently OFR to Farm
    joined.loc[joined["FeatureType"] == "OFR", "FeatureType"] = "Farm"

    # if feature type is canal or basin, remove in-lieu recharge rows (not valid)
    joined.drop(
        joined[(joined["FeatureType"] == "Canal") & (joined["recharge_volume_type"] == "In-Lieu")].index,
        inplace=True,
    )
    joined.drop(
        joined[(joined["FeatureType"] == "Basin") & (joined["recharge_volume_type"] == "In-Lieu")].index,
        inplace=True,
    )

    # rename rechargeType to delineate between OFR and In-Lieu where feature type is Farm
    joined.loc[
        (joined["recharge_volume_type"] == "In-Lieu") & (joined["FeatureType"] == "Farm"),
        "rechargeType",
    ] = "In-Lieu"
    joined.loc[
        (joined["recharge_volume_type"] == "OFR/Basin/Canal") & (joined["FeatureType"] == "Farm"),
        "rechargeType",
    ] = "OFR"

    # drop the recharge_volume_type column
    joined.drop("recharge_volume_type", axis=1, inplace=True)
    joined.drop("FeatureType", axis=1, inplace=True)

    return joined


def monthly_recharge_by_site_summary(df):
    """Selects the columns that report 06 publishes from the pivoted monthly frame.

    Report 07 publishes the same frame in full; report 06 keeps only the site
    identifiers and the per-month value columns.

    Args:
        df: dataframe from monthly_recharge_by_site_report_post

    Returns: dataframe with gratID, rechargeType and the "Year N Month M" columns
    """
    columns_to_keep = []
    for c in df.columns.tolist():
        if re.match(r"^Year \d+ Month \d{1,2}$", c):  # match the year and month columns
            columns_to_keep.append(c)

        if c in ("gratID", "rechargeType"):  # match the gratID identifier and rechargeType columns
            columns_to_keep.append(c)

    return df[columns_to_keep]


def daily_farm_recharge_report(site_ofr_usage_report_df, site_info_df):
    """Post-process the siteOfrUsageReport df to return values grouped by crop + soilType.

    Args:
        site_ofr_usage_report_df: dataframe with site OFR usage report values
        site_info_df:   dataframe with site information

    Returns: dataframe with daily_farm_recharge_report values

    """
    # join site the site info
    joined = site_info_df.merge(site_ofr_usage_report_df, on="gratID", how="right").sort_values("sortIndex")

    split = pd.DataFrame(
        joined["ofrDailyRechargeVolumesArray"].to_list(),
        columns=[f"DOWY {i}" for i in range(1, 367)],
    )

    # join the split attribute back with the original
    joined = pd.concat([joined, split], axis=1).drop("dailyRechargeVolumesArray", axis=1)

    # group by to summ by year variable key
    column_names = [f"DOWY {i}" for i in range(1, 367)]

    # group by soilType + OFR crop
    grouped_df = joined.groupby(["Year", "crop", "soilType"])[column_names].agg("sum").reset_index()
    grouped_df["variable_key"] = grouped_df["crop"] + "-" + grouped_df["soilType"]

    # get the list of years
    years = grouped_df["Year"].unique()

    # df_pivot = pd.pivot_table(df, index='gratID', columns=)
    d1 = grouped_df.set_index(["variable_key", "Year"]).unstack()
    d1.columns = d1.columns.map(lambda x: "Year {} {}".format(*reversed(x)))
    d1.reset_index(inplace=True)

    # set columns in year -> date order and drop extra day for non-leap years
    # build columns names "Year 2001 DOWY 1"
    ordered_columns = ["variable_key"]
    for y in years:
        if is_leap_year(y):
            for d in range(1, 367):
                ordered_columns.append(f"Year {y} DOWY {d}")
        else:
            for d in range(1, 366):
                ordered_columns.append(f"Year {y} DOWY {d}")

    d1_order = d1[ordered_columns]

    joined_transpose = d1_order.set_index("variable_key").transpose().reset_index()
    return joined_transpose.rename(columns={"index": "Year and Day"})


def yearly_aggregate_farm_recharge_report(site_ofr_usage_report_df, site_info_df):
    """Post-process the siteOfrUsageReport df to return values grouped by crop + soilType.

    Args:
        site_ofr_usage_report_df: dataframe with site OFR usage report values
        site_info_df: dataframe with site information

    Returns: dataframe with yearly_aggregate_farm_recharge_report values

    """
    # join site the site info
    joined = site_info_df.merge(site_ofr_usage_report_df, on="gratID", how="right").sort_values("sortIndex")

    # collapse the daily arrays into single value
    joined["Used"] = joined.apply(lambda x: sum(x["ofrUsedVolumeArray"]), axis=1)
    joined["Unused"] = joined.apply(lambda x: sum(x["ofrUnusedVolumeArray"]), axis=1)

    # group by soilType + OFR crop and sum up the
    grouped_df = joined.groupby(["Year", "crop", "soilType"]).agg({"Used": "sum", "Unused": "sum"}).reset_index()

    grouped_df["variable_key"] = grouped_df["crop"] + "-" + grouped_df["soilType"]

    pivoted_df = grouped_df.pivot(index="Year", columns="variable_key", values=["Used", "Unused"])

    # flatten multi-index
    pivoted_df.columns = [f"{col[1]}-{col[0]}" for col in pivoted_df.columns]

    return pivoted_df.reset_index()


def daily_wafr_report(year, wafr):
    """Report the unused wafr by source for every day.

    Args:
        year: current year
        wafr: dictionary of unused wafr by source

    Returns: pandas dataframe with columns Year, Day, and each source of unused wafr

    """
    df = pd.DataFrame.from_dict(wafr)
    df["Year"] = year
    df["Day"] = df.index + 1

    # set the column order
    header_rows = ["Year", "Day"]
    unique_wafr_sources = sorted(set(wafr.keys()))
    header_rows += unique_wafr_sources

    df = df[header_rows]

    if is_leap_year(int(year)) is False:
        # drop day 366 if not a leap year
        df = df.drop(df[df["Day"] == 366].index)
    return df


def atoi(text):
    """Convert text to integer if it is a digit, otherwise return the text."""
    return int(text) if text.isdigit() else text


def natural_keys(text):
    """Sort key that orders embedded numbers in human order.

    Use as alist.sort(key=natural_keys). See
    https://nedbatchelder.com/blog/200712/human_sorting.html
    (Toothy's implementation in the comments).
    """
    return [atoi(c) for c in re.split(r"(\d+)", text)]


def bottlenecks_capacity_limitations_report(year, bottleneck_list):
    """Construct dataframe with years as the rows and bottleneckIDs as the column names.

    Cell values are the number of days when bottleneck capacity is hit
    (e.g. 0 cfs capacity remaining at bottleneck).

    Args:
        year: current year
        bottleneck_list: list of bottleneck objects

    Returns: dataframe

    """
    header = ["Year", "bottleneckID", "numberDaysZero"]
    rows = []

    for b in bottleneck_list:
        rows.append(
            (
                year,
                f"BottleneckID {b.bottleneck_id}",
                list(b.available_throughput).count(0),
            )
        )

    df = pd.DataFrame(rows, columns=header)

    df_wide = (
        pd.pivot(df, index=["Year"], columns="bottleneckID", values="numberDaysZero")
        .rename_axis(None, axis=1)
        .reset_index()
    )

    # set the column order
    b_ids = [n for n in list(df_wide) if "BottleneckID" in n]
    b_ids.sort(key=natural_keys)
    columns = ["Year"] + list(b_ids)

    return df_wide[columns]


def bottlenecks_daily_conveyance_limits_by_volume(year, bottleneck_list):
    """Construct dataframe with years as the rows and bottleneckIDs as the column names.

    Args:
        year: current year
        bottleneck_list: list of bottleneck objects

    Returns: dataframe with bottlenecks_daily_conveyance_limits_by_volume values
    """
    header = ["Year", "bottleneckID", "throughputArray"]
    rows = []

    for b in bottleneck_list:
        rows.append(
            (
                year,
                f"BottleneckID {b.bottleneck_id}",
                b.available_throughput,
            )
        )
    df = pd.DataFrame(rows, columns=header)

    split = pd.DataFrame(
        df["throughputArray"].to_list(),
        columns=[f"{i}" for i in range(1, 367)],
    )

    # convert bottleneck throughput units to cfs
    split = split / 1.983

    # join the split attribute back with the original
    df = pd.concat([df, split], axis=1).drop("throughputArray", axis=1)
    d1 = df.set_index(["bottleneckID", "Year"]).unstack()
    d1.columns = d1.columns.map(lambda x: "{}_{}".format(*reversed(x)))

    # transpose
    d1t = d1.T.reset_index()
    d1t[["Year", "Day"]] = d1t["index"].str.split("_", expand=True)
    d1t.drop(columns=["index"], inplace=True)

    # set the column order
    b_ids = [n for n in list(d1t) if "BottleneckID" in n]
    b_ids.sort(key=natural_keys)
    columns = ["Year", "Day"] + list(b_ids)
    return d1t[columns]


def yearly_bottleneck_capacity_logger(year, bottleneck_list):
    """Yearly Bottleneck Capacity Logger.

    Args:
        year: current year
        bottleneck_list: list of bottleneck objects

    Returns: dataframe with yearly_bottleneck_capacity_logger values
    """
    header = ["Year", "bottleneckID", "throughputArray"]
    rows = []

    for b in bottleneck_list:
        rows.append(
            (
                year,
                f"{b.bottleneck_id}",
                ["" if t > 0 else f"{b.bottleneck_id}" for t in b.available_throughput],
            )
        )

    df = pd.DataFrame(rows, columns=header)

    split = pd.DataFrame(
        df["throughputArray"].to_list(),
        columns=[f"{i}" for i in range(1, 367)],
    )
    # join the split attribute back with the original
    df = pd.concat([df, split], axis=1).drop("throughputArray", axis=1)

    # define a custom aggregation function that excludes empty strings
    def join_non_empty(x):
        return ";".join([val for val in x if val != ""])

    agg_dict = {f"{i}": join_non_empty for i in range(1, 367)}
    return df.groupby(["Year"]).agg(agg_dict).reset_index()


def annual_recharge_by_grouping(year, sites):
    """Annual Recharge by Grouping (used as input for 15,16,17 post processing).

    Args:
        year: current year
        sites: list of site objects

    Returns: dataframe with annual_recharge_by_grouping values

    """
    data = {}

    for site in sites:
        # build unique key
        if site.subbasin is not None and site.district is not None:
            # canals can have multiple subbasins
            subbasin_list = site.subbasin if type(site.subbasin) is list else [site.subbasin]

            number_basins = len(subbasin_list)

            for sb in subbasin_list:
                unique_key = sb + ";" + site.district
                wafr_yearly_log = site.wafr_log
                for wafr_source, vol in wafr_yearly_log.items():
                    unique_key_wafr = unique_key + ";" + wafr_source
                    prior_results = data.get(unique_key_wafr)
                    if prior_results is None:
                        data[unique_key_wafr] = vol / number_basins  # canal volume is split evenly among subbasins
                    else:
                        data[unique_key_wafr] += vol / number_basins  # canal volume is split evenly among subbasins

    df = pd.DataFrame.from_dict(data, orient="index", columns=["value"]).reset_index()

    if len(df) > 0:
        df[["subbasin", "district", "wafrsource"]] = df["index"].str.split(";", expand=True)

        df["Year"] = year

        return df[["Year", "subbasin", "district", "wafrsource", "value"]]
    return None


def annual_recharge_by_sw_and_gw(df_annual_recharge_by_grouping):
    """Group by WAFR and subbasin.

    Args:
        df_annual_recharge_by_grouping: dataframe with annual_recharge_by_grouping values
            (generated from annual_recharge_by_grouping function)

    Returns: dataframe with annual_recharge_by_sw_and_gw values

    """
    # group by subbasin + wafrsource
    g = df_annual_recharge_by_grouping.groupby(["Year", "subbasin", "wafrsource"])["value"].sum().reset_index()

    return g.pivot(index="Year", columns=["subbasin", "wafrsource"], values="value").reset_index()


def annual_recharge_by_district_and_gw(df_annual_recharge_by_grouping):
    """Annual District Recharge by GW Basin.

    Args:
        df_annual_recharge_by_grouping: dataframe with annual_recharge_by_grouping values
            (generated from annual_recharge_by_grouping function)

    Returns: dataframe with annual_recharge_by_district_and_gw values

    """
    # group by district + gw basins
    g = df_annual_recharge_by_grouping.groupby(["Year", "subbasin", "district"])["value"].sum().reset_index()

    return g.pivot(index="Year", columns=["subbasin", "district"], values="value").reset_index()


def annual_recharge_by_district_and_wafr(df_annual_recharge_by_grouping):
    """Annual District Recharge by SW Source (wafr).

    Args:
        df_annual_recharge_by_grouping: dataframe with annual_recharge_by_grouping values
            (generated from annual_recharge_by_grouping function)

    Returns: dataframe with annual_recharge_by_district_and_wafr values

    """
    # group by district + gw basins
    g = df_annual_recharge_by_grouping.groupby(["Year", "wafrsource", "district"])["value"].sum().reset_index()

    return g.pivot(index="Year", columns=["wafrsource", "district"], values="value").reset_index()


def daily_recharge_by_gw_basin(site_volume_report_df, site_info_df):
    """Post-process the siteOfrUsageReport df.

    Args:
        site_volume_report_df: dataframe with the site volume report values (from site_volume_report function())
        site_info_df: dataframe with the site info

    Returns: transposed dataframe with daily recharge by GW basin

    """
    split = pd.DataFrame(
        site_volume_report_df["dailyRechargeVolumesArray"].to_list(),
        columns=[f"DOWY {i}" for i in range(1, 367)],
    )

    # join the split attribute back with the original
    df = pd.concat([site_volume_report_df, split], axis=1).drop(
        ["dailyRechargeVolumesArray", "UsedVolumeArray"], axis=1
    )

    joined = site_info_df.merge(df, on="gratID", how="right").sort_values("sortIndex")

    def subbasin_list(v):
        if isinstance(v, list):
            return v
        return [v]

        # cast the strings to a list as a new attribute

    joined["subbasinList"] = joined["subbasin"].apply(subbasin_list)

    # divide the volumes by the number of subbasins
    def standardize_by_number_basins(row):
        numb = len(row["subbasinList"])
        if numb > 1:
            for i in range(1, 367):
                row[f"DOWY {i}"] = row[f"DOWY {i}"] / numb
            return row
        return row

    joined = joined.apply(standardize_by_number_basins, axis=1)

    # explode the rows have more than one basin
    joined_explode = joined.explode("subbasinList").copy()

    # group by year and district and sum up the volumes
    # group by to summ by year variable key
    column_names = [f"DOWY {i}" for i in range(1, 367)]

    # group by soilType + OFR crop
    grouped_df = joined_explode.groupby(["Year", "subbasinList"])[column_names].agg("sum").reset_index()

    # rename column back to subbasin
    grouped_df.rename(columns={"subbasinList": "subbasin"}, inplace=True)

    # get the list of years
    years = grouped_df["Year"].unique()

    # df_pivot = pd.pivot_table(df, index='gratID', columns=)
    d1 = grouped_df.set_index(["subbasin", "Year"]).unstack()
    d1.columns = d1.columns.map(lambda x: "Year {} {}".format(*reversed(x)))
    d1.reset_index(inplace=True)

    # set columns in year -> date order and drop extra day for non-leap years
    # build columns names "Year 2001 DOWY 1"
    ordered_columns = ["subbasin"]
    for y in years:
        if is_leap_year(y):
            for d in range(1, 367):
                ordered_columns.append(f"Year {y} DOWY {d}")
        else:
            for d in range(1, 366):
                ordered_columns.append(f"Year {y} DOWY {d}")

    d1_order = d1[ordered_columns]

    joined_transpose = d1_order.set_index("subbasin").transpose().reset_index()
    return joined_transpose.rename(columns={"index": "Year and Day"})


def acres_available_and_used(year, site_list):
    """Calculates the acres available and used for different recharge types and other categories for a given year.

    Args:
        year: the current year iteration
        site_list: list of site objects

    Returns: dataframe with Year, USED FTB, USED In-Lieu, USED OFR, FTB, In-Lieu, OFR, DAC, Subsidence, GSC, INBASINRET
    """
    # initialize variables to store acreage
    data = {
        "Year": year,
        "USED FTB": "WARN",
        "USED In-Lieu": 0.0,
        "USED OFR": 0.0,
        "FTB": "WARN",
        "In-Lieu": 0.0,
        "OFR": 0.0,
        "DAC": 0.0,
        "Subsidence": 0.0,
        "GSC": 0.0,
        "INBASINRET": 0.0,
    }

    for site in site_list:
        if site.recharge_type == "OFR":
            if site.crop is not None:
                data["OFR"] += site.acres
                if sum(site.ofr_used_volume) > 0:
                    data["USED OFR"] += site.acres
            if site.in_lieu_crop is not None:
                data["In-Lieu"] += site.acres
                if sum(site.in_lieu_used_volume) > 0:
                    data["USED In-Lieu"] += site.acres

                    # report acreage used for DAC/Subsidence/GSC
                    # site is used when any of the volumes are > 0
            if sum(site.ofr_used_volume) > 0 or sum(site.in_lieu_used_volume) > 0:
                if site.dac is not None:
                    data["DAC"] += site.acres
                if site.subsidence is not None:
                    data["Subsidence"] += site.acres
                if site.gsc is not None:
                    data["GSC"] += site.acres
                if site.inbasinret is not None:
                    data["INBASINRET"] += site.acres
                    # TODO flow through basins (FTB)

    return pd.DataFrame([data])


def yearly_wafr_applied_by_site(year, sites_list):
    """Report of the WAFR applied per site for each year.

    Used for joining back to the input sites polygons for viz.

    Args:
        year: the current year iteration
        sites_list: list of site objects

    Returns: dataframe with gratID, Year, and usedVolume
    """
    data_rows = []

    for site in sites_list:
        # volume for basins is used volume, OFR is ofrUsed + inLieuUsed
        if site.recharge_type in ("Basin", "Canal"):
            data_rows.append((site.grat_id, year, sum(site.used_volume)))
        elif site.recharge_type == "OFR":
            data_rows.append(
                (
                    site.grat_id,
                    year,
                    sum(site.ofr_used_volume) + sum(site.in_lieu_used_volume),
                )
            )

    return pd.DataFrame(data_rows, columns=["gratID", "Year", "usedVolume"])


def yearly_wafr_report(year, wafr_dict, raw_wafr_dict):
    """Create a yearly WAFR report by source with unused and total WAFR.

    Args:
        year: the current year iteration
        wafr_dict: dictionary of unused WAFR by source
        raw_wafr_dict: dictionary of total WAFR by source

    Returns: dataframe of unused and total WAFR by source

    """
    # sum the wafr values (list) by source
    sum_wafr = {k: sum(v) for k, v in wafr_dict.items()}
    sum_raw_wafr = {k: sum(v) for k, v in raw_wafr_dict.items()}

    # create dataframe with year, source, unused wafr, total wafr
    df_input = {
        "Input WAFR": sum_raw_wafr,
        "Unused WAFR": sum_wafr,
    }

    df = pd.DataFrame(df_input)

    # switch the columns and rows
    df = df.transpose().reset_index()
    # rename the index column
    df = df.rename(columns={"index": "Type"})
    df["Year"] = year

    return df


def mlrp_report(site_info_df):
    """Report the list of gratIDs that got converted to MLRP.

    Args:
        site_info_df: dataframe of site attribution, from summary_operations.get_site_info

    Returns: dataframe of the gratIDs that got converted to MLRP

    """
    # filter the dataframe to only include rows where the crop type is MLRP
    df = site_info_df[site_info_df["crop"] == "MLRP"]

    # keep only the gratID, district, agency and acres columns
    return df[["gratID", "district", "agency", "acres"]]


def daily_water_transfer_by_sustain_zone_report(year, site_list, transfer_list):
    """Report the daily water transfer by sustainability zone.

    Args:
        year: current year
        site_list: list of sites
        transfer_list: list of zones to include in the report

    Returns: dataframe with daily water transfer by sustainability zone report

    """
    # initialize variables to store acreage
    data = {}

    # volume is an array of 366 days, need to sum the values per day

    for site in site_list:
        # build unique key
        if site.sustainability_zone is not None and site.sustainability_zone in transfer_list:
            if site.recharge_type in ("Basin", "Canal"):
                volume_array_daily = site.used_volume

                # add the daily volume to the data
                data[site.sustainability_zone] = data.get(site.sustainability_zone, np.array([0] * 366)) + np.array(
                    volume_array_daily
                )

            elif site.recharge_type == "OFR":
                volume_array_daily = np.array(site.ofr_used_volume) + np.array(site.in_lieu_used_volume)

                # add the daily volume to the data
                data[site.sustainability_zone] = data.get(site.sustainability_zone, np.array([0] * 366)) + np.array(
                    volume_array_daily
                )

                # pandas operation to turn the data into a dataframe
    df = pd.DataFrame(data)

    # convert index to a field called Day
    df["Day"] = df.index + 1

    # add a column for the year
    df["Year"] = year

    # rearrange the columns
    order_cols = ["Year", "Day"] + list(data.keys())
    return df[order_cols]


def yearly_water_transfer_by_sustain_zone_report(daily_df):
    """Rolls the daily water transfer report up to a yearly total per sustainability zone.

    Args:
        daily_df: dataframe from daily_water_transfer_by_sustain_zone_report, combined
            across every water year (report 20)

    Returns: dataframe of yearly totals, with the Day column dropped
    """
    # group by year and district and sum up the volumes
    yearly_df = daily_df.groupby(["Year"]).sum().reset_index()  # rollup to a yearly total

    # drop the day column
    return yearly_df.drop(columns=["Day"])


def total_recharge_by_sustainability_zone_report(year, site_list):
    """Report the total Recharge by sustainability zone.

    Args:
        year: current year
        site_list: list of sites

    Returns: dataframe of total recharge by sustainability zone

    """
    # initialize variables to store acre-feet of total WAFR applied as recharge
    data = {}

    for site in site_list:
        # build unique key
        if site.sustainability_zone is None:
            zone = "No Zone"
        else:
            value = site.sustainability_zone
            try:
                # if it's numeric (int, float, or numeric string like "1.0")
                zone = str(int(float(value)))
            except (ValueError, TypeError):
                # fallback: just make sure it's a string
                zone = str(value).strip()
        try:
            # volume is an array of 366 days, need to sum the values per day
            if site.recharge_type in ("Basin", "Canal"):
                vol = sum(site.daily_recharge_volumes)

            elif site.recharge_type == "OFR":
                # volume is an array of 366 days, need to sum the values per day
                vol = sum(site.ofr_daily_recharge_volumes) + sum(site.in_lieu_daily_recharge_volumes)
            else:
                vol = 0

                # add the daily volume to the data
            data[zone] = data.get(zone, 0) + vol
        except (AttributeError, TypeError):
            logger.warning(
                "Skipping site %s: could not total its recharge volumes",
                getattr(site, "grat_id", "<unknown>"),
                exc_info=True,
            )

            # pandas operation to turn the data into a dataframe
    df = pd.DataFrame(data.items(), columns=["sustainabilityZone", "acreFeet"])
    df["Year"] = year

    # rearrange the columns
    order_cols = ["Year", "sustainabilityZone", "acreFeet"]

    return df[order_cols]


def total_recharge_by_district_report(year, site_list):
    """Report the total Recharge by district.

    Args:
        year: current year
        site_list: list of sites

    Returns: dataframe of total recharge by district

    """
    # initialize variables to store acre-feet of total WAFR applied as recharge
    data = {}

    for site in site_list:
        # build unique key
        if site.district is None or site.district == "<Null>":
            continue
        value = site.district
        try:
            # if it's numeric (int, float, or numeric string like "1.0")
            zone = str(int(float(value)))
        except (ValueError, TypeError):
            # fallback: just make sure it's a string
            zone = str(value).strip()
        try:
            # volume is an array of 366 days, need to sum the values per day
            if site.recharge_type in ("Basin", "Canal"):
                vol = sum(site.daily_recharge_volumes)

            elif site.recharge_type == "OFR":
                # volume is an array of 366 days, need to sum the values per day
                vol = sum(site.ofr_daily_recharge_volumes) + sum(site.in_lieu_daily_recharge_volumes)
            else:
                vol = 0

                # add the daily volume to the data
            data[zone] = data.get(zone, 0) + vol
        except (AttributeError, TypeError):
            logger.warning(
                "Skipping site %s: could not total its recharge volumes",
                getattr(site, "grat_id", "<unknown>"),
                exc_info=True,
            )

            # pandas operation to turn the data into a dataframe
    df = pd.DataFrame(data.items(), columns=["district", "acreFeet"])
    df["Year"] = year

    # rearrange the columns
    order_cols = ["Year", "district", "acreFeet"]

    return df[order_cols]
