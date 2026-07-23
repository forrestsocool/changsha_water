"""Tests for recharge-safe water usage inference."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[1] / "custom_components" / "changsha_water" / "ledger.py"
)
SPEC = importlib.util.spec_from_file_location("changsha_water_ledger", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
ledger_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ledger_module
SPEC.loader.exec_module(ledger_module)
UsageLedger = ledger_module.UsageLedger

DAY = date(2026, 7, 23)
NOW = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)


def test_recharge_never_creates_negative_usage() -> None:
    ledger = UsageLedger(retention_days=90, unit_price=Decimal("3.27"))
    ledger.apply_balance(Decimal("100"), local_day=DAY, observed_at=NOW)
    ledger.apply_balance(Decimal("96.73"), local_day=DAY, observed_at=NOW)
    ledger.apply_balance(Decimal("196.73"), local_day=DAY, observed_at=NOW)

    today = ledger.current_day(DAY)
    assert today.cost == Decimal("3.27")
    assert today.water == Decimal("1")
    assert today.recharge_minimum == Decimal("100.00")
    assert today.recharge_events == 1
    assert ledger.tracked_total_water == Decimal("1")


def test_second_balance_increase_is_adjustment_not_negative_consumption() -> None:
    ledger = UsageLedger(retention_days=90, unit_price=Decimal("3.27"))
    ledger.apply_balance(Decimal("10"), local_day=DAY, observed_at=NOW)
    ledger.apply_balance(Decimal("60"), local_day=DAY, observed_at=NOW)
    ledger.apply_balance(Decimal("60.50"), local_day=DAY, observed_at=NOW)

    today = ledger.current_day(DAY)
    assert today.recharge_events == 1
    assert today.balance_adjustments == 1
    assert today.cost == 0
    assert today.water == 0


def test_token_outage_uses_last_known_price() -> None:
    ledger = UsageLedger(retention_days=90)
    ledger.apply_details(
        total_water=Decimal("113"),
        total_water_amount=Decimal("369.51"),
        last_bill_water=Decimal("30"),
        last_bill_amount=Decimal("98.1"),
        local_day=DAY,
        observed_at=NOW,
    )
    ledger.apply_balance(Decimal("116.37"), local_day=DAY, observed_at=NOW)
    ledger.apply_balance(Decimal("113.10"), local_day=DAY, observed_at=NOW)

    assert ledger.unit_price == Decimal("3.27")
    assert ledger.current_day(DAY).water == Decimal("1")
    assert ledger.tracked_total_water == Decimal("114")


def test_authoritative_catch_up_is_not_double_counted() -> None:
    ledger = UsageLedger(retention_days=90)
    ledger.apply_details(
        total_water=Decimal("113"),
        total_water_amount=Decimal("369.51"),
        last_bill_water=Decimal("30"),
        last_bill_amount=Decimal("98.1"),
        local_day=DAY,
        observed_at=NOW,
    )
    ledger.apply_balance(Decimal("116.37"), local_day=DAY, observed_at=NOW)
    ledger.apply_balance(Decimal("113.10"), local_day=DAY, observed_at=NOW)
    ledger.apply_details(
        total_water=Decimal("114"),
        total_water_amount=Decimal("372.78"),
        last_bill_water=Decimal("30"),
        last_bill_amount=Decimal("98.1"),
        local_day=DAY,
        observed_at=NOW,
    )

    assert ledger.current_day(DAY).water == Decimal("1")
    assert ledger.tracked_total_water == Decimal("114")
    assert ledger.inferred_since_authoritative == 0


def test_authoritative_details_fill_missing_usage() -> None:
    ledger = UsageLedger(retention_days=90)
    ledger.apply_details(
        total_water=Decimal("113"),
        total_water_amount=Decimal("369.51"),
        last_bill_water=Decimal("30"),
        last_bill_amount=Decimal("98.1"),
        local_day=DAY,
        observed_at=NOW,
    )
    ledger.apply_details(
        total_water=Decimal("115"),
        total_water_amount=Decimal("376.05"),
        last_bill_water=Decimal("30"),
        last_bill_amount=Decimal("98.1"),
        local_day=DAY,
        observed_at=NOW,
    )

    assert ledger.current_day(DAY).water == Decimal("2")
    assert ledger.tracked_total_water == Decimal("115")


def test_unpriced_cost_is_backfilled_when_details_return() -> None:
    ledger = UsageLedger(retention_days=90)
    ledger.apply_balance(Decimal("20"), local_day=DAY, observed_at=NOW)
    ledger.apply_balance(Decimal("16.73"), local_day=DAY, observed_at=NOW)
    assert ledger.current_day(DAY).water == 0
    assert ledger.current_day(DAY).unpriced_cost == Decimal("3.27")

    ledger.apply_details(
        total_water=Decimal("10"),
        total_water_amount=Decimal("32.7"),
        last_bill_water=None,
        last_bill_amount=None,
        local_day=DAY,
        observed_at=NOW,
    )

    assert ledger.current_day(DAY).water == Decimal("1")
    assert ledger.current_day(DAY).unpriced_cost == 0
    assert ledger.tracked_total_water == Decimal("10")


def test_storage_round_trip() -> None:
    ledger = UsageLedger(retention_days=90, unit_price=Decimal("3.27"))
    ledger.apply_balance(Decimal("10"), local_day=DAY, observed_at=NOW)
    ledger.apply_balance(Decimal("6.73"), local_day=DAY, observed_at=NOW)
    restored = UsageLedger.from_dict(ledger.as_dict(), retention_days=90)

    assert restored.as_dict() == ledger.as_dict()
