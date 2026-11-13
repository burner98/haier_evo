"""Raw GB transport for the separately registered boiler companion entities."""

from .device import HaierDevice, device_part


class HaierGB(HaierDevice):
    """Keep GB descriptions and pushes live without creating duplicate entities."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._get_status(self.status_data)

    def _load_config_from_attributes(self, data):
        for attr in device_part(data).get("attributes") or []:
            if isinstance(attr, dict) and attr.get("name") is not None:
                self._apply_value(str(attr["name"]), attr.get("currentValue"))

    def update_from_backend(self, data):
        self._get_status(data)
        self.synced = True
