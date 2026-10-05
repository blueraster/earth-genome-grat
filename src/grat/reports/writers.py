"""Writes report dataframes to csv files, and manages the output folder."""

import datetime
import logging
import os
import shutil
from typing import NamedTuple

import pandas as pd

logger = logging.getLogger(__name__)


class ReportFile(NamedTuple):
    """Where one report is written.

    Attributes:
        filename: basename written inside the run's output folder.
        append: True when each water year appends to a single file, in which case
            the header is written only for the first year.
    """

    filename: str
    append: bool = True


# Every default report filename defined here
REPORT_FILES: dict[str, ReportFile] = {
    "annual_summary_recharge": ReportFile("02_Annual Summary Recharge and WAFR.csv"),
    "daily_summary_recharge": ReportFile("03_Daily Summary Recharge.csv"),
    "daily_wafr_applied_by_site": ReportFile("04_Daily WAFR Applied by Site.csv", append=False),
    "daily_recharge_by_site": ReportFile("05_Daily Detailed Recharge Applied by Site.csv", append=False),
    "monthly_recharge_by_site_report": ReportFile("06_Monthly Recharge by Site.csv"),
    "monthly_recharge_by_site_report_detailed": ReportFile("07_Monthly Detailed Recharge by Site.csv", append=False),
    "daily_farm_recharge_report": ReportFile("08_Daily OFR by Crop and Soil Type.csv"),
    "yearly_aggregate_farm_recharge_report": ReportFile("09_Annual OFR by Crop and Soil Type.csv"),
    "daily_wafr_report": ReportFile("10_Daily Unused WAFR by Source.csv"),
    "bottlenecks_capacity_limitations_report": ReportFile("11_Annual Conveyance Bottleneck Count.csv"),
    "bottlenecks_daily_conveyance_limits_by_volume": ReportFile("12_Daily Conveyance Limits by Volume.csv"),
    "yearly_bottleneck_capacity_logger": ReportFile("13_Daily Conveyance Bottleneck IDs.csv"),
    "annual_recharge_by_sw_and_gw": ReportFile("15_Annual Recharge by SW Source and GW Basin.csv"),
    "annual_recharge_by_district_and_gw": ReportFile("16_Annual District Recharge by GW Basin.csv"),
    "annual_recharge_by_district_and_wafr": ReportFile("17_Annual District Recharge by SW Source.csv"),
    "daily_recharge_by_gw_basin": ReportFile("18_Daily Recharge by GW Basin.csv"),
    "acres_available_and_used": ReportFile("19_Acres Available and Used.csv"),
    "daily_water_transfer_by_sustain_zone_report": ReportFile("20_Daily Water Transfer by Sustainability Zone.csv"),
    "yearly_water_transfer_by_sustain_zone_report": ReportFile(
        "21_Yearly Water Transfer by Sustainability Zone.csv", append=False
    ),
    "fields_repurposed": ReportFile("22_Fields Repurposed.csv", append=False),
    # Intermediates. Written per year, read back after the run, then deleted.
    "site_info": ReportFile("temp_siteInfo.csv", append=False),
    # Intermediates. These are appended to across the years, read back by
    # `selector.post_process`, and deleted once the run finishes.
    "annual_recharge_by_grouping": ReportFile("annualRechargeByGrouping.csv"),
    "monthly_recharge_by_site_temp": ReportFile("temp_Monthly Recharge by Site.csv"),
    "yearly_wafr_applied_by_site": ReportFile("temp_Yearly WAFR Applied by Site.csv"),
    "unused_and_orig_wafr": ReportFile("temp_unused_and_orig_wafr_by_source.csv"),
    "total_by_sustainability_zone": ReportFile("temp_totalBySustainabilityZone.csv"),
    "total_by_district": ReportFile("temp_totalByDistrict.csv"),
}


def construct_output_folder_name(path_to_folder: str):
    """Creates a new unique folder using the current datetime to store the exported csv results.

    Args:
        path_to_folder: path to the output parent directory where the results folder will be created

    Returns: path to the result folder that was just created
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    suffix = 0
    while True:
        name = f"results_{timestamp}" if suffix == 0 else f"results_{timestamp}_{suffix}"
        folder_name = os.path.join(path_to_folder, name)
        try:
            os.mkdir(folder_name)
        except FileExistsError:
            suffix += 1
        else:
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


def write_csv(df, output_folder, filename, *, append=False):
    """Writes a dataframe to a csv file inside the output folder.

    Args:
        df: dataframe to write.
        output_folder: folder the file is written into.
        filename: basename of the output file.
        append: when True, append to any existing file and write the header only if
            the file is not already there. Used by the reports that build up a row
            per water year.

    Returns: path to the csv file that was written
    """
    out_file = os.path.join(output_folder, filename)

    if append:
        df.to_csv(out_file, index=False, mode="a", header=not os.path.exists(out_file))
    else:
        df.to_csv(out_file, index=False)

    return out_file


def write_report(df, output_folder, key):
    """Writes a dataframe to the file that `REPORT_FILES` gives for `key`.

    Args:
        df: dataframe to write.
        output_folder: folder the file is written into.
        key: entry in `REPORT_FILES`, which supplies the filename and whether the
            report appends across water years.

    Returns: path to the csv file that was written

    Raises:
        KeyError: `key` is not a known report.
    """
    report_file = REPORT_FILES[key]
    return write_csv(df, output_folder, report_file.filename, append=report_file.append)


def read_report(output_folder, key, year=None, dtype=None):
    """Reads a report back from the folder it was written into.

    Args:
        output_folder: the run's output folder.
        key: entry in `REPORT_FILES`.
        year: water year, for the reports written into a per-year subfolder.
        dtype: optional column types, passed through to `pandas.read_csv`. The
            reports that are read back and re-pivoted need the types the csv threw away.

    Returns: the report as a dataframe

    Raises:
        KeyError: `key` is not a known report.
        FileNotFoundError: that report is not in `output_folder`.
    """
    folder = output_folder if year is None else os.path.join(output_folder, str(year))
    return pd.read_csv(os.path.join(folder, REPORT_FILES[key].filename), dtype=dtype)
