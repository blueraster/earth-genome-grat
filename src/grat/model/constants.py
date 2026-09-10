"""Shared constants for the GRAT model."""

# Length of every daily array in the model.
# Arrays are always sized for a leap year so that the same code runs a 365- or
# 366-day water year without reallocation. The actual length of a given year is
# taken from the WAFR series at run time, so the trailing entry is simply unused
# in a non-leap year.
DAYS_PER_WATER_YEAR = 366

# Volume delivered in one day by a sustained flow of one cubic-foot per second.
# One cubic-foot per second for 24 hours is 86,400 cubic feet, which is
# 86,400 / 43,560 = 1.9835 acre-feet.
CFS_TO_ACRE_FEET_PER_DAY = 1.983

# Turnout flow rate (cubic-feet per second) assumed for a farm that has none.
DEFAULT_CFS_LIMIT = 15

# Water years `start_analysis` runs when the caller does not choose a span.
DEFAULT_YEARS = range(2001, 2100)
