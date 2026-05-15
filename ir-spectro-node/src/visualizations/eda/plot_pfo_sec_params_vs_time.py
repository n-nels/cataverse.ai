"""Plot secondary PFO kinetic parameters versus time for each file."""

from __future__ import annotations

from pathlib import Path
import argparse
import logging
import sys

import matplotlib.pyplot as plt
import pandas as pd


path = Path(__file__).parent.parent.parent.parent
if str(path) not in sys.path:
    sys.path.append(str(path))


LOGGER = logging.getLogger(__name__)

INPUT_DIR = Path(r"C:\Data\peakFit\nn1120-3_pd_ceo2_004")
OUTPUT_DIR = Path(r"C:\Figures\_plot")
FILE_PATTERN = (
    "20260423_055558_pd_ceo2_004-016_CarbonylPeakArea.csv"
)
PEAK_NAME = "monomer_sum"
TIME_COLUMN = "Time (s)"
PARAM_PREFIX = "pfo-sec_"
FIG_DPI = 300


def _collect_param_columns(df: pd.DataFrame) -> list[str]:
    return [col for col in df.columns if col.startswith(PARAM_PREFIX)]


def _prep_dataframe(df: pd.DataFrame, peak_name: str | None) -> pd.DataFrame:
    df = df.copy()
    if peak_name and "Peak_Name" in df.columns:
        df = df.loc[df["Peak_Name"] == peak_name].copy()
    if TIME_COLUMN not in df.columns:
        return pd.DataFrame()

    df[TIME_COLUMN] = pd.to_numeric(df[TIME_COLUMN], errors="coerce")
    df = df.dropna(subset=[TIME_COLUMN])
    return df


def _plot_file(csv_path: Path, output_dir: Path, peak_name: str | None) -> None:
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        LOGGER.warning("Failed to read %s: %s", csv_path, exc)
        return

    df = _prep_dataframe(df, peak_name)
    if df.empty:
        LOGGER.info("No data to plot for %s", csv_path.name)
        return

    param_columns = _collect_param_columns(df)
    if not param_columns:
        LOGGER.info("No secondary PFO columns in %s", csv_path.name)
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    for param in param_columns:
        df[param] = pd.to_numeric(df[param], errors="coerce")
        fig, ax = plt.subplots(figsize=(6, 4))
        df_plot = df.dropna(subset=[TIME_COLUMN, param]).copy()
        if df_plot.empty:
            plt.close(fig)
            continue
        df_plot = df_plot.sort_values(TIME_COLUMN)
        ax.scatter(
            df_plot[TIME_COLUMN],
            df_plot[param],
            s=14,
            alpha=0.7,
        )

        ax.set_xlabel(TIME_COLUMN)
        ax.set_ylabel(param)
        ax.set_title(f"{csv_path.stem}: {param}")

        fig.tight_layout()
        output_path = output_dir / f"{csv_path.stem}_{param}_pfo-sec_vs_time.tiff"
        fig.savefig(output_path, dpi=FIG_DPI, bbox_inches="tight")
        plt.close(fig)


def plot_folder(
    input_dir: Path = INPUT_DIR,
    output_dir: Path = OUTPUT_DIR,
    peak_name: str | None = PEAK_NAME,
    file_pattern: str = FILE_PATTERN,
) -> None:
    if not input_dir.exists():
        raise SystemExit(f"Missing input folder: {input_dir}")

    csv_paths = sorted(input_dir.glob(file_pattern))
    if not csv_paths:
        raise SystemExit(f"No CSV files found under: {input_dir}")

    for csv_path in csv_paths:
        _plot_file(csv_path, output_dir, peak_name)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Plot secondary PFO parameters vs time (one plot per parameter).")
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=INPUT_DIR,
        help="Folder containing CarbonylPeakArea CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Output folder for plots.",
    )
    parser.add_argument(
        "--peak-name",
        type=str,
        default=PEAK_NAME,
        help="Peak name to plot (set empty to disable filtering).",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default=FILE_PATTERN,
        help="Filename glob pattern for input CSVs.",
    )
    return parser


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args()
    peak_name_arg = args.peak_name or None
    plot_folder(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        peak_name=peak_name_arg,
        file_pattern=args.pattern,
    )
