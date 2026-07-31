"""units module."""

from pint import UnitRegistry

UREG: UnitRegistry = UnitRegistry(None)
UREG.define("gram = [mass] = g")
UREG.define("milligram = 0.001 gram = mg")
UREG.define("kilogram = 1000 gram = kg")
UREG.define("ounce = 28.349523125 gram = oz")
UREG.define("pound = 16 ounce = lb")
UREG.define("liter = [volume] = l")
UREG.define("milliliter = 0.001 liter = ml")
UREG.define("centiliter = 0.01 liter = cl")
UREG.define("fluid_ounce = 29.573529562499985 milliliter = floz")
UREG.define("cup = 8 fluid_ounce = c")
UREG.define("teaspoon = 4.92892159375 milliliter = tsp")
UREG.define("tablespoon = 3 teaspoon = tbsp")
UREG.define("pint = 16 fluid_ounce = pt")

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

MASS_UNITS = frozenset(
    {UNIT_MILLIGRAM, UNIT_GRAM, UNIT_KILOGRAM, UNIT_OUNCE, UNIT_POUND}
)
VOLUME_UNITS = frozenset(
    {
        UNIT_LITRE,
        UNIT_CENTILITRE,
        UNIT_MILLILITRE,
        UNIT_CUP,
        UNIT_FLUID_OUNCE,
        UNIT_TEASPOON,
        UNIT_TABLESPOON,
        UNIT_PINT,
    }
)
CONTEXTUAL_UNITS = frozenset({UNIT_UNIT, UNIT_SERVING, UNIT_CONTAINER})


def units_are_compatible(first: str, second: str) -> bool:
    """Return whether two canonical units can be converted meaningfully.

    Concrete mass and volume units convert within their dimensions. Abstract
    units have no implicit density or item conversion factor, so only the
    exact same contextual unit is compatible.

    Args:
        first (str): First canonical unit value.
        second (str): Second canonical unit value.

    Returns:
        bool: Whether the units have compatible conversion semantics.
    """
    if first == second:
        return True
    return (first in MASS_UNITS and second in MASS_UNITS) or (
        first in VOLUME_UNITS and second in VOLUME_UNITS
    )


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
