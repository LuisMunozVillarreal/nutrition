"""units module."""

from pint import UnitRegistry

UREG: UnitRegistry = UnitRegistry()

# Weight
UNIT_MILLIGRAM = "mg"
UNIT_GRAM = "g"
UNIT_KILOGRAM = "kg"
# - Imperial
UNIT_OUNCE = "oz"
UNIT_POUND = "lb"

# Volume
UNIT_LITRE = "l"
UNIT_CENTILITRE = "cl"
UNIT_MILLILITRE = "ml"
# - Imperial
UNIT_CUP = "c"
UNIT_FLUID_OUNCE = "floz"
UNIT_TEASPOON = "tsp"
UNIT_TABLESPOON = "tbsp"
UNIT_PINT = "pt"

# Other
UNIT_UNIT = "unit"
UNIT_SERVING = "serving"
UNIT_CONTAINER = "container"

UNIT_CHOICES = (
    #
    # Weight
    (UNIT_MILLIGRAM, "milligram(s)"),
    (UNIT_GRAM, "gram(s)"),
    (UNIT_KILOGRAM, "kilogram(s)"),
    # - Imperial
    (UNIT_OUNCE, "ounce(s)"),
    (UNIT_POUND, "pound(s)"),
    #
    # Volume
    (UNIT_MILLILITRE, "millilitre(s)"),
    (UNIT_CENTILITRE, "centilitre(s)"),
    (UNIT_LITRE, "litre(s)"),
    # - Imperial
    (UNIT_CUP, "cup(s)"),
    (UNIT_FLUID_OUNCE, "fluid ounce(s)"),
    (UNIT_TABLESPOON, "tablespoon(s)"),
    (UNIT_TEASPOON, "teaspoon(s)"),
    (UNIT_PINT, "pint(s)"),
    #
    # Other
    (UNIT_UNIT, "unit(s)"),
    (UNIT_SERVING, "serving(s)"),
    (UNIT_CONTAINER, "container(s)"),
)
