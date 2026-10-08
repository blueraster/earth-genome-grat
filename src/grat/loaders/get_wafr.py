"""Loads the water available for recharge input (csv) into a dictionary."""

import numpy as np
import pandas as pd


def load_wafr_csv(file, offset_years: int = 0):
    """Loads a transposed WAFR csv into a nested dictionary of daily values by water year + source.

    Years are the keys at the first level and water source names the keys at the second level, with the values being
    a list of daily water available for recharge in acre feet. Index position 0 represents start of the water year
    (October 1st).

    The csv has one column per year + source: the first row holds the water year (only on the first column of each
    year), the second row the source name, and every row after that one day of the water year.

    Example output: `{1981: {"source A": [0, 1.2, ...], "source B": [1.2, 4, 5, ...]}, 1982: {...}, ...}`

    Args:
        file: path to the WAFR csv file
        offset_years: number of years to adjust to match the precip input

    Returns:
        nested dictionary with WAFR organized by year + source
    """
    # set header to none in order to read in the oddly formatted header
    df = pd.read_csv(file, header=None)

    # transpose, then promote the first row to the column names
    df_t = df.transpose()
    df_h = df_t.rename(columns=df_t.iloc[0]).drop(df_t.index[0])
    df_h = df_h.rename(columns={np.nan: "source"})  # the source row has no label (NaN)

    # use forward fill to populate the missing values for the water year
    df_h["Water Year"] = df_h["Water Year"].ffill()

    # every other column is a day of the water year
    day_columns = [c for c in df_h.columns if c not in ["Water Year", "source"]]
    df_f = pd.DataFrame(
        {
            "Water Year": pd.to_numeric(df_h["Water Year"]) + offset_years,
            "source": df_h["source"],
            "AF": df_h[day_columns].astype(float).to_numpy().tolist(),
        }
    )

    # pivot wide so each year is a column, then convert to a dictionary
    return pd.pivot(df_f, columns="Water Year", values="AF", index="source").to_dict()


def load_wafr(file, offset_years=0):
    """Loads a WAFR csv with one row per day into a nested dictionary of daily values by water year + source.

    Example output: `{1981: {"source A": [0, 1.2, ...], "source B": [1.2, 4, 5, ...]}, 1982: {...}, ...}`

    Args:
        file: path to the input csv. Expects `Year` and `Day` columns, plus one column of daily
            water available for recharge (acre-feet) per source.
        offset_years: number of years to adjust to match the precip input

    Returns:
        nested dictionary with WAFR organized by year + source
    """
    df = pd.read_csv(file)
    df["WaterYear"] = df["Year"] + offset_years

    # convert wide dataframe to long, one row per year + day + source
    m = pd.melt(df.drop(columns=["Year"]), id_vars=["WaterYear", "Day"])

    # group by to aggregate the daily values into a list
    m2 = m.drop(columns=["Day"]).groupby(["WaterYear", "variable"]).agg(tuple).map(list).reset_index()

    return pd.pivot(m2, columns="WaterYear", values="value", index="variable").to_dict()
