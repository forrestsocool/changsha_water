"""Binary sensors for Changsha Water."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ChangshaWaterConfigEntry
from .coordinator import BalanceCoordinator, DetailsCoordinator
from .entity import device_info, meter_fingerprint


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChangshaWaterConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up water account binary sensors."""
    async_add_entities(
        [
            ChangshaWaterTokenProblem(entry),
            ChangshaWaterPaymentAllowed(entry),
        ]
    )


class ChangshaWaterTokenProblem(
    CoordinatorEntity[DetailsCoordinator], BinarySensorEntity
):
    """Indicate that detailed data needs a fresh token."""

    _attr_has_entity_name = True
    _attr_translation_key = "token_problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:key-alert-outline"

    def __init__(self, entry: ChangshaWaterConfigEntry) -> None:
        super().__init__(entry.runtime_data.details_coordinator)
        self.entry = entry
        self._attr_unique_id = f"{meter_fingerprint(entry)}_token_problem"
        self._attr_device_info = device_info(entry)

    @property
    def is_on(self) -> bool:
        """Return true when details are using stale/fallback data."""
        return not self.entry.runtime_data.auth_valid


class ChangshaWaterPaymentAllowed(
    CoordinatorEntity[BalanceCoordinator], BinarySensorEntity
):
    """Expose the payment permission returned by the balance endpoint."""

    _attr_has_entity_name = True
    _attr_translation_key = "payment_allowed"
    _attr_icon = "mdi:credit-card-check-outline"

    def __init__(self, entry: ChangshaWaterConfigEntry) -> None:
        super().__init__(entry.runtime_data.balance_coordinator)
        self.entry = entry
        self._attr_unique_id = f"{meter_fingerprint(entry)}_payment_allowed"
        self._attr_device_info = device_info(entry)

    @property
    def is_on(self) -> bool | None:
        """Return whether the provider currently permits payment."""
        data = self.coordinator.data
        return None if data is None else data.payment_allowed
