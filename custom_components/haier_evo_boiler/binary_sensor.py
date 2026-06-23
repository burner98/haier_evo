"""Binary sensors for Haier TechLine S."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.entity import EntityCategory

from .boiler import HaierBoilerAdapter
from .const import CODE_FLAME, CODE_SERVICE
from .entity import HaierBoilerEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    adapters: list[HaierBoilerAdapter] = hass.data["haier_evo_boiler"][entry.entry_id]
    entities = []
    for adapter in adapters:
        entities.extend(
            [
                HaierBoilerBinarySensor(
                    adapter,
                    key="flame",
                    name="Пламя",
                    code=CODE_FLAME,
                    icon_on="mdi:fire",
                    icon_off="mdi:fire-off",
                    entity_category=None,
                ),
                HaierBoilerBinarySensor(
                    adapter,
                    key="service",
                    name="Требуется обслуживание",
                    code=CODE_SERVICE,
                    icon_on="mdi:wrench-clock",
                    icon_off="mdi:wrench-check",
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
                HaierBoilerAlarmBinarySensor(adapter),
            ]
        )
    async_add_entities(entities)


class HaierBoilerBinarySensor(HaierBoilerEntity, BinarySensorEntity):
    """Boolean property sensor."""

    def __init__(
        self,
        adapter: HaierBoilerAdapter,
        key: str,
        name: str,
        code: str,
        icon_on: str,
        icon_off: str,
        entity_category,
    ) -> None:
        super().__init__(adapter, key)
        self._attr_name = name
        self.code = code
        self.icon_on = icon_on
        self.icon_off = icon_off
        self._attr_entity_category = entity_category

    @property
    def is_on(self) -> bool:
        return self.adapter.as_bool(self.code)

    @property
    def icon(self) -> str:
        return self.icon_on if self.is_on else self.icon_off


class HaierBoilerAlarmBinarySensor(HaierBoilerEntity, BinarySensorEntity):
    """Problem sensor driven by the active Haier alarm list."""

    _attr_name = "Авария котла"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, adapter: HaierBoilerAdapter) -> None:
        super().__init__(adapter, "alarm")

    @property
    def is_on(self) -> bool:
        return self.adapter.has_alarm

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            "summary": self.adapter.alarm_summary,
            "details": self.adapter.active_alarm_details,
        }
