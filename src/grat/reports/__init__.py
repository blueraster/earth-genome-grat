"""Turns GRAT model results into report dataframes.

Reports are asked for by name. `catalog.ALL_REPORTS` lists them; `builders` holds the
pure functions that compute them, and `writers` is the only module that touches disk -
a caller who wants the numbers and not the csv files can ignore it.

`selector.report_picker` builds one water year's reports and returns them as
dataframes;
`selector.post_process` builds the reports that need every year at once.
"""

from grat.reports.catalog import ALL_REPORTS, CSV_REPORTS, FRONTEND_SERIES, expand
from grat.reports.selector import post_process, report_picker
from grat.reports.writers import read_report, write_report

__all__ = [
    "ALL_REPORTS",
    "CSV_REPORTS",
    "FRONTEND_SERIES",
    "expand",
    "post_process",
    "read_report",
    "report_picker",
    "write_report",
]
