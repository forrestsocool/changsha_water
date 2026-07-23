"""Config flow for Changsha Water."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util

from .api import (
    ChangshaWaterApi,
    ChangshaWaterApiError,
    ChangshaWaterAuthError,
    ChangshaWaterMeterNotFound,
)
from .const import (
    CONF_BALANCE_INTERVAL,
    CONF_DETAILS_INTERVAL,
    CONF_METER_NUMBER,
    CONF_RETENTION_DAYS,
    CONF_TOKEN,
    CONF_USER_ID,
    DEFAULT_BALANCE_INTERVAL_MINUTES,
    DEFAULT_DETAILS_INTERVAL_MINUTES,
    DEFAULT_RETENTION_DAYS,
    DOMAIN,
    MAX_BALANCE_INTERVAL_MINUTES,
    MAX_DETAILS_INTERVAL_MINUTES,
    MAX_RETENTION_DAYS,
    MIN_BALANCE_INTERVAL_MINUTES,
    MIN_DETAILS_INTERVAL_MINUTES,
    MIN_RETENTION_DAYS,
)


def _credentials_schema() -> vol.Schema:
    """Return a schema with no private suggested/default values."""
    return vol.Schema(
        {
            vol.Required(CONF_METER_NUMBER): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Required(CONF_USER_ID): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Required(CONF_TOKEN): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
    )


def _reauth_schema() -> vol.Schema:
    """Return a token refresh schema with no secret defaults."""
    return vol.Schema(
        {
            vol.Required(CONF_USER_ID): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Required(CONF_TOKEN): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
    )


def _normalize(data: Mapping[str, Any]) -> dict[str, str]:
    """Strip fields and enforce basic privacy-safe validation."""
    normalized = {
        CONF_METER_NUMBER: str(data.get(CONF_METER_NUMBER, "")).strip(),
        CONF_USER_ID: str(data.get(CONF_USER_ID, "")).strip(),
        CONF_TOKEN: str(data.get(CONF_TOKEN, "")).strip(),
    }
    if (
        not normalized[CONF_METER_NUMBER]
        or not normalized[CONF_USER_ID].isdigit()
        or not normalized[CONF_TOKEN]
    ):
        raise ValueError
    return normalized


def _private_unique_id(meter_number: str) -> str:
    """Hash the meter number so registry metadata does not expose it."""
    return hashlib.sha256(meter_number.encode()).hexdigest()


def _masked_title(meter_number: str) -> str:
    """Return a useful title without exposing the full meter number."""
    suffix = "****" if len(meter_number) <= 4 else f"••••{meter_number[-4:]}"
    return f"长沙水费 {suffix}"


async def _async_validate(hass: Any, data: dict[str, str]) -> None:
    """Validate both endpoints and the meter/user relationship."""
    api = ChangshaWaterApi(
        async_get_clientsession(hass),
        data[CONF_METER_NUMBER],
        data[CONF_USER_ID],
        data[CONF_TOKEN],
    )
    await api.async_get_balance(dt_util.now().date())
    await api.async_get_details()


class ChangshaWaterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle initial, reauth and reconfigure flows."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up a water account."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = _normalize(user_input)
                await _async_validate(self.hass, data)
            except ValueError:
                errors["base"] = "invalid_input"
            except ChangshaWaterAuthError:
                errors["base"] = "invalid_auth"
            except ChangshaWaterMeterNotFound:
                errors["base"] = "meter_not_found"
            except ChangshaWaterApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(
                    _private_unique_id(data[CONF_METER_NUMBER])
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_masked_title(data[CONF_METER_NUMBER]),
                    data=data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_credentials_schema(),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after an expired token."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect a fresh user ID and token without pre-filling secrets."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                data = _normalize(
                    {
                        CONF_METER_NUMBER: entry.data[CONF_METER_NUMBER],
                        **user_input,
                    }
                )
                await _async_validate(self.hass, data)
            except ValueError:
                errors["base"] = "invalid_input"
            except ChangshaWaterAuthError:
                errors["base"] = "invalid_auth"
            except ChangshaWaterMeterNotFound:
                errors["base"] = "meter_not_found"
            except ChangshaWaterApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(
                    _private_unique_id(data[CONF_METER_NUMBER])
                )
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_USER_ID: data[CONF_USER_ID],
                        CONF_TOKEN: data[CONF_TOKEN],
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_reauth_schema(),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change all three private inputs without displaying old values."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            try:
                data = _normalize(user_input)
                await _async_validate(self.hass, data)
            except ValueError:
                errors["base"] = "invalid_input"
            except ChangshaWaterAuthError:
                errors["base"] = "invalid_auth"
            except ChangshaWaterMeterNotFound:
                errors["base"] = "meter_not_found"
            except ChangshaWaterApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(
                    _private_unique_id(data[CONF_METER_NUMBER])
                )
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=data,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_credentials_schema(),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: Any,
    ) -> ChangshaWaterOptionsFlow:
        """Return polling/retention options."""
        return ChangshaWaterOptionsFlow()


class ChangshaWaterOptionsFlow(OptionsFlowWithReload):
    """Configure non-sensitive polling behavior."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_BALANCE_INTERVAL,
                    default=DEFAULT_BALANCE_INTERVAL_MINUTES,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_BALANCE_INTERVAL_MINUTES,
                        max=MAX_BALANCE_INTERVAL_MINUTES,
                    ),
                ),
                vol.Required(
                    CONF_DETAILS_INTERVAL,
                    default=DEFAULT_DETAILS_INTERVAL_MINUTES,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_DETAILS_INTERVAL_MINUTES,
                        max=MAX_DETAILS_INTERVAL_MINUTES,
                    ),
                ),
                vol.Required(
                    CONF_RETENTION_DAYS,
                    default=DEFAULT_RETENTION_DAYS,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_RETENTION_DAYS,
                        max=MAX_RETENTION_DAYS,
                    ),
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, self.config_entry.options
            ),
        )
