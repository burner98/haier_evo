"""Haier Evo Boiler companion integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .boiler import HaierBoilerAdapter, is_supported_boiler_device
from .const import DOMAIN, SOURCE_DOMAIN

PLATFORMS = [Platform.CLIMATE, Platform.SWITCH, Platform.SENSOR, Platform.BINARY_SENSOR]


def _find_source_devices(hass: HomeAssistant):
    source_data = hass.data.get(SOURCE_DOMAIN, {})
    for source_object in source_data.values():
        for device in getattr(source_object, "devices", []):
            if is_supported_boiler_device(device):
                yield device


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    devices = list(_find_source_devices(hass))
    if not devices:
        raise ConfigEntryNotReady(
            "Haier Evo is not ready or no supported TechLine S boiler was found"
        )

    adapters = [HaierBoilerAdapter(hass, device) for device in devices]
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = adapters
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        adapters: list[HaierBoilerAdapter] = hass.data[DOMAIN].pop(entry.entry_id, [])
        for adapter in adapters:
            adapter.close()
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unloaded
