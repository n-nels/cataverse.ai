"""ZMQ message handling and server loop."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
import subprocess
import time
from typing import Optional

import zmq

try:
    from ..analysis import peak_fitting as fit  # type: ignore
except ImportError:  # pragma: no cover - legacy module may be absent
    fit = None
from ..core import config

from .acquisition import opus_acquire
from .client import do_background_measurement, unload_file
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


def handle_readme() -> str:
    if fit is None:
        raise RuntimeError("Legacy peak_fitting module is unavailable.")
    state = get_state()
    if not state.all_fileids:
        raise RuntimeError("No file IDs available to build readme.")
    root_dir = config.get_path("data.peak_fit")
    fileid = state.all_fileids[-1]
    fileid = fileid[:-1]
    foldername = fileid.split("\\")[-2]
    filename = fileid.split("\\")[-1]
    sample_name = filename.rsplit(".", 1)[0]
    path = os.path.join(root_dir, foldername, sample_name)
    file_name = path + "_README.md"
    fit.readme_to_csv(file_name)
    print("readme converted to .csv")
    return "readme converted to .csv"


def handle_end_experiment() -> str:
    state = get_state()
    paths = ensure_paths(state)
    for fileid in state.all_fileids[-10:]:
        try:
            unload_file(fileid)
        except Exception as exc:
            print(f"Failed to unload {fileid}: {exc}")
    now = datetime.now() + timedelta(minutes=10)
    print(f"Waiting until {now} before copying files to cloud...")
    time.sleep(10 * 60)
    subprocess.run([paths.cloud_script], shell=True, check=True)
    return "End of experiment, files copied to cloud"


def handle_message(message: dict) -> Optional[str]:
    if not isinstance(message, dict) or not message:
        raise ValueError("Empty or invalid message payload")
    if message.get("readme"):
        return handle_readme()
    if message.get("end_experiment"):
        if message.get("foldername") and message.get("filename"):
            state = get_state()
            state.foldername = message["foldername"]
            state.filename = message["filename"]
            define_paths()
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
