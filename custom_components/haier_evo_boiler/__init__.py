"""Haier Evo Boiler companion integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady

from .boiler import HaierBoilerAdapter, is_supported_boiler_device
from .const import SOURCE_DOMAIN

PLATFORMS = [Platform.CLIMATE, Platform.SWITCH, Platform.SENSOR, Platform.BINARY_SENSOR]


def _find_source_devices(hass: HomeAssistant):
    for source_entry in hass.config_entries.async_entries(SOURCE_DOMAIN):
        if source_entry.state is not ConfigEntryState.LOADED:
            continue
        source_object = getattr(source_entry, "runtime_data", None)
        for device in getattr(source_object, "devices", []):
            if is_supported_boiler_device(device):
                yield device


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    devices = list(_find_source_devices(hass))
    if not devices:
        raise ConfigEntryNotReady(
            "Haier Evo is not ready or no supported TechLine S boiler was found"
        )

    hass.config_entries.async_update_entry(
        entry, title="Haier Evo — котёл TechLine S"
    )
    adapters = [HaierBoilerAdapter(hass, device) for device in devices]
    entry.runtime_data = adapters
    reload_scheduled = False

    @callback
    def source_changed() -> None:
        """Stop using old devices as soon as their owning entry unloads."""
        nonlocal reload_scheduled
        for adapter in adapters:
            owner = next((
                source for source in hass.config_entries.async_entries(SOURCE_DOMAIN)
                if getattr(source, "runtime_data", None) is adapter.device._haier
            ), None)
            if owner is None or owner.state is not ConfigEntryState.LOADED:
                adapter.close()
        if not reload_scheduled and any(adapter._closed for adapter in adapters) and any(
            source.state is ConfigEntryState.LOADED
            for source in hass.config_entries.async_entries(SOURCE_DOMAIN)
        ) and all(
            source.state is ConfigEntryState.LOADED
            for source in hass.config_entries.async_entries(SOURCE_DOMAIN)
            if source.disabled_by is None
        ):
            reload_scheduled = True
            hass.config_entries.async_schedule_reload(entry.entry_id)

    for source in hass.config_entries.async_entries(SOURCE_DOMAIN):
        entry.async_on_unload(source.async_on_state_change(source_changed))
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        for adapter in adapters:
            adapter.close()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        adapters: list[HaierBoilerAdapter] = entry.runtime_data
        for adapter in adapters:
            adapter.close()
    return unloaded
