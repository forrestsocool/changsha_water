"""Pure API helper tests without importing Home Assistant."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parents[1]
PACKAGE_PATH = ROOT / "custom_components" / "changsha_water"
PACKAGE_NAME = "custom_components.changsha_water"

package = ModuleType(PACKAGE_NAME)
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault(PACKAGE_NAME, package)

for module_name in ("const", "api"):
    full_name = f"{PACKAGE_NAME}.{module_name}"
    spec = importlib.util.spec_from_file_location(
        full_name, PACKAGE_PATH / f"{module_name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)

api = sys.modules[f"{PACKAGE_NAME}.api"]


def test_signature_matches_documented_algorithm() -> None:
    timestamp = "1780000000"
    token = "test-token"
    nonce = "ABCDEFGH2345678x"
    expected = (
        hashlib.sha256(f"{timestamp}{token}{nonce}{timestamp}".encode())
        .hexdigest()
        .upper()
    )

    assert api.generate_signature(timestamp, token, nonce) == expected


def test_authenticated_error_code_is_token_problem() -> None:
    payload = {"Code": 10000, "SubCode": 40102, "Data": ""}
    with pytest.raises(api.ChangshaWaterAuthError):
        api.ChangshaWaterApi._data_or_raise(payload, authenticated=True)


def test_stale_details_keep_only_sanitized_fields() -> None:
    details = api.WaterDetails(
        previous_water_quantity=Decimal("10"),
        last_bill_water=Decimal("2"),
        last_bill_amount=Decimal("6.54"),
        total_water=Decimal("12"),
        total_water_amount=Decimal("39.24"),
        api_balance=Decimal("100"),
        device_type="远传水表",
        device_size="20",
    )

    stale = api.WaterDetails.unavailable(details)
    assert stale.total_water == Decimal("12")
    assert stale.auth_valid is False
    assert stale.stale is True


def test_balance_data_tracks_local_day_for_daily_reset() -> None:
    data = api.BalanceData(
        balance=Decimal("100"),
        owed_amount=Decimal("0"),
        penalty=Decimal("0"),
        payment_allowed=True,
        local_day=date(2026, 7, 23),
    )
    assert data.local_day.isoformat() == "2026-07-23"
