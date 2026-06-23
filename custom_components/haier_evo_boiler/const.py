"""Constants for Haier Evo Boiler companion integration."""

DOMAIN = "haier_evo_boiler"
SOURCE_DOMAIN = "haier_evo"

PLATFORMS = ["climate", "switch", "sensor", "binary_sensor"]

# Haier Evo property codes for TechLine S single-circuit boilers.
CODE_POWER = "101"
CODE_HEATING = "125"
CODE_TARGET_CH_TEMP = "7"
CODE_CURRENT_CH_TEMP = "5"
CODE_ECO = "142"
CODE_GAS_POWER = "31"
CODE_FLAME = "107"
CODE_ANTIFREEZE = "123"
CODE_SERVICE = "119"

REQUIRED_CODES = {
    CODE_POWER,
    CODE_HEATING,
    CODE_TARGET_CH_TEMP,
    CODE_CURRENT_CH_TEMP,
}
