"""
Base class used for all recharge types
"""

import warnings

import numpy as np


class BaseSite:
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
        """
        Used as the foundation for basins & farm classes.

        Args:
            grat_id: internal unique identifier for the site
            acres: polygon area in acres
            recharge_type: type of recharge at site.
            bottleneck_ids: list of the bottlenecks identifiers that restricts flow to this site
            wafr_sources_primary: list of sources that can supply water to this site (in-district)
            wafr_sources_secondary: list of sources that can supply water to this site (from other districts)
            precip_grid: Precipitation data GRID identifier
            **kwargs: Optional additional parameters
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
        self.used_volume = np.full(366, 0.0)
        self.daily_recharge_volumes = np.full(366, 0.0)
        self.precip = np.full(366, 0.0)
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
        """
        Calculates the site's precip volume by multiplying the area (acres) by the precipitation received at the grid
        identifier (decimal-feet). Output should be in acre-feet.

        Args:
            precip_dictionary: dictionary of water from precip grid for the water year

        Returns: array of the daily volume (acre-feet) the site received from precipitation

        """
        if self.precip_grid is not None and precip_dictionary is not None:
            if self.precip_grid not in precip_dictionary:
                warnings.warn(
                    f"Site {self.grat_id} has precip_grid {self.precip_grid} "
                    f"which is not found in the precip_dictionary",
                    stacklevel=2,
                )
                return

            precip_values = [g * self.acres for g in precip_dictionary[self.precip_grid]]
            for idx, v in enumerate(precip_values):
                self.precip[idx] = v
        return

    def set_daily_recharge(self, day: int, new_volume: float):
        """
        Update the daily recharge value by adding the new volume that goes to groundwater recharge

        Args:
            day: zero-index day of the water year
            new_volume: volume to add (acre-feet)

        """
        self.daily_recharge_volumes[day] += new_volume

    def set_wafr_log(self, wafr_source: str, volume: float):
        """
        Adds the WAFR source to the log for the site.
        Args:
            day: zero-index day of the water year
            wafr_source: name of the WAFR source that supplied water to this site
            volume: amount of water from source in acre-feet

        Returns:

        """
        # check if the wafr src is already in the dictionary, if so then just add the volume
        current_value = self.wafr_log.get(wafr_source, None)  # will return none if the key doesn't exist
        if current_value is None:
            self.wafr_log[wafr_source] = volume
        else:
            self.wafr_log[wafr_source] = current_value + volume  # add the new volume to the existing value

    def __repr__(self):
        return f"{self.__dict__}"
