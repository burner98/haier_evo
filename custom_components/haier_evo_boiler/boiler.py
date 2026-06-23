"""Bridge to an already loaded Haier Evo boiler device."""

from __future__ import annotations

from collections.abc import Callable
import json
import logging
import time
from types import MethodType
from typing import Any

from homeassistant.core import HomeAssistant, callback

from .const import REQUIRED_CODES

_LOGGER = logging.getLogger(__name__)


def _find_control_node(data: Any) -> dict[str, Any] | None:
    """Find the smartDeviceControl-like object containing attributes."""
    if isinstance(data, dict):
        attrs = data.get("attributes")
        if isinstance(attrs, list):
            return data
        for value in data.values():
            found = _find_control_node(value)
            if found is not None:
                return found
    elif isinstance(data, list):
        for value in data:
            found = _find_control_node(value)
            if found is not None:
                return found
    return None


def is_supported_boiler_device(device: Any) -> bool:
    """Return True for the TechLine S GB payload discovered in Haier Evo."""
    control = _find_control_node(getattr(device, "status_data", None))
    if not control:
        return False
    codes = {
        str(item.get("name"))
        for item in control.get("attributes", [])
        if isinstance(item, dict) and item.get("name") is not None
    }
    if not REQUIRED_CODES.issubset(codes):
        return False

    model = str(control.get("info", {}).get("model", ""))
    name = str(getattr(device, "device_name", ""))
    # Codes are the primary check. These strings reduce the risk of matching
    # an unrelated future device that happens to reuse the same properties.
    text = f"{model} {name}".lower()
    return "boiler" in text or "techline" in text or "кот" in text


class HaierBoilerAdapter:
    """Expose a generic HaierDevice as a TechLine S boiler."""

    def __init__(self, hass: HomeAssistant, device: Any) -> None:
        self.hass = hass
        self.device = device
        self.control = _find_control_node(getattr(device, "status_data", None)) or {}
        self.values: dict[str, Any] = {}
        self.specs: dict[str, dict[str, Any]] = {}
        self._listeners: set[Callable[[], None]] = set()
        self._original_set_attribute_value = getattr(device, "_set_attribute_value", None)
        self._load_initial_values()
        self._install_hook()

    @property
    def device_id(self) -> str:
        return str(self.device.device_id)

    @property
    def name(self) -> str:
        return str(getattr(self.device, "device_name", None) or "Haier TechLine S")

    @property
    def device_info(self) -> Any:
        return self.device.device_info

    @property
    def available(self) -> bool:
        return bool(getattr(self.device, "available", True))

    def _load_initial_values(self) -> None:
        for item in self.control.get("attributes", []):
            if not isinstance(item, dict) or item.get("name") is None:
                continue
            code = str(item["name"])
            self.values[code] = item.get("currentValue")
            self.specs[code] = item

    def _install_hook(self) -> None:
        adapter = self
        original = self._original_set_attribute_value

        def patched_set_attribute_value(device_self: Any, code: str, value: Any) -> None:
            adapter.values[str(code)] = value
            if callable(original):
                try:
                    original(code, value)
                except Exception:  # Source device is generic; do not break WS updates.
                    _LOGGER.debug("Source attribute handler failed", exc_info=True)

        self.device._set_attribute_value = MethodType(
            patched_set_attribute_value, self.device
        )
        self.device.add_write_ha_state_callback(self._source_updated)

    def close(self) -> None:
        """Restore the source device when this integration is unloaded."""
        if self._original_set_attribute_value is not None:
            self.device._set_attribute_value = self._original_set_attribute_value
        callbacks = getattr(self.device, "_write_ha_state_callbacks", None)
        if isinstance(callbacks, list) and self._source_updated in callbacks:
            callbacks.remove(self._source_updated)
        self._listeners.clear()

    @callback
    def _source_updated(self) -> None:
        self._notify_on_loop()

    @callback
    def _notify_on_loop(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    def notify(self) -> None:
        self.hass.loop.call_soon_threadsafe(self._notify_on_loop)

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)

        @callback
        def remove_listener() -> None:
            self._listeners.discard(listener)

        return remove_listener

    def raw(self, code: str, default: Any = None) -> Any:
        return self.values.get(str(code), default)

    def as_bool(self, code: str, default: bool = False) -> bool:
        value = self.raw(code)
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "on", "yes"}

    def as_float(self, code: str, default: float | None = None) -> float | None:
        value = self.raw(code)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def range_for(
        self, code: str, default_min: float, default_max: float, default_step: float = 1
    ) -> tuple[float, float, float]:
        data = (
            self.specs.get(str(code), {})
            .get("range", {})
            .get("data", {})
        )
        try:
            minimum = float(data.get("minValue", default_min))
            maximum = float(data.get("maxValue", default_max))
            step = float(data.get("step", default_step))
        except (TypeError, ValueError):
            return default_min, default_max, default_step
        return minimum, maximum, step

    def send(self, code: str, value: Any) -> None:
        """Send one raw Evo property command through the source WebSocket."""
        code = str(code)
        if isinstance(value, bool):
            wire_value = "1" if value else "0"
        elif isinstance(value, float) and value.is_integer():
            wire_value = str(int(value))
        else:
            wire_value = str(value)

        command = {"commandName": code, "value": wire_value}
        _LOGGER.debug("Sending boiler command %s", command)
        self.device._send_single_command(command)

        # Optimistic state. The next status push remains authoritative.
        self.values[code] = wire_value
        self.notify()

    def send_many(self, commands: list[tuple[str, Any]], delay: float = 0.25) -> None:
        for index, (code, value) in enumerate(commands):
            self.send(code, value)
            if index < len(commands) - 1 and delay:
                time.sleep(delay)

    def diagnostic_dump(self) -> str:
        """Return a compact diagnostic representation without credentials."""
        return json.dumps(self.values, ensure_ascii=False, sort_keys=True)
