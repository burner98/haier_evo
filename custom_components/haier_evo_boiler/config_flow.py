"""Config flow for Haier Evo Boiler."""

from __future__ import annotations

from homeassistant import config_entries

from .const import DOMAIN


class HaierEvoBoilerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create the companion config entry."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id("haier_evo_boiler_companion")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Haier Evo — котёл TechLine S", data={})
