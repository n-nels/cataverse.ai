"""ZeroMQ spectrometer messaging adapter for the hardware layer.

This module ports OPUS/ZeroMQ request-reply behavior from legacy networking
code while accepting an injected socket.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, cast

import zmq


logger = logging.getLogger(__name__)


class OpusSpectrometer:
    """OPUS spectrometer request-reply wrapper over an injected ZeroMQ socket."""

    def __init__(self, socket: zmq.Socket) -> None:
        self.socket = socket
        self._context = socket.context
        self._endpoint: str | None = self._get_last_endpoint()
        self._rcv_timeout_ms = cast(int, socket.getsockopt(zmq.RCVTIMEO))

    def _get_last_endpoint(self) -> str | None:
        """Read socket's last endpoint when available."""

        try:
            endpoint = self.socket.getsockopt_string(zmq.LAST_ENDPOINT)
            return endpoint or None
        except Exception:
            return None

    def connect(self, endpoint: str) -> None:
        """Connect socket to an endpoint and store for reconnection."""

        self._endpoint = endpoint
        self.socket.connect(endpoint)
        logger.info("Connected to %s", endpoint)

    def reconnect(self) -> None:
        """Reconnect REQ socket using stored endpoint and timeout settings."""

        if self._endpoint is None:
            self._endpoint = self._get_last_endpoint()

        logger.warning("Reconnecting socket...")
        try:
            self.socket.setsockopt(zmq.LINGER, 0)
            self.socket.close()
            time.sleep(0.5)
            logger.info("Socket closed")
        except Exception as exc:
            logger.error("Error closing socket: %s", exc)

        logger.info("Creating new socket...")
        self.socket = self._context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, self._rcv_timeout_ms)
        if self._endpoint is not None:
            self.socket.connect(self._endpoint)
            logger.info("Socket reconnected successfully")
        else:
            logger.error("No endpoint available; socket could not reconnect.")

    def send(self, message: dict[str, Any]) -> dict[str, Any]:
        """Send one JSON request and return one parsed reply dictionary."""

        message_json = json.dumps(message)
        try:
            self.socket.send_string(message_json)
            logger.info("Sent message: %s", message_json)
        except zmq.ZMQError as exc:
            error_msg = str(exc)
            logger.error("Failed to send message: %s", error_msg)
            if "current state" in error_msg.lower() or "fsm" in error_msg.lower():
                logger.warning("Socket in invalid state detected - attempting auto-recovery...")
                try:
                    self.reconnect()
                    logger.info("Retrying message send...")
                    self.socket.send_string(message_json)
                    logger.info("Message sent successfully after reconnection: %s", message_json)
                except Exception as retry_err:
                    logger.error("Reconnection and retry failed: %s", retry_err)
                    return {}
            else:
                return {}

        try:
            reply_raw = self.socket.recv_string()
        except zmq.Again:
            timeout_sec = self._rcv_timeout_ms / 1000
            logger.warning(
                "Receive timeout: No response from server after %.1f seconds", timeout_sec
            )
            logger.warning("Socket in invalid state - connection is corrupted")
            logger.warning("Next send will trigger automatic reconnection")
            return {}
        except zmq.ZMQError as exc:
            logger.error("Failed to receive message: %s", exc)
            return {}
        except KeyboardInterrupt:
            logger.warning("Program interrupted by user. Exiting.")
            return {}

        try:
            reply = json.loads(reply_raw)
            return reply if isinstance(reply, dict) else {"reply": reply}
        except json.JSONDecodeError:
            return {"reply": reply_raw}

    def send_message(self, message: dict[str, Any]) -> bool:
        """Compatibility send method that mirrors legacy boolean semantics."""

        message_json = json.dumps(message)
        try:
            self.socket.send_string(message_json)
            logger.info("Sent message: %s", message_json)
            return True
        except zmq.ZMQError as exc:
            error_msg = str(exc)
            logger.error("Failed to send message: %s", error_msg)

            if "current state" in error_msg.lower() or "fsm" in error_msg.lower():
                logger.warning("Socket in invalid state detected - attempting auto-recovery...")
                try:
                    self.reconnect()
                    logger.info("Retrying message send...")
                    self.socket.send_string(message_json)
                    logger.info("Message sent successfully after reconnection: %s", message_json)
                    return True
                except Exception as retry_err:
                    logger.error("Reconnection and retry failed: %s", retry_err)
                    return False
            return False

    def receive_message(self, timeout_ms: int | None = None) -> str:
        """Compatibility receive method that mirrors legacy string semantics."""

        old_timeout: int | None = None
        try:
            if timeout_ms is not None:
                old_timeout = cast(int, self.socket.getsockopt(zmq.RCVTIMEO))
                self.socket.setsockopt(zmq.RCVTIMEO, timeout_ms)

            message = self.socket.recv_string()

            if timeout_ms is not None and old_timeout is not None:
                self.socket.setsockopt(zmq.RCVTIMEO, old_timeout)

            return message
        except zmq.Again:
            timeout_sec = (timeout_ms if timeout_ms else self._rcv_timeout_ms) / 1000
            logger.warning(
                "Receive timeout: No response from server after %.1f seconds", timeout_sec
            )
            logger.warning("Socket in invalid state - connection is corrupted")
            logger.warning("Next send will trigger automatic reconnection")
            return ""
        except zmq.ZMQError as exc:
            logger.error("Failed to receive message: %s", exc)
            return ""
        except KeyboardInterrupt:
            logger.warning("Program interrupted by user. Exiting.")
            return ""
