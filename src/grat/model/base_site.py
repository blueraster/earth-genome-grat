"""Base class used for all recharge types."""

import logging

import numpy as np

from .constants import DAYS_PER_WATER_YEAR

logger = logging.getLogger(__name__)


class BaseSite:
    """Foundation for every recharge site (basins, canals and farms).

    A site holds the static attributes that describe a parcel (area, location,
    which WAFR sources can reach it) plus the per-day arrays that the model
    fills in as it allocates water across the water year. All volumes are in
    acre-feet unless stated otherwise, and all day indexes are zero-indexed
    days of the water year.

    Attributes:
        wafr_sources: combined primary and secondary WAFR source names, built at
            construction time from `wafr_sources_primary` + `wafr_sources_secondary`.
        used_volume: daily volume applied to the site (acre-feet), one entry per day.
            Populated for basins and canals only — `Farm` overrides
            `set_used_volume` and records into its own arrays, leaving this at zero.
        daily_recharge_volumes: daily volume that reached groundwater (acre-feet).
            Populated for basins and canals only — `Farm` overrides
            `set_daily_recharge` and records into its own arrays, leaving this at
            zero.
        precip: daily volume received as precipitation (acre-feet), populated by
            `calc_precip`.
        wafr_log: running total of volume supplied (acre-feet), keyed by WAFR
            source name.
        sort_index: position of the site in the processing order, assigned by
            `sorters.sort_sites`. `None` until the site has been sorted.
    """

    def __init__(
        self,
        grat_id,
        acres=0,
        recharge_type=None,
        bottleneck_ids=None,
        wafr_sources_primary=None,
        wafr_sources_secondary=None,
        precip_grid=0,
        district=None,
        subbasin=None,
        watershed=None,
        agency=None,
        nondistrict=None,
        inbasinret=None,
        dac=None,
        gsc=None,
        streamretu=None,
        subsidence=None,
        shorebird=None,
        rsi=None,
        groundwater_change=None,
        rma=None,
        region_number=None,
        mlrp_score=None,
        projects=None,
        sustainability_zone=None,
        depth_to_groundwater=None,
        **kwargs,
    ):
        """Build a site.

        Args:
            grat_id: internal unique identifier for the site.
            acres: polygon area in acres.
            recharge_type: type of recharge at the site, e.g. "Canal", "Basin" or "OFR".
                Determines which sublist the site is grouped into by
                `sorters.group_sites_by_recharge_type`.
            bottleneck_ids: identifiers of the bottlenecks that restrict flow to this
                site. A single identifier is accepted and wrapped in a list.
            wafr_sources_primary: names of the sources that can supply water to this
                site from within its own district.
            wafr_sources_secondary: names of the sources that can supply water to this
                site from other districts. Used only after the primary sources are spent.
            precip_grid: identifier of the precipitation grid cell covering this site.
                Used as the lookup key into the precipitation dictionary passed to
                `calc_precip`.
            district: district the site belongs to. Transfer limits are tracked per
                district, so this is the key used to charge a transfer against a budget.
            agency: agency the site belongs to, referred to as the GSA elsewhere in
                the model. Used by `sorters.mlrp_sorter` to pool acreage per agency.
            rsi: RSI score. Higher scores are processed first by the default sort rule.
            rma: RMA rank. Lower ranks are processed first by the "RMA" sort rule.
            groundwater_change: change in groundwater level. Lower (more negative)
                values are prioritised when ordering in-lieu sites.
            region_number: climate region number. Used as the crop calendar lookup key
                for in-lieu recharge, where accepted rates vary by region.
            mlrp_score: MLRP rank. Lower ranks are converted to the "MLRP" crop first
                by `sorters.mlrp_sorter`.
            sustainability_zone: sustainability zone name. Coerced to a string when set.
            subbasin: groundwater subbasin containing the site.
            watershed: watershed containing the site.
            depth_to_groundwater: depth to groundwater at the site.
            projects: projects associated with the site.
            nondistrict: site attribute carried through the model. Meaning not
                documented in this codebase.
            inbasinret: site attribute carried through the model. Meaning not
                documented in this codebase.
            dac: site attribute carried through the model. Meaning not documented in
                this codebase.
            gsc: site attribute carried through the model. Meaning not documented in
                this codebase.
            streamretu: site attribute carried through the model. Meaning not
                documented in this codebase.
            subsidence: site attribute carried through the model. Meaning not
                documented in this codebase.
            shorebird: site attribute carried through the model. Meaning not
                documented in this codebase.
            **kwargs: additional site attributes. `wafr_sources` is accepted here as an
                alias for `wafr_sources_primary`; anything else is ignored.

        Note:
            `subbasin`, `watershed`, `depth_to_groundwater`, `projects`, `nondistrict`,
            `inbasinret`, `dac`, `gsc`, `streamretu`, `subsidence`, `shorebird` and
            `sustainability_zone` are stored on the site but are not read by any model
            calculation. They are carried through so the reporting layer can group and
            filter results.
        """
        # site info
        self.grat_id = grat_id
        self.acres = acres
        self.recharge_type = recharge_type
        if wafr_sources_primary is None and "wafr_sources" in kwargs:
            wafr_sources_primary = kwargs["wafr_sources"]
        self.wafr_sources_primary = wafr_sources_primary
        self.wafr_sources_secondary = wafr_sources_secondary

        if bottleneck_ids is not None and not isinstance(bottleneck_ids, (list, tuple, set)):
            bottleneck_ids = [bottleneck_ids]
        self.bottleneck_ids = bottleneck_ids

        # init empty default values
        self.used_volume = np.full(DAYS_PER_WATER_YEAR, 0.0)
        self.daily_recharge_volumes = np.full(DAYS_PER_WATER_YEAR, 0.0)
        self.precip = np.full(DAYS_PER_WATER_YEAR, 0.0)
        self.wafr_log = {}

        # sort index (order sites are processed)
        self.precip_grid = precip_grid
        self.sort_index = None
        self.rsi = rsi
        self.subbasin = subbasin
        self.district = district
        self.watershed = watershed
        self.agency = agency
        self.nondistrict = nondistrict
        self.inbasinret = inbasinret
        self.dac = dac
        self.gsc = gsc
        self.streamretu = streamretu
        self.subsidence = subsidence
        self.shorebird = shorebird
        self.rma = rma
        self.groundwater_change = groundwater_change
        self.region_number = region_number  # climate region number
        self.sustainability_zone = None if sustainability_zone is None else str(sustainability_zone)
        if self.wafr_sources_primary is None:
            self.wafr_sources_primary = []
        if self.wafr_sources_secondary is None:
            self.wafr_sources_secondary = []

        self.wafr_sources = self.wafr_sources_primary + self.wafr_sources_secondary

        self.mlrp_score = mlrp_score
        self.projects = projects
        self.depth_to_groundwater = depth_to_groundwater

    def calc_precip(self, precip_dictionary: dict):
        """Populate the site's daily precipitation volumes.

        Multiplies the site area (acres) by the depth received at the site's
        precipitation grid cell (decimal-feet) to give a volume in acre-feet, and
        writes the result into `self.precip`.

        Does nothing if the site has no precipitation grid or no dictionary is
        supplied. Logs a warning and leaves `self.precip` untouched if the site's
        grid is missing from the dictionary.

        Args:
            precip_dictionary: daily precipitation depth (decimal-feet) for the water
                year, keyed by precipitation grid identifier.
        """
        if self.precip_grid is not None and precip_dictionary is not None:
            if self.precip_grid not in precip_dictionary:
                logger.warning(
                    "Site %s has precip_grid %s which is not found in the precip_dictionary",
                    self.grat_id,
                    self.precip_grid,
                )
                return

            precip_values = [g * self.acres for g in precip_dictionary[self.precip_grid]]
            for idx, v in enumerate(precip_values):
                self.precip[idx] = v
        return

    def set_daily_recharge(self, day: int, new_volume: float):
        """Add volume to the site's groundwater recharge for a day.

        Args:
            day: zero-indexed day of the water year.
            new_volume: volume to add (acre-feet).
        """
        self.daily_recharge_volumes[day] += new_volume

    def set_wafr_log(self, wafr_source: str, volume: float):
        """Record volume supplied to this site by a WAFR source.

        Accumulates across the whole water year rather than per day: repeated calls
        for the same source add to its running total.

        Args:
            wafr_source: name of the WAFR source that supplied water to this site.
            volume: volume supplied by that source (acre-feet).
        """
        # check if the wafr src is already in the dictionary, if so then just add the volume
        current_value = self.wafr_log.get(wafr_source, None)  # will return none if the key doesn't exist
        if current_value is None:
            self.wafr_log[wafr_source] = volume
        else:
            self.wafr_log[wafr_source] = current_value + volume  # add the new volume to the existing value

    def __repr__(self):
        """Return every attribute of the site, including the full daily arrays."""
        return f"{self.__dict__}"
