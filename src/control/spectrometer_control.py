"""Behavior-preserving OPUS spectrometer acquisition control.

This module ports legacy OPUS acquisition wrappers to the new control layer
using the hardware `OpusSpectrometer` adapter.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

from src.core import get_logger
from src.hardware.spectrometer import OpusSpectrometer


logger = get_logger(__name__)


class SpectrometerController:
    """Control OPUS acquisition request/retry sequences."""

    def __init__(self, spectrometer: OpusSpectrometer) -> None:
        self.spectrometer = spectrometer

    def opus_vertex80(
        self,
        message: dict[str, Any],
        timeout_ms: int = 300000,
        retry_on_timeout: bool = True,
    ) -> str | None:
        """Collect one spectrum with timeout/retry behavior."""

        # Attempt to send message
        msg = self.spectrometer.send_message(message)
        if not msg:
            logger.info("Error: Failed to send message to OPUS")
            return None

        logger.info("Collecting spectrum...")
        reply = self.spectrometer.receive_message(timeout_ms=timeout_ms)

        # Check if we got a valid response
        if reply:
            logger.info("fileid: %s", reply)
            return reply

        if not retry_on_timeout:
            logger.info("Error: No response from OPUS (timeout)")
            return None

        try:
            self.spectrometer.reconnect()
            time.sleep(2)  # Wait for server to recover

            logger.info("Retrying message after reconnect...")
            msg = self.spectrometer.send_message(message)
            if msg:
                reply = self.spectrometer.receive_message(timeout_ms=timeout_ms)
                if reply:
                    logger.info("fileid: %s", reply)
                    return reply
        except Exception as exc:
            logger.info("Reconnection or retry failed: %s", exc)

        logger.info("Error: No response from OPUS after timeout and retry")
        return None

    def opus_acquire(
        self,
        filename: str,
        foldername: str,
        repeat: list[int],
        delay: list[float],
        all_fileids: bool,
        do_bckg: bool,
        do_fit: bool,
    ) -> None:
        """Run repeated OPUS acquisition loops with configured delays."""

        message = {
            "foldername": foldername,
            "filename": filename,
            "do_bckg": do_bckg,
            "do_fit": do_fit,
            "reset_fileids": all_fileids,
        }

        if do_bckg or all_fileids:
            self.opus_vertex80(message)

        message = {
            "foldername": foldername,
            "filename": filename,
            "do_bckg": False,
            "do_fit": do_fit,
            "reset_fileids": False,
        }

        # Collect spectra
        j = 0
        for i in range(len(delay)):
            for k in range(repeat[j]):
                now = datetime.now()
                self.opus_vertex80(message)

                logger.info(
                    "Collected spectrum %s of %s for %s minute delay",
                    k + 1,
                    repeat[j],
                    round(float(delay[i]) / 60, 2),
                )

                if i == (len(delay) - 1) and k == (repeat[i] - 1):
                    logger.info("End of OPUS Acquisition")
                    continue

                delta = datetime.now() - now
                time_wait = delay[i] - delta.total_seconds()

                if time_wait < 0:
                    continue

                next_meas = datetime.now() + timedelta(seconds=time_wait)
                logger.info("Next measurement:\n%s\n", next_meas)
                time.sleep(time_wait)

            j += 1
