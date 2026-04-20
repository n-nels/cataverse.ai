from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from src.control.spectrometer_control import SpectrometerController


def test_opus_vertex80_returns_reply_on_successful_send_and_receive() -> None:
    spectrometer = MagicMock()
    spectrometer.send_message.return_value = True
    spectrometer.receive_message.return_value = "file_001"

    controller = SpectrometerController(spectrometer=spectrometer)
    message = {"foldername": "f", "filename": "n"}

    reply = controller.opus_vertex80(message, timeout_ms=12345)

    assert reply == "file_001"
    spectrometer.send_message.assert_called_once_with(message)
    spectrometer.receive_message.assert_called_once_with(timeout_ms=12345)


def test_opus_vertex80_reconnects_and_retries_once_after_timeout() -> None:
    spectrometer = MagicMock()
    spectrometer.send_message.side_effect = [True, True]
    spectrometer.receive_message.side_effect = ["", "file_retry"]

    controller = SpectrometerController(spectrometer=spectrometer)
    message = {"foldername": "f", "filename": "n"}

    with patch("src.control.spectrometer_control.time.sleep") as sleep_mock:
        reply = controller.opus_vertex80(message, timeout_ms=300000, retry_on_timeout=True)

    assert reply == "file_retry"
    spectrometer.reconnect.assert_called_once()
    assert spectrometer.send_message.call_count == 2
    spectrometer.send_message.assert_has_calls([call(message), call(message)])
    spectrometer.receive_message.assert_has_calls([
        call(timeout_ms=300000),
        call(timeout_ms=300000),
    ])
    sleep_mock.assert_called_once_with(2)


def test_opus_acquire_calls_vertex_for_background_and_sequence() -> None:
    spectrometer = MagicMock()
    controller = SpectrometerController(spectrometer=spectrometer)
    controller.opus_vertex80 = MagicMock(return_value="file_001")

    with patch("src.control.spectrometer_control.time.sleep"):
        controller.opus_acquire(
            filename="exp",
            foldername="run",
            repeat=[2],
            delay=[0.0],
            all_fileids=True,
            do_bckg=False,
            do_fit=False,
        )

    # one initialization call + two collection calls
    assert controller.opus_vertex80.call_count == 3
    init_msg = controller.opus_vertex80.call_args_list[0].args[0]
    assert init_msg["reset_fileids"] is True

    first_collect_msg = controller.opus_vertex80.call_args_list[1].args[0]
    second_collect_msg = controller.opus_vertex80.call_args_list[2].args[0]
    assert first_collect_msg["do_bckg"] is False
    assert first_collect_msg["reset_fileids"] is False
    assert second_collect_msg["do_bckg"] is False
    assert second_collect_msg["reset_fileids"] is False
