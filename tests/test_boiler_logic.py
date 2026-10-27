"""Offline tests for boiler logic without a Home Assistant installation."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "haier_evo_boiler"
ha = types.ModuleType("homeassistant")
ha.__path__ = []
core = types.ModuleType("homeassistant.core")
core.HomeAssistant = object
core.callback = lambda fn: fn
exceptions = types.ModuleType("homeassistant.exceptions")
class HomeAssistantError(Exception): pass
exceptions.HomeAssistantError = HomeAssistantError
helpers = types.ModuleType("homeassistant.helpers")
helpers.__path__ = []
registry = types.ModuleType("homeassistant.helpers.device_registry")
registry.DeviceInfo = dict
sys.modules.update({
    "homeassistant": ha, "homeassistant.core": core,
    "homeassistant.exceptions": exceptions, "homeassistant.helpers": helpers,
    "homeassistant.helpers.device_registry": registry,
})
pkg = types.ModuleType("haier_evo_boiler")
pkg.__path__ = [str(COMPONENT)]
sys.modules["haier_evo_boiler"] = pkg
spec = importlib.util.spec_from_file_location("haier_evo_boiler.boiler", COMPONENT / "boiler.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
Adapter = module.HaierBoilerAdapter

class FakeDevice:
    device_id = "test-boiler"
    device_mac = "test-boiler"
    device_name = "TechLine S 1.24TW"

    def __init__(self):
        self._haier = types.SimpleNamespace(
            socket_status=types.SimpleNamespace(name="INITIALIZED"),
            socket_generation=1,
        )
        self._available = True
        self._status_data = {
            "info": {"model": "TechLine S 1.24TW"},
            "attributes": [
                {"name": "101", "currentValue": "1"},
                {"name": "125", "currentValue": "1"},
                {"name": "7", "currentValue": "47"},
                {"name": "5", "currentValue": "43"},
            ],
            "errors": {"alarmToResult": {
                "flameDetectionCircuitErr": {"text": "[F1] Нет пламени"},
                "temperatureErr": {"text": "[43] Авария температуры"},
            }},
            "alarms": [],
        }
        self._write_ha_state_callbacks = []
        self.sent = []
    @property
    def status_data(self): return self._status_data
    def _get_status(self, snapshot): self._status_data = snapshot
    def _set_attribute_value(self, code, value): pass
    def on_message(self, data): pass
    def add_write_ha_state_callback(self, callback):
        self._write_ha_state_callbacks.append(callback)
    def _send_single_command(self, command): self.sent.append(command)

class TestBoiler(unittest.TestCase):
    def setUp(self):
        self.device = FakeDevice()
        async def executor_job(fn, *args): return fn(*args)
        self.hass = types.SimpleNamespace(
            loop=types.SimpleNamespace(call_soon_threadsafe=lambda cb: cb()),
            async_add_executor_job=executor_job,
        )
        self.adapter = Adapter(self.hass, self.device)
    def tearDown(self):
        self.adapter.close()
    def test_no_optimistic_state_change(self):
        self.adapter.send("7", 55)
        self.assertEqual(self.device.sent, [{"commandName": "7", "value": "55"}])
        self.assertEqual(self.adapter.raw("7"), "47")
    def test_disconnected_commands_rejected(self):
        self.device._haier.socket_status.name = "NOT_INITIALIZED"
        self.assertFalse(self.adapter.available)
        with self.assertRaises(HomeAssistantError):
            self.adapter.send("125", False)
        self.assertFalse(self.device.sent)
    def test_device_offline_commands_rejected(self):
        self.device._available = False
        with self.assertRaises(HomeAssistantError):
            self.adapter.send("101", False)
    def test_reconnect_requires_refresh(self):
        self.device._haier.socket_generation = 2
        self.assertFalse(self.adapter.available)
        snapshot = dict(self.device.status_data)
        snapshot["attributes"] = [dict(x) for x in snapshot["attributes"]]
        snapshot["attributes"][2]["currentValue"] = "50"
        self.device._haier.pull_device_data = lambda mac: snapshot
        asyncio.run(self.adapter._refresh_after_reconnect(2))
        self.assertTrue(self.adapter.available)
        self.assertEqual(self.adapter.raw("7"), "50")
    def test_temperature_not_an_alarm(self):
        self.adapter._ingest_alarm_message({
            "event": "status", "payload": {
                "statuses": [{"properties": {"5": "43", "7": "43"}}]
            }
        })
        self.assertFalse(self.adapter.has_alarm)
    def test_alarm_and_clear(self):
        self.adapter._ingest_alarm_message({"payload": {"alarms": ["F1"]}})
        self.assertTrue(self.adapter.has_alarm)
        self.adapter._ingest_alarm_message({"payload": {"alarms": []}})
        self.assertFalse(self.adapter.has_alarm)
    def test_static_dictionary_not_an_alarm(self):
        self.adapter._ingest_alarm_message({
            "payload": {"errors": self.device.status_data["errors"]}
        })
        self.assertFalse(self.adapter.has_alarm)

if __name__ == "__main__":
    unittest.main()
