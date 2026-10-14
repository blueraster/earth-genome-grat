"""Loads crop compatibility calendars from csvs."""

import copy
import json
from collections import defaultdict

import pandas as pd

from grat.model.constants import DAYS_PER_WATER_YEAR


def _read_daily_calendar(ccc_file, crop_column, key_column, key_as_str=False):
    """Reads a crop calendar csv into a nested dictionary of daily values.

    Args:
        ccc_file: path to a csv with one row per crop and key, and columns `dowy1` to `dowy366`.
            A calendar ending at `dowy365` repeats its last day as `dowy366`.
        crop_column: name of the crop column
        key_column: name of the column for the second level of the dictionary
        key_as_str: cast the key column to string, e.g. for numeric region codes

    Returns:
        dictionary of daily values, structured as `{crop: {key: [day values]}}`
    """
    df = pd.read_csv(ccc_file)

    # 365 day calendars repeat the last day for leap years
    last_day = f"dowy{DAYS_PER_WATER_YEAR}"
    if last_day not in df.columns:
        df = pd.concat([df, df[f"dowy{DAYS_PER_WATER_YEAR - 1}"].rename(last_day)], axis=1)

    dowy_column_names = [f"dowy{i}" for i in range(1, DAYS_PER_WATER_YEAR + 1)]
    combined = df[dowy_column_names].to_numpy().tolist()
    df = df.drop(columns=dowy_column_names).assign(combined=combined)
    if key_as_str:
        df[key_column] = df[key_column].astype(str)

    by_crop = (
        df.groupby(crop_column)[[key_column, "combined"]]
        .apply(lambda x: x.set_index(key_column).to_dict(orient="index"))
        .to_dict()
    )

    # keep just the combined list of daily values as the nested value
    return {crop: {key: v["combined"] for key, v in by_key.items()} for crop, by_key in by_crop.items()}


def get_crop_calendar(ccc_file):
    """Constructs the crop calendar data dictionary.

    The crop compatibility calendar (CCC) is an agronomic model that determines quantity and timing of water applied
    based on the weekly capacity of crops to receive water for or in excess of crop demand (evapotranspiration, ETc)
    for in lieu or direct on-farm recharge (OFR), respectively, while maintaining crop health. The CCC is applicable
    only to these two types of recharge and does not apply to canal seepage or basin recharge.
    For both in-lieu and on-farm recharge types, the output of the CCC is the maximum volume (ft) of water a field can
    receive for OFR that is spatially and temporally compatible with the season, cultural practices, SAGBI soil type,
    and crop type.

    Args:
        ccc_file: path to the crop compatibility calendar csv file

    Returns:
        Crop calendar dictionary, recording each crop's retention depth (feet) per SAGBI type::

            {"Alfalfa": {"Very Poor": [0, 0, 0.1, 0], "Poor": [0, 0, 0, 0]},
             "Corn": {"Very Poor": [0, 0, 0, 0], "Poor": [0, 0, 5, 0]}}
    """
    return _read_daily_calendar(ccc_file, crop_column="Crop", key_column="SAGBI")


def ccc_valid_crops(ccc_dictionary):
    """Return the crops present in the crop compatibility calendar.

    Args:
        ccc_dictionary: input crop compatibility dictionary (output from get_crop_calendar())

    Returns:
        list of crop types
    """
    return list(ccc_dictionary.keys())


def ccc_valid_soil_types(ccc_dictionary):
    """Return a list of the soil types (SAGBI classification) found in the crop compatibility calendar.

    Args:
        ccc_dictionary: input crop compatibility dictionary (output from get_crop_calendar())

    Returns:
        list of soil types
    """
    return list({soil_type for soil_types in ccc_dictionary.values() for soil_type in soil_types})


def get_il_crop_calendar(ccc_file):
    """Constructs the in-lieu crop calendar data dictionary.

    Args:
        ccc_file: path to the in-lieu crop compatibility calendar csv file

    Returns:
        Crop calendar dictionary, each crop's retention depth (feet) per climate region::

            {"Alfalfa": {"8": [0, 0, 0.1, 0], "12": [0, 0, 0, 0]},
             "Corn": {"8": [0, 0, 0, 0], "10": [0, 0, 5, 0]}}
    """
    return _read_daily_calendar(ccc_file, crop_column="crop", key_column="region", key_as_str=True)


def load_in_lieu_climate_multiplier(path_to_ratio_file: str, scenario: str = "T0") -> pd.DataFrame:
    """Load the in-lieu climate multiplier file.

    Args:
        path_to_ratio_file: path to the csv file
        scenario: name of the scenario to load

    Returns:
        dataframe with columns: Crop, Region, MonthlyMultiplier (12 values, January first)

    Raises:
        ValueError: the scenario is not a column in the multiplier file.
    """
    df = pd.read_csv(path_to_ratio_file).rename(columns=str.upper)
    column_names = df.columns.tolist()

    df = df.rename(columns={"MONTH": "Month", "SR": "Region", "CROP_GRAT_IL": "Crop"}).drop_duplicates()

    scenario = scenario.upper()
    if scenario not in column_names:
        raise ValueError(f"Scenario {scenario} not found in the in-lieu multiplier file")

    # the month column is the calendar month, so sorting puts the multipliers January first,
    # the order multiply_by_monthly_factor expects
    df = df.sort_values(by=["Month"])[["Crop", "Region", "Month", scenario]]

    # group by rows to cast the month and scenario columns as lists
    df = df.groupby(["Crop", "Region"]).agg(tuple).map(list).reset_index()
    df["MonthlyMultiplier"] = df[scenario]

    return df[["Crop", "Region", "MonthlyMultiplier"]]


