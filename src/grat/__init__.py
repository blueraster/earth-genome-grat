"""GRAT - a groundwater recharge allocation model.

The model lives in `grat.model`; `grat.model.engine.start_analysis` runs it across a
span of water years. `grat.reports` turns a run's results into report dataframes, and
`grat.reports.writers` writes them to csv.

To run the model and produce reports in one call::

    from grat import read_report, run_grat

    result = run_grat(sites, wafr, bottlenecks, crop_calendar, precip,
                      reports=["annual_summary_recharge", "acres_available_and_used"])

    result["zip_path"]    # the results archive
    result["reports"]     # the report names that were produced

    read_report(result["output_folder"], "annual_summary_recharge")

`grat.reports.catalog.ALL_REPORTS` lists everything that can be asked for.
"""

from grat.reports.writers import read_report
from grat.run import run_grat

__all__ = ["read_report", "run_grat"]
