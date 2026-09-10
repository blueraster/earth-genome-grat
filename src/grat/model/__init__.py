"""The GRAT recharge model.

Sites come in three kinds, all built on `base_site.BaseSite`: `canals.Canal`,
`basins.Basin` and `farms.Farm`. `bottlenecks.Bottleneck` caps delivery to the
sites behind it, `sorters` decides which sites are served first, `transfers`
caps how much water each district may transfer in, and `grat` drives the
allocation across days and years.
"""
