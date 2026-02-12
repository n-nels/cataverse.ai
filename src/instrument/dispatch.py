"""Analysis queue helpers for background processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from queue import Queue
import threading
from typing import Callable, Optional

from ..analysis import integrate_ir_iso_xchg as iso_xchg_analyzer
from ..analysis.main import DataAnalysisRunner
from ..analysis.peak_heights import PeakHeightsAnalyzer


@dataclass
class AnalysisQueue:
    name: str
    worker: Callable[[str], None]
    queue: Queue[str] = field(default_factory=Queue)
    thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def enqueue(self, file_path: str) -> None:
        self.start()
        self.queue.put(file_path)

    def _run(self) -> None:
        while True:
            file_path = self.queue.get()
            try:
                self.worker(file_path)
            except Exception as exc:
                print(f"Error in {self.name} worker: {exc}")
            finally:
                self.queue.task_done()


@dataclass
class AnalysisQueues:
    spectral_fit: AnalysisQueue
    peak_heights: AnalysisQueue
    iso_xchg: AnalysisQueue


def build_analysis_queues() -> AnalysisQueues:
    spectral_runner = DataAnalysisRunner()
    peak_heights_runner = PeakHeightsAnalyzer()

    def run_spectral_fit_worker(file_path: str) -> None:
        spectral_runner.run_spectral_fit(file_path)

    return AnalysisQueues(
        spectral_fit=AnalysisQueue(
            name="spectral_fit",
            worker=run_spectral_fit_worker,
        ),
        peak_heights=AnalysisQueue(
            name="peak_heights",
            worker=peak_heights_runner.run,
        ),
        iso_xchg=AnalysisQueue(
            name="iso_xchg",
            worker=iso_xchg_analyzer.integrate_irIsoXchg,
        ),
    )


def dispatch_analysis(file_path: str) -> None:
    from .state import ensure_queues, get_state

    state = get_state()
    queues = ensure_queues(state)

    if "isoX" in file_path:
        queues.iso_xchg.enqueue(file_path)
    else:
        queues.spectral_fit.enqueue(file_path)
        queues.peak_heights.enqueue(file_path)
