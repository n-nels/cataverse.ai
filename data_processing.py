# Requirements: pip install pandas matplotlib

import glob
import os

import matplotlib.pyplot as plt
import pandas as pd

REQUIRED_COLS = ["relative_time_s", "amount_adsorbed_umol/g", "apparent_conversion"]

def load_pressure_data(csv_path):
    """Load a single *_pressure_log.csv and ensure required columns exist."""
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Could not read {csv_path}: {e}")
        return None

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        print(f"Skipping {os.path.basename(csv_path)}: missing columns {missing}")
        return None

    return df

def plot_pressure_data(df, output_path, title=None):
    """Plot relative_time_s vs amount_adsorbed_umol/g (left) and apparent_conversion (right)."""
    if df is None:
        return

    x = df["relative_time_s"]
    y_left = df["amount_adsorbed_umol/g"]
    y_right = df["apparent_conversion"]

    fig, ax1 = plt.subplots()
    ax1.scatter(x, y_left, s=10)
    ax1.set_xlabel("Relative time (s)")
    ax1.set_ylabel("Amount adsorbed (µmol/g)")
    ax1.tick_params(axis="y")

    ax2 = ax1.twinx()
    ax2.scatter(x, y_right, s=10)
    ax2.set_ylabel("Apparent conversion")
    ax2.tick_params(axis="y")

    if title:
        plt.title(title)
    plt.tight_layout()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=300, format="tiff")
    plt.close(fig)
    print(f"Saved {output_path}")

def process_folder(folder_name):
    # """Process all *_pressure_log.csv in C:\Data\{folder_name} and save to C:\Figures\{folder_name}."""
    # input_dir = os.path.join(r"C:\Data", folder_name)
    # output_dir = os.path.join(r"C:\Figures", folder_name)
    os.makedirs(output_dir, exist_ok=True)

    pattern = os.path.join(input_dir, "*_pressureLog.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"No files matching *_pressureLog.csv in {input_dir}")
        return

    for csv_path in files:
        title = os.path.splitext(os.path.basename(csv_path.split('_pressureLog')[0]))[0]
        df = load_pressure_data(csv_path)
        if df is None:
            continue
        out_path = os.path.join(output_dir, f"{title}.tiff")
        if os.path.exists(out_path):
            print(f"Figure already exists: {out_path}, skipping.")
            continue
        plot_pressure_data(df, out_path, title=title)

if __name__ == "__main__":

    folder = r'nn1120-3_pd_ceo2_004'
    input_dir = f"C:\\Data\\{folder}"
    output_dir = f"C:\\Figures\\{folder}"

    file = r'20250610_200952_pd_ceo2_001-044_pressureLog.csv'

    process_folder(folder)
