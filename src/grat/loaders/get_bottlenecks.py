"""Loads info from a csv into bottleneck objects."""

import pandas as pd

from grat.loaders.helpers import split_multivalues
from grat.model.bottlenecks import Bottleneck
from grat.model.constants import CFS_TO_ACRE_FEET_PER_DAY, DEFAULT_IRRIGATION_DAYS


def bottleneck_from_row(row, irrigation_days):
    """Builds a Bottleneck from one csv row or JSON record.

    Args:
        row: mapping with `bid`, `name`, `capacity_cfs`, `capacity_irr_cfs` and `wafrsource`
        irrigation_days: zero-indexed days of the water year that use the irrigation capacity

    Returns:
        bottleneck object
    """
    # an empty csv cell is read as NaN
    wafrsource = row["wafrsource"] if isinstance(row["wafrsource"], str) else None

    return Bottleneck(
        bottleneck_id=int(row["bid"]),
        name=row["name"],
        capacity=row["capacity_cfs"] * CFS_TO_ACRE_FEET_PER_DAY,
        capacity_irrigation=row["capacity_irr_cfs"] * CFS_TO_ACRE_FEET_PER_DAY,
        wafr_sources=split_multivalues(wafrsource),
        irrigation_days=irrigation_days,
    )


def load_bottlenecks(path_to_bottleneck_csv, irrigation_days=None):
    """Reads csv rows into a list of bottleneck objects.

    Args:
        path_to_bottleneck_csv: file location of the bottleneck csv
        irrigation_days: zero-indexed days of the water year that use the irrigation
            capacity. Defaults to `DEFAULT_IRRIGATION_DAYS`.

    Returns:
        list of bottleneck objects
    """
    if irrigation_days is None:
        irrigation_days = DEFAULT_IRRIGATION_DAYS

    df = pd.read_csv(path_to_bottleneck_csv)

    # drop empty rows
    df = df.dropna(subset=["bid"])

    return [bottleneck_from_row(row, irrigation_days) for _, row in df.iterrows()]


def unpack_bottlenecks(list_of_bottlenecks, irrigation_days=None):
    """Unpacks the bottleneck data from the list of bottlenecks (JSON INPUT).

    Args:
        list_of_bottlenecks: a list of bottleneck data structured as follows::

            [
                {
                    "bid": 62,
                    "name": "Planada Canal",
                    "capacity_cfs": 250,
                    "capacity_irr_cfs": 135,
                    "wafrsource": "MercedRiver,UCC,UCC_L,Fahren,Bear"
                },
                {
                    "bid": 63,
                    "name": "Fairfield Canal",
                    "capacity_cfs": 500,
                    "capacity_irr_cfs": 287,
                    "wafrsource": "MercedRiver,UCC,UCC_L,Fahren,Bear"
                }
            ]

        irrigation_days: zero-indexed days of the water year that use the irrigation
            capacity. Defaults to `DEFAULT_IRRIGATION_DAYS`.

    Returns:
        list of bottleneck objects
    """
    if irrigation_days is None:
        irrigation_days = DEFAULT_IRRIGATION_DAYS

    return [bottleneck_from_row(b, irrigation_days) for b in list_of_bottlenecks]
