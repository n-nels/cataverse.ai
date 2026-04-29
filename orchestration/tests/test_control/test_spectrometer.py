from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from src.control.spectrometer_control import SpectrometerController


def test_send_opus_request_returns_reply_on_successful_send() -> None:
    spectrometer = MagicMock()
    spectrometer.send.return_value = {"reply": "file_001"}

    controller = SpectrometerController(spectrometer=spectrometer)
    message = {"foldername": "f", "filename": "n"}

    reply = controller.send_opus_request(message, timeout_ms=12345)

    assert reply == "file_001"
    spectrometer.send.assert_called_once_with(message, timeout_ms=12345)


def test_send_opus_request_reconnects_and_retries_once_after_empty_reply() -> None:
    spectrometer = MagicMock()
    spectrometer.send.side_effect = [{}, {"reply": "file_retry"}]

    controller = SpectrometerController(spectrometer=spectrometer)
    message = {"foldername": "f", "filename": "n"}

    with patch("src.control.spectrometer_control.time.sleep") as sleep_mock:
        reply = controller.send_opus_request(message, timeout_ms=300000, retry_on_timeout=True)

    assert reply == "file_retry"
    spectrometer.reconnect.assert_called_once()
    assert spectrometer.send.call_count == 2
    spectrometer.send.assert_has_calls([
        call(message, timeout_ms=300000),
        call(message, timeout_ms=300000),
    ])
    sleep_mock.assert_called_once_with(2)


def test_opus_acquire_calls_vertex_for_background_and_sequence() -> None:
    spectrometer = MagicMock()
    controller = SpectrometerController(spectrometer=spectrometer)
    controller.send_opus_request = MagicMock(return_value="file_001")

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
    assert controller.send_opus_request.call_count == 3
    init_msg = controller.send_opus_request.call_args_list[0].args[0]
    assert init_msg["reset_fileids"] is True

    first_collect_msg = controller.send_opus_request.call_args_list[1].args[0]
    second_collect_msg = controller.send_opus_request.call_args_list[2].args[0]
    assert first_collect_msg["do_bckg"] is False
    assert first_collect_msg["reset_fileids"] is False
    assert second_collect_msg["do_bckg"] is False
    assert second_collect_msg["reset_fileids"] is False
