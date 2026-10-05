"""Builds the reports a caller asked for, and writes them."""

import logging
import os

import pandas as pd

from grat.reports import catalog
from grat.reports.builders import (
    acres_available_and_used,
    annual_recharge_by_district_and_gw,
    annual_recharge_by_district_and_wafr,
    annual_recharge_by_grouping,
    annual_recharge_by_sw_and_gw,
    annual_summary_recharge,
    bottlenecks_capacity_limitations_report,
    bottlenecks_daily_conveyance_limits_by_volume,
    daily_farm_recharge_report,
    daily_recharge_by_gw_basin,
    daily_recharge_by_site,
    daily_summary_recharge,
    daily_summary_recharge_report,
    daily_wafr_applied_by_site,
    daily_wafr_report,
    daily_water_transfer_by_sustain_zone_report,
    get_site_info,
    mlrp_report,
    monthly_recharge_by_site_report,
    monthly_recharge_by_site_report_post,
    monthly_recharge_by_site_summary,
    site_volume_report,
    total_recharge_by_sustainability_zone_report,
    yearly_aggregate_farm_recharge_report,
    yearly_bottleneck_capacity_logger,
    yearly_wafr_applied_by_site,
    yearly_wafr_report,
    yearly_water_transfer_by_sustain_zone_report,
)
from grat.reports.writers import (
    REPORT_FILES,
    read_report,
    write_report,
)

logger = logging.getLogger(__name__)

# Working files. These are written per year, read back once the run finishes, and then deleted.
INTERMEDIATE_FILES = frozenset(REPORT_FILES) - catalog.CSV_REPORTS


