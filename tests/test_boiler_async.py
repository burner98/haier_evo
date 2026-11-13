"""Boiler migration: real HA core, simulated transport, no gas hardware."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haier_evo.device import HaierDevice
from custom_components.haier_evo_boiler import async_setup_entry
from custom_components.haier_evo_boiler.boiler import HaierBoilerAdapter

MAC = "00:00:5e:00:53:03"
KEYS = {
    "heating": "climate", "power": "switch", "eco": "switch",
    "ch_temperature": "sensor", "burner_power": "sensor", "antifreeze_level": "sensor",
    "current_alarm": "sensor", "flame": "binary_sensor", "service": "binary_sensor",
    "alarm": "binary_sensor",
}


@pytest.fixture
async def boiler(hass):
    status = {
        "info": {"model": "TechLine S 1.24TW"}, "status": "ONLINE",
        "attributes": [{"name": code, "currentValue": value} for code, value in {
            "101": "1", "125": "1", "7": "47", "5": "43", "142": "0",
            "31": "0", "107": "0", "123": "0", "119": "0",
        }.items()],
        "alarms": [], "errors": {"alarmToResult": {
            "flameDetectionCircuitErr": {"text": "[F1] Нет пламени"},
            "temperatureErr": {"text": "[43] Авария температуры"},
        }},
    }
    hub = SimpleNamespace(
        hass=hass, connected=True, cloud_available=True, reconnects=0,
        async_send=AsyncMock(),
        client=SimpleNamespace(async_get_device_status=AsyncMock(return_value=status)),
    )
    device = await hass.async_add_executor_job(lambda: HaierDevice.create(
        hub, "GB", MAC, device_title="TechLine S 1.24TW", backend_data=deepcopy(status),
    ))
    hub.devices = [device]
    adapter = HaierBoilerAdapter(hass, device)
    yield adapter, device, hub
    adapter.close()
    await hass.async_block_till_done()


async def test_await_transport_without_optimistic_state(boiler):
    adapter, _, hub = boiler
    await adapter.send("7", 55)
    assert hub.async_send.await_count == 1
    assert hub.async_send.call_args.args[0]["command"] == {"commandName": "7", "value": "55"}
    assert adapter.raw("7") == "47"
    hub.async_send.side_effect = HomeAssistantError("delivery failed")
    with pytest.raises(HomeAssistantError):
        await adapter.send("7", 50)
    assert adapter.raw("7") == "47"


@pytest.mark.parametrize("failure", ["socket", "cloud", "device", "cached"])
async def test_unavailable_commands_rejected(boiler, failure):
    adapter, device, hub = boiler
    if failure == "socket":
        hub.connected = False
    elif failure == "cloud":
        hub.cloud_available = False
    elif failure == "device":
        device.available = "OFFLINE"
    else:
        device.synced = False
    assert not adapter.available
    with pytest.raises(HomeAssistantError):
        await adapter.send("101", True)
    hub.async_send.assert_not_awaited()


async def test_push_alarms_and_clear(boiler):
    adapter, device, _ = boiler
    def push(properties, alarms):
        device.on_message({"event": "status", "payload": {
            "statuses": [{"properties": properties, "alarms": alarms}],
        }})
    push({"5": "43"}, [])
    assert not adapter.has_alarm
    push({"7": "50"}, ["F1"])
    assert adapter.raw("7") == "50"
    assert adapter.active_alarm_keys == ("flameDetectionCircuitErr",)
    push({}, [])
    assert not adapter.has_alarm
    adapter._ingest_alarm_message({"errors": device.status_data["errors"]})
    assert not adapter.has_alarm


async def test_reconnect_requires_fresh_rest(hass, boiler):
    adapter, device, hub = boiler
    hub.reconnects = 1
    assert not adapter.available
    snapshot = deepcopy(device.status_data)
    snapshot["attributes"][2]["currentValue"] = "50"
    hub.client.async_get_device_status.return_value = snapshot
    device.notify()
    await hass.async_block_till_done()
    assert adapter.available
    assert adapter.raw("7") == "50"
    hub.client.async_get_device_status.assert_awaited_once_with(MAC)


async def test_stale_rest_does_not_overwrite_push(hass, boiler):
    adapter, device, hub = boiler
    old = deepcopy(device.status_data)
    fresh = deepcopy(old)
    fresh["attributes"][2]["currentValue"] = "51"
    calls = 0
    async def read_status(mac):
        nonlocal calls
        calls += 1
        if calls == 1:
            device.on_message({"event": "status", "payload": {
                "statuses": [{"properties": {"7": "51"}}],
            }})
            return old
        return fresh
    hub.client.async_get_device_status.side_effect = read_status
    hub.reconnects += 1
    device.notify()
    await hass.async_block_till_done()
    assert adapter.raw("7") == "51"
    assert adapter.available


async def test_close_cancels_refresh_and_detaches(hass, boiler):
    adapter, device, hub = boiler
    entered = asyncio.Event()
    async def slow_read(mac):
        entered.set()
        await asyncio.Event().wait()
    hub.client.async_get_device_status.side_effect = slow_read
    hub.reconnects += 1
    device.notify()
    await entered.wait()
    adapter.close()
    adapter.close()
    await hass.async_block_till_done()
    assert adapter._refresh_task.cancelled()
    assert not device._listeners
    assert not adapter.available


async def test_missing_source_retries(hass):
    entry = MockConfigEntry(domain="haier_evo_boiler", data={})
    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)


async def test_ten_existing_registry_ids_survive(hass, boiler):
    adapter, device, hub = boiler
    source = MockConfigEntry(domain="haier_evo", data={}, title="Evo", state=ConfigEntryState.LOADED)
    source.add_to_hass(hass)
    source.runtime_data = hub
    entry = MockConfigEntry(domain="haier_evo_boiler", data={}, title="Boiler")
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old_ids = {}
    for key, platform in KEYS.items():
        uid = f"haier_evo_boiler_{MAC}_{key}"
        old_ids[uid] = registry.async_get_or_create(
            platform, "haier_evo_boiler", uid, config_entry=entry,
            suggested_object_id=f"existing_{key}",
        ).entity_id
    adapter.close()
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert {item.unique_id: item.entity_id for item in entries} == old_ids
    assert len(entries) == 10
    assert all(hass.states.get(eid) is not None for eid in old_ids.values())
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not device._listeners
