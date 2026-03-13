## network_messaging.py

import json
import logging
import time
from typing import Any

import zmq

from ..core.config import opus_default_ip, opus_default_port, zmq_receive_timeout_ms


logger = logging.getLogger(__name__)


class NetworkMessaging:
    """Class to handle network messaging using ZeroMQ."""

    def __init__(
        self,
        context: zmq.Context | None = None,
        rcv_timeout: int = zmq_receive_timeout_ms,
    ):
        """Initializes the NetworkMessaging with a ZeroMQ context.

        Args:
            context: An optional ZeroMQ context. If not provided, a new context will be created.
            rcv_timeout: Receive timeout in milliseconds (default 300000 milliseconds)
        """
        self.context = context if context is not None else zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, rcv_timeout)  # Set receive timeout
        self.rcv_timeout = rcv_timeout  # Store for reconnection
        self.default_ip = opus_default_ip
        self.default_port = opus_default_port

    def connect(self, ip: str | None = None, port: int | None = None) -> None:
        """Connects the socket to the specified IP and port.

        Args:
            ip: The IP address to connect to. Defaults to configured OPUS IP.
            port: The port number to connect to. Defaults to configured OPUS port.
        """
        ip = ip if ip is not None else self.default_ip
        port = port if port is not None else self.default_port
        self.socket.connect(f"tcp://{ip}:{port}")
        logger.info("Connected to %s:%s", ip, port)

    def reconnect(self, ip: str | None = None, port: int | None = None) -> None:
        """Reconnects the socket after a timeout or error.

        Args:
            ip: The IP address to connect to. Defaults to stored default.
            port: The port number to connect to. Defaults to stored default.
        """
        logger.warning("Reconnecting socket...")
        try:
            self.socket.setsockopt(zmq.LINGER, 0)  # Don't wait for pending messages
            self.socket.close()
            time.sleep(0.5)  # Give socket time to fully close
            logger.info("Socket closed")
        except Exception as e:
            logger.error("Error closing socket: %s", e)

        logger.info("Creating new socket...")
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, self.rcv_timeout)  # Use stored timeout
        self.connect(ip, port)
        logger.info("Socket reconnected successfully")

    def send_message(self, message: dict[str, Any]) -> bool:
        """Sends a message to the specified IP address.

        Args:
            message: The message to send.

        Returns:
            A boolean indicating if the message was successfully sent.
        """
        try:
            message_json = json.dumps(message)
            self.socket.send_string(message_json)
            logger.info("Sent message: %s", message_json)
            return True
        except zmq.ZMQError as e:
            error_msg = str(e)
            logger.error("Failed to send message: %s", error_msg)

            # If socket is in invalid state, attempt immediate reconnection
            if "current state" in error_msg.lower() or "fsm" in error_msg.lower():
                logger.warning("Socket in invalid state detected - attempting auto-recovery...")
                try:
                    self.reconnect()
                    # Retry once after reconnection
                    logger.info("Retrying message send...")
                    message_json = json.dumps(message)
                    self.socket.send_string(message_json)
                    logger.info("Message sent successfully after reconnection: %s", message_json)
                    return True
                except Exception as retry_err:
                    logger.error("Reconnection and retry failed: %s", retry_err)
                    return False
            return False

    def receive_message(self, timeout_ms: int | None = None) -> str:
        """Receives a message from the connected socket.

        Args:
            timeout_ms: Optional timeout in milliseconds. If not provided, uses socket default.

        Returns:
            The received message as a string, or empty string on timeout/error.
        """
        try:
            if timeout_ms is not None:
                old_timeout = self.socket.getsockopt(zmq.RCVTIMEO)
                self.socket.setsockopt(zmq.RCVTIMEO, timeout_ms)

            message = self.socket.recv_string()

            # Restore original timeout if it was temporarily changed
            if timeout_ms is not None:
                self.socket.setsockopt(zmq.RCVTIMEO, old_timeout)

            return message
        except zmq.Again:
            timeout_sec = (timeout_ms if timeout_ms else self.rcv_timeout) / 1000
            logger.warning(
                "Receive timeout: No response from server after %.1f seconds", timeout_sec
            )
            logger.warning("Socket in invalid state - connection is corrupted")
            logger.warning("Next send will trigger automatic reconnection")
            return ""
        except zmq.ZMQError as e:
            logger.error("Failed to receive message: %s", e)
            return ""
        except KeyboardInterrupt:
            logger.warning("Program interrupted by user. Exiting.")
            return ""


if __name__ == "__main__":

    def run_client(message: dict[str, Any]) -> None:
        messaging = NetworkMessaging()
        ip = "130.20.216.127"
        messaging.connect(ip=ip, port=5555)

        # Send a message
        success = messaging.send_message(message)

        if success:
            # Receive reply
            reply = messaging.receive_message()
            logger.info("Received reply from server: %s", reply)
            messaging.send_message(message)

    message = {
        "foldername": "_test",
        "filename": "test",
        "do_fit": False,
        "do_bckg": False,
        "reset_fileids": True,
    }
    run_client(message)
    time.sleep(30)

    message = {
        "foldername": "_test",
        "filename": "test",
        "do_fit": False,
        "do_bckg": False,
        "reset_fileids": True,
        "end_experiment": True,
    }
    run_client(message)