def ccc_dict_to_df(ccc_dictionary: dict) -> pd.DataFrame:
    """Convert the IL crop compatibility calendar dictionary to a dataframe.

    Args:
        ccc_dictionary: input IL crop compatibility dictionary (output from get_il_crop_calendar())

    Returns:
        dataframe with columns: Crop, Region, depth
    """
    return pd.DataFrame(
        [
            {"Crop": crop, "Region": region, "depth": depth}
            for crop, by_region in ccc_dictionary.items()
            for region, depth in by_region.items()
        ]
    )


def multiply_by_monthly_factor(daily_values, monthly_factors):
    """Multiply daily values by monthly factors.

    Args:
        daily_values: array of daily values for the water year
        monthly_factors: array of 12 monthly factors, January first

    Returns:
        array of daily values multiplied by monthly factors

    Raises:
        ValueError: there are not 365 or 366 daily values, or not 12 monthly factors.
    """
    list_of_values = list(daily_values)
    list_of_monthly_factors = list(monthly_factors)

    if len(list_of_values) not in (365, 366):
        raise ValueError("Length of daily values must be 365 or 366")

    if len(list_of_monthly_factors) != 12:
        raise ValueError("Length of monthly multipliers must be 12")

    # month lengths in water year order; February is never a leap month, and September
    # carries an extra day so the months cover a 366 day array
    month_lengths = {10: 31, 11: 30, 12: 31, 1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 31}

    result_array = []
    start_day = 0
    for month, num_days in month_lengths.items():
        monthly_multiplier = list_of_monthly_factors[month - 1]
        result_array.extend(x * monthly_multiplier for x in list_of_values[start_day : start_day + num_days])
        start_day += num_days

    return result_array


def ccc_multiplier(ccc_df, multiplier_df):
    """Multiplies the depth by the monthly multiplier for the chosen scenario.

    Args:
        ccc_df: in-lieu crop compatibility calendar dataframe
        multiplier_df: multiplier dataframe

    Returns:
        the joined dataframe, with the multiplied daily values in a `depth_factor` column
    """
    # set region columns to string to simplify the joins
    ccc_df = ccc_df.assign(Region=ccc_df["Region"].astype(str))
    multiplier_df = multiplier_df.assign(Region=multiplier_df["Region"].astype(str))

    ccc_df_multi = ccc_df.merge(multiplier_df, how="right", on=["Crop", "Region"])

    # drop the rows that have NaN values for the depth column (these are crops that are not in the crop calendar)
    ccc_df_multi = ccc_df_multi.dropna(subset=["depth"])

    ccc_df_multi["depth_factor"] = ccc_df_multi.apply(
        lambda x: multiply_by_monthly_factor(x["depth"], x["MonthlyMultiplier"]), axis=1
    )

    return ccc_df_multi


def in_lieu_crop_calendar_multiplier_dict(ccc_df_multi) -> dict:
    """Converts the dataframe into a nested dictionary.

    Args:
        ccc_df_multi: dataframe with columns: Crop, Region, depth_factor

    Returns:
        nested dictionary with keys: Crop, Region
    """
    d = defaultdict(dict)
    for _, row in ccc_df_multi.iterrows():
        d[row["Crop"]][row["Region"]] = row["depth_factor"]

    return json.loads(json.dumps(d))  # convert to plain dicts of plain floats


def multiply_crop_calendar(il_ccc, multiplier_df):
    """Multiply the crop calendar by the monthly factor for the chosen scenario.

    Args:
        il_ccc: crop calendar dictionary
        multiplier_df: multiplier dataframe

    Returns:
        crop calendar dictionary with the depth values multiplied by the monthly multipliers
    """
    il_df_multi = ccc_multiplier(ccc_dict_to_df(il_ccc), multiplier_df)
    return in_lieu_crop_calendar_multiplier_dict(il_df_multi)


def add_mlrp_to_ccc(ccc_dict, mlrp_crop_name="MLRP"):
    """Add the MLRP crop type to the crop calendar dictionary by cloning the Fallow crop type.

    Args:
        ccc_dict: crop calendar dictionary
        mlrp_crop_name: name of the MLRP crop

    Returns:
        crop calendar dictionary with the MLRP crop added

    Raises:
        KeyError: the crop calendar has no Fallow crop type.
    """
    fallow = ccc_dict.get("Fallow")
    if fallow is None:
        raise KeyError("Fallow crop type not found in the crop calendar dictionary")

    ccc_dict[mlrp_crop_name] = copy.deepcopy(fallow)

    return ccc_dict
