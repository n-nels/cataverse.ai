"""Kasa cloud power-control adapter for the hardware layer.

This module ports Kasa smart-plug login and relay-state control behavior from
legacy scripts into a typed class suitable for injected use by controllers.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from src.core.config_loader import KasaConfig
from src.hardware.errors import HardwareConnectionError


logger = logging.getLogger(__name__)


class KasaPower:
    """Kasa cloud power-switching helper."""

    def __init__(self, credentials: KasaConfig) -> None:
        self.credentials = credentials
        self.endpoints = [
            "https://use1-wap.tplinkcloud.com",
            "https://wap.tplinkcloud.com",
        ]
        self.username = (
            credentials.username
            or os.getenv("KASA_USERNAME")
        )
        self.password = (
            credentials.password
            or os.getenv("KASA_PASSWORD")
        )
        self.token: str | None = None
        self.url: str | None = None

    def login(self) -> bool:
        """Log in to Kasa cloud and cache auth token/url."""

        if not self.username or not self.password:
            raise HardwareConnectionError(
                "Kasa credentials not configured. "
                "Set username/password in KasaConfig or KASA_USERNAME/KASA_PASSWORD env vars."
            )

        self.token = None
        self.url = None

        payload = {
            "method": "login",
            "params": {
                "appType": "Kasa_iOS",
                "cloudUserName": self.username,
                "cloudPassword": self.password,
                "terminalUUID": "test-uuid",
            },
        }

        for endpoint in self.endpoints:
            try:
                response = requests.post(endpoint, json=payload, timeout=10)
                response_json = response.json()
                if response_json.get("error_code") == 0:
                    self.token = response_json["result"]["token"]
                    self.url = endpoint
                    return True

                error_msg = response_json.get("msg", "Unknown error")
                logger.error("Kasa login failed: %s", error_msg)
            except Exception as exc:
                logger.error("Kasa login error with endpoint %s: %s", endpoint, exc)

        logger.error("All Kasa endpoints failed. Unable to log in.")
        return False

    def set_state(self, device_id: str, on: bool) -> dict[str, Any]:
        """Set smart-plug relay state for the given device ID.

        Uses a cached auth token when available.  On auth failure (non-zero
        ``error_code``), re-authenticates once and retries.
        """

        if self.token is None:
            logger.info("No cached Kasa token — logging in.")
            if not self.login():
                logger.error("Unable to log in. Cannot control Kasa device.")
                return {}

        result = self._send_control(device_id, on)

        # Re-authenticate once on auth failure
        error_code = result.get("error_code")
        if error_code is not None and error_code != 0:
            logger.warning(
                "Kasa control returned error_code %s — re-authenticating.", error_code
            )
            if not self.login():
                logger.error("Re-login failed. Cannot control Kasa device.")
                return {}
            result = self._send_control(device_id, on)

        return result

    def _send_control(self, device_id: str, on: bool) -> dict[str, Any]:
        """Send a relay-state control request using the cached token."""

        payload = {
            "method": "passthrough",
            "params": {
                "deviceId": device_id,
                "requestData": {
                    "system": {"set_relay_state": {"state": 1 if on else 0}},
                },
            },
        }

        try:
            device_url = f"{self.url}?token={self.token}"
            response = requests.post(device_url, json=payload, timeout=10)
            return response.json()
        except Exception as exc:
            logger.error("Kasa control error: %s", exc)
            return {}
