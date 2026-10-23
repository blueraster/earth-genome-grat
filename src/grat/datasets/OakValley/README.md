# Oak Valley sample dataset

**Version date:** 2026-10-07

This is synthetic data for a fictional water district called Oak Valley. It is not real
hydrologic, crop or parcel data. It is included so GRAT can be tried out and tested
without a real district's inputs.

## Files

| File | Contents |
| --- | --- |
| `oakvalley.*` | Shapefile of the district's sites, 685 features (crop, soil, conveyance, bottleneck and WAFR source attributes). NAD 1983 (2011) California Teale Albers. |
| `canals.csv` | Canal sites: district, volume, seepage, WAFR source and groundwater basin. |
| `bottlenecks.csv` | Conveyance bottlenecks: capacity (cfs) and the WAFR sources they carry. |
| `WAFR_optimistic.csv` | Daily water available for recharge by source, optimistic scenario, water years 1969–2018 (1968-10-01 to 2018-09-30). |
| `WAFR_pessimistic.csv` | Daily water available for recharge by source, pessimistic scenario, same period. |
| `Precip_optimistic.csv` | Daily precipitation (mm) by precipitation grid (`pid_<PRECIP_IDX>`), optimistic scenario, same period. `WaterYear` is the water year and `Day` is the day of the water year, as in the WAFR files. |
| `Precip_pessimistic.csv` | Daily precipitation (mm) by precipitation grid, pessimistic scenario, same period and layout. |
| `CCC_ofr.csv` | Crop calendar for on-farm recharge: accepted application by crop and SAGBI class, per day of water year. |
| `CCC_inlieu.csv` | Crop calendar for in-lieu recharge, by crop and region, per day of water year. |
| `CCC_inlieu_multiplier.csv` | In-lieu multipliers by crop, region and month. |
