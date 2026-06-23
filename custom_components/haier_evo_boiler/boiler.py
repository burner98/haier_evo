"""Bridge to an already loaded Haier Evo boiler device."""

from __future__ import annotations

from collections.abc import Callable
import json
import logging
import re
import time
from types import MethodType
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import REQUIRED_CODES, SOURCE_DOMAIN

_LOGGER = logging.getLogger(__name__)

_ALARM_CONTAINER_KEYS = {
    "alarm",
    "alarms",
    "activealarm",
    "activealarms",
    "alarmcode",
    "alarmcodes",
    "alarmname",
    "alarmnames",
    "error",
    "errors",
    "fault",
    "faults",
}
_ALARM_DEFINITION_PSEUDO_KEYS = {"alarmCancel"}
_ALARM_CODE_RE = re.compile(r"^\[([^\]]+)\]")


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
        self._original_on_message = getattr(device, "on_message", None)

        self._alarm_definitions = self._load_alarm_definitions()
        self._alarm_code_to_key = self._build_alarm_code_index()
        self._active_alarm_keys: set[str] = set()

        self._load_initial_values()
        self._load_initial_alarms()
        self._install_hooks()

    @property
    def device_id(self) -> str:
        return str(self.device.device_id)

    @property
    def model(self) -> str:
        model = self.control.get("info", {}).get("model")
        return str(model or "TechLine S")

    @property
    def firmware(self) -> str | None:
        firmware = (
            self.control.get("settings", {})
            .get("firmware", {})
            .get("value")
        )
        if firmware is None:
            firmware = getattr(self.device, "sw_version", None)
        return str(firmware) if firmware not in (None, "") else None

    @property
    def name(self) -> str:
        raw_name = str(getattr(self.device, "device_name", "") or "").strip()
        if not raw_name or raw_name.lower().startswith("gas boiler"):
            return f"Газовый котёл Haier {self.model}"
        return raw_name

    @property
    def device_info(self) -> DeviceInfo:
        """Use the source identifier, but replace generic UNKNOWN metadata."""
        return DeviceInfo(
            identifiers={(SOURCE_DOMAIN, self.device_id)},
            name=self.name,
            manufacturer="Haier",
            model=self.model,
            sw_version=self.firmware,
        )

    @property
    def available(self) -> bool:
        return bool(getattr(self.device, "available", True))

    @property
    def has_alarm(self) -> bool:
        return bool(self._active_alarm_keys)

    @property
    def active_alarm_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._active_alarm_keys))

    @property
    def active_alarm_details(self) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for key in self.active_alarm_keys:
            definition = self._alarm_definitions.get(key, {})
            text = str(definition.get("text") or key)
            description = str(definition.get("description") or "")
            match = _ALARM_CODE_RE.match(text)
            code = match.group(1) if match else ""
            result.append(
                {
                    "key": key,
                    "code": code,
                    "text": text,
                    "description": description,
                }
            )
        return result

    @property
    def alarm_summary(self) -> str:
        if not self._active_alarm_keys:
            return "Нет аварий"
        return "; ".join(item["text"] for item in self.active_alarm_details)

    def _load_initial_values(self) -> None:
        for item in self.control.get("attributes", []):
            if not isinstance(item, dict) or item.get("name") is None:
                continue
            code = str(item["name"])
            self.values[code] = item.get("currentValue")
            self.specs[code] = item

    def _load_alarm_definitions(self) -> dict[str, dict[str, str]]:
        raw = (
            self.control.get("errors", {})
            .get("alarmToResult", {})
        )
        if not isinstance(raw, dict):
            return {}
        result: dict[str, dict[str, str]] = {}
        for key, value in raw.items():
            if key in _ALARM_DEFINITION_PSEUDO_KEYS or not isinstance(value, dict):
                continue
            result[str(key)] = {
                "text": str(value.get("text") or key),
                "description": str(value.get("description") or ""),
            }
        return result

    def _build_alarm_code_index(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, definition in self._alarm_definitions.items():
            match = _ALARM_CODE_RE.match(definition.get("text", ""))
            if match:
                result[match.group(1).strip().upper()] = key
        return result

    def _load_initial_alarms(self) -> None:
        alarms = self.control.get("alarms", [])
        self._active_alarm_keys = self._extract_alarm_keys(alarms)

    def _install_hooks(self) -> None:
        adapter = self
        original_set = self._original_set_attribute_value
        original_message = self._original_on_message

        def patched_set_attribute_value(device_self: Any, code: str, value: Any) -> None:
            adapter.values[str(code)] = value
            if callable(original_set):
                try:
                    original_set(code, value)
                except Exception:
                    _LOGGER.debug("Source attribute handler failed", exc_info=True)

        def patched_on_message(device_self: Any, message_dict: Any) -> Any:
            result = None
            if callable(original_message):
                result = original_message(message_dict)
            try:
                adapter._ingest_alarm_message(message_dict)
            except Exception:
                _LOGGER.debug("Unable to parse boiler alarm message", exc_info=True)
            return result

        self.device._set_attribute_value = MethodType(
            patched_set_attribute_value, self.device
        )
        if callable(original_message):
            self.device.on_message = MethodType(patched_on_message, self.device)
        self.device.add_write_ha_state_callback(self._source_updated)

    def close(self) -> None:
        """Restore the source device when this integration is unloaded."""
        if self._original_set_attribute_value is not None:
            self.device._set_attribute_value = self._original_set_attribute_value
        if self._original_on_message is not None:
            self.device.on_message = self._original_on_message
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

    def _normalize_alarm_token(self, value: Any) -> str | None:
        if value is None:
            return None
        token = str(value).strip()
        if not token:
            return None
        if token in self._alarm_definitions:
            return token
        upper = token.upper()
        if upper in self._alarm_code_to_key:
            return self._alarm_code_to_key[upper]
        match = re.search(r"\[?([A-F]?\d{1,2}|F[A-F0-9])\]?", upper)
        if match and match.group(1) in self._alarm_code_to_key:
            return self._alarm_code_to_key[match.group(1)]
        return None

    def _extract_alarm_keys(self, value: Any) -> set[str]:
        found: set[str] = set()

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for key, child in node.items():
                    key_l = str(key).replace("_", "").lower()
                    if key_l == "alarmtoresult":
                        continue
                    if (
                        key_l == "errors"
                        and isinstance(child, dict)
                        and "alarmToResult" in child
                    ):
                        continue
                    normalized_key = self._normalize_alarm_token(key)
                    if normalized_key and child not in (False, 0, "0", "false", None):
                        found.add(normalized_key)
                    walk(child)
            elif isinstance(node, (list, tuple, set)):
                for child in node:
                    walk(child)
            else:
                normalized = self._normalize_alarm_token(node)
                if normalized:
                    found.add(normalized)

        walk(value)
        return found

    def _explicit_alarm_containers(self, message: Any) -> list[Any]:
        containers: list[Any] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for key, child in node.items():
                    key_l = str(key).replace("_", "").lower()
                    is_static_dictionary = (
                        key_l == "errors"
                        and isinstance(child, dict)
                        and "alarmToResult" in child
                    )
                    if key_l in _ALARM_CONTAINER_KEYS and not is_static_dictionary:
                        containers.append(child)
                    if key_l != "alarmtoresult" and not is_static_dictionary:
                        walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(message)
        return containers

    def _ingest_alarm_message(self, message: Any) -> None:
        """Update active alarms from a live Haier WebSocket message."""
        explicit = self._explicit_alarm_containers(message)
        if explicit:
            new_keys: set[str] = set()
            for container in explicit:
                new_keys.update(self._extract_alarm_keys(container))
            if new_keys != self._active_alarm_keys:
                self._active_alarm_keys = new_keys
                self.notify()
            return

        discovered = self._extract_alarm_keys(message)
        if discovered and discovered != self._active_alarm_keys:
            self._active_alarm_keys = discovered
            self.notify()

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
        data = self.specs.get(str(code), {}).get("range", {}).get("data", {})
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
