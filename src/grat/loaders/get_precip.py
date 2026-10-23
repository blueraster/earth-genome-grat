"""Loads precipitation file (csv) into a dictionary."""

import pandas as pd

from grat.model.engine import timer_func

# millimetres of rain to feet
MM_TO_FEET = 0.00328084


@timer_func
def get_precip(input_precip_file, precip_coef: float = 1.0, offset_years: int = 0) -> dict:
    """Load precipitation data from a csv file and return values as a nested dictionary by water year + grid.

    Data structure: `{year: {grid: [depth, depth, depth, ...]}}`

    Args:
        input_precip_file: file path to the input precipitation file. Expects `WaterYear` and `Day`
            columns, plus one `pid_<grid>` column of daily rainfall (mm) per precipitation grid.
            A `Year` column is read as the water year when there is no `WaterYear` column.
        precip_coef: coefficient to multiply input file to modify rainfall totals in different runs
        offset_years: number of years to adjust to match the WAFR input

    Returns:
        dictionary with daily depth of rain (feet) grouped by year + grid code
    """
    # load csv and offset the water year (older files name it `Year`)
    df = pd.read_csv(input_precip_file)
    year_col = "WaterYear" if "WaterYear" in df.columns else "Year"
    df["WaterYear"] = df[year_col] + offset_years

    # the daily lists are built in row order
    df = df.sort_values(["WaterYear", "Day"])

    # convert wide dataframe to long
    m = pd.melt(df, id_vars=["WaterYear", "Day"], value_vars=[col for col in df.columns if col.startswith("pid_")])

    # unit conversion (mm to feet) * coefficient
    m["precip_ft"] = m["value"] * MM_TO_FEET * precip_coef

    # group by to aggregate the daily values into a list
    m2 = m.drop(columns=["Day", "value"]).groupby(["WaterYear", "variable"]).agg(tuple).map(list).reset_index()

    # "pid_1102" -> 1102
    m2["pid"] = m2["variable"].str.split("_").str[1].astype("int")

    # pivot again and return as dictionary
    return pd.pivot(m2, columns="WaterYear", values="precip_ft", index="pid").to_dict()
