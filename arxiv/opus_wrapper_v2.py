"""ZMQ server wrapper for OPUS command execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from queue import Queue
from typing import Callable, IO, Optional, cast

import json
import os
import subprocess
import threading
import time

import zmq

from analysis import integrate_ir_iso_xchg as iso_xchg_analyzer

try:
    from analysis import peak_fitting as fit  # type: ignore
except (
    ImportError
):  # pragma: no cover - legacy module may be absent in refactor workspace
    fit = None
from analysis.main import DataAnalysisRunner
from analysis.peak_heights import PeakHeightsAnalyzer
from core import config


@dataclass
class OpusPaths:
    opus_files: str
    opus_calibrations: str
    calibration_data: str
    lg_refl: str
    sub_ifg: str
    scsm: str
    fsd: str
    read_params_dir: str
    peak_fit: str
    cloud_script: str
    read_params_file: str
    subifg_files: str


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
    queues: Optional[AnalysisQueues] = None


STATE: Optional[OpusState] = None
socket: Optional[zmq.Socket] = None


def get_state() -> OpusState:
    if STATE is None:
        raise RuntimeError("Opus state has not been initialized.")
    return STATE


def ensure_paths(state: OpusState) -> OpusPaths:
    if state.paths is None:
        raise RuntimeError("Opus paths have not been initialized.")
    return state.paths


def ensure_queues(state: OpusState) -> AnalysisQueues:
    if state.queues is None:
        state.queues = build_analysis_queues()
    return state.queues


def build_paths(foldername: str, filename: str) -> OpusPaths:
    path_opus_files = config.get_path("data.opus_files", foldername)
    path_opus_calibrations = config.get_path("data.opus_calibrations", foldername)
    path_calibration_data = config.get_path(
        "data.peak_fit", foldername, "CalibrationData"
    )
    path_lg_refl = config.get_path("utility.subtract_ifg.lg_refl_output", foldername)
    path_sub_ifg = config.get_path("utility.subtract_ifg.sub_ifg_output", foldername)
    path_scsm = config.get_path("utility.subtract_ifg.ssc_output", foldername)
    path_fsd = config.get_path("utility.subtract_ifg.fsd_output", foldername)
    path_read_params = config.get_path(
        "utility.subtract_ifg.read_params_output", foldername
    )
    path_peak_fit = config.get_path("data.peak_fit", foldername)
    path_cloud = cast(str, config.get_setting("utility.cloud_copy_script"))

    paths = [
        path_scsm,
        path_lg_refl,
        path_opus_files,
        path_read_params,
        path_sub_ifg,
        path_fsd,
        path_peak_fit,
        path_opus_calibrations,
        path_calibration_data,
    ]
    for path in paths:
        if not os.path.exists(path):
            os.makedirs(path)

    read_params = os.path.join(path_read_params, filename + ".txt")
    subifg_files = os.path.join(path_read_params, filename + "_subIFGfiles.txt")

    return OpusPaths(
        opus_files=path_opus_files,
        opus_calibrations=path_opus_calibrations,
        calibration_data=path_calibration_data,
        lg_refl=path_lg_refl,
        sub_ifg=path_sub_ifg,
        scsm=path_scsm,
        fsd=path_fsd,
        read_params_dir=path_read_params,
        peak_fit=path_peak_fit,
        cloud_script=path_cloud,
        read_params_file=read_params,
        subifg_files=subifg_files,
    )


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


def get_socket() -> zmq.Socket:
    if socket is None:
        raise RuntimeError("Socket has not been initialized.")
    return socket


def pipe_command(cmd: str, show: int) -> str:
    state = get_state()
    if show == -1:
        show = state.default_printout
    if show & 1:
        print(cmd)
    if state.hpipe is None:
        raise RuntimeError("Pipe handle is not initialized.")
    state.hpipe.write(bytes(cmd + "\r\n", "utf-8"))
    data = state.hpipe.read(1000)
    response = data.decode("utf-8")
    if show & 2:
        print(response, "\n")
    return response


def check_instrument_status() -> bool:
    result = pipe_command("DIAG_STATUS", 1)
    arr = result.split(chr(10))
    if arr[0] == "OK":
        number = int(arr[1])
        if number == -1:
            print(
                "No instrument connected. Check 'Measure/Setup optics and services'.\n"
            )
            return False
        if number == 1:
            print(
                "Instrument warnings present. Nevertheless measurements are possible.\n"
            )
            return True
        if number == 2:
            print("Instrument errors present. Measurement not possible.\n")
            return False
        if number == 0:
            print("Connection to instrument is OK.\n")
            return True
        if number == 3:
            print(
                "Instrument warnings and alarms present. Nevertheless measurements are possible.\n"
            )
            return True
    print("DIAG_STATUS was not successful.\n")
    return False


def deconvolute(file: str) -> None:
    pipe_command(
        "COMMAND_LINE Deconvolution([" + file + ":lgRefl], {"
        "DEE=1000, DES=4000, DSP='LO', DWR=0, DNR=0.5, DEF=876719.515768})",
        0,
    )


def do_background_measurement() -> None:
    state = get_state()
    pipe_command(
        "TAKE_REFERENCE " + state.xpm_path + "\\" + state.xpm_name,
        1,
    )


def do_sample_measurement(nss_value: int, n: str) -> str:
    state = get_state()
    add_params = f", NSS={nss_value}"
    if state.filename is None:
        raise RuntimeError("Filename is not set.")
    try:
        paths = ensure_paths(state)
        arr = pipe_command(
            "COMMAND_LINE MeasureSample (, {EXP='" + state.xpm_name + "', "
            "XPP='" + state.xpm_path + "', NAM='" + state.filename + "." + n + "',"
            "SNM='" + state.filename + "',"
            "PTH='" + paths.opus_files + "'" + add_params + "});",
            1,
        ).split(chr(10))
        return arr[2]
    except Exception:
        define_paths()
        paths = ensure_paths(state)
        arr = pipe_command(
            "COMMAND_LINE MeasureSample (, {EXP='" + state.xpm_name + "', "
            "XPP='" + state.xpm_path + "', NAM='" + state.filename + "." + n + "',"
            "SNM='" + state.filename + "',"
            "PTH='" + paths.opus_files + "'" + add_params + "});",
            1,
        ).split(chr(10))
        return arr[2]


def get_experiment_path() -> str:
    arr = pipe_command("GET_OPUSPATH", 1).split(chr(10))
    if arr[0] == "OK":
        return arr[1] + "\\XPM"
    return ""


def get_version() -> bool:
    return pipe_command("GET_VERSION_EXTENDED", 3) != ""


def load_file(file: str) -> None:
    pipe_command("LOAD_FILE" + file, 0)


def read_parameter(file: str, block: str, name: str) -> Optional[str]:
    arr = pipe_command("FILE_PARAMETERS", 0).split(chr(10))
    if arr[0] == "OK":
        arr = pipe_command("READ_FROM_FILE " + file, 0).split(chr(10))
        if arr[0] == "OK":
            arr = pipe_command("READ_FROM_BLOCK " + block, 0).split(chr(10))
            if arr[0] == "OK":
                arr = pipe_command("READ_PARAMETER " + name, 0).split(chr(10))
                if arr[0] == "OK":
                    return arr[1]
    else:
        print("Reading parameter" + name + "failed")
    return None


def read_multiple_parameters(file: str, block: str, name: str) -> Optional[list[str]]:
    arr = pipe_command("READ_FROM_FILE " + file, 0).split(chr(10))
    if arr[0] == "OK":
        arr = pipe_command("READ_FROM_BLOCK " + block, 0).split(chr(10))
        if arr[0] == "OK":
            arr = pipe_command("READ_MULTIPLE_PARAMETERS " + name, 0).split(chr(10))
            if arr[0] == "OK":
                return arr
    else:
        print("Reading parameter" + name + "failed")
    return None


def save_as(file: str, name: str, path: str) -> None:
    pipe_command(
        "COMMAND_LINE SaveAs ([" + file + ":lgRefl], {DAP='" + path + "',"
        "SAN='" + name + "', SEP=',', DPA=8, DPO=8, "
        "ADP='1', YON='0', OEX='0', X64='1'});",
        0,
    )


def save_as_scsm(file: str, name: str) -> None:
    paths = ensure_paths(get_state())
    pipe_command(
        "COMMAND_LINE SaveAs ([" + file + ":ScSm], {DAP='" + paths.scsm + "',"
        "SAN='" + name + "', SEP=',', DPA=8, DPO=8,"
        "ADP='1', YON='0', OEX='0', X64='1'});",
        0,
    )


def spectrum_from_interferogram(meas: str, bckg: str) -> None:
    pipe_command(
        "COMMAND_LINE SpecFromIfgs ([" + meas + ":IgSm], [" + bckg + ":IgSm], {"
        "PPF='LRF', CPF=0})",
        0,
    )


def unload_file(file: str) -> None:
    pipe_command("COMMAND_LINE Unload([" + file + ":Spec], {})", 0)


def subtract_ifg_files(files: list[str]) -> None:
    state = get_state()
    paths = ensure_paths(state)

    if len(files) <= 1:
        state.processed_files = set()
        return

    for step in range(1, 11):
        start = 0 if step == 1 else 2

        for i in range(start + step, len(files), step):
            pair = (files[i], files[i - step])

            if pair not in state.processed_files:
                file_ids = list(pair)
                sub_ifg_list = []

                spectrum_from_interferogram(file_ids[0], file_ids[1])
                name = (
                    f"{file_ids[0].split('\\\\')[-1][:-8]}_delta{step}."
                    f"{file_ids[0].split('.')[-1][:-3]}"
                )
                sub_ifg_list.append((name, file_ids[0], file_ids[1]))
                save_as(file_ids[0], name, paths.sub_ifg)

                for file in file_ids:
                    unload_file(file)
                for file in file_ids:
                    load_file(file.split('"')[1])
                state.processed_files.add(pair)

                with open(paths.subifg_files, "a") as txt_file:
                    for entry in sub_ifg_list:
                        txt_file.write(f"{entry}\n")

                if state.do_fit:
                    dispatch_analysis(paths.sub_ifg + "\\" + name)


def main_tpd(
    sample_name: str,
    folder_name: str,
    repeat: list[int],
    delay: list[float],
    nss_value: int,
    do_bckg: bool,
) -> None:
    print("\nStart of program...")

    state = get_state()
    state.xpm_name = "ncnels_v2.xpm"
    state.default_printout = 3
    state.hpipe = open(cast(str, config.get_setting("opus.pipe")), "r+b", 0)
    state.sample_name = sample_name
    state.foldername = folder_name
    state.nss_value = nss_value

    # Read OPUS path from workspace
    state.xpm_path = get_experiment_path()
    if state.xpm_path == "":
        print("Error on trying to evaluate the OPUS path.")
        return
    print("Ensure you have an experiment file defined in:\n" + state.xpm_path)
    print("The experiment file must have the name " + state.xpm_name + ".\n")

    # Define filename
    now = datetime.now()
    formatted_time = now.strftime("%Y%m%d_%H%M%S")
    state.filename = formatted_time + "_" + sample_name
    state.paths = build_paths(folder_name, state.filename)

    # Collect background
    if do_bckg:
        do_background_measurement()

    # Collect spectra
    j = 0
    m = 0
    state.all_fileids = []
    for i in range(len(delay)):
        for _ in range(repeat[j]):
            state.n = str(m).zfill(4)
            now = datetime.now()
            fileid = do_sample_measurement(state.nss_value, state.n)

            unload_file(fileid)

            m += 1
            delta = datetime.now() - now
            time_wait = delay[i] - delta.total_seconds()
            if time_wait < 0:
                continue
            time.sleep(time_wait)
        j += 1


def opus_acquire() -> str:
    state = get_state()
    fileid = do_sample_measurement(state.nss_value, state.n)
    if state.paths is None:
        define_paths()
    paths = ensure_paths(state)
    state.all_fileids.append(fileid)
    file_name = fileid.split("\\")[-1][:-3]

    save_as(fileid, file_name, paths.lg_refl)
    save_as_scsm(fileid, file_name)
    deconvolute(fileid)
    save_as(fileid, file_name, paths.fsd)
    unload_file(fileid)
    load_file(fileid.split('"')[1])

    inst_params = read_multiple_parameters(fileid, "lgRefl", "DATTIMPKANSS")
    if inst_params is None:
        raise ValueError("Failed to read instrument parameters.")
    dat_in = datetime.strptime(inst_params[1][4:], "%d/%m/%Y").date()
    dat_out = dat_in.strftime("%m/%d/%Y")
    dat = datetime.strptime(dat_out, "%m/%d/%Y").date()

    tim = datetime.strptime(inst_params[2][4:].split()[0], "%H:%M:%S.%f")
    pka = inst_params[3][4:]
    nss = inst_params[4][4:]

    with open(paths.read_params_file, "a") as file:
        file.write(f"{fileid}, {dat}, {tim.time()}, {pka}, {nss}\n")

    subtract_ifg_files(state.all_fileids)

    for file in state.all_fileids[:-10]:
        unload_file(file)
    return fileid


def dispatch_analysis(file_path: str) -> None:
    state = get_state()
    queues = ensure_queues(state)

    if "isoX" in file_path:
        queues.iso_xchg.enqueue(file_path)
    else:
        queues.spectral_fit.enqueue(file_path)
        queues.peak_heights.enqueue(file_path)
    print("\npeak fitting file:\n", file_path, "\n")


def define_paths() -> None:
    state = get_state()
    if state.foldername is None or state.filename is None:
        raise RuntimeError("Foldername/filename not set before path resolution.")
    state.paths = build_paths(state.foldername, state.filename)


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
    state = get_state()
    if fit is None:
        raise RuntimeError("Legacy peak_fitting module is unavailable.")
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


def handle_end_experiment(paths: OpusPaths) -> str:
    state = get_state()
    for fileid in state.all_fileids[-10:]:
        try:
            unload_file(fileid)
        except Exception as exc:
            print(f"Failed to unload {fileid}: {exc}")
    now = datetime.now() + timedelta(minutes=10)
    print(f"Waiting until {now} before copying files to cloud...")
    time.sleep(10 * 60)
    subprocess.run([paths.cloud_script], shell=True)
    return "End of experiment, files copied to cloud"


def handle_message(message: dict) -> Optional[str]:
    if message.get("readme"):
        return handle_readme()
    if message.get("end_experiment"):
        if message.get("foldername") and message.get("filename"):
            state = get_state()
            state.foldername = message["foldername"]
            state.filename = message["filename"]
            define_paths()
        paths = ensure_paths(get_state())
        return handle_end_experiment(paths)

    state = get_state()
    state.foldername = message["foldername"]
    state.filename = message["filename"]
    state.do_fit = message["do_fit"]
    do_bckg = message["do_bckg"]
    reset_fileids = message["reset_fileids"]

    define_paths()
    if do_bckg:
        do_background_measurement()
        if reset_fileids:
            state.all_fileids = []
            define_paths()
            return "Collected background and all_fileids reset"
        return None
    if reset_fileids:
        state.all_fileids = []
        define_paths()
        return "all_fileids reset"

    fileid = opus_acquire()
    return str(fileid)


def handle_message_fallback(message: dict) -> Optional[str]:
    raise ValueError("Invalid message payload")


def run_server() -> None:
    global socket

    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind(
        f"tcp://{config.get_setting('opus.server.host')}:{config.get_setting('opus.server.port')}"
    )

    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)

    print("Server is listening on 130.20.216.127...")
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


def main() -> None:
    global STATE
    STATE = OpusState(
        hpipe=None,
        default_printout=3,
        xpm_path="",
        xpm_name="ncnels_v2.xpm",
    )
    STATE.hpipe = open(cast(str, config.get_setting("opus.pipe")), "r+b", 0)
    STATE.xpm_path = get_experiment_path()
    run_server()


if __name__ == "__main__":
    main()
