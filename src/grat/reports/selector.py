"""Selects which reports to generate and saves them."""

import glob
import logging
import os

import pandas as pd
from model.engine import timer_func
from reports.report_generator import (
    acres_available_and_used,
    acres_available_and_used_save,
    annual_recharge_by_district_and_gw,
    annual_recharge_by_district_and_gw_save,
    annual_recharge_by_district_and_wafr,
    annual_recharge_by_district_and_wafr_save,
    annual_recharge_by_grouping,
    annual_recharge_by_grouping_save,
    annual_recharge_by_sw_and_gw,
    annual_recharge_by_sw_and_gw_save,
    annual_summary_recharge,
    annual_summary_recharge_save,
    bottlenecks_capacity_limitations_report,
    bottlenecks_capacity_limitations_report_save,
    bottlenecks_daily_conveyance_limits_by_volume,
    bottlenecks_daily_conveyance_limits_by_volume_save,
    daily_farm_recharge_report,
    daily_farm_recharge_report_save,
    daily_recharge_by_gw_basin,
    daily_recharge_by_gw_basin_save,
    daily_recharge_by_site,
    daily_recharge_by_site_save,
    daily_summary_recharge_save,
    daily_wafr_applied_by_site,
    daily_wafr_applied_by_site_save,
    daily_wafr_report,
    daily_wafr_report_save,
    daily_water_transfer_by_sustain_zone_report,
    daily_water_transfer_by_sustain_zone_report_save,
    mlrp_report,
    monthly_recharge_by_site_report,
    monthly_recharge_by_site_report_append,
    monthly_recharge_by_site_report_detailed_save,
    monthly_recharge_by_site_report_post,
    monthly_recharge_by_site_report_save,
    total_recharge_by_sustainability_zone_report,
    yearly_aggregate_farm_recharge_report,
    yearly_aggregate_farm_recharge_report_save,
    yearly_bottleneck_capacity_logger,
    yearly_bottleneck_capacity_logger_save,
    yearly_wafr_applied_by_site,
    yearly_wafr_applied_by_site_save,
    yearly_wafr_report,
    yearly_water_transfer_by_sustain_zone_report_save,
)
from reports.summary_operations import (
    daily_summary_recharge,
    get_site_info,
    site_volume_report,
)

logger = logging.getLogger(__name__)


