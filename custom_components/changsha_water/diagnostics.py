"""Privacy-safe diagnostics for Changsha Water."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ChangshaWaterConfigEntry
from .const import CONF_METER_NUMBER, CONF_TOKEN, CONF_USER_ID

TO_REDACT = {CONF_METER_NUMBER, CONF_USER_ID, CONF_TOKEN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ChangshaWaterConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with all account identifiers redacted."""
    runtime = entry.runtime_data
    details = runtime.details_coordinator.data
    today = runtime.ledger.current_day(
        runtime.balance_coordinator.data.local_day
        if runtime.balance_coordinator.data
        else __import__("datetime").date.today()
    )
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "balance_endpoint_available": runtime.balance_coordinator.last_update_success,
        "details_endpoint_available": runtime.details_coordinator.last_update_success,
        "token_details_available": runtime.auth_valid,
        "ledger": {
            "has_balance_baseline": runtime.ledger.last_balance is not None,
            "has_unit_price": runtime.ledger.unit_price is not None,
            "has_tracked_total": runtime.ledger.tracked_total_water is not None,
            "retained_day_count": len(runtime.ledger.days),
            "today_recharge_events": today.recharge_events,
            "today_balance_adjustments": today.balance_adjustments,
        },
        "details": {
            "has_total_water": bool(details and details.total_water is not None),
            "has_last_bill": bool(details and details.last_bill_amount is not None),
            "stale": bool(details and details.stale),
            "device_type": details.device_type if details else None,
        },
    }
