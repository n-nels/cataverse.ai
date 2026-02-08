"""Entry point for the OPUS ZMQ server."""

from __future__ import annotations

from typing import cast

from ..core import config

from .client import get_experiment_path
from .server import run_server
from .state import OpusState, set_state


def main() -> None:
    state = OpusState(
        hpipe=None,
        default_printout=3,
        xpm_path="",
        xpm_name="ncnels_v2.xpm",
    )
    state.hpipe = open(cast(str, config.get_setting("opus.pipe")), "r+b", 0)
    set_state(state)
    state.xpm_path = get_experiment_path()
    if state.xpm_path == "":
        raise RuntimeError("Error on trying to evaluate the OPUS path.")
    run_server()


def run_server_main() -> None:
    main()