@timer_func
def report_picker(
    report_ids,
    output_folder,
    year,
    sites,
    year_raw_wafr,
    wafr,
    bottlenecks,
    frontend_viz=True,
    transfer_list=None,
):
    """Generates the reports for a single year of results.

    Will either append rows or save to a year specific output folder.

    Args:
        report_ids: list of reports to be generated
        output_folder: path to the folder used to store the outputs
        year: the current year
        sites: list of the sites objects
        year_raw_wafr: the unmodified WAFR for this year
        wafr: the end wafr after water has been applied to the sites
        bottlenecks: list of bottlenecks
        frontend_viz: boolean to generate the frontend visualizations data
        transfer_list: list of sustainability zones that can receive water from transfers
    """
    logger.info("Generating reports")

    site_info_df = get_site_info(sites)
    site_info_df.to_csv(os.path.join(output_folder, "temp_siteInfo.csv"), index=False)

    if any(e in [2, 3] for e in report_ids):
        # create the dailySummaryDF
        daily_summary_df = daily_summary_recharge(year, sites, year_raw_wafr, wafr)
        if 2 in report_ids:
            d = annual_summary_recharge(daily_summary_df)
            annual_summary_recharge_save(d, output_folder)

        if 3 in report_ids:
            daily_summary_recharge_save(daily_summary_df, output_folder)

    if any(e in [4, 5, 6, 7, 8, 9, 18] for e in report_ids):
        # create output folder for year if it doesn't exist
        output_folder_year = os.path.join(output_folder, f"{year}")

        site_volume_report_df = site_volume_report(year, sites)

        if 4 in report_ids:
            if not os.path.exists(output_folder_year):
                os.mkdir(output_folder_year)

            d = daily_wafr_applied_by_site(site_volume_report_df, site_info_df)
            daily_wafr_applied_by_site_save(d, output_folder_year)

        if 5 in report_ids:
            if not os.path.exists(output_folder_year):
                os.mkdir(output_folder_year)

            d = daily_recharge_by_site(site_volume_report_df, site_info_df)
            daily_recharge_by_site_save(d, output_folder_year)

        if 6 in report_ids or 7 in report_ids:
            d = monthly_recharge_by_site_report(site_volume_report_df)
            monthly_recharge_by_site_report_append(d, output_folder)

        if 8 in report_ids:
            d = daily_farm_recharge_report(site_volume_report_df, site_info_df)
            daily_farm_recharge_report_save(d, output_folder)

        if 9 in report_ids:
            d = yearly_aggregate_farm_recharge_report(site_volume_report_df, site_info_df)
            yearly_aggregate_farm_recharge_report_save(d, output_folder)

        if 18 in report_ids:
            d = daily_recharge_by_gw_basin(site_volume_report_df, site_info_df)
            daily_recharge_by_gw_basin_save(d, output_folder)

    if 10 in report_ids:
        d = daily_wafr_report(year, wafr)
        daily_wafr_report_save(d, output_folder)

    if 11 in report_ids:
        if bottlenecks is not None:
            d = bottlenecks_capacity_limitations_report(year, bottlenecks)
            bottlenecks_capacity_limitations_report_save(d, output_folder)
        else:
            logger.info("No bottlenecks provided, skipping report 11")

    if 12 in report_ids:
        if bottlenecks is not None:
            d = bottlenecks_daily_conveyance_limits_by_volume(year, bottlenecks)
            bottlenecks_daily_conveyance_limits_by_volume_save(d, output_folder)
        else:
            logger.info("No bottlenecks provided, skipping report 12")

    if 13 in report_ids:
        if bottlenecks is not None:
            d = yearly_bottleneck_capacity_logger(year, bottlenecks)
            yearly_bottleneck_capacity_logger_save(d, output_folder)
        else:
            logger.info("No bottlenecks provided, skipping report 13")

    if any(e in [15, 16, 17] for e in report_ids):
        # reports 15, 16, 17 are generated in postProcess since they have a complicated header
        annual_recharge_by_grouping_df = annual_recharge_by_grouping(year, sites)
        annual_recharge_by_grouping_save(annual_recharge_by_grouping_df, output_folder)

    if 19 in report_ids:
        d = acres_available_and_used(year, sites)
        acres_available_and_used_save(d, output_folder)

    if any(e in [20, 21] for e in report_ids):
        if transfer_list is None:
            logger.warning("No transfer list provided, skipping report 20 & 21")

        else:
            # create the dailyWaterTransferBySustainZoneReport report
            df = daily_water_transfer_by_sustain_zone_report(year, sites, transfer_list)
            daily_water_transfer_by_sustain_zone_report_save(df, output_folder)

    if frontend_viz:
        yearly_wafr_report(output_folder, year, wafr, year_raw_wafr)
        yearly_wafr_df = yearly_wafr_applied_by_site(year, sites)
        yearly_wafr_applied_by_site_save(yearly_wafr_df, output_folder)
        total_recharge_by_sustainability_zone_report(year, sites, output_folder)

    return


