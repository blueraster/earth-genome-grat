"""Loads the water available for recharge input (csv) into a dictionary."""

import pandas as pd


def load_wafr(file, offset_years=0):
    """Loads a WAFR csv with one row per day into a nested dictionary of daily values by water year + source.

    Example output: `{1981: {"source A": [0, 1.2, ...], "source B": [1.2, 4, 5, ...]}, 1982: {...}, ...}`

    Args:
        file: path to the input csv. Expects `WaterYear` and `Day` columns, plus one column of daily
            water available for recharge (acre-feet) per source.
        offset_years: number of years to adjust to match the precip input

    Returns:
        nested dictionary with WAFR organized by water year + source
    """
    df = pd.read_csv(file)
    df["WaterYear"] = df["WaterYear"] + offset_years

    # convert wide dataframe to long, one row per year + day + source
    m = pd.melt(df, id_vars=["WaterYear", "Day"])

    # group by to aggregate the daily values into a list
    m2 = m.drop(columns=["Day"]).groupby(["WaterYear", "variable"]).agg(tuple).map(list).reset_index()

    return pd.pivot(m2, columns="WaterYear", values="value", index="variable").to_dict()
