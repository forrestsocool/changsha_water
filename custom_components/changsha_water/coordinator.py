"""Data coordinators for Changsha Water."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    BalanceData,
    ChangshaWaterApiError,
    ChangshaWaterAuthError,
    WaterDetails,
)
from .const import (
    DOCUMENTATION_URL,
    DOMAIN,
    ISSUE_ID_PREFIX,
    NOTIFICATION_ID_PREFIX,
)

if TYPE_CHECKING:
    from . import ChangshaWaterConfigEntry, ChangshaWaterRuntimeData

_LOGGER = logging.getLogger(__name__)


class BalanceCoordinator(DataUpdateCoordinator[BalanceData]):
    """Poll the token-free balance endpoint."""

    def __init__(
        self,
        hass: HomeAssistant,
        runtime: ChangshaWaterRuntimeData,
        update_interval: timedelta,
    ) -> None:
        self.runtime = runtime
        super().__init__(
            hass,
            _LOGGER,
            config_entry=runtime.entry,
            name=f"{DOMAIN}_balance",
            update_interval=update_interval,
            always_update=False,
        )

    async def _async_update_data(self) -> BalanceData:
        try:
            now = dt_util.now()
            data = await self.runtime.api.async_get_balance(now.date())
        except ChangshaWaterApiError as err:
            raise UpdateFailed(str(err)) from err

        self.runtime.ledger.apply_balance(
            data.balance,
            local_day=now.date(),
            observed_at=now,
        )
        self.runtime.schedule_save()
        return data


class DetailsCoordinator(DataUpdateCoordinator[WaterDetails]):
    """Poll authenticated details without taking balance tracking down."""

    def __init__(
        self,
        hass: HomeAssistant,
        runtime: ChangshaWaterRuntimeData,
        update_interval: timedelta,
    ) -> None:
        self.runtime = runtime
        super().__init__(
            hass,
            _LOGGER,
            config_entry=runtime.entry,
            name=f"{DOMAIN}_details",
            update_interval=update_interval,
            always_update=False,
        )

    async def _async_update_data(self) -> WaterDetails:
        try:
            data = await self.runtime.api.async_get_details()
        except ChangshaWaterAuthError:
            await _async_mark_token_invalid(self.hass, self.runtime.entry, self.runtime)
            return WaterDetails.unavailable(self.data)
        except ChangshaWaterApiError as err:
            raise UpdateFailed(str(err)) from err

        now = dt_util.now()
        self.runtime.ledger.apply_details(
            total_water=data.total_water,
            total_water_amount=data.total_water_amount,
            last_bill_water=data.last_bill_water,
            last_bill_amount=data.last_bill_amount,
            local_day=now.date(),
            observed_at=now,
        )
        self.runtime.schedule_save()
        await _async_clear_token_issue(self.hass, self.runtime.entry, self.runtime)
        _async_refresh_balance_entities(self.runtime)
        return data


async def _async_mark_token_invalid(
    hass: HomeAssistant,
    entry: ChangshaWaterConfigEntry,
    runtime: ChangshaWaterRuntimeData,
) -> None:
    """Create one repair/notification and start reauthentication."""
    runtime.auth_valid = False
    _async_refresh_balance_entities(runtime)
    if runtime.auth_issue_active:
        return
    runtime.auth_issue_active = True

    notification_id = f"{NOTIFICATION_ID_PREFIX}_{entry.entry_id}"
    persistent_notification.async_create(
        hass,
        (
            "长沙水费的明细 Token 已失效或无权访问。余额与基于余额的"
            "日用量推算仍会继续运行。\n\n"
            "请重新抓包获取 `x-tif-token`，然后在集成的重新认证流程中"
            "填写用户 ID 和新 Token。"
        ),
        title="长沙水费需要更新 Token",
        notification_id=notification_id,
    )
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"{ISSUE_ID_PREFIX}_{entry.entry_id}",
        is_fixable=False,
        is_persistent=True,
        learn_more_url=f"{DOCUMENTATION_URL}#token-失效与降级",
        severity=ir.IssueSeverity.WARNING,
        translation_key="token_expired",
        translation_placeholders={"entry_title": entry.title},
    )
    entry.async_start_reauth(hass)


async def _async_clear_token_issue(
    hass: HomeAssistant,
    entry: ChangshaWaterConfigEntry,
    runtime: ChangshaWaterRuntimeData,
) -> None:
    """Clear token warnings after a successful authenticated request."""
    runtime.auth_valid = True
    _async_refresh_balance_entities(runtime)
    if not runtime.auth_issue_active:
        return
    runtime.auth_issue_active = False
    persistent_notification.async_dismiss(
        hass, f"{NOTIFICATION_ID_PREFIX}_{entry.entry_id}"
    )
    ir.async_delete_issue(hass, DOMAIN, f"{ISSUE_ID_PREFIX}_{entry.entry_id}")


def _async_refresh_balance_entities(runtime: ChangshaWaterRuntimeData) -> None:
    """Notify derived entities after details/auth state changes."""
    coordinator = runtime.balance_coordinator
    if coordinator is not None and coordinator.data is not None:
        coordinator.async_set_updated_data(coordinator.data)
