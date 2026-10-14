"""Constructs site classes from the attributes of a sites layer (shapefile, geodatabase, geopackage or csv)."""

import logging
from numbers import Number
from pathlib import Path

import pandas as pd
from pyogrio.raw import read

from grat.loaders import helpers
from grat.model.sites import Basin, Farm

logger = logging.getLogger(__name__)


def read_attributes(path, layer=None, where=None):
    """Reads the attribute table of a sites layer into a dataframe. Geometry is not read.

    Args:
        path: csv, or any vector file GDAL can read (shapefile, file geodatabase folder, geopackage, geojson)
        layer: layer name, for files that hold more than one (e.g. a feature class in a file geodatabase)
        where: optional sql where clause, e.g. `"R_TYPE = 'OFR'"`. Not supported for csv.

    Returns:
        dataframe with one row per site
    """
    if Path(path).suffix.lower() == ".csv":
        if where is not None:
            raise ValueError("where is not supported for csv input")
        return pd.read_csv(path)

    meta, _, _, field_data = read(path, layer=layer, where=where, read_geometry=False)
    return pd.DataFrame(dict(zip(meta["fields"], field_data, strict=True)))


def load_sites(path, layer=None, where=None, ignore_fields=None, attribute_renamer=None):
    """Loads the crop/basin sites layer.

    Each row is turned into a dictionary with the keys being the attribute field names (or the attribute_renamer
    argument) and the values are the row values.

    Args:
        path: csv, or any vector file GDAL can read (shapefile, file geodatabase folder, geopackage, geojson)
        layer: layer name, for files that hold more than one (e.g. a feature class in a file geodatabase)
        where: optional sql where clause, e.g. `"R_TYPE = 'OFR'"`. Not supported for csv.
        ignore_fields: list of fields to ignore
        attribute_renamer: dictionary of attributes to rename to something different

    Returns:
        list of dictionaries
    """
    if ignore_fields is None:
        ignore_fields = []
    if attribute_renamer is None:
        attribute_renamer = {}

    df = read_attributes(path, layer=layer, where=where)
    df = df.drop(columns=[f for f in ignore_fields if f in df.columns])
    df = df.astype(object).where(pd.notnull(df), None)
    logger.debug("Fields: %s", list(df.columns))
    logger.debug("Where: %s", where)

    sites = []
    for row in df.to_dict(orient="records"):
        # treat empty or whitespace-only strings as None
        values = {k: None if isinstance(v, str) and not v.strip() else v for k, v in row.items()}
        sites.append(helpers.rename_dictionary_keys(values, attribute_renamer))

    return sites


def parse_compatible_sources(compatible_sources):
    """Split WAFRSOURCE string (comma-delimited) into a list.

    Args:
        compatible_sources: string

    Returns:
        list of WAFR source names
    """
    return helpers.split_multivalues(compatible_sources)


def parse_bottleneck_ids(bottleneck_id_string):
    """Split string (comma-delimited) into a list of integers.

    Args:
        bottleneck_id_string: string, or a number when the field holds a single id

    Returns:
        list of bottleneck ids, or None when the string is empty
    """
    if bottleneck_id_string is None:
        return None
    if isinstance(bottleneck_id_string, Number):
        return [int(bottleneck_id_string)]
    return [int(x) for x in helpers.split_multivalues(bottleneck_id_string)] or None


def build_sites(sites_dictionary_list):
    """Takes a list of input dictionaries and creates the OFR + Basin + other object types.

    Args:
        sites_dictionary_list: list of site attribute dictionaries, keyed by `Basin` and `Farm` argument names

    Returns:
        list of site objects
    """
    sites = []
    for p in sites_dictionary_list:
        p = dict(p)  # leave the caller's dictionary unchanged
        region_number = p.get("region_number")
        if isinstance(region_number, Number) and region_number % 1 == 0:
            p["region_number"] = str(int(region_number))

        # split multiple wafr sources string into list
        if p.get("wafr_sources_primary") is None and "wafr_sources" in p:
            p["wafr_sources_primary"] = p["wafr_sources"]
        else:
            p["wafr_sources_primary"] = parse_compatible_sources(p.get("wafr_sources_primary"))
        p["wafr_sources_secondary"] = parse_compatible_sources(p.get("wafr_sources_secondary"))

        # split bottleneck id string into list
        p["bottleneck_ids"] = parse_bottleneck_ids(p.get("bottleneck_ids"))

        if p.get("recharge_type") == "OFR":
            sites.append(Farm(**p))
        elif p.get("recharge_type") == "Basin":
            sites.append(Basin(**p))
        elif p.get("recharge_type") is None and p.get("in_lieu_crop") is not None:
            il_only_site = Farm(**p)
            il_only_site.recharge_type = "OFR"
            sites.append(il_only_site)
        else:
            logger.debug("site: %s has unknown recharge type: %s", p.get("grat_id"), p.get("recharge_type"))

    return sites


def drop_invalid_sites(sites, valid_crop_list, valid_il_crop_list, valid_soil_types):
    """Drops sites if the crops types don't match the values in the crop compatibility calendar.

    Args:
        sites: list of sites object
        valid_crop_list: list of crop types from the crop compatibility calendar
        valid_il_crop_list: list of in-lieu crop types from the IL compatibility calendar
        valid_soil_types: list of soil classification types (also from the crop compatibility calendar)

    Returns:
        list of the sites that passed validation
    """
    passed_validation = []
    valid_crop_list_with_none = [*valid_crop_list, None]
    valid_il_crop_list_with_none = [*valid_il_crop_list, None]

    for site in sites:
        if site.recharge_type == "OFR" and site.crop is not None and site.soil_type not in valid_soil_types:
            logger.debug("Removing site: %s. Invalid soil type: %s", site.grat_id, site.soil_type)
        elif site.recharge_type == "OFR" and site.crop not in valid_crop_list_with_none:
            logger.debug("Removing site: %s. Invalid crop type: %s", site.grat_id, site.crop)
        elif site.recharge_type == "OFR" and site.in_lieu_crop not in valid_il_crop_list_with_none:
            logger.debug("Removing site: %s. Invalid in_lieu_crop: %s", site.grat_id, site.in_lieu_crop)
        elif site.recharge_type == "OFR" and site.in_lieu_crop is None and site.crop is None:
            logger.debug("Removing site: %s. crop and in_lieu_crop are both null", site.grat_id)
        else:
            passed_validation.append(site)
    return passed_validation
