"""Generates output reports using pandas."""

import datetime
import logging
import os
import re
import shutil

import numpy as np
import pandas as pd
from reports.converters import is_leap_year, sum_array_by_month

logger = logging.getLogger(__name__)


def construct_output_folder_name(path_to_folder: str):
    """Creates a new unique folder using the current datetime to store the exported csv results.

    Args:
        path_to_folder: path to the output parent directory where the results folder will be created

    Returns: path to the result folder that was just created
    """
    t = datetime.datetime.now().strftime("%Y%m%d%H%M%S")  # current timestamp
    folder_name = os.path.join(path_to_folder, f"results_{t}")
    if not os.path.exists(folder_name):
        os.mkdir(folder_name)
    return folder_name


def zip_output_folder(result_folder_path, custom_name=None):
    """Zips up the output folder as a zipfile.

    Args:
        result_folder_path: path to zip up
        custom_name: optional custom name for the zip file

    Returns: path to the output zip file
    """
    parent_dir = os.path.dirname(result_folder_path)
    basename = os.path.basename(result_folder_path)

    if custom_name:
        basename = custom_name
    output_zip = os.path.join(parent_dir, basename)
    shutil.make_archive(output_zip, "zip", result_folder_path)
    return output_zip + ".zip"

    ########################################################################################
    # Report 1
    ########################################################################################

    # ##############################################r########################################
    # Report 2
    # #######################################################################################


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


def annual_summary_recharge_save(df, output_folder):
    """Saves the annualSummary dataframe to a csv file.

    Args:
        df: dataframe with annualSummaryRecharge values (generated from annualSummaryRecharge function())
        output_folder: path to the folder to save the output file

    Returns: path to csv file (02_Annual Summary Recharge and WAFR.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "02_Annual Summary Recharge and WAFR.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file

    ########################################################################################
    # Report 3
    ########################################################################################


def daily_summary_recharge_save(df, output_folder):
    """Saves the daily_summary_recharge combined dataframe to a csv file.

    Args:
        df: dataframe with all years of daily_summary_recharge combined.
        output_folder: path to the folder to save the output file

    Returns: path to csv file (03_Daily Summary Recharge.csv)

    """
    # don't need the "Canals Current Capacity" or "Basins Current Capacity" columns

    df = df[
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

    # create the output file name
    out_file = os.path.join(output_folder, "03_Daily Summary Recharge.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file

    ########################################################################################
    # Report 4
    ########################################################################################


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


def daily_wafr_applied_by_site_save(df, output_folder):
    """Saves the daily_wafr_applied_by_site dataframe to a csv file.

    Args:
        df: dataframe with daily_wafr_applied_by_site values (generated from daily_wafr_applied_by_site function())
        output_folder: path to the folder to save the output file

    Returns: path to csv file (04_Daily WAFR Applied by Site.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "04_Daily WAFR Applied by Site.csv")

    # save to csv
    df.to_csv(out_file, index=False)

    return out_file

    ########################################################################################
    # Report 5
    ########################################################################################


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


