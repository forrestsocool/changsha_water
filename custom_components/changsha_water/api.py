"""Async API client for Changsha Water."""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout

from .const import (
    APP_ID,
    AUTH_ERROR_CODES,
    BALANCE_URL,
    DETAILS_URL,
    MOBILE_ORIGIN,
    SUCCESS_CODE,
)

_NONCE_ALPHABET: Final = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"
_REQUEST_TIMEOUT: Final = ClientTimeout(total=25)


class ChangshaWaterApiError(Exception):
    """Base API error."""


class ChangshaWaterAuthError(ChangshaWaterApiError):
    """Token is expired or lacks permission."""


class ChangshaWaterMeterNotFound(ChangshaWaterApiError):
    """Configured meter is not linked to the supplied user."""


class ChangshaWaterInvalidResponse(ChangshaWaterApiError):
    """The server response cannot be parsed safely."""


def _as_decimal(value: Any, field: str) -> Decimal:
    """Convert an API value to Decimal."""
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, ValueError) as err:
        raise ChangshaWaterInvalidResponse(f"Invalid numeric field: {field}") from err


def _optional_decimal(value: Any, field: str) -> Decimal | None:
    """Convert an optional API value to Decimal."""
    if value in (None, ""):
        return None
    return _as_decimal(value, field)


def generate_nonce(length: int = 16) -> str:
    """Return a cryptographically strong API nonce."""
    return "".join(secrets.choice(_NONCE_ALPHABET) for _ in range(length))


def generate_signature(timestamp: str, token: str, nonce: str) -> str:
    """Generate the TIF SHA-256 signature used by both endpoints."""
    raw = f"{timestamp}{token}{nonce}{timestamp}".encode()
    return hashlib.sha256(raw).hexdigest().upper()


@dataclass(frozen=True, slots=True)
class BalanceData:
    """Sanitized balance response."""

    balance: Decimal
    owed_amount: Decimal
    penalty: Decimal
    payment_allowed: bool
    local_day: date


@dataclass(frozen=True, slots=True)
class WaterDetails:
    """Sanitized detailed meter response."""

    previous_water_quantity: Decimal | None
    last_bill_water: Decimal | None
    last_bill_amount: Decimal | None
    total_water: Decimal | None
    total_water_amount: Decimal | None
    api_balance: Decimal | None
    device_type: str | None
    device_size: str | None
    auth_valid: bool = True
    stale: bool = False

    @classmethod
    def unavailable(cls, previous: WaterDetails | None = None) -> WaterDetails:
        """Return a stale snapshot without exposing API payload data."""
        if previous is not None:
            return cls(
                previous_water_quantity=previous.previous_water_quantity,
                last_bill_water=previous.last_bill_water,
                last_bill_amount=previous.last_bill_amount,
                total_water=previous.total_water,
                total_water_amount=previous.total_water_amount,
                api_balance=previous.api_balance,
                device_type=previous.device_type,
                device_size=previous.device_size,
                auth_valid=False,
                stale=True,
            )
        return cls(
            previous_water_quantity=None,
            last_bill_water=None,
            last_bill_amount=None,
            total_water=None,
            total_water_amount=None,
            api_balance=None,
            device_type=None,
            device_size=None,
            auth_valid=False,
            stale=True,
        )


