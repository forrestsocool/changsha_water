"""Shared entity helpers."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

from . import ChangshaWaterConfigEntry
from .const import CONF_METER_NUMBER, DOMAIN


def meter_fingerprint(entry: ChangshaWaterConfigEntry) -> str:
    """Return a non-reversible meter identifier."""
    meter = str(entry.data[CONF_METER_NUMBER])
    return sha256(meter.encode()).hexdigest()[:24]


def masked_meter(entry: ChangshaWaterConfigEntry) -> str:
    """Mask a meter number for display."""
    meter = str(entry.data[CONF_METER_NUMBER])
    if len(meter) <= 4:
        return "****"
    return f"****{meter[-4:]}"


def device_info(entry: ChangshaWaterConfigEntry) -> DeviceInfo:
    """Return privacy-preserving device metadata."""
    details = entry.runtime_data.details_coordinator.data
    model = "水费账户"
    if details is not None and details.device_type:
        model = details.device_type
    return DeviceInfo(
        identifiers={(DOMAIN, meter_fingerprint(entry))},
        name=f"长沙水费 {masked_meter(entry)}",
        manufacturer="长沙供水",
        model=model,
        serial_number=masked_meter(entry),
        configuration_url="https://mobile.supplywater.com/",
    )


def compact_decimal(value: Any, places: str) -> float | None:
    """Convert Decimal-like values to recorder-friendly floats."""
    if value is None:
        return None
    return float(value.quantize(type(value)(places)))
