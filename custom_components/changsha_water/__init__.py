"""Changsha Water Home Assistant integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .api import ChangshaWaterApi
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
    ISSUE_ID_PREFIX,
    NOTIFICATION_ID_PREFIX,
    STORAGE_SAVE_DELAY_SECONDS,
    STORAGE_VERSION,
)
from .ledger import UsageLedger

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


@dataclass(slots=True)
class ChangshaWaterRuntimeData:
    """Runtime state for one private water account."""

    hass: HomeAssistant
    entry: ChangshaWaterConfigEntry
    api: ChangshaWaterApi
    ledger: UsageLedger
    store: Store[dict[str, Any]]
    balance_coordinator: Any = None
    details_coordinator: Any = None
    auth_valid: bool = True
    auth_issue_active: bool = False

    @callback
    def schedule_save(self) -> None:
        """Persist ledger changes with write coalescing."""
        self.store.async_delay_save(self.ledger.as_dict, STORAGE_SAVE_DELAY_SECONDS)


ChangshaWaterConfigEntry = ConfigEntry[ChangshaWaterRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant, entry: ChangshaWaterConfigEntry
) -> bool:
    """Set up Changsha Water from a config entry."""
    from .coordinator import BalanceCoordinator, DetailsCoordinator

    retention_days = int(entry.options.get(CONF_RETENTION_DAYS, DEFAULT_RETENTION_DAYS))
    store = Store[dict[str, Any]](
        hass,
        STORAGE_VERSION,
        f"{DOMAIN}.{entry.entry_id}",
        private=True,
        atomic_writes=True,
    )
    ledger = UsageLedger.from_dict(
        await store.async_load(), retention_days=retention_days
    )
    api = ChangshaWaterApi(
        async_get_clientsession(hass),
        str(entry.data[CONF_METER_NUMBER]),
        str(entry.data[CONF_USER_ID]),
        str(entry.data[CONF_TOKEN]),
    )
    runtime = ChangshaWaterRuntimeData(
        hass=hass,
        entry=entry,
        api=api,
        ledger=ledger,
        store=store,
    )
    entry.runtime_data = runtime

    runtime.balance_coordinator = BalanceCoordinator(
        hass,
        runtime,
        timedelta(
            minutes=int(
                entry.options.get(
                    CONF_BALANCE_INTERVAL,
                    DEFAULT_BALANCE_INTERVAL_MINUTES,
                )
            )
        ),
    )
    runtime.details_coordinator = DetailsCoordinator(
        hass,
        runtime,
        timedelta(
            minutes=int(
                entry.options.get(
                    CONF_DETAILS_INTERVAL,
                    DEFAULT_DETAILS_INTERVAL_MINUTES,
                )
            )
        ),
    )

    # Balance is the resilient baseline and must work for initial setup.
    await runtime.balance_coordinator.async_config_entry_first_refresh()
    # Auth failures are represented as stale detail data, so setup continues.
    await runtime.details_coordinator.async_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ChangshaWaterConfigEntry
) -> bool:
    """Unload a config entry and flush its private ledger."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.store.async_save(entry.runtime_data.ledger.as_dict())
    return unload_ok


async def async_remove_entry(
    hass: HomeAssistant, entry: ChangshaWaterConfigEntry
) -> None:
    """Remove private ledger data and any account-specific notices."""
    store = Store[dict[str, Any]](
        hass,
        STORAGE_VERSION,
        f"{DOMAIN}.{entry.entry_id}",
        private=True,
        atomic_writes=True,
    )
    await store.async_remove()
    persistent_notification.async_dismiss(
        hass, f"{NOTIFICATION_ID_PREFIX}_{entry.entry_id}"
    )
    ir.async_delete_issue(hass, DOMAIN, f"{ISSUE_ID_PREFIX}_{entry.entry_id}")
