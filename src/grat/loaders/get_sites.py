"""Constructs site classes from attributes in a file geodatabase layer."""

import logging

import arcpy

from grat.loaders import helpers
from grat.model.sites import Basin, Farm

logger = logging.getLogger(__name__)


def get_sites_from_gdb(fc, query="1-1", ignore_fields=None, attribute_renamer=None):
    """Loads crop/basin layer from local file geodatabase using arcpy.

    Each row is turned into a dictionary with the keys being the attribute field names (or the attribute_renamer
    argument) and the values are the row values.

    Args:
        fc: input feature class
        query: optional sql query to use in the search cursor
        ignore_fields: list of fields to ignore
        attribute_renamer: dictionary of attributes to rename to something different

    Returns:
        list of dictionaries
    """
    if ignore_fields is None:
        ignore_fields = []
    if attribute_renamer is None:
        attribute_renamer = {}

    fields = [f.name for f in arcpy.ListFields(fc) if f.name not in ignore_fields]
    sites = []
    logger.debug("Fields: %s", fields)
    logger.debug("Query: %s", query)
    with arcpy.da.SearchCursor(fc, fields, where_clause=query) as cursor:
        for row in cursor:
            values = [None if r == " " else r for r in row]  # treat empty strings as None
            zipped_row = dict(zip(fields, values, strict=True))
            sites.append(helpers.rename_dictionary_keys(zipped_row, attribute_renamer))

    return sites


def parse_compatible_sources(compatible_sources):
    """Split WAFRSOURCE string (comma delimited) into a list.

    Args:
        compatible_sources: string

    Returns:
        list of WAFR source names
    """
    if compatible_sources is None:
        return []
    return [x.strip() for x in compatible_sources.split(",")]


def parse_bottleneck_ids(bottleneck_id_string):
    """Split string (comma delimited) into a list of integers.

    Args:
        bottleneck_id_string: string

    Returns:
        list of bottleneck ids, or None when the string is empty
    """
    if bottleneck_id_string is None or bottleneck_id_string.strip() == "":
        return None
    return [int(x.strip()) for x in bottleneck_id_string.split(",")]


def build_sites(sites_dictionary_list):
    """Takes a list of input dictionaries and creates the OFR + Basin + other object types.

    Args:
        sites_dictionary_list: list of site attribute dictionaries, keyed by `Basin` and `Farm` argument names

    Returns:
        list of site objects
    """
    sites = []
    for p in sites_dictionary_list:
        # split multiple wafr sources string into list
        p["wafr_sources_primary"] = parse_compatible_sources(p.get("wafr_sources_primary", []))
        p["wafr_sources_secondary"] = parse_compatible_sources(p.get("wafr_sources_secondary", []))

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
        if site.recharge_type == "OFR" and site.soil_type not in valid_soil_types:
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