def daily_recharge_by_site_save(df, output_folder):
    """Saves the daily_recharge_by_site dataframe to a csv file.

    Args:
        df: dataframe with daily_recharge_by_site values (generated from daily_recharge_by_site function())
        output_folder: path to the folder to save the output file

    Returns: path to csv file (05_Daily Detailed Recharge Applied by Site.c)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "05_Daily Detailed Recharge Applied by Site.csv")

    # save to csv
    df.to_csv(out_file, index=False)

    return out_file

    ########################################################################################
    # Report 6 & Report 7
    ########################################################################################


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


def monthly_recharge_by_site_report_append(df, output_folder):
    """Saves the monthly_recharge_by_site_report dataframe to a csv file.

    Args:
        df: dataframe with monthly_recharge_by_site_report values
            (generated from monthly_recharge_by_site_report function())
        output_folder: path to the folder to save the output file

    Returns: path to csv file (06_Monthly Recharge by Site.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "temp_Monthly Recharge by Site.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file


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


def monthly_recharge_by_site_report_save(df, output_folder):
    """Saves the monthly_recharge_by_site_report dataframe to a csv file.

    Args:
        df: dataframe monthly_recharge_by_site_report_post
        output_folder: path to the folder to save the output file

    Returns: path to csv file (06_Monthly Recharge by Site.csv)
    """
    # get list of the df columns
    columns = df.columns.tolist()

    # loop through the existing columns and return the subset that match conditions below
    columns_to_keep = []
    for c in columns:
        if re.match(r"^Year \d+ Month \d{1,2}$", c):  # match the year and month columns
            columns_to_keep.append(c)

        if c in [
            "gratID",
            "rechargeType",
        ]:  # match the gratID identifier and rechargeType columns
            columns_to_keep.append(c)

            # create the output file name
    out_file = os.path.join(output_folder, "06_Monthly Recharge by Site.csv")

    # save to csv
    df[columns_to_keep].to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file


def monthly_recharge_by_site_report_detailed_save(df, output_folder):
    """Saves the monthly_recharge_by_site_report dataframe with site_info to a csv file.

    Args:
        df: dataframe with monthly_recharge_by_site_report values
            (from monthly_recharge_by_site_report function() + site_info)
        output_folder: path to the folder to save the output file

    Returns: path to csv file (07_Monthly Detailed Recharge by Site.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "07_Monthly Detailed Recharge by Site.csv")

    # save to csv
    df.to_csv(out_file, index=False)

    return out_file

    ########################################################################################
    # Report 8
    ########################################################################################


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


def daily_farm_recharge_report_save(df, output_folder):
    """Saves the daily_farm_recharge_report dataframe to a csv file.

    Args:
        df: dataframe with daily_farm_recharge_report values (generated from daily_farm_recharge_report function)
        output_folder: path to the folder to save the output file

    Returns: path to csv file (08_Daily OFR by Crop and Soil Type.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "08_Daily OFR by Crop and Soil Type.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file

    ########################################################################################
    # Report 9
    ########################################################################################


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

    return pivoted_df


def yearly_aggregate_farm_recharge_report_save(df, output_folder):
    """Saves the yearly_aggregate_farm_recharge_report dataframe to a csv file.

    Args:
        df: dataframe with yearly_aggregate_farm_recharge_report values
            (from yearly_aggregate_farm_recharge_report function)
        output_folder: path to the folder to save the output file

    Returns: path to csv file (09_Annual OFR by Crop and Soil Type.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "09_Annual OFR by Crop and Soil Type.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file

    ########################################################################################
    # Report 10
    ########################################################################################


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


def daily_wafr_report_save(df, output_folder):
    """Saves the daily_wafr_report dataframe to a csv file.

    Args:
        df: dataframe with daily_wafr_report values (from daily_wafr_report function)
        output_folder: path to the folder to save the output file

    Returns: path to csv file (10_Daily Unused WAFR by Source.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "10_Daily Unused WAFR by Source.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file

    ########################################################################################
    # Report 11
    ########################################################################################


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


def bottlenecks_capacity_limitations_report_save(df, output_folder):
    """Saves the bottlenecks_capacity_limitations_report dataframe to a csv file.

    Args:
        df: dataframe with bottlenecks_capacity_limitations_report values
            (from bottlenecks_capacity_limitations_report function)
        output_folder: path to the folder to save the output file

    Returns: path to csv file (11_Annual Conveyance Bottleneck Count.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "11_Annual Conveyance Bottleneck Count.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file

    ########################################################################################
    # Report 12
    ########################################################################################


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


def bottlenecks_daily_conveyance_limits_by_volume_save(df, output_folder):
    """Saves the bottlenecks_daily_conveyance_limits_by_volume dataframe to a csv file.

    Args:
        df: dataframe with bottlenecks_daily_conveyance_limits_by_volume values
            (from bottlenecks_daily_conveyance_limits_by_volume function)
        output_folder: path to the folder to save the output file

    Returns: path to csv file (12_Daily Conveyance Limits by Volume.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "12_Daily Conveyance Limits by Volume.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file

    ########################################################################################
    # Report 13
    ########################################################################################


def yearly_bottleneck_capacity_logger(year, bottleneck_list):
    """Yearly Bottleneck Capacity Logger (used as input for 14 post processing).

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


def yearly_bottleneck_capacity_logger_save(df, output_folder):
    """Saves the yearly_bottleneck_capacity_logger dataframe to a csv file.

    Args:
        df: dataframe with yearly_bottleneck_capacity_logger values (from yearly_bottleneck_capacity_logger function)
        output_folder: path to the folder to save the output file

    Returns: path to csv file (13_Daily Conveyance Bottleneck IDs.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "13_Daily Conveyance Bottleneck IDs.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file

    ########################################################################################
    # annualRechargeByGrouping (used as input for 15,16,17 post processing)
    ########################################################################################


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


def annual_recharge_by_grouping_save(df, output_folder):
    """Saves the annual_recharge_by_grouping dataframe to a csv file.

    Args:
        df: dataframe with annual_recharge_by_grouping values (generated from annual_recharge_by_grouping function)
        output_folder: path to the folder to save the output file

    Returns: path to csv file (18_Daily Recharge by GW Basin.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "annualRechargeByGrouping.csv")

    if df is not None:
        # save to csv
        df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file

    ########################################################################################
    # Report 15
    ########################################################################################


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


def annual_recharge_by_sw_and_gw_save(df, output_folder):
    """Saves the annual_recharge_by_sw_and_gw dataframe to a csv file.

    Args:
        df: dataframe with annual_recharge_by_sw_and_gw values (generated from annual_recharge_by_sw_and_gw function)
        output_folder: path to the folder to save the output file

    Returns: path to csv file (15_Annual Recharge by SW Source and GW Basin.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "15_Annual Recharge by SW Source and GW Basin.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file

    ########################################################################################
    # Report 16
    ########################################################################################


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


def annual_recharge_by_district_and_gw_save(df, output_folder):
    """Saves the annual_recharge_by_district_and_gw dataframe to a csv file.

    Args:
        df: dataframe with annual_recharge_by_district_and_gw values
        output_folder: path to the folder to save the output file

    Returns: path to csv file (16_Annual District Recharge by GW Basin.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "16_Annual District Recharge by GW Basin.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file

    ########################################################################################
    # Report 17
    ########################################################################################


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


def annual_recharge_by_district_and_wafr_save(df, output_folder):
    """Saves the annual_recharge_by_district_and_wafr dataframe to a csv file.

    Args:
        df: dataframe with annual_recharge_by_district_and_wafr values
        output_folder: path to the folder to save the output file

    Returns: path to csv file (17_Annual District Recharge by SW Source.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "17_Annual District Recharge by SW Source.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file

    ########################################################################################
    # Report 18
    ########################################################################################


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


def daily_recharge_by_gw_basin_save(df, output_folder):
    """Saves the dailyRechargeByGWBasin dataframe to a csv file.

    Args:
        df: dataframe with dailyRechargeByGWBasin values (generated from dailyRechargeByGWBasin function)
        output_folder: path to the folder to save the output file

    Returns: path to csv file (18_Daily Recharge by GW Basin.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "18_Daily Recharge by GW Basin.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file

    ########################################################################################
    # Report 19
    ########################################################################################


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


def acres_available_and_used_save(df, output_folder):
    """Saves the acres_available_and_used dataframe to a csv file.

    Args:
        df: dataframe with acres_available_and_used values
        output_folder: path to the folder to save the output file

    Returns: path to csv file (19_Acres Available and Used.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "19_Acres Available and Used.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file

    ########################################################################################
    # Experimental
    ########################################################################################


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


def yearly_wafr_applied_by_site_save(df, output_folder):
    """Saves the yearly_wafr_applied_by_site dataframe to a csv file.

    Args:
        df: dataframe with yearly_wafr_applied_by_site values
        output_folder: path to the folder to save the output file

    Returns: path to csv file (20_Yearly WAFR Applied by Site.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "temp_Yearly WAFR Applied by Site.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file

    ##################################################################################
    # frontend table generation showing unused WAFR by source vs original WAFR
    ########################################################################################


def yearly_wafr_report(output_folder, year, wafr_dict, raw_wafr_dict):
    """Create a yearly WAFR report by source with unused and total WAFR.

    Args:
        output_folder: path to save the report
        year: the current year iteration
        wafr_dict: dictionary of unused WAFR by source
        raw_wafr_dict: dictionary of total WAFR by source

    Returns: report of unused and total WAFR by source as a csv file

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

    # save to a temp csv
    # create the output file name
    out_file = os.path.join(output_folder, "temp_unused_and_orig_wafr_by_source.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return

    ##################################################################################
    # 22 MLRP report - list of gratIDs that got converted to MLRP
    ##################################################################################


def mlrp_report(output_folder, site_info):
    """Report the list of gratIDs that got converted to MLRP.

    Args:
        output_folder: path to save the report
        site_info: path to the siteInfo.csv file

    Returns: the list of gratIDs that got converted to MLRP as a csv file

    """
    # load the temp_siteInfo.csv file
    df = pd.read_csv(site_info)

    # filter the dataframe to only include rows where the crop type is MLRP
    df = df[df["crop"] == "MLRP"]

    # keep only the gratID, district, agency and acres columns
    df = df[["gratID", "district", "agency", "acres"]]

    # save to a csv
    df.to_csv(os.path.join(output_folder, "22_Fields Repurposed.csv"), index=False)

    return

    ##################################################################################
    # 20 Daily Water Transfer by Sustainability Zone
    ##################################################################################


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

    # save the dataframe to csv using the append method


def daily_water_transfer_by_sustain_zone_report_save(df, output_folder):
    """Saves the daily_water_transfer_by_sustain_zone_report dataframe to a csv file.

    Args:
        df: dataframe with daily_water_transfer_by_sustain_zone_report values
        output_folder: path to the folder to save the output file

    Returns: path to csv file (20_Daily Water Transfer by Sustainability Zone.csv)
    """
    # create the output file name
    out_file = os.path.join(output_folder, "20_Daily Water Transfer by Sustainability Zone.csv")

    # save to csv
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))

    return out_file

    # roll up the daily water transfer by sustainability zone to a yearly report


def yearly_water_transfer_by_sustain_zone_report_save(output_folder):
    """Saves the daily_water_transfer_by_sustain_zone_report csv to a yearly csv file.

    Args:
        output_folder: path to the folder to save the output file

    Returns: path to csv file (21_Yearly Water Transfer by Sustainability Zone.csv)
    """
    # load the daily water transfer by district csv file
    try:
        daily_df = pd.read_csv(os.path.join(output_folder, "20_Daily Water Transfer by Sustainability Zone.csv"))

        # group by year and district and sum up the volumes
        yearly_df = daily_df.groupby(["Year"]).sum().reset_index()  # rollup to a yearly total

        # drop the day column
        yearly_df.drop(columns=["Day"], inplace=True)

        # save to a csv
        out_file = os.path.join(output_folder, "21_Yearly Water Transfer by Sustainability Zone.csv")
        yearly_df.to_csv(out_file, index=False)

    except FileNotFoundError:
        logger.info("The daily water transfer by sustainability zone report has not been generated yet")
        return None

    else:
        return out_file

        ##################################################################################
        # Frontend table generation showing total WAFR by sustainability zone or district
        ##################################################################################


def total_recharge_by_sustainability_zone_report(year, site_list, output_folder):
    """Report the total Recharge by sustainability zone.

    Args:
        year: current year
        site_list: list of sites
        output_folder: path to save the report

    Returns: total recharge by sustainability zone report as a csv file

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
    df = df[order_cols]

    # append to a temp csv file
    out_file = os.path.join(output_folder, "temp_totalBySustainabilityZone.csv")
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))
    return


def total_recharge_by_district_report(year, site_list, output_folder):
    """Report the total Recharge by district.

    Args:
        year: current year
        site_list: list of sites
        output_folder: path to save the report

    Returns: total recharge by district report as a csv file

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
    df = df[order_cols]

    # append to a temp csv file
    out_file = os.path.join(output_folder, "temp_totalByDistrict.csv")
    df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))
    return
