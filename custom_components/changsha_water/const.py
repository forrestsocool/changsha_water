"""Constants for the Changsha Water integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "changsha_water"
NAME: Final = "长沙水费"

CONF_METER_NUMBER: Final = "meter_number"
CONF_USER_ID: Final = "user_id"
CONF_TOKEN: Final = "token"
CONF_BALANCE_INTERVAL: Final = "balance_interval"
CONF_DETAILS_INTERVAL: Final = "details_interval"
CONF_RETENTION_DAYS: Final = "retention_days"

DEFAULT_BALANCE_INTERVAL_MINUTES: Final = 5
DEFAULT_DETAILS_INTERVAL_MINUTES: Final = 360
DEFAULT_RETENTION_DAYS: Final = 90

MIN_BALANCE_INTERVAL_MINUTES: Final = 1
MAX_BALANCE_INTERVAL_MINUTES: Final = 60
MIN_DETAILS_INTERVAL_MINUTES: Final = 30
MAX_DETAILS_INTERVAL_MINUTES: Final = 1440
MIN_RETENTION_DAYS: Final = 7
MAX_RETENTION_DAYS: Final = 366

APP_ID: Final = "handheld"
API_BASE_URL: Final = "https://smartgate.supplywater.com"
BALANCE_URL: Final = f"{API_BASE_URL}/WFTPay/JSAPI/balanceInfo"
DETAILS_URL: Final = f"{API_BASE_URL}/BasicsApi/MarkData/WaterPointPaymentsPaging"
MOBILE_ORIGIN: Final = "https://mobile.supplywater.com"

STORAGE_VERSION: Final = 1
STORAGE_SAVE_DELAY_SECONDS: Final = 15

AUTH_ERROR_CODES: Final = {40102, 40103}
SUCCESS_CODE: Final = 10000

NOTIFICATION_ID_PREFIX: Final = f"{DOMAIN}_token_expired"
ISSUE_ID_PREFIX: Final = "token_expired"
DOCUMENTATION_URL: Final = "https://github.com/forrestsocool/changsha_water"
