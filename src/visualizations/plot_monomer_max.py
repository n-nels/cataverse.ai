"""Plot the most-likely monomer peak per experiment stem.

For each experiment stem, take the peak_bin with the largest time_total_fraction.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import cast

import matplotlib.pyplot as plt
import pandas as pd

path = Path(__file__).parent.parent.parent
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.core import config

LOGGER = logging.getLogger(__name__)

PLOT_ALL = False
FOLDER_NAME = "nn1120-3_pd_ceo2_001"


def _resolve_input_root() -> Path:
    return Path(config.get_path("data.peak_fit"))


def _resolve_output_root() -> Path:
    return Path(config.get_path("data.figures"))


def load_folder_data(folder_name: str, input_root: Path) -> pd.DataFrame:
    csv_path = input_root / folder_name / f"{folder_name}_monomerMax.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    df = pd.read_csv(csv_path)
    df["folder"] = folder_name
    return df


def load_all_data(input_root: Path) -> pd.DataFrame:
    csv_files = list(input_root.rglob("*_monomerMax.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No monomerMax CSV files found in {input_root}")
    frames = []
    for path in csv_files:
        df = pd.read_csv(path)
        if "folder" not in df.columns:
            df["folder"] = path.parent.name
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def build_stem_index(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["stem"] = df["file_name"].astype(str).str.split(".").str[0]
    unique_stems = sorted(df["stem"].unique())
    stem_to_index = {stem: idx for idx, stem in enumerate(unique_stems)}
    df["x_index"] = df["stem"].apply(lambda stem: stem_to_index.get(stem, -1))
    return df


def select_mode(df: pd.DataFrame) -> pd.DataFrame:
    filtered = df[df["x_index"] >= 0].copy()
    grouped = filtered.groupby("stem", as_index=False)["time_total_fraction"].max()
    grouped = cast(pd.DataFrame, grouped)
    merged = filtered.merge(grouped, on=["stem", "time_total_fraction"], how="inner")
    return cast(pd.DataFrame, merged)


def plot_mode(
    df: pd.DataFrame, title: str, output_path: Path, boundaries: list[int]
) -> None:
    if df.empty:
        LOGGER.warning("No data available to plot.")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.scatter(
        df["x_index"],
        df["peak_bin"],
        c=df["time_total_fraction"],
        cmap="plasma",
        s=60,
        edgecolors="black",
        linewidth=0.5,
    )

    ax.set_xlabel("Experiment Index")
    ax.set_ylabel("Monomer Maximum (cm⁻¹)")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    for boundary in boundaries:
        ax.axvline(boundary - 0.5, color="gray", linestyle="--", linewidth=0.8)

    cbar = plt.colorbar(ax.collections[0], ax=ax)
    cbar.set_label("Time Fraction")

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight", format="tiff")
    plt.close(fig)

    LOGGER.info(f"Saved mode plot: {output_path}")


def plot_monomer_max(
    *,
    plot_all: bool = False,
    folder_name: str | None = None,
    input_root: Path | None = None,
    output_root: Path | None = None,
) -> Path | None:
    """Plot monomer max mode data for one folder or all folders."""
    input_root = _resolve_input_root() if input_root is None else input_root
    output_root = _resolve_output_root() if output_root is None else output_root

    if plot_all:
        df = load_all_data(input_root)
        title = "All Folders - Dominant Monomer Peak"
        all_output = Path(config.get_path("data.plot_monomer_max_all"))
        output_path = all_output / "all_monomer_max.tiff"
    else:
        if not folder_name:
            raise ValueError("folder_name is required when plot_all is False")
        df = load_folder_data(folder_name, input_root)
        title = f"{folder_name} - Dominant Monomer Peak"
        output_path = output_root / folder_name / f"{folder_name}_monomerMax.tiff"
    df = build_stem_index(df)
    df_mode = select_mode(df)
    boundaries: list[int] = []
    if plot_all and not df_mode.empty:
        folder_bounds = (
            df_mode.groupby("folder")["x_index"].min().sort_values().tolist()
        )
        boundaries = folder_bounds[1:]
    plot_mode(df_mode, title, output_path, boundaries)
    return output_path


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    plot_monomer_max(
        plot_all=PLOT_ALL,
        folder_name=FOLDER_NAME,
        input_root=_resolve_input_root(),
        output_root=_resolve_output_root(),
    )


if __name__ == "__main__":
    main()
