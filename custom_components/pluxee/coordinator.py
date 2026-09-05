"""DataUpdateCoordinator for the Pluxee integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PluxeeAPI
from .exceptions import AuthenticationError, PluxeeAPIError
from .interfaces import Card, Balance, Transaction
from .const import (
    DOMAIN,
    UPDATE_INTERVAL,
    CONF_NIF,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRES_AT,
    DEFAULT_TRANSACTIONS_COUNT,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class PluxeeData:
    """Data returned by a single coordinator refresh."""

    card: Card
    balances: list[Balance]
    transactions: list[Transaction]


class PluxeeCoordinator(DataUpdateCoordinator[PluxeeData]):
    """Coordinator that manages all Pluxee API calls.

    Pluxee authentication strategy:
    - Persist the portal auth context token (JWT from cookie)
    - Refresh authentication silently before token expiry
    - Retry once with forced login on session expiration
    - Only request reauth when credentials are no longer valid
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: PluxeeAPI,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self._entry = entry
        self._api = api
        self._authenticated = False
        self._refresh_buffer_seconds = 300
        # Cache: last known balance to detect changes
        self._last_balance: float | None = None
        # Cache: last fetched transactions
        self._cached_transactions: list[Transaction] = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _async_save_auth_context(self) -> None:
        """Persist latest auth context in config_entry.data."""
        expires_at = self._api.token_expires_at
        new_data = {
            **self._entry.data,
            CONF_REFRESH_TOKEN: self._api.refresh_token or "",
            CONF_TOKEN_EXPIRES_AT: (
                expires_at.astimezone(timezone.utc).isoformat()
                if expires_at is not None
                else ""
            ),
        }
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)

    async def _async_ensure_authenticated(self, force: bool = False) -> None:
        """Ensure we have a valid authenticated session."""
        if (
            not force
            and self._authenticated
            and not self._api.is_token_expiring_soon(self._refresh_buffer_seconds)
        ):
            return

        data = self._entry.data
        nif: str = data[CONF_NIF]
        password: str = data[CONF_PASSWORD]

        try:
            success = await self._api.login(nif, password)
            if not success:
                _LOGGER.warning("Authentication failed for NIF %s", nif)
                raise ConfigEntryAuthFailed("Pluxee authentication failed")

            self._authenticated = True
            await self._async_save_auth_context()
            _LOGGER.debug(
                "Successfully authenticated with Pluxee (token expiring soon=%s)",
                self._api.is_token_expiring_soon(self._refresh_buffer_seconds),
            )

        except AuthenticationError as err:
            _LOGGER.warning("Authentication failed: %s", err)
            raise ConfigEntryAuthFailed(f"Pluxee authentication failed: {err}") from err

    # ------------------------------------------------------------------
    # DataUpdateCoordinator protocol
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> PluxeeData:
        """Fetch the latest data from the Pluxee API."""
        try:
            # Ensure we're authenticated
            await self._async_ensure_authenticated()

            try:
                # Fetch card and balance data
                card = await self._api.get_card()
                balances = await self._api.get_balances()
            except AuthenticationError:
                # Session can expire unexpectedly between polls.
                # Retry once with a forced login before requesting reauth.
                _LOGGER.debug("Session expired while fetching data, forcing re-login")
                self._authenticated = False
                await self._async_ensure_authenticated(force=True)
                card = await self._api.get_card()
                balances = await self._api.get_balances()

            if card is None or balances is None:
                raise UpdateFailed("Pluxee API returned incomplete data.")

            # Fetch transactions only if balance changed (or first run)
            current_balance = balances[0].balance if balances else 0.0
            if self._last_balance is None or self._last_balance != current_balance:
                _LOGGER.debug(
                    "Balance changed (%.2f → %.2f), fetching transactions.",
                    self._last_balance if self._last_balance is not None else 0.0,
                    current_balance,
                )
                movements = await self._api.get_movements(limit=DEFAULT_TRANSACTIONS_COUNT)
                self._cached_transactions = movements or []
                self._last_balance = current_balance
            else:
                _LOGGER.debug(
                    "Balance unchanged (%.2f), reusing cached transactions.",
                    current_balance,
                )

            return PluxeeData(
                card=card,
                balances=balances,
                transactions=self._cached_transactions,
            )

        except ConfigEntryAuthFailed:
            # Credentials or full auth flow failed, let HA handle reauth
            self._authenticated = False
            raise
        except AuthenticationError as err:
            self._authenticated = False
            raise ConfigEntryAuthFailed(f"Pluxee authentication error: {err}") from err
        except PluxeeAPIError as err:
            raise UpdateFailed(f"Pluxee API error: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error communicating with Pluxee: {err}") from err

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    async def async_force_refresh(self) -> None:
        """Force a full refresh, clearing the balance cache so all transactions are re-fetched."""
        self._last_balance = None
        await self.async_refresh()