def report_picker(
    names,
    output_folder,
    year,
    sites,
    year_raw_wafr,
    wafr,
    bottlenecks=None,
    transfer_list=None,
):
    """Generates the reports for a single year of results.

    Args:
        names: report names to generate. Post-run names are accepted and used only to
            decide which intermediates this year must contribute to.
        output_folder: folder to write into, or None to build the dataframes
        year: the current year
        sites: list of the sites objects
        year_raw_wafr: the unmodified WAFR for this year
        wafr: the end wafr after water has been applied to the sites
        bottlenecks: list of bottlenecks, or None if the run has none
        transfer_list: list of zones that can receive water from transfers

    Returns: dict of report name to dataframe, for the reports produced this year

    Raises:
        KeyError: a name is not a known report.
    """
    logger.info("Generating reports")
    wanted = catalog.expand(names)

    if bottlenecks is None:
        skipped = wanted & catalog.NEEDS_BOTTLENECKS
        if skipped:
            logger.info("No bottlenecks provided, skipping %s", ", ".join(sorted(skipped)))
        wanted -= catalog.NEEDS_BOTTLENECKS

    if transfer_list is None:
        skipped = wanted & catalog.NEEDS_TRANSFERS
        if skipped:
            logger.warning("No transfer list provided, skipping %s", ", ".join(sorted(skipped)))
        wanted -= catalog.NEEDS_TRANSFERS

    def publish(df, key, folder=output_folder):
        """Writes a report and records its frame."""
        if folder is not None:
            write_report(df, folder, key)
        if key in wanted:
            produced[key] = df

    produced = {}

    # Site attribution
    if wanted & catalog.NEEDS_SITE_INFO:
        site_info_df = get_site_info(sites)
        if output_folder is not None:
            write_report(site_info_df, output_folder, "site_info")

    if wanted & catalog.NEEDS_DAILY_SUMMARY:
        daily_summary_df = daily_summary_recharge(year, sites, year_raw_wafr, wafr)

        if "annual_summary_recharge" in wanted:
            publish(annual_summary_recharge(daily_summary_df), "annual_summary_recharge")

        if "daily_summary_recharge" in wanted:
            publish(daily_summary_recharge_report(daily_summary_df), "daily_summary_recharge")

    if wanted & catalog.NEEDS_SITE_VOLUME:
        site_volume_report_df = site_volume_report(year, sites)
        year_folder = None if output_folder is None else os.path.join(output_folder, f"{year}")
        if year_folder is not None and wanted & catalog.YEAR_SUBFOLDER:
            os.makedirs(year_folder, exist_ok=True)

        if "daily_wafr_applied_by_site" in wanted:
            publish(
                daily_wafr_applied_by_site(site_volume_report_df, site_info_df),
                "daily_wafr_applied_by_site",
                year_folder,
            )

        if "daily_recharge_by_site" in wanted:
            publish(
                daily_recharge_by_site(site_volume_report_df, site_info_df),
                "daily_recharge_by_site",
                year_folder,
            )

        if wanted & catalog.NEEDS_MONTHLY:
            # accumulated per year and pivoted after the run
            monthly_df = monthly_recharge_by_site_report(site_volume_report_df)
            if output_folder is not None:
                write_report(monthly_df, output_folder, "monthly_recharge_by_site_temp")

        if "daily_farm_recharge_report" in wanted:
            publish(daily_farm_recharge_report(site_volume_report_df, site_info_df), "daily_farm_recharge_report")

        if "yearly_aggregate_farm_recharge_report" in wanted:
            publish(
                yearly_aggregate_farm_recharge_report(site_volume_report_df, site_info_df),
                "yearly_aggregate_farm_recharge_report",
            )

        if "daily_recharge_by_gw_basin" in wanted:
            publish(daily_recharge_by_gw_basin(site_volume_report_df, site_info_df), "daily_recharge_by_gw_basin")

    if "daily_wafr_report" in wanted:
        publish(daily_wafr_report(year, wafr), "daily_wafr_report")

    if "bottlenecks_capacity_limitations_report" in wanted:
        publish(bottlenecks_capacity_limitations_report(year, bottlenecks), "bottlenecks_capacity_limitations_report")

    if "bottlenecks_daily_conveyance_limits_by_volume" in wanted:
        publish(
            bottlenecks_daily_conveyance_limits_by_volume(year, bottlenecks),
            "bottlenecks_daily_conveyance_limits_by_volume",
        )

    if "yearly_bottleneck_capacity_logger" in wanted:
        publish(yearly_bottleneck_capacity_logger(year, bottlenecks), "yearly_bottleneck_capacity_logger")

    if wanted & catalog.NEEDS_ANNUAL_GROUPING:
        # reports 15, 16 and 17 have a complicated header, so they are built after the run
        grouping_df = annual_recharge_by_grouping(year, sites)
        if grouping_df is not None and output_folder is not None:
            write_report(grouping_df, output_folder, "annual_recharge_by_grouping")

    if "acres_available_and_used" in wanted:
        publish(acres_available_and_used(year, sites), "acres_available_and_used")

    if "daily_water_transfer_by_sustain_zone_report" in wanted:
        publish(
            daily_water_transfer_by_sustain_zone_report(year, sites, transfer_list),
            "daily_water_transfer_by_sustain_zone_report",
        )

    # Intermediates for the frontend series.
    if wanted & catalog.NEEDS_UNUSED_WAFR and output_folder is not None:
        write_report(yearly_wafr_report(year, wafr, year_raw_wafr), output_folder, "unused_and_orig_wafr")

    if wanted & catalog.NEEDS_WAFR_BY_SITE and output_folder is not None:
        write_report(yearly_wafr_applied_by_site(year, sites), output_folder, "yearly_wafr_applied_by_site")

    if wanted & catalog.NEEDS_TOTAL_BY_ZONE and output_folder is not None:
        write_report(
            total_recharge_by_sustainability_zone_report(year, sites),
            output_folder,
            "total_by_sustainability_zone",
        )

    return produced


MONTHLY_DTYPES = {
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
}

SITE_INFO_DTYPES = {
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
}