def post_process(report_ids, output_folder, frontend_viz=True):
    """Dataframe operations that run AFTER all years are completed.

    Args:
        report_ids: list of reports that were selected
        output_folder: path to the output folder
        frontend_viz: boolean to generate the frontend visualizations data

    Returns: dict of the frontend visualization results, or None when frontend_viz is False
    """
    if any(e in [15, 16, 17] for e in report_ids):
        try:
            annual_recharge_by_grouping_df = pd.read_csv(os.path.join(output_folder, "annualRechargeByGrouping.csv"))
        except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
            logger.exception("unable to read annualRechargeByGrouping.csv in post_process")
        else:
            if 15 in report_ids:
                d = annual_recharge_by_sw_and_gw(annual_recharge_by_grouping_df)
                annual_recharge_by_sw_and_gw_save(d, output_folder)

            if 16 in report_ids:
                d = annual_recharge_by_district_and_gw(annual_recharge_by_grouping_df)
                annual_recharge_by_district_and_gw_save(d, output_folder)

            if 17 in report_ids:
                d = annual_recharge_by_district_and_wafr(annual_recharge_by_grouping_df)
                annual_recharge_by_district_and_wafr_save(d, output_folder)

        # cleanup by deleting "annualRechargeByGrouping.csv"
        try:
            os.remove(os.path.join(output_folder, "annualRechargeByGrouping.csv"))
        except OSError:
            logger.warning("unable to remove files in post_process reports function", exc_info=True)

    if any(e in [6, 7] for e in report_ids):
        monthly_recharge_df = pd.read_csv(
            os.path.join(output_folder, "temp_Monthly Recharge by Site.csv"),
            dtype={
                "Year": int,
                "gratID": "string",
                "1": float,
                "2": float,
                "3": float,
                "4": float,
                "5": float,
                "6": float,
                "7": float,
                "8": float,
                "9": float,
                "10": float,
                "11": float,
                "12": float,
            },
        )

        site_info_df = pd.read_csv(
            os.path.join(output_folder, "temp_siteInfo.csv"),
            dtype={
                "gratID": "string",
                "rechargeType": "string",
                "acres": float,
                "cfsLimit": float,
                "precipGrid": float,
                "bottleneckIDs": "string",
                "soilType": "string",
                "rsi": float,
                "sortIndex": int,
                "crop": "string",
                "inLieuCrop": "string",
                "subbasin": "string",
                "district": "string",
                "sustainabilityZone": "string",
                "rma": "string",
                "watershed": "string",
                "dac": "string",
                "gsc": "string",
                "subsidence": "string",
                "inbasinret": "string",
                "shorebird": "string",
            },
        )
        pivot = monthly_recharge_by_site_report_post(monthly_recharge_df, site_info_df)

        if 6 in report_ids:
            monthly_recharge_by_site_report_save(pivot, output_folder)

        if 7 in report_ids:
            monthly_recharge_by_site_report_detailed_save(pivot, output_folder)

            # front end visualizations here
    if frontend_viz:
        yearly_recharge_volumes_json = post_process_viz_recharge_by_type(output_folder) if 2 in report_ids else None

        unused_wafr_json = post_process_unused_wafr(output_folder)

        max_wafr_per_site = post_process_max_per_site(output_folder)

        sustain_zones = post_process_recharge_by_sustain_zone(output_folder)

        frontend_viz_results = {
            "yearly_recharge_volumes": yearly_recharge_volumes_json,
            "unused_wafr": unused_wafr_json,
            "max_wafr_per_site": max_wafr_per_site,
            "recharge_by_sustainability_zone": sustain_zones,
        }

    else:
        frontend_viz_results = None

    if 22 in report_ids:
        mlrp_report(output_folder, os.path.join(output_folder, "temp_siteInfo.csv"))

    if 21 in report_ids:
        # create the yearly yearlyWaterTransferBySustainZoneReport_save report
        yearly_water_transfer_by_sustain_zone_report_save(output_folder)

        # cleanup by deleting all files in the output folder that begin with "temp_"
    try:
        temp_files = glob.glob(os.path.join(output_folder, "temp_*"))
        for t in temp_files:
            os.remove(t)
    except OSError:
        logger.warning("unable to remove files in post_process reports function", exc_info=True)
    return frontend_viz_results


def post_process_viz_recharge_by_type(output_folder):
    """Outputs the JSON used to build the frontend chart visualizations using report 2.

    Args:
        output_folder: path to the output folder containing the report 2 csv

    Returns: dict keyed by "Years" and "Total" of recharge volumes by type
    """
    # load the data from report 2 - annual summary recharge and wafr
    annual_summary_recharge_df = pd.read_csv(os.path.join(output_folder, "02_Annual Summary Recharge and WAFR.csv"))

    # keep only the columns needed for the visualization
    annual_summary_recharge_df = annual_summary_recharge_df[
        [
            "Year",
            "Total Recharge (AF) Canals",
            "Total Recharge (AF) Basins",
            "Total Recharge (AF) In-Lieu",
            "Total Recharge (AF) On Farm",
        ]
    ]

    # rename the columns to match the frontend
    annual_summary_recharge_df.columns = ["Year", "Canals", "Basins", "In-Lieu", "On Farm"]

    # convert year to string
    annual_summary_recharge_df["Year"] = annual_summary_recharge_df["Year"].astype(str)

    # add a row for the total of all the years
    total_row = annual_summary_recharge_df.sum(numeric_only=True)
    total_row["Year"] = "Total"

    # combine the total row with the rest of the data
    df = pd.concat([annual_summary_recharge_df, pd.DataFrame([total_row])], ignore_index=True)

    # Round to one decimal place
    df = df.round(1)

    # Create the final dictionary
    return {
        "Years": df.loc[df["Year"] != "Total"].set_index("Year").to_dict(orient="index"),
        "Total": df.loc[df["Year"] == "Total"].set_index("Year").to_dict(orient="index")["Total"],
    }