class ChangshaWaterApi:
    """Client for the public balance and authenticated meter APIs."""

    def __init__(
        self,
        session: ClientSession,
        meter_number: str,
        user_id: str,
        token: str,
    ) -> None:
        self._session = session
        self._meter_number = meter_number.strip()
        self._user_id = user_id.strip()
        self._token = token.strip()

    @property
    def meter_number(self) -> str:
        """Return the configured meter number."""
        return self._meter_number

    def update_credentials(self, user_id: str, token: str) -> None:
        """Update credentials after reauthentication."""
        self._user_id = user_id.strip()
        self._token = token.strip()

    def _headers(self, token: str, login_user_id: str) -> dict[str, str]:
        timestamp = str(int(time.time()))
        nonce = generate_nonce()
        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": MOBILE_ORIGIN,
            "Referer": f"{MOBILE_ORIGIN}/",
            "User-Agent": "HomeAssistant/ChangshaWater",
            "x-tif-appid": APP_ID,
            "x-tif-loginUserid": login_user_id,
            "x-tif-token": token,
            "x-tif-timestamp": timestamp,
            "x-tif-nonce": nonce,
            "x-tif-sign": generate_signature(timestamp, token, nonce),
        }

    async def _post(
        self,
        url: str,
        body: dict[str, Any],
        *,
        token: str,
        login_user_id: str,
    ) -> dict[str, Any]:
        try:
            async with self._session.post(
                url,
                headers=self._headers(token, login_user_id),
                json=body,
                timeout=_REQUEST_TIMEOUT,
            ) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except ClientResponseError as err:
            raise ChangshaWaterApiError(f"HTTP error {err.status}") from err
        except ClientError as err:
            raise ChangshaWaterApiError("Unable to reach the water service") from err
        except (ValueError, TypeError) as err:
            raise ChangshaWaterInvalidResponse("Server returned invalid JSON") from err

        if not isinstance(payload, dict):
            raise ChangshaWaterInvalidResponse("Server returned an invalid object")
        return payload

    @staticmethod
    def _data_or_raise(payload: dict[str, Any], *, authenticated: bool) -> Any:
        try:
            code = int(payload.get("Code"))
            sub_code = int(payload.get("SubCode"))
        except (TypeError, ValueError) as err:
            raise ChangshaWaterInvalidResponse("Missing API status code") from err

        if authenticated and sub_code in AUTH_ERROR_CODES:
            raise ChangshaWaterAuthError("The saved token is expired or unauthorized")
        if code != SUCCESS_CODE or sub_code != SUCCESS_CODE:
            raise ChangshaWaterApiError(f"Water service error ({sub_code})")
        return payload.get("Data")

    async def async_get_balance(self, local_day: date) -> BalanceData:
        """Fetch the high-frequency, token-free balance."""
        payload = await self._post(
            BALANCE_URL,
            {"water_meterno": self._meter_number},
            token="",
            login_user_id="0",
        )
        data = self._data_or_raise(payload, authenticated=False)
        if not isinstance(data, dict):
            raise ChangshaWaterInvalidResponse("Balance data is missing")

        returned_meter = str(data.get("water_meterno") or "").strip()
        if returned_meter and returned_meter != self._meter_number:
            raise ChangshaWaterInvalidResponse("Balance response meter mismatch")

        return BalanceData(
            balance=_as_decimal(data.get("balance"), "balance"),
            owed_amount=_as_decimal(data.get("oweamt", 0), "oweamt"),
            penalty=_as_decimal(data.get("penalty", 0), "penalty"),
            payment_allowed=str(data.get("pay_permission", "")).lower()
            in {"1", "true", "yes"},
            local_day=local_day,
        )

    async def async_get_details(self) -> WaterDetails:
        """Fetch authenticated meter details and locate the configured meter."""
        if not self._user_id.isdigit():
            raise ChangshaWaterAuthError("User ID must contain digits only")

        page = 1
        while page <= 20:
            payload = await self._post(
                DETAILS_URL,
                {
                    "loginId": int(self._user_id),
                    "pageIndex": page,
                    "pageSize": 20,
                },
                token=self._token,
                login_user_id=self._user_id,
            )
            data = self._data_or_raise(payload, authenticated=True)
            if not isinstance(data, dict):
                raise ChangshaWaterInvalidResponse("Meter details are missing")

            rows = data.get("rows")
            if not isinstance(rows, list):
                raise ChangshaWaterInvalidResponse("Meter detail rows are invalid")

            for row in rows:
                if not isinstance(row, dict):
                    continue
                if str(row.get("waterNumber") or "").strip() == self._meter_number:
                    return WaterDetails(
                        previous_water_quantity=_optional_decimal(
                            row.get("prevWaterQuantity"), "prevWaterQuantity"
                        ),
                        last_bill_water=_optional_decimal(
                            row.get("last_water"), "last_water"
                        ),
                        last_bill_amount=_optional_decimal(
                            row.get("last_amount"), "last_amount"
                        ),
                        total_water=_optional_decimal(
                            row.get("total_water"), "total_water"
                        ),
                        total_water_amount=_optional_decimal(
                            row.get("total_water_amount"), "total_water_amount"
                        ),
                        api_balance=_optional_decimal(row.get("balance"), "balance"),
                        device_type=str(row.get("waterDeviceType") or "").strip()
                        or None,
                        device_size=str(row.get("waterDeviceSize") or "").strip()
                        or None,
                    )

            try:
                total_pages = max(1, int(data.get("totalPages", 1)))
            except (TypeError, ValueError) as err:
                raise ChangshaWaterInvalidResponse("Invalid page count") from err
            if page >= total_pages:
                break
            page += 1

        raise ChangshaWaterMeterNotFound(
            "The meter is not linked to the supplied user ID"
        )
