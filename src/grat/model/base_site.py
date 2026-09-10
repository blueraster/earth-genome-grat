"""
Base class used for all recharge types
"""

import warnings

import numpy as np


class BaseSite:
    def __init__(
        self,
        gratID,
        acres=0,
        rechargeType=None,
        bottleneckIDs=None,
        wafrSourcesPrimary=None,
        wafrSourcesSecondary=None,
        precipGrid=0,
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
        groundwaterChange=None,
        rma=None,
        regionNumber=None,
        mlrpScore=None,
        projects=None,
        sustainabilityZone=None,
        depthToGroundwater=None,
        **kwargs,
    ):
        """
        Used as the foundation for basins & farm classes.

        Args:
            gratID: internal unique identifier for the site
            acres: polygon area in acres
            rechargeType: type of recharge at site.
            bottleneckIDs: list of the bottlenecks identifiers that restricts flow to this site
            wafrSourcesPrimary: list of sources that can supply water to this site (in-district)
            wafrSourcesSecondary: list of sources that can supply water to this site (from other districts)
            precipGrid: Precipitation data GRID identifier
            **kwargs: Optional additional parameters
        """

        # site info
        self.gratID = gratID
        self.acres = acres
        self.rechargeType = rechargeType
        if wafrSourcesPrimary is None and "wafrSources" in kwargs:
            wafrSourcesPrimary = kwargs["wafrSources"]
        self.wafrSourcesPrimary = wafrSourcesPrimary
        self.wafrSourcesSecondary = wafrSourcesSecondary

        if bottleneckIDs is not None and not isinstance(bottleneckIDs, (list, tuple, set)):
            bottleneckIDs = [bottleneckIDs]
        self.bottleneckIDs = bottleneckIDs

        # init empty default values
        self.usedVolume = np.full(366, 0.0)
        self.dailyRechargeVolumes = np.full(366, 0.0)
        self.precip = np.full(366, 0.0)
        self.wafrLog = {}

        # sort index (order sites are processed)
        self.precipGrid = precipGrid
        self.sortIndex = None
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
        self.groundwaterChange = groundwaterChange
        self.regionNumber = regionNumber  # climate region number
        self.sustainabilityZone = None if sustainabilityZone is None else str(sustainabilityZone)
        if self.wafrSourcesPrimary is None:
            self.wafrSourcesPrimary = []
        if self.wafrSourcesSecondary is None:
            self.wafrSourcesSecondary = []

        self.wafrSources = self.wafrSourcesPrimary + self.wafrSourcesSecondary

        self.mlrpScore = mlrpScore
        self.projects = projects
        self.depthToGroundwater = depthToGroundwater

    def calc_precip(self, precipDictionary: dict):
        """
        Calculates the site's precip volume by multiplying the area (acres) by the precipitation received at the grid
        identifier (decimal-feet). Output should be in acre-feet.

        Args:
            precipDictionary: dictionary of water from precip grid for the water year

        Returns: array of the daily volume (acre-feet) the site received from precipitation

        """
        if self.precipGrid is not None and precipDictionary is not None:
            if self.precipGrid not in precipDictionary:
                warnings.warn(
                    f"Site {self.gratID} has precipGrid {self.precipGrid} which is not found in the precipDictionary",
                    stacklevel=2,
                )
                return

            precip_values = [g * self.acres for g in precipDictionary[self.precipGrid]]
            for idx, v in enumerate(precip_values):
                self.precip[idx] = v
        return

    def set_daily_recharge(self, day: int, newVolume: float):
        """
        Update the daily recharge value by adding the new volume that goes to groundwater recharge

        Args:
            day: zero-index day of the water year
            newVolume: volume to add (acre-feet)

        """
        self.dailyRechargeVolumes[day] += newVolume

    def set_wafr_log(self, wafrSource: str, volume: float):
        """
        Adds the WAFR source to the log for the site.
        Args:
            day: zero-index day of the water year
            wafrSource: name of the WAFR source that supplied water to this site
            volume: amount of water from source in acre-feet

        Returns:

        """
        # check if the wafr src is already in the dictionary, if so then just add the volume
        currentValue = self.wafrLog.get(wafrSource, None)  # will return none if the key doesn't exist
        if currentValue is None:
            self.wafrLog[wafrSource] = volume
        else:
            self.wafrLog[wafrSource] = currentValue + volume  # add the new volume to the existing value

    def __repr__(self):
        return f"{self.__dict__}"
