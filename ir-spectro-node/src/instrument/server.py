"""ZMQ message handling and server loop."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import zmq

from ..core import config
from ..visualizations.plot_spectrum_fit import plot_spectrum_fit
from ..visualizations.plot_monomer_cluster_fit import plot_kinetic_fit
from ..visualizations.plot_params import plot_params_all, plot_params_folder
from ..visualizations.plot_monomer_max import plot_monomer_max

from .acquisition import opus_acquire
from .client import do_background_measurement, unload_file, do_sample_measurement
from .paths import define_paths
from .state import ensure_paths, get_state, set_socket


def handle_background(do_bckg: bool, reset_fileids: bool) -> Optional[str]:
    state = get_state()
    if do_bckg:
        do_background_measurement()
        if reset_fileids:
            state.all_fileids = []
            define_paths()
            return "Collected background and all_fileids reset"
        return "Background measurement successfully performed."
    if reset_fileids:
        state.all_fileids = []
        define_paths()
        return "all_fileids reset"
    return None


def handle_end_experiment() -> str:
    state = get_state()
    for fileid in state.all_fileids[-11:]:
        try:
            unload_file(fileid)
        except Exception as exc:
            print(f"Failed to unload {fileid}: {exc}")

    if state.all_fileids:
        file_path: str | None = None
        folder_name: str | None = None
        base_name: str | None = None
        try:
            file_path = state.all_fileids[-1].split('"')[1]
            folder_name = os.path.basename(os.path.dirname(file_path))
            base_name = os.path.basename(file_path).split(".")[0]
            subifg_dir = config.get_path(
                "utility.subtract_ifg.sub_ifg_output", folder_name
            )
            plot_spectrum_fit(os.path.join(subifg_dir, base_name))
            csv = (
                Path(config.get_path("data.peak_fit", folder_name))
                / f"{base_name}_CarbonylPeakArea.csv"
            )
            plot_kinetic_fit(str(csv))
            plot_params_folder(csv)
            if folder_name:
                plot_params_all()
                plot_monomer_max(folder_name=folder_name)
        except Exception as exc:
            print(
                "Plot spectrum fit failed for "
                f"file_path={file_path} folder_name={folder_name} "
                f"base_name={base_name}: {exc}"
            )

    return "Experiment ended successfully."


def handle_message(message: dict) -> Optional[str]:
    if not isinstance(message, dict) or not message:
        raise ValueError("Empty or invalid message payload")
    if message.get("end_experiment"):
        state = get_state()
        state.foldername = message["foldername"]
        state.filename = message["filename"]
        define_paths()
        fileid = do_sample_measurement(state.nss_value, state.n)
        unload_file(fileid)
        return handle_end_experiment()

    required_keys = ["foldername", "filename", "do_fit", "do_bckg", "reset_fileids"]
    missing = [key for key in required_keys if key not in message]
    if missing:
        raise ValueError(f"Missing required message keys: {', '.join(missing)}")

    state = get_state()
    state.foldername = message["foldername"]
    state.filename = message["filename"]
    state.do_fit = message["do_fit"]
    do_bckg = message["do_bckg"]
    reset_fileids = message["reset_fileids"]

    define_paths()
    background_response = handle_background(do_bckg, reset_fileids)
    if background_response is not None:
        return background_response

    fileid = opus_acquire()
    return str(fileid)


def run_server() -> None:
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    set_socket(socket)
    socket.bind(
        f"tcp://{config.get_setting('opus.server.host')}:{config.get_setting('opus.server.port')}"
    )

    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)

    host = config.get_setting("opus.server.host")
    port = config.get_setting("opus.server.port")
    print(f"Server is listening on {host}:{port}...")
    try:
        while True:
            try:
                events = dict(poller.poll(timeout=1000))
                if socket in events and events[socket] == zmq.POLLIN:
                    message_json = socket.recv_string()
                    try:
                        message = json.loads(message_json)
                    except json.JSONDecodeError as exc:
                        socket.send_string("Error: " + str(exc))
                        continue
                    if isinstance(message, dict) and message:
                        print(f"\nReceived request:\n {message}\n")
                        try:
                            reply = handle_message(message)
                            socket.send_string(reply if reply is not None else "OK")
                        except Exception as error:
                            print("Error:", error)
                            socket.send_string("Error: " + str(error))
                    elif message:
                        socket.send_string("Error: Message must be a JSON object")
                    else:
                        socket.send_string("Error: Empty message")
            except zmq.Again:
                continue
            except KeyboardInterrupt:
                print("Program interrupted. Exiting.")
                break
    finally:
        socket.close()
        context.term()
