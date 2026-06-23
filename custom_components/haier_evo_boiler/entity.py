"""Shared entity base for Haier Evo Boiler."""

from __future__ import annotations

from homeassistant.helpers.entity import Entity

from .boiler import HaierBoilerAdapter


class HaierBoilerEntity(Entity):
    """Base entity linked to the source Haier device."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, adapter: HaierBoilerAdapter, key: str) -> None:
        self.adapter = adapter
        self._attr_unique_id = f"haier_evo_boiler_{adapter.device_id}_{key}"
        self._attr_device_info = adapter.device_info
        self._remove_listener = None

    @property
    def available(self) -> bool:
        return self.adapter.available

    async def async_added_to_hass(self) -> None:
        self._remove_listener = self.adapter.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
