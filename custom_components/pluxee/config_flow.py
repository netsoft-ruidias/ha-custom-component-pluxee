"""Config flow for Pluxee integration."""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PluxeeAPI
from .exceptions import AuthenticationError
from .const import DOMAIN, CONF_NIF

_LOGGER = logging.getLogger(__name__)

_SCHEMA_USER = vol.Schema(
    {
        vol.Required(CONF_NIF): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Pluxee.

    Step (user):  NIF + Password
      → success  → create entry
      → auth failure  → show error, repeat
    """

    VERSION = 1

    def __init__(self) -> None:
        self._nif: str = ""
        self._password: str = ""

    # ------------------------------------------------------------------
    # Step 1 — Credentials
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial credentials step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            nif = user_input[CONF_NIF].strip()
            password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(nif)
            self._abort_if_unique_id_configured()

            api = PluxeeAPI(async_get_clientsession(self.hass))

            try:
                # Try to login
                success = await api.login(nif, password)
                if success:
                    return self._async_create_entry(nif=nif, password=password)
                else:
                    errors["base"] = "invalid_auth"

            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during Pluxee login")
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=_SCHEMA_USER,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Reauth flow — triggered when session expires
    # ------------------------------------------------------------------

    async def async_step_reauth(
        self, entry_data: dict
    ) -> config_entries.FlowResult:
        """Start the reauth flow."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        """Handle reauth: prompt for password."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            nif = reauth_entry.data[CONF_NIF]
            password = user_input[CONF_PASSWORD]
            api = PluxeeAPI(async_get_clientsession(self.hass))

            try:
                success = await api.login(nif, password)
                if success:
                    self.hass.config_entries.async_update_entry(
                        reauth_entry,
                        data={
                            **reauth_entry.data,
                            CONF_PASSWORD: password,
                        },
                    )
                    await self.hass.config_entries.async_reload(reauth_entry.entry_id)
                    return self.async_abort(reason="reauth_successful")
                else:
                    errors["base"] = "invalid_auth"

            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during Pluxee reauth")
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={"nif": reauth_entry.data[CONF_NIF]},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _async_create_entry(
        self, nif: str, password: str
    ) -> config_entries.FlowResult:
        """Build the config entry data dict and create the entry."""
        data = {
            CONF_NIF: nif,
            CONF_PASSWORD: password,
        }
        return self.async_create_entry(
            title=f"Pluxee ({nif})",
            data=data,
        )
