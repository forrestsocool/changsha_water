"""Sensors for Changsha Water."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import ChangshaWaterConfigEntry
from .api import WaterDetails
from .coordinator import BalanceCoordinator, DetailsCoordinator
from .entity import compact_decimal, device_info, meter_fingerprint

CURRENCY = "CNY"
UNIT_PRICE = "CNY/m³"


@dataclass(frozen=True, kw_only=True)
class ChangshaWaterSensorDescription(SensorEntityDescription):
    """Describe a sensor and its value source."""

    value_fn: Callable[[ChangshaWaterConfigEntry], Any]
    coordinator: str = "balance"


def _today(entry: ChangshaWaterConfigEntry) -> Any:
    return entry.runtime_data.ledger.current_day(dt_util.now().date())


SENSORS: tuple[ChangshaWaterSensorDescription, ...] = (
    ChangshaWaterSensorDescription(
        key="balance",
        translation_key="balance",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wallet-outline",
        value_fn=lambda entry: compact_decimal(
            entry.runtime_data.balance_coordinator.data.balance
            if entry.runtime_data.balance_coordinator.data
            else None,
            "0.01",
        ),
    ),
    ChangshaWaterSensorDescription(
        key="estimated_total_water",
        translation_key="estimated_total_water",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:water",
        value_fn=lambda entry: compact_decimal(
            entry.runtime_data.ledger.tracked_total_water, "0.001"
        ),
    ),
    ChangshaWaterSensorDescription(
        key="owed_amount",
        translation_key="owed_amount",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cash-minus",
        value_fn=lambda entry: compact_decimal(
            entry.runtime_data.balance_coordinator.data.owed_amount
            if entry.runtime_data.balance_coordinator.data
            else None,
            "0.01",
        ),
    ),
    ChangshaWaterSensorDescription(
        key="penalty",
        translation_key="penalty",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:alert-circle-outline",
        value_fn=lambda entry: compact_decimal(
            entry.runtime_data.balance_coordinator.data.penalty
            if entry.runtime_data.balance_coordinator.data
            else None,
            "0.01",
        ),
    ),
    ChangshaWaterSensorDescription(
        key="daily_water",
        translation_key="daily_water",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:water-check-outline",
        value_fn=lambda entry: compact_decimal(_today(entry).water, "0.001"),
    ),
    ChangshaWaterSensorDescription(
        key="daily_cost",
        translation_key="daily_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:cash-clock",
        value_fn=lambda entry: compact_decimal(_today(entry).cost, "0.01"),
    ),
    ChangshaWaterSensorDescription(
        key="recharge_today",
        translation_key="recharge_today",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:cash-plus",
        value_fn=lambda entry: compact_decimal(_today(entry).recharge_minimum, "0.01"),
    ),
    ChangshaWaterSensorDescription(
        key="unit_price",
        translation_key="unit_price",
        native_unit_of_measurement=UNIT_PRICE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cash-multiple",
        value_fn=lambda entry: compact_decimal(
            entry.runtime_data.ledger.unit_price, "0.0001"
        ),
    ),
    ChangshaWaterSensorDescription(
        key="authoritative_total_water",
        translation_key="authoritative_total_water",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:counter",
        coordinator="details",
        value_fn=lambda entry: compact_decimal(
            _detail_value(entry, "total_water"), "0.001"
        ),
    ),
    ChangshaWaterSensorDescription(
        key="last_bill_water",
        translation_key="last_bill_water",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:receipt-text-outline",
        coordinator="details",
        value_fn=lambda entry: compact_decimal(
            _detail_value(entry, "last_bill_water"), "0.001"
        ),
    ),
    ChangshaWaterSensorDescription(
        key="last_bill_amount",
        translation_key="last_bill_amount",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:receipt-text-outline",
        coordinator="details",
        value_fn=lambda entry: compact_decimal(
            _detail_value(entry, "last_bill_amount"), "0.01"
        ),
    ),
    ChangshaWaterSensorDescription(
        key="total_water_amount",
        translation_key="total_water_amount",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:cash-sync",
        coordinator="details",
        value_fn=lambda entry: compact_decimal(
            _detail_value(entry, "total_water_amount"), "0.01"
        ),
    ),
    ChangshaWaterSensorDescription(
        key="previous_water_quantity",
        translation_key="previous_water_quantity",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:history",
        coordinator="details",
        entity_registry_enabled_default=False,
        value_fn=lambda entry: compact_decimal(
            _detail_value(entry, "previous_water_quantity"), "0.001"
        ),
    ),
)


def _detail_value(entry: ChangshaWaterConfigEntry, key: str) -> Decimal | None:
    details: WaterDetails | None = entry.runtime_data.details_coordinator.data
    return None if details is None else getattr(details, key)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChangshaWaterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up water sensors."""
    async_add_entities(
        ChangshaWaterSensor(entry, description) for description in SENSORS
    )


class ChangshaWaterSensor(
    CoordinatorEntity[BalanceCoordinator | DetailsCoordinator], SensorEntity
):
    """Representation of one water account sensor."""

    _attr_has_entity_name = True
    entity_description: ChangshaWaterSensorDescription

    def __init__(
        self,
        entry: ChangshaWaterConfigEntry,
        description: ChangshaWaterSensorDescription,
    ) -> None:
        coordinator = (
            entry.runtime_data.details_coordinator
            if description.coordinator == "details"
            else entry.runtime_data.balance_coordinator
        )
        super().__init__(coordinator)
        self.entry = entry
        self.entity_description = description
        self._attr_unique_id = f"{meter_fingerprint(entry)}_{description.key}"
        self._attr_device_info = device_info(entry)

    @property
    def native_value(self) -> Any:
        """Return an in-memory value only."""
        return self.entity_description.value_fn(self.entry)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose only non-sensitive calculation metadata."""
        if self.entity_description.key not in {
            "daily_water",
            "daily_cost",
            "recharge_today",
            "estimated_total_water",
        }:
            return None
        ledger = self.entry.runtime_data.ledger
        today = ledger.current_day(dt_util.now().date())
        attrs: dict[str, Any] = {
            "calculation_mode": (
                "authoritative"
                if self.entry.runtime_data.auth_valid
                else "balance_estimate"
            ),
            "token_details_available": self.entry.runtime_data.auth_valid,
        }
        if self.entity_description.key == "recharge_today":
            attrs["recharge_events"] = today.recharge_events
            attrs["balance_adjustments"] = today.balance_adjustments
            attrs["estimate_is_minimum"] = True
        return attrs
