"""Persistent recharge-safe water usage ledger."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

ZERO = Decimal("0")
MONEY_EPSILON = Decimal("0.005")
WATER_EPSILON = Decimal("0.0005")


def _decimal(value: Any, default: Decimal | None = ZERO) -> Decimal | None:
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


@dataclass(slots=True)
class DailyRecord:
    """One local day's inferred usage."""

    water: Decimal = ZERO
    cost: Decimal = ZERO
    unpriced_cost: Decimal = ZERO
    recharge_minimum: Decimal = ZERO
    recharge_events: int = 0
    balance_adjustments: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "water": str(self.water),
            "cost": str(self.cost),
            "unpriced_cost": str(self.unpriced_cost),
            "recharge_minimum": str(self.recharge_minimum),
            "recharge_events": self.recharge_events,
            "balance_adjustments": self.balance_adjustments,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DailyRecord:
        return cls(
            water=_decimal(data.get("water")) or ZERO,
            cost=_decimal(data.get("cost")) or ZERO,
            unpriced_cost=_decimal(data.get("unpriced_cost")) or ZERO,
            recharge_minimum=_decimal(data.get("recharge_minimum")) or ZERO,
            recharge_events=_nonnegative_int(data.get("recharge_events")),
            balance_adjustments=_nonnegative_int(data.get("balance_adjustments")),
        )


