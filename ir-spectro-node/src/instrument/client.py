"""OPUS pipe command adapters."""

from __future__ import annotations

from typing import Optional

from .paths import define_paths
from .state import ensure_paths, get_state


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
    except Exception as exc:
        print(f"Failed to measure sample; retrying with refreshed paths: {exc}")
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
        print(f"Reading parameter {name} failed")
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
        print(f"Reading parameter {name} failed")
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
