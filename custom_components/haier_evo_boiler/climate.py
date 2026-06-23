"""Heating control for Haier TechLine S."""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

from .boiler import HaierBoilerAdapter
from .const import (
    CODE_CURRENT_CH_TEMP,
    CODE_FLAME,
    CODE_GAS_POWER,
    CODE_HEATING,
    CODE_POWER,
    CODE_TARGET_CH_TEMP,
)
from .entity import HaierBoilerEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    adapters: list[HaierBoilerAdapter] = hass.data["haier_evo_boiler"][entry.entry_id]
    async_add_entities([HaierBoilerClimate(adapter) for adapter in adapters])


class HaierBoilerClimate(HaierBoilerEntity, ClimateEntity):
    """Control the central-heating circuit."""

    _attr_name = "Отопление"
    _attr_icon = "mdi:radiator"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, adapter: HaierBoilerAdapter) -> None:
        super().__init__(adapter, "heating")
        minimum, maximum, step = adapter.range_for(
            CODE_TARGET_CH_TEMP, 20, 85, 1
        )
        # TechLine S firmware does not accept a CH setpoint below 35 °C.
        self._attr_min_temp = max(35.0, minimum)
        self._attr_max_temp = maximum
        self._attr_target_temperature_step = step

    @property
    def current_temperature(self) -> float | None:
        return self.adapter.as_float(CODE_CURRENT_CH_TEMP)

    @property
    def target_temperature(self) -> float | None:
        return self.adapter.as_float(CODE_TARGET_CH_TEMP)

    @property
    def hvac_mode(self) -> HVACMode:
        if self.adapter.as_bool(CODE_POWER) and self.adapter.as_bool(CODE_HEATING):
            return HVACMode.HEAT
        return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if self.adapter.as_bool(CODE_FLAME) or (
            self.adapter.as_float(CODE_GAS_POWER, 0) or 0
        ) > 0:
            return HVACAction.HEATING
        return HVACAction.IDLE

    async def async_set_temperature(self, **kwargs) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        temperature = max(self.min_temp, min(self.max_temp, float(temperature)))
        await self.hass.async_add_executor_job(
            self.adapter.send, CODE_TARGET_CH_TEMP, round(temperature)
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            # Disable the heating circuit, but do not hard-power-off the boiler.
            await self.hass.async_add_executor_job(
                self.adapter.send, CODE_HEATING, False
            )
            return
        if hvac_mode != HVACMode.HEAT:
            raise ValueError(f"Unsupported HVAC mode: {hvac_mode}")
        commands: list[tuple[str, bool]] = []
        if not self.adapter.as_bool(CODE_POWER):
            commands.append((CODE_POWER, True))
        commands.append((CODE_HEATING, True))
        await self.hass.async_add_executor_job(self.adapter.send_many, commands)

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
