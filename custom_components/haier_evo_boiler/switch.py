"""Switches for Haier TechLine S."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .boiler import HaierBoilerAdapter
from .const import CODE_ECO, CODE_POWER
from .entity import HaierBoilerEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    adapters: list[HaierBoilerAdapter] = hass.data["haier_evo_boiler"][entry.entry_id]
    entities = []
    for adapter in adapters:
        entities.extend(
            [
                HaierBoilerSwitch(
                    adapter,
                    key="power",
                    name="Питание котла",
                    code=CODE_POWER,
                    icon="mdi:power",
                ),
                HaierBoilerSwitch(
                    adapter,
                    key="eco",
                    name="Eco",
                    code=CODE_ECO,
                    icon="mdi:leaf",
                ),
            ]
        )
    async_add_entities(entities)


class HaierBoilerSwitch(HaierBoilerEntity, SwitchEntity):
    """Raw Boolean boiler property represented as a switch."""

    def __init__(
        self,
        adapter: HaierBoilerAdapter,
        key: str,
        name: str,
        code: str,
        icon: str,
    ) -> None:
        super().__init__(adapter, key)
        self._attr_name = name
        self._attr_icon = icon
        self.code = code

    @property
    def is_on(self) -> bool:
        return self.adapter.as_bool(self.code)

    async def async_turn_on(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.adapter.send, self.code, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.adapter.send, self.code, False)
