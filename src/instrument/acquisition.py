"""Measurement workflow helpers."""

from __future__ import annotations

from datetime import datetime

from .client import (
    deconvolute,
    do_sample_measurement,
    load_file,
    read_multiple_parameters,
    save_as,
    save_as_scsm,
    spectrum_from_interferogram,
    unload_file,
)
from .dispatch import dispatch_analysis
from .paths import define_paths
from .state import ensure_paths, get_state


def subtract_ifg_files(files: list[str]) -> None:
    state = get_state()

    if len(files) <= 1:
        state.processed_files = set()
        return

    paths = ensure_paths(state)

    for step in range(1, 11):
        start = 0 if step == 1 else 2

        for i in range(start + step, len(files), step):
            pair = (files[i], files[i - step])

            if pair not in state.processed_files:
                file_ids = list(pair)
                sub_ifg_list = []

                spectrum_from_interferogram(file_ids[0], file_ids[1])
                name = (
                    f"{file_ids[0].split('\\')[-1][:-8]}_delta{step}."
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
    if inst_params is None or len(inst_params) < 5:
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
