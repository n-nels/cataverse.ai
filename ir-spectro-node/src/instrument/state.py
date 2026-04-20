"""Runtime state container for the OPUS server."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import IO, Optional, TYPE_CHECKING

import zmq

from .paths import OpusPaths

if TYPE_CHECKING:
    from .dispatch import AnalysisQueues


@dataclass
class OpusState:
    hpipe: Optional[IO[bytes]]
    default_printout: int
    xpm_path: str
    xpm_name: str
    foldername: Optional[str] = None
    filename: Optional[str] = None
    sample_name: Optional[str] = None
    n: str = field(default_factory=lambda: str(0).zfill(4))
    nss_value: int = 256
    all_fileids: list[str] = field(default_factory=list)
    do_fit: bool = False
    processed_files: set[tuple[str, str]] = field(default_factory=set)
    paths: Optional[OpusPaths] = None
    queues: Optional["AnalysisQueues"] = None


STATE: Optional[OpusState] = None
socket: Optional[zmq.Socket] = None


def get_state() -> OpusState:
    if STATE is None:
        raise RuntimeError("Opus state has not been initialized.")
    return STATE


def set_state(state: OpusState) -> None:
    global STATE
    STATE = state


def get_socket() -> zmq.Socket:
    if socket is None:
        raise RuntimeError("Socket has not been initialized.")
    return socket


def set_socket(new_socket: zmq.Socket) -> None:
    global socket
    socket = new_socket


def ensure_paths(state: OpusState) -> OpusPaths:
    if state.paths is None:
        raise RuntimeError("Opus paths have not been initialized.")
    return state.paths


def ensure_queues(state: OpusState) -> "AnalysisQueues":
    if state.queues is None:
        from .dispatch import build_analysis_queues

        state.queues = build_analysis_queues()
    return state.queues
