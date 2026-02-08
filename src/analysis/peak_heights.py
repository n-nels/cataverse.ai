from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Mapping

import numpy as np
import pandas as pd
from pybaselines.classification import std_distribution
from scipy.signal import find_peaks

try:
    from ..core import config
except ImportError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core import config

Spectrum = np.ndarray
PeakRecord = dict[str, float | str]
ProminenceHeight = tuple[float, float]


@dataclass
class ParsedPaths:
    """Container for resolved input/output paths for a run."""

    folder: str
    base_name: str
    iterator: str
    delta_file: str | None
    time_file: str
    fsd_path: str
    lgrfl_path: str
    subifg_path: str
    save_dir: str


class PeakHeightsAnalyzer:
    """Class-based analyzer for extracting peak heights."""

    def __init__(
        self,
        *,
        windows: Mapping[str, tuple[float, float]] | None = None,
        fsd_thresholds: dict[str, ProminenceHeight] | None = None,
        lgrfl_thresholds: dict[str, ProminenceHeight] | None = None,
        subifg_thresholds: dict[str, ProminenceHeight] | None = None,
        baseline_params: dict[str, float | None] | None = None,
        peak_finder: Callable = find_peaks,
        baseline_method: Callable = std_distribution,
        output_suffixes: dict[str, str] | None = None,
    ) -> None:
        self.windows = dict(
            windows
            or {
                "hydroxyl": (3000, 3900),
                "carbonate": (1000, 1700),
            }
        )
        self.fsd_thresholds = dict(
            fsd_thresholds
            or {
                "hydroxyl": (0.0001, 0.01),
                "carbonate": (0.001, 0.01),
            }
        )
        self.lgrfl_thresholds = dict(
            lgrfl_thresholds
            or {
                "hydroxyl": (0.0002, 0.001),
                "carbonate": (0.0002, 0.001),
            }
        )
        self.subifg_thresholds = dict(
            subifg_thresholds
            or {
                "hydroxyl": (0.0001, 0.001),
                "carbonate": (0.0001, 0.001),
            }
        )
        self.baseline_params = dict(
            baseline_params
            or {
                "half_window": 10,
                "interp_half_window": 5,
                "fill_half_window": 6,
                "num_std": 1.1,
                "smooth_half_window": None,
                "weights": None,
            }
        )
        self.peak_finder = peak_finder
        self.baseline_method = baseline_method
        self.output_suffixes = output_suffixes or {
            "fsd": "fsdPeakHeight",
            "lgrfl": "lgrflPeakHeight",
            "subifg": "subifgPeakHeight",
        }

    def run(self, file_path: str) -> None:
        """Run peak height extraction for the provided subIFG file."""

        parsed = self._parse_input_paths(file_path)
        exp_params = self._load_experiment_params(parsed.time_file)
        elapsed_s = self._compute_elapsed_seconds(exp_params, parsed.iterator)

        fsd_regions = self._slice_regions(self._load_spectrum(parsed.fsd_path))
        lgrfl_regions = self._slice_regions(self._load_spectrum(parsed.lgrfl_path))
        subifg_regions = self._slice_regions(self._load_spectrum(parsed.subifg_path))

        fsd_tag = f"{parsed.base_name}.{parsed.iterator}"
        lgrfl_tag = f"{parsed.base_name}.{parsed.iterator}"
        subifg_tag = (
            f"{parsed.base_name}_{parsed.delta_file}.{parsed.iterator}"
            if parsed.delta_file
            else f"{parsed.base_name}.{parsed.iterator}"
        )

        subifg_skip = self._should_skip_subifg(parsed.delta_file, parsed.iterator)

        fsd_records = self._process_dtype(
            fsd_regions, self.fsd_thresholds, fsd_tag, elapsed_s
        )
        self._dedupe_and_save(fsd_records, self._save_file(parsed, "fsd"), fsd_tag)

        lgrfl_records = self._process_dtype(
            lgrfl_regions, self.lgrfl_thresholds, lgrfl_tag, elapsed_s
        )
        self._dedupe_and_save(
            lgrfl_records, self._save_file(parsed, "lgrfl"), lgrfl_tag
        )

        subifg_records = self._process_dtype(
            subifg_regions,
            self.subifg_thresholds,
            subifg_tag,
            elapsed_s,
            skip=subifg_skip,
        )
        self._dedupe_and_save(
            subifg_records, self._save_file(parsed, "subifg"), subifg_tag
        )

    def _parse_input_paths(self, file_path: str) -> ParsedPaths:
        normalized = os.path.normpath(file_path)
        folder = os.path.basename(os.path.dirname(normalized))
        filename = os.path.basename(normalized)

        if "." not in filename:
            raise ValueError(f"Expected iterator in filename: {filename}")

        base_with_delta, iterator = filename.split(".", 1)
        name_parts = base_with_delta.split("_")
        if len(name_parts) > 1:
            delta_file = name_parts[-1]
            base_name = "_".join(name_parts[:-1])
        else:
            delta_file = None
            base_name = base_with_delta

        time_file = config.get_path(
            "utility.subtract_ifg.read_params_output", folder, f"{base_name}.txt"
        )
        fsd_path = config.get_path(
            "utility.subtract_ifg.fsd_output", folder, f"{base_name}.{iterator}"
        )
        lgrfl_path = config.get_path(
            "utility.subtract_ifg.lg_refl_output", folder, f"{base_name}.{iterator}"
        )
        save_dir = config.get_path("data.peak_fit", folder)

        os.makedirs(save_dir, exist_ok=True)

        return ParsedPaths(
            folder=folder,
            base_name=base_name,
            iterator=iterator,
            delta_file=delta_file,
            time_file=time_file,
            fsd_path=fsd_path,
            lgrfl_path=lgrfl_path,
            subifg_path=normalized,
            save_dir=save_dir,
        )

    def _load_experiment_params(self, path: str) -> pd.DataFrame:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Time parameter file not found: {path}")

        exp_params = pd.read_csv(
            path, header=None, names=["file_directory", "Date", "Time", "PKA", "NSS"]
        )

        if exp_params.empty:
            raise ValueError(f"Time parameter file is empty: {path}")

        exp_params["file_directory"] = exp_params["file_directory"].apply(
            lambda x: str(x).split()[0].strip("\"'")
        )
        exp_params["iterator"] = exp_params["file_directory"].apply(
            lambda x: str(x).split(".")[-1]
        )

        time_strings = exp_params["Time"].astype(str).str.strip()
        time_strings = time_strings.apply(lambda t: self._add_milliseconds(t, path))
        exp_params["Time"] = time_strings

        datetime_primary = pd.to_datetime(
            exp_params["Date"] + " " + time_strings,
            format=" %Y-%m-%d %H:%M:%S.%f",
            errors="coerce",
        )
        datetime_time_only = pd.to_datetime(
            time_strings, format="%H:%M:%S.%f", errors="coerce"
        )
        datetime_trailing_dot = pd.to_datetime(
            time_strings, format="%H:%M:%S.", errors="coerce"
        )

        exp_params["DateTime"] = datetime_primary.fillna(datetime_time_only).fillna(
            datetime_trailing_dot
        )

        if bool(exp_params["DateTime"].isna().any()):
            bad_rows = exp_params[exp_params["DateTime"].isna()].index.tolist()
            raise ValueError(
                f"Failed to parse DateTime from {path}; problematic rows: {bad_rows}"
            )

        return exp_params

    def _compute_elapsed_seconds(
        self, exp_params: pd.DataFrame, iterator: str
    ) -> float:
        if exp_params.empty:
            raise ValueError(
                "Experiment parameters are empty; cannot compute elapsed time."
            )

        time_ref = exp_params["DateTime"].min()
        match = exp_params[exp_params["iterator"] == iterator]
        if match.empty:
            raise ValueError(f"Iterator {iterator} not found in experiment parameters.")

        time_val = match.iloc[0]["DateTime"]
        return float((time_val - time_ref).total_seconds())

    def _load_spectrum(self, csv_path: str) -> Spectrum:
        if not os.path.isfile(csv_path):
            raise FileNotFoundError(f"Spectrum file not found: {csv_path}")

        df = pd.read_csv(csv_path, header=None)
        arr = df.values

        if arr.ndim != 2 or arr.shape[1] < 2:
            raise ValueError(
                f"Spectrum file must have at least two columns: {csv_path}"
            )

        return arr[:, :2].astype(float)

    def _slice_regions(self, spec: Spectrum) -> dict[str, Spectrum]:
        regions: dict[str, Spectrum] = {}
        for key, (low, high) in self.windows.items():
            mask = (spec[:, 0] >= low) & (spec[:, 0] <= high)
            regions[key] = spec[mask]
        return regions

    def _baseline_subtract(self, y: np.ndarray) -> np.ndarray:
        baseline_result = self.baseline_method(y, **self.baseline_params)
        if baseline_result is None:
            raise ValueError(
                "Baseline computation failed; std_distribution returned None."
            )
        baseline = baseline_result[0]
        return y - baseline

    def _detect_peaks(
        self, x: np.ndarray, y_bs: np.ndarray, params: ProminenceHeight
    ) -> tuple[np.ndarray, np.ndarray]:
        prominence, height = params
        peaks, properties = self.peak_finder(y_bs, prominence=prominence, height=height)
        peak_positions = x[peaks]
        peak_heights = properties["peak_heights"]
        return peak_positions, peak_heights

    def _build_records(
        self,
        tag: str,
        peak_positions: np.ndarray,
        peak_heights: np.ndarray,
        elapsed_s: float,
    ) -> list[PeakRecord]:
        records: list[PeakRecord] = []
        for wnum, height in zip(peak_positions, peak_heights):
            records.append(
                {
                    "file": tag,
                    "time (s)": elapsed_s,
                    "peak": wnum,
                    "height": height,
                }
            )
        return records

    def _process_dtype(
        self,
        regions: dict[str, Spectrum],
        thresholds: dict[str, ProminenceHeight],
        tag: str,
        elapsed_s: float,
        skip: bool = False,
    ) -> list[PeakRecord]:
        if skip:
            return []

        records: list[PeakRecord] = []
        for region, spec in regions.items():
            if spec.size == 0:
                continue
            if region not in thresholds:
                raise KeyError(f"Missing thresholds for region '{region}'")
            x = spec[:, 0]
            y_bs = self._baseline_subtract(spec[:, 1])
            peak_positions, peak_heights = self._detect_peaks(
                x, y_bs, thresholds[region]
            )
            records.extend(
                self._build_records(tag, peak_positions, peak_heights, elapsed_s)
            )
        return records

    def _dedupe_and_save(
        self, records: list[PeakRecord], outfile: str, tag: str
    ) -> None:
        if not records:
            return

        os.makedirs(os.path.dirname(outfile), exist_ok=True)
        new_df = pd.DataFrame(records)

        if os.path.isfile(outfile):
            existing = pd.read_csv(outfile, header=0, dtype={"file": str})
            if "file" in existing.columns and (existing["file"] == tag).any():
                return
            combined = pd.concat([existing, new_df], axis=0, ignore_index=True)
        else:
            combined = new_df

        combined = combined.sort_values(by=["file", "peak"]).reset_index(drop=True)
        combined.to_csv(outfile, index=False)

    def _save_file(self, parsed: ParsedPaths, dtype_key: str) -> str:
        suffix = self.output_suffixes[dtype_key]
        return os.path.join(parsed.save_dir, f"{parsed.base_name}_{suffix}.csv")

    @staticmethod
    def _add_milliseconds(time_str: str, source: str) -> str:
        if time_str is None:
            raise ValueError(f"Missing Time value in {source}")

        clean = str(time_str).strip()
        if clean == "" or clean.lower() == "nan":
            raise ValueError(f"Missing Time value in {source}")

        if clean.endswith("."):
            return f"{clean}000000"
        if "." not in clean:
            return f"{clean}.000000"
        return clean

    @staticmethod
    def _should_skip_subifg(delta_file: str | None, iterator: str) -> bool:
        if delta_file is None:
            return False

        if delta_file == "delta1":
            try:
                return int(iterator) > 2
            except ValueError:
                return False

        return delta_file in {"delta2", "delta3", "delta4"}