@dataclass(slots=True)
class UsageLedger:
    """Track monotonic water usage while treating balance increases as recharge."""

    retention_days: int
    last_balance: Decimal | None = None
    unit_price: Decimal | None = None
    tracked_total_water: Decimal | None = None
    last_authoritative_total: Decimal | None = None
    inferred_since_authoritative: Decimal = ZERO
    days: dict[str, DailyRecord] = field(default_factory=dict)
    last_balance_at: str | None = None
    last_details_at: str | None = None

    def _day(self, local_day: date) -> DailyRecord:
        key = local_day.isoformat()
        if key not in self.days:
            self.days[key] = DailyRecord()
        return self.days[key]

    def current_day(self, local_day: date) -> DailyRecord:
        """Return the current daily record."""
        return self._day(local_day)

    def apply_balance(
        self,
        balance: Decimal,
        *,
        local_day: date,
        observed_at: datetime,
    ) -> None:
        """Apply a balance sample without ever subtracting inferred usage."""
        record = self._day(local_day)
        if self.last_balance is None:
            self.last_balance = balance
            self.last_balance_at = observed_at.isoformat()
            self._prune(local_day)
            return

        delta = self.last_balance - balance
        if delta > MONEY_EPSILON:
            record.cost += delta
            if self.unit_price is not None and self.unit_price > ZERO:
                water = delta / self.unit_price
                record.water += water
                self._add_tracked_water(water)
            else:
                record.unpriced_cost += delta
        elif delta < -MONEY_EPSILON:
            increase = -delta
            if record.recharge_events == 0:
                record.recharge_minimum += increase
                record.recharge_events = 1
            else:
                # The provider can make corrections, but the stated business rule
                # allows at most one actual recharge per day. Never treat either
                # event as negative consumption.
                record.balance_adjustments += 1

        self.last_balance = balance
        self.last_balance_at = observed_at.isoformat()
        self._prune(local_day)

    def apply_details(
        self,
        *,
        total_water: Decimal | None,
        total_water_amount: Decimal | None,
        last_bill_water: Decimal | None,
        last_bill_amount: Decimal | None,
        local_day: date,
        observed_at: datetime,
    ) -> None:
        """Apply an authoritative anchor and reconcile only missing increments."""
        price = self._derive_price(
            total_water=total_water,
            total_water_amount=total_water_amount,
            last_bill_water=last_bill_water,
            last_bill_amount=last_bill_amount,
        )
        if price is not None:
            self.unit_price = price
            self._backfill_unpriced_cost(price)

        if total_water is not None and total_water >= ZERO:
            if self.last_authoritative_total is None:
                if self.tracked_total_water is None:
                    self.tracked_total_water = total_water
                else:
                    self.tracked_total_water = max(
                        self.tracked_total_water, total_water
                    )
                self.last_authoritative_total = total_water
                self.inferred_since_authoritative = ZERO
            elif total_water >= self.last_authoritative_total:
                authoritative_delta = total_water - self.last_authoritative_total
                missing = authoritative_delta - self.inferred_since_authoritative
                if missing > WATER_EPSILON:
                    self._day(local_day).water += missing
                    self._add_tracked_water(missing, inferred=False)
                self.inferred_since_authoritative = max(
                    ZERO,
                    self.inferred_since_authoritative - authoritative_delta,
                )
                self.last_authoritative_total = total_water
            else:
                # Meter replacement/provider correction: preserve our monotonic
                # tracked total and start a new authoritative baseline.
                self.last_authoritative_total = total_water
                self.inferred_since_authoritative = ZERO

        self.last_details_at = observed_at.isoformat()
        self._prune(local_day)

    @staticmethod
    def _derive_price(
        *,
        total_water: Decimal | None,
        total_water_amount: Decimal | None,
        last_bill_water: Decimal | None,
        last_bill_amount: Decimal | None,
    ) -> Decimal | None:
        if (
            last_bill_water is not None
            and last_bill_water > ZERO
            and last_bill_amount is not None
            and last_bill_amount >= ZERO
        ):
            return last_bill_amount / last_bill_water
        if (
            total_water is not None
            and total_water > ZERO
            and total_water_amount is not None
            and total_water_amount >= ZERO
        ):
            return total_water_amount / total_water
        return None

    def _backfill_unpriced_cost(self, price: Decimal) -> None:
        if price <= ZERO:
            return
        for record in self.days.values():
            if record.unpriced_cost <= ZERO:
                continue
            water = record.unpriced_cost / price
            record.water += water
            record.unpriced_cost = ZERO
            self._add_tracked_water(water)

    def _add_tracked_water(self, water: Decimal, *, inferred: bool = True) -> None:
        if water <= ZERO:
            return
        if self.tracked_total_water is None:
            self.tracked_total_water = water
        else:
            self.tracked_total_water += water
        if inferred:
            self.inferred_since_authoritative += water

    def _prune(self, local_day: date) -> None:
        keep_after = local_day.toordinal() - self.retention_days
        self.days = {
            key: value
            for key, value in self.days.items()
            if _safe_date_ordinal(key) >= keep_after
        }

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-serializable private storage data."""
        return {
            "last_balance": _string_or_none(self.last_balance),
            "unit_price": _string_or_none(self.unit_price),
            "tracked_total_water": _string_or_none(self.tracked_total_water),
            "last_authoritative_total": _string_or_none(self.last_authoritative_total),
            "inferred_since_authoritative": str(self.inferred_since_authoritative),
            "days": {key: value.as_dict() for key, value in self.days.items()},
            "last_balance_at": self.last_balance_at,
            "last_details_at": self.last_details_at,
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any] | None, *, retention_days: int
    ) -> UsageLedger:
        """Restore a ledger, tolerating partial/corrupt legacy values."""
        if not isinstance(data, dict):
            return cls(retention_days=retention_days)
        raw_days = data.get("days")
        days: dict[str, DailyRecord] = {}
        if isinstance(raw_days, dict):
            for key, value in raw_days.items():
                if isinstance(key, str) and isinstance(value, dict):
                    days[key] = DailyRecord.from_dict(value)
        return cls(
            retention_days=retention_days,
            last_balance=_decimal(data.get("last_balance"), None),
            unit_price=_decimal(data.get("unit_price"), None),
            tracked_total_water=_decimal(data.get("tracked_total_water"), None),
            last_authoritative_total=_decimal(
                data.get("last_authoritative_total"), None
            ),
            inferred_since_authoritative=_decimal(
                data.get("inferred_since_authoritative")
            )
            or ZERO,
            days=days,
            last_balance_at=data.get("last_balance_at"),
            last_details_at=data.get("last_details_at"),
        )


def _safe_date_ordinal(value: str) -> int:
    try:
        return date.fromisoformat(value).toordinal()
    except ValueError:
        return 0


def _string_or_none(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
