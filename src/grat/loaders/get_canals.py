"""Loads canal info from a csv into Canal objects."""

import pandas as pd

from grat.loaders.helpers import single_value_as_string, split_multivalues
from grat.model.constants import DEFAULT_IRRIGATION_DAYS
from grat.model.sites import Canal


def load_canals(path_to_canal_csv, irrigation_days=None):
    """Loads canal info from a csv file into Canal objects.

    Args:
        path_to_canal_csv: csv with attribute for name, wafr sources, perc rate and daily max capacity
        irrigation_days: zero-indexed days of the water year in the irrigation season,
            during which canals accept no WAFR. Defaults to `DEFAULT_IRRIGATION_DAYS`.

    Returns:
        list of canal objects
    """
    if irrigation_days is None:
        irrigation_days = DEFAULT_IRRIGATION_DAYS

    list_of_canals = []

    df = pd.read_csv(path_to_canal_csv)
    df = df.astype(object).where(pd.notnull(df), None)

    # loop through the rows in the csv and construct the canals
    for _, row in df.iterrows():
        c = Canal(
            grat_id=row["District"],
            district=row["District"],
            wafr_sources_primary=split_multivalues(row["WAFRSOURCE"]),
            wafr_sources_secondary=split_multivalues(row["WAFRSOURCE2"]),
            perc_rate=row["Seepage"],
            subbasin=single_value_as_string(split_multivalues(row["GWBASIN"])),
            irrigation_days=irrigation_days,
            max_capacity=row["Volume"],
        )
        list_of_canals.append(c)

    return list_of_canals
