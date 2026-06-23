"""Sensors for Haier TechLine S."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature

from .boiler import HaierBoilerAdapter
from .const import CODE_ANTIFREEZE, CODE_CURRENT_CH_TEMP, CODE_GAS_POWER
from .entity import HaierBoilerEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    adapters: list[HaierBoilerAdapter] = hass.data["haier_evo_boiler"][entry.entry_id]
    entities = []
    for adapter in adapters:
        entities.extend(
            [
                HaierBoilerNumericSensor(
                    adapter,
                    key="ch_temperature",
                    name="Температура теплоносителя",
                    code=CODE_CURRENT_CH_TEMP,
                    native_unit=UnitOfTemperature.CELSIUS,
                    device_class=SensorDeviceClass.TEMPERATURE,
                    icon="mdi:thermometer-water",
                    state_class=SensorStateClass.MEASUREMENT,
                ),
                HaierBoilerNumericSensor(
                    adapter,
                    key="burner_power",
                    name="Мощность горелки",
                    code=CODE_GAS_POWER,
                    native_unit=PERCENTAGE,
                    device_class=None,
                    icon="mdi:fire",
                    state_class=SensorStateClass.MEASUREMENT,
                ),
                HaierBoilerNumericSensor(
                    adapter,
                    key="antifreeze_level",
                    name="Ступень антизамерзания",
                    code=CODE_ANTIFREEZE,
                    native_unit=None,
                    device_class=None,
                    icon="mdi:snowflake-thermometer",
                    state_class=None,
                ),
            ]
        )
    async_add_entities(entities)


class HaierBoilerNumericSensor(HaierBoilerEntity, SensorEntity):
    """Numeric property exposed without inventing vendor semantics."""

    def __init__(
        self,
        adapter: HaierBoilerAdapter,
        key: str,
        name: str,
        code: str,
        native_unit,
        device_class,
        icon: str,
        state_class,
    ) -> None:
        super().__init__(adapter, key)
        self._attr_name = name
        self._attr_native_unit_of_measurement = native_unit
        self._attr_device_class = device_class
        self._attr_icon = icon
        self._attr_state_class = state_class
        self.code = code

    @property
    def native_value(self) -> float | int | None:
        value = self.adapter.as_float(self.code)
        if value is None:
            return None
        return int(value) if value.is_integer() else value
