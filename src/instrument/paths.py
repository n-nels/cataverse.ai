"""Path and configuration helpers for OPUS runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import os

from ..core import config


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
        os.makedirs(path, exist_ok=True)

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


def define_paths() -> None:
    from .state import get_state

    state = get_state()
    if state.foldername is None or state.filename is None:
        raise RuntimeError("Foldername/filename not set before path resolution.")
    state.paths = build_paths(state.foldername, state.filename)
