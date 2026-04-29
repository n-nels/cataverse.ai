"""Behavior-preserving OPUS spectrometer acquisition control.

This module ports legacy OPUS acquisition wrappers to the new control layer
using the hardware `OpusSpectrometer` adapter.
"""

from __future__ import annotations

import time
import logging
from datetime import datetime, timedelta
from typing import Any

from src.hardware.spectrometer import OpusSpectrometer


logger = logging.getLogger(__name__)


class SpectrometerController:
    """Control OPUS acquisition request/retry sequences."""

    def __init__(self, spectrometer: OpusSpectrometer) -> None:
        self.spectrometer = spectrometer

    def send_opus_request(
        self,
        message: dict[str, Any],
        timeout_ms: int = 300000,
        retry_on_timeout: bool = True,
    ) -> str | None:
        """Collect one spectrum with timeout/retry behavior."""

        reply = self.spectrometer.send(message, timeout_ms=timeout_ms)
        if not reply:
            logger.error("Failed to send/receive message to OPUS")
            if not retry_on_timeout:
                return None

            try:
                self.spectrometer.reconnect()
                time.sleep(2)  # Wait for server to recover

                logger.info("Retrying message after reconnect...")
                reply = self.spectrometer.send(message, timeout_ms=timeout_ms)
                if reply:
                    file_id = reply.get("reply", str(reply))
                    logger.info("fileid: %s", file_id)
                    return file_id
            except Exception as exc:
                logger.error("Reconnection or retry failed: %s", exc)

            logger.error("No response from OPUS after timeout and retry")
            return None

        file_id = reply.get("reply", str(reply))
        logger.info("fileid: %s", file_id)
        return file_id

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
            self.send_opus_request(message)

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
                self.send_opus_request(message)

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
