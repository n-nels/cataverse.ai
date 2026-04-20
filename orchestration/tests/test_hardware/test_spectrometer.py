from __future__ import annotations

from unittest.mock import MagicMock

import zmq

from src.hardware.spectrometer import OpusSpectrometer


def test_send_returns_parsed_dict_reply() -> None:
    socket = MagicMock()
    socket.context = MagicMock()
    socket.getsockopt.return_value = 300000
    socket.getsockopt_string.return_value = "tcp://127.0.0.1:5555"
    socket.recv_string.return_value = '{"ok": true}'

    opus = OpusSpectrometer(socket)
    reply = opus.send({"hello": "world"})

    assert reply == {"ok": True}
    socket.send_string.assert_called_once()


def test_reconnect_creates_new_socket_and_reconnects_endpoint() -> None:
    old_socket = MagicMock()
    context = MagicMock()
    new_socket = MagicMock()

    old_socket.context = context
    old_socket.getsockopt.return_value = 300000
    old_socket.getsockopt_string.return_value = "tcp://127.0.0.1:5555"
    context.socket.return_value = new_socket

    opus = OpusSpectrometer(old_socket)
    opus.reconnect()

    context.socket.assert_called_once()
    new_socket.connect.assert_called_once_with("tcp://127.0.0.1:5555")


def test_send_reconnects_and_retries_on_fsm_error() -> None:
    socket = MagicMock()
    socket.context = MagicMock()
    socket.getsockopt.return_value = 300000
    socket.getsockopt_string.return_value = "tcp://127.0.0.1:5555"
    fsm_error = zmq.ZMQError()
    fsm_error.strerror = "Operation cannot be accomplished in current state"
    socket.send_string.side_effect = [fsm_error, None]
    socket.recv_string.return_value = '{"ok": true}'

    opus = OpusSpectrometer(socket)
    opus.reconnect = MagicMock()  # focus on retry path trigger

    reply = opus.send({"hello": "world"})

    assert reply == {"ok": True}
    assert socket.send_string.call_count == 2
    opus.reconnect.assert_called_once()


def test_send_returns_reply_wrapper_for_non_json() -> None:
    socket = MagicMock()
    socket.context = MagicMock()
    socket.getsockopt.return_value = 300000
    socket.getsockopt_string.return_value = "tcp://127.0.0.1:5555"
    socket.recv_string.return_value = "plain text"

    opus = OpusSpectrometer(socket)
    reply = opus.send({"hello": "world"})

    assert reply == {"reply": "plain text"}