def post_process(names, output_folder, produced=None):
    """Builds the reports that can only run once every water year is done.

    Args:
        names: report names that were selected.
        output_folder: path to the output folder.
        produced: report names that report_picker  produced.

    Returns: dict of report name to result, holding the frontend series as json-ready
        dicts and the post-run csv reports as dataframes

    Raises:
        KeyError: a name is not a known report.
    """
    wanted = catalog.expand(names)
    if produced is not None:
        # report can be dropped by a missing model input
        guarded = (catalog.NEEDS_TRANSFERS | catalog.NEEDS_BOTTLENECKS) & catalog.PER_YEAR
        missing = guarded - set(produced)
        wanted -= missing
        wanted -= {name for name, sources in catalog.IMPLIES.items() if sources & missing}
    results = {}

    if wanted & catalog.NEEDS_ANNUAL_GROUPING:
        try:
            grouping_df = read_report(output_folder, "annual_recharge_by_grouping")
        except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
            logger.exception("unable to read the annual recharge by grouping intermediate")
        else:
            for name, build in (
                ("annual_recharge_by_sw_and_gw", annual_recharge_by_sw_and_gw),
                ("annual_recharge_by_district_and_gw", annual_recharge_by_district_and_gw),
                ("annual_recharge_by_district_and_wafr", annual_recharge_by_district_and_wafr),
            ):
                if name in wanted:
                    results[name] = build(grouping_df)
                    write_report(results[name], output_folder, name)

    if wanted & catalog.NEEDS_MONTHLY:
        pivot = monthly_recharge_by_site_report_post(
            read_report(output_folder, "monthly_recharge_by_site_temp", dtype=MONTHLY_DTYPES),
            read_report(output_folder, "site_info", dtype=SITE_INFO_DTYPES),
        )

        if "monthly_recharge_by_site_report" in wanted:
            results["monthly_recharge_by_site_report"] = monthly_recharge_by_site_summary(pivot)
            write_report(results["monthly_recharge_by_site_report"], output_folder, "monthly_recharge_by_site_report")

        if "monthly_recharge_by_site_report_detailed" in wanted:
            results["monthly_recharge_by_site_report_detailed"] = pivot
            write_report(pivot, output_folder, "monthly_recharge_by_site_report_detailed")

    if "fields_repurposed" in wanted:
        results["fields_repurposed"] = mlrp_report(read_report(output_folder, "site_info"))
        write_report(results["fields_repurposed"], output_folder, "fields_repurposed")

    if "yearly_water_transfer_by_sustain_zone_report" in wanted:
        name = "yearly_water_transfer_by_sustain_zone_report"
        results[name] = yearly_water_transfer_by_sustain_zone_report(
            read_report(output_folder, "daily_water_transfer_by_sustain_zone_report")
        )
        write_report(results[name], output_folder, name)

    # the frontend series
    for name, source, build in (
        ("yearly_recharge_volumes", "annual_summary_recharge", post_process_viz_recharge_by_type),
        ("unused_wafr", "unused_and_orig_wafr", post_process_unused_wafr),
        ("max_wafr_per_site", "yearly_wafr_applied_by_site", post_process_max_per_site),
        ("recharge_by_sustainability_zone", "total_by_sustainability_zone", post_process_recharge_by_sustain_zone),
    ):
        if name in wanted:
            results[name] = build(read_report(output_folder, source))

    _remove_intermediates(output_folder)
    return results


def _remove_intermediates(output_folder):
    """Deletes the per-year working files, leaving only the published reports."""
    for key in INTERMEDIATE_FILES:
        path = os.path.join(output_folder, REPORT_FILES[key].filename)
        try:
            os.remove(path)
        except FileNotFoundError:
            continue
        except OSError:
            logger.warning("unable to remove the intermediate %s", path, exc_info=True)


def post_process_viz_recharge_by_type(annual_summary_recharge_df):
    """Outputs the JSON used to build the frontend chart visualizations using report 2.

    Args:
        annual_summary_recharge_df: report 2 values for every water year

    Returns: dict keyed by "Years" and "Total" of recharge volumes by type
    """
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


def post_process_unused_wafr(wafr_unused_and_orig_all_years):
    """Post process the unused vs original WAFR.

    Args:
        wafr_unused_and_orig_all_years: input and unused WAFR by source, every water year

    Returns: dict of WAFR source to its input and unused volumes
    """
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


def post_process_max_per_site(df):
    """Post process the max used volume per site.

    Args:
        df: WAFR applied per site for every water year

    Returns: dict of gratID to the largest single-year used volume, omitting sites that used nothing
    """
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


# TODO how to enable ability to post process by a variable for when there isn't sustainability zones defined?
def post_process_recharge_by_sustain_zone(df):
    """Post process to get the WAFR by sustainability zone for the whole run.

    Sums the recharge by sustainability zone collected from each of the model year runs.

    Args:
        df: total recharge by sustainability zone for every water year

    Returns: dictionary with sustainability zone as key and total acre-feet as value
    """
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
