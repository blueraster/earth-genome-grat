"""Runs the model and produces the reports, in one call.

This is the only module that imports both `grat.model` and `grat.reports`. The model
knows nothing about reports; the reports layer knows nothing about how a run is driven.
They meet here, through `start_analysis`'s `on_year` hook.

One call runs every water year and writes the reports::

    result = run_grat(sites, wafr, bottlenecks, crop_calendar, precip,
                      reports=["annual_summary_recharge", "daily_summary_recharge"])

    result["zip_path"]                     # the archive to hand to someone
    result["reports"]                      # the report names that were produced
    result["series"]["unused_wafr"]        # the frontend visualisation data

Any report the run produced can then be read back as a dataframe, without the run having
held anything in memory::

    from grat import read_report

    read_report(result["output_folder"], "annual_summary_recharge")
    read_report(result["output_folder"], "daily_recharge_by_site", year=2047)
"""

import logging

from grat.model.engine import start_analysis
from grat.reports import catalog
from grat.reports.selector import post_process, report_picker
from grat.reports.writers import construct_output_folder_name, zip_output_folder

logger = logging.getLogger(__name__)


def _transfer_zones(transfer_limits):
    """The districts or zones eligible for transferred water.

    `calc_transfer_limits` returns the budgets keyed by district, plus a
    `"transfer_wafr_sources"` entry carrying its own input. That entry is not a district
    and must not reach the reports as one.

    Args:
        transfer_limits: the mapping `calc_transfer_limits` returned.

    Returns: list of zone names, or None when the run has no transfers
    """
    zones = [zone for zone in transfer_limits or {} if zone != "transfer_wafr_sources"]
    return zones or None


def run_grat(
    raw_sites,
    raw_wafr,
    raw_bottlenecks,
    crop_calendar,
    precip,
    *,
    reports=catalog.ALL_REPORTS,
    output_parent=".",
    zip_output=True,
    zip_name=None,
    **model_kwargs,
):
    """Runs the model across every water year and produces the requested reports.

    Args:
        raw_sites: every canal, basin and farm, in processing order.
        raw_wafr: water available for recharge, indexed as `[year][source][day]`.
        raw_bottlenecks: the bottlenecks restricting delivery, or None.
        crop_calendar: accepted application rate, indexed as `[crop][soil_type][day]`.
        precip: precipitation, indexed as `[year][precip_grid][day]`.
        reports: report names to produce. Defaults to everything in the catalog; pass a
            smaller list and only the intermediates those reports need are built.
        output_parent: directory to create the timestamped results folder in.
        zip_output: zip the results folder when the run finishes.
        zip_name: name for the zip, defaulting to the results folder's name.
        **model_kwargs: passed through to `start_analysis` - `years`,
            `crop_calendar_in_lieu`, `use_in_lieu`, `use_ofr`, `rma_sort`,
            `transfer_goals`.

    Returns:
        A dict with four keys:

        - `"output_folder"`: where the csv files were written. Pass it to `read_report`
          to get any of them back as a dataframe.
        - `"zip_path"`: the zip archive, or None when `zip_output` was False.
        - `"reports"`: sorted names of the reports produced. A report whose model input
          was missing - no bottlenecks, no transfer list - is absent.
        - `"series"`: the frontend visualisation data, keyed by series name.

    Raises:
        KeyError: a report name is not in the catalog.
    """
    names = catalog.expand(reports)
    output_folder = construct_output_folder_name(output_parent)
    logger.info("Writing reports to %s", output_folder)

    produced = set()

    def build_this_years_reports(year, sites, raw_wafr, wafr, bottlenecks, transfer_limits):
        """Builds one water year's reports, called as the model finishes each year."""
        built = report_picker(
            names,
            output_folder,
            year,
            sites,
            raw_wafr,
            wafr,
            bottlenecks,
            transfer_list=_transfer_zones(transfer_limits),
        )
        produced.update(built)

    start_analysis(
        raw_sites,
        raw_wafr,
        raw_bottlenecks,
        crop_calendar,
        precip,
        on_year=build_this_years_reports,
        **model_kwargs,
    )

    results = post_process(names, output_folder, produced)
    produced.update(name for name in results if name in catalog.CSV_REPORTS)

    return {
        "output_folder": output_folder,
        "zip_path": zip_output_folder(output_folder, zip_name) if zip_output else None,
        "reports": sorted(produced),
        "series": {name: value for name, value in results.items() if name in catalog.FRONTEND_SERIES},
    }