def post_process_unused_wafr(output_folder):
    """Post process the unused vs original WAFR.

    Args:
        output_folder: path to the output folder containing temp_unused_and_orig_wafr_by_source.csv

    Returns: dict of WAFR source to its input and unused volumes
    """
    # post process the unused vs original WAFR
    wafr_unused_and_orig_all_years = pd.read_csv(os.path.join(output_folder, "temp_unused_and_orig_wafr_by_source.csv"))
    df = wafr_unused_and_orig_all_years.groupby("Type").sum(numeric_only=True).reset_index().drop(columns=["Year"])

    # round to one decimal place
    df = df.round(1)

    # convert to dictionary
    result = {}
    for col in df.columns[1:]:  # Skip the 'Type' column
        result[col] = {
            df.iloc[0, 0]: df.iloc[0, df.columns.get_loc(col)],  # Input WAFR value
            df.iloc[1, 0]: df.iloc[1, df.columns.get_loc(col)],  # Unused WAFR value
        }
    return result


def post_process_max_per_site(output_folder):
    """Post process the max used volume per site.

    Args:
        output_folder: path to the output folder containing temp_Yearly WAFR Applied by Site.csv

    Returns: dict of gratID to the largest single-year used volume, omitting sites that used nothing
    """
    df = pd.read_csv(os.path.join(output_folder, "temp_Yearly WAFR Applied by Site.csv"))

    # for each site (gratID) in the dataframe, get the max usedVolume value
    df = df.groupby("gratID")["usedVolume"].max().reset_index().rename(columns={"usedVolume": "maxUsedVolumeForAYear"})

    # round the maxUsedVolumeForAYear to 2 decimal places
    df["maxUsedVolumeForAYear"] = df["maxUsedVolumeForAYear"].round(2)

    # save the df to a dict where the key is the gratID and the value is the maxUsedVolumeForAYear
    max_used_volume_dict = {}
    for _index, row in df.iterrows():
        if row["maxUsedVolumeForAYear"] == 0.0:
            continue
        max_used_volume_dict[row["gratID"]] = row["maxUsedVolumeForAYear"]

    return max_used_volume_dict


def post_process_recharge_by_sustain_zone(output_folder):
    """Post process to get the WAFR by sustainability zone for the 50-year period.

    Sums the recharge by sustainability zone that is appended per-year in each of the model year runs.

    Args:
        output_folder: path to the output folder containing the temp_totalBySustainabilityZone.csv file

    Returns: dictionary with sustainability zone as key and total acre-feet as value
    """
    df = pd.read_csv(os.path.join(output_folder, "temp_totalBySustainabilityZone.csv"))

    # group by the sustainability zone and sum the acre-feet to get the total for each zone
    df = df.groupby("sustainabilityZone")["acreFeet"].sum().reset_index()

    # round the acreFeet to 2 decimal places
    df["acreFeet"] = df["acreFeet"].round(2)
    # save the df to a dict where the key is the sustainability zone and the value is the acreFeet
    recharge_by_sustain_zone_dict = {}
    for _index, row in df.iterrows():
        raw_value = row["sustainabilityZone"]

        try:
            # handle numeric values like 1, 1.0, "1.0"
            zone = str(int(float(raw_value)))
        except (ValueError, TypeError):
            # fallback for text values like "No Zone"
            zone = str(raw_value).strip()

        recharge_by_sustain_zone_dict[zone] = float(row["acreFeet"])

    return recharge_by_sustain_zone_dict


def post_process_recharge_by_district(output_folder):
    """Post process to get the WAFR by district for the 50-year period.

    Sums the recharge by district that is appended per-year in each of the model year runs.

    Args:
        output_folder: path to the output folder containing the temp_totalByDistrict.csv file

    Returns: dictionary with district as key and total acre-feet as value
    """
    df = pd.read_csv(os.path.join(output_folder, "temp_totalByDistrict.csv"))

    # group by zone and sum the acre-feet to get the total for each zone
    df = df.groupby("district")["acreFeet"].sum().reset_index()

    # round the acreFeet to 2 decimal places
    df["acreFeet"] = df["acreFeet"].round(2)
    # save the df to a dict where the key is the district and the value is the acreFeet
    recharge_by_district_dict = {}
    for _index, row in df.iterrows():
        raw_value = row["district"]

        try:
            # handle numeric values like 1, 1.0, "1.0"
            zone = str(int(float(raw_value)))
        except (ValueError, TypeError):
            # fallback for text values like "No Zone"
            zone = str(raw_value).strip()

        recharge_by_district_dict[zone] = row["acreFeet"]

    return recharge_by_district_dict
