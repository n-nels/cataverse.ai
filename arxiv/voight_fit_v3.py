import os
import glob
import warnings
import pandas as pd
import numpy as np
import pybaselines
from lmfit import Model
from lmfit import Parameters, Minimizer
from scipy.signal import find_peaks
from scipy.special import voigt_profile
from scipy.integrate import trapezoid
from scipy.optimize import curve_fit, OptimizeWarning
from scipy.stats import t

try:
    from ..core import config
except ImportError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core import config


def get_peak_list(config_settings):
    base_list = config_settings.get("peak_list_base", [])
    if not base_list:
        return [  # /let's do error handling and tell user that base list is missing
            2196,
            2176,
            2156,
            2146,
            2136,
            2125,
            2113,
            2103,
            2093,
            2073,
            2062,
            2050,
            2040,
            2030,
            2015,
            2000,
            1988,
            1975,
        ]

    isotope = config_settings.get("isotope_default", "13CO")
    shifts = config_settings.get("isotope_shift_cm1", {})
    shift_value = shifts.get(isotope, 0)
    return [peak + shift_value for peak in base_list]


def get_shifted_rules(config_settings):
    isotope = config_settings.get("isotope_default", "13CO")
    rule_isotope = config_settings.get("param_rules_base_isotope", isotope)
    shifts = config_settings.get("isotope_shift_cm1", {})
    shift_value = shifts.get(isotope, 0) - shifts.get(rule_isotope, 0)
    if shift_value == 0:
        return config_settings.get("param_rules", [])

    shifted_rules = []
    for rule in config_settings.get("param_rules", []):
        rule_copy = dict(rule)
        range_cm1 = rule.get("range_cm1")
        if range_cm1 and len(range_cm1) == 2:
            rule_copy["range_cm1"] = [
                range_cm1[0] + shift_value,
                range_cm1[1] + shift_value,
            ]
        shifted_rules.append(rule_copy)
    return shifted_rules


def get_shifted_monomer_peaks(config_settings):
    isotope = config_settings.get("isotope_default", "13CO")
    monomer_isotope = config_settings.get("monomer_peaks_base_isotope", isotope)
    shifts = config_settings.get("isotope_shift_cm1", {})
    shift_value = shifts.get(isotope, 0) - shifts.get(monomer_isotope, 0)
    monomer_peaks = config_settings.get("monomer_peaks_base")
    if not monomer_peaks:
        return [2093, 2103, 2113, 2125]
    return [peak + shift_value for peak in monomer_peaks]


def add_milliseconds(time_str):
    if "." not in time_str:
        return time_str + ".000000"
    return time_str


def voigt_model(x, y0, amplitude, center, sigma, gamma):
    return y0 + (amplitude * voigt_profile(x - center, sigma, gamma))


def combined_voigt(x, fit_params, peak_list_core):
    combined_profile = np.zeros_like(x)
    for peak in peak_list_core:
        center = fit_params[f"center_{peak}"].value
        amplitude = fit_params[f"amplitude_{peak}"].value
        sigma = fit_params[f"sigma_{peak}"].value
        gamma = fit_params[f"gamma_{peak}"].value
        y0 = fit_params[f"y0_{peak}"].value
        combined_profile += Model(voigt_model).eval(
            x=x, y0=y0, center=center, amplitude=amplitude, sigma=sigma, gamma=gamma
        )
    return combined_profile


def objective(fit_params, wavenumbers, y_baseline, peak_list_core):
    return combined_voigt(wavenumbers, fit_params, peak_list_core) - y_baseline


def peak_fit(fit_params, wavenumbers, y_baseline, peak_list_core):
    minimizer = Minimizer(
        lambda current_params: objective(
            current_params, wavenumbers, y_baseline, peak_list_core
        ),
        fit_params,
    )
    return minimizer.minimize()


def save_data(new_data, file_path, axis):
    if os.path.isfile(file_path):
        try:
            existing_data = pd.read_csv(file_path, header=0)
        except Exception as e:
            existing_data = pd.DataFrame()
            print(f"Error reading existing data {file_path}: {e}")
        if "Wavenumber (cm-1)" in existing_data.columns:
            new_data = new_data.drop(columns=["Wavenumber (cm-1)"])
        combined_data = pd.concat(
            [existing_data, new_data], axis=axis, ignore_index=False
        )
        try:
            combined_data = combined_data.sort_values(by=["Peak_Name", "File"])
        except Exception as e:
            if 'Peak_Name' not in combined_data.columns or 'File' not in combined_data.columns:
                pass
            else:
                print(f"Error sorting combined data for {file_path}: {e}")
    else:
        combined_data = new_data

    combined_data.to_csv(file_path, index=False)


def import_data(file_path, fsd_dir, subifg_log_dir, time_dir):

    # import subifg data
    df_subifg = pd.read_csv(file_path, header=None)
    df_subifg_roi_cm1 = df_subifg.loc[(df_subifg[0] >= 1750) & (df_subifg[0] <= 2250)]
    if df_subifg_roi_cm1.empty:
        raise ValueError(f"No subifg data in ROI for {file_path}")
    arr_subifg_roi = df_subifg_roi_cm1.values

    # import fsd data
    df_fsd = pd.read_csv(fsd_dir, header=None)
    df_fsd_roi_cm1 = df_fsd.loc[(df_fsd[0] >= 1750) & (df_fsd[0] <= 2250)]
    if df_fsd_roi_cm1.empty:
        raise ValueError(f"No FSD data in ROI for {fsd_dir}")
    arr_fsd_roi = df_fsd_roi_cm1.values

    # import subifg file log
    subifg_log = pd.read_csv(
        subifg_log_dir, header=None, names=["sample_name", "sample", "background"]
    )
    if subifg_log.empty:
        raise ValueError(f"No subifg log entries found in {subifg_log_dir}")

    subifg_log["sample_name"] = (
        subifg_log["sample_name"].str.replace(r"[\'\(\)]", "", regex=True).str.strip()
    )

    subifg_log["sample"] = (
        subifg_log["sample"]
        .str.extract(r"([^\s\'\"]+)")
        .replace(r"\\\\", r"\\", regex=True)
    )

    subifg_log["background"] = (
        subifg_log["background"]
        .str.extract(r"([^\s\'\"]+)")
        .replace(r"\\\\", r"\\", regex=True)
    )

    # import experimental parameters
    exp_params = pd.read_csv(
        time_dir,
        header=None,
        names=["file_directory", "Date", "Time", "PKA", "NSS"],
    )
    if exp_params.empty:
        raise ValueError(f"No experiment parameters found in {time_dir}")

    exp_params["file_directory"] = exp_params["file_directory"].apply(
        lambda x: x.split()[0].strip("\"'")
    )

    exp_params["Time"] = exp_params["Time"].str.strip()
    exp_params["Time"] = exp_params["Time"].apply(add_milliseconds)

    exp_params["datetime"] = pd.to_datetime(
        exp_params["Date"] + " " + exp_params["Time"],
        format=" %Y-%m-%d %H:%M:%S.%f",
        errors="coerce",
    )

    exp_params["datetime"] = exp_params["datetime"].fillna(
        pd.to_datetime(exp_params["Time"], format="%H:%M:%S.", errors="coerce")
    )

    return arr_subifg_roi, arr_fsd_roi, subifg_log, exp_params


def find_fsd_peaks(arr_fsd_roi, baseline_settings, fsd_peak_settings):
    x = arr_fsd_roi[:, 0]
    fsd_signal = arr_fsd_roi[:, 1].T

    fsd_baseline = pybaselines.classification.std_distribution(
        fsd_signal,
        half_window=baseline_settings.get("half_window", 10),
        interp_half_window=baseline_settings.get("interp_half_window", 5),
        fill_half_window=baseline_settings.get("fill_half_window", 6),
        num_std=baseline_settings.get("num_std", 1.1),
        smooth_half_window=baseline_settings.get("smooth_half_window"),
        weights=baseline_settings.get("weights"),
    )[0]
    fsd_baseline_corrected = fsd_signal - fsd_baseline

    peaks, properties = find_peaks(
        fsd_baseline_corrected,
        prominence=fsd_peak_settings.get("prominence", 0.0001),
        height=fsd_peak_settings.get("height", 0.003),
    )
    peak_wavenumbers = x[peaks]

    return peaks


def linfunc(x, a, b):
    return a * x + b


def linfunc_no_intercept(x, a):
    return a * x


def pfo_decay(time_s, k_a, k_d, qe):
    return (qe * (1 - np.exp(-k_a * time_s))) * np.exp(-k_d * time_s)


def calculate_metrics(intensity, y_pred):
    residuals = intensity - y_pred
    ss_tot = np.sum((intensity - np.mean(intensity)) ** 2)  # total sum of squares
    ss_res = np.sum(residuals**2)  # residual sum of squares

    r_squared = 1 - (ss_res / ss_tot)
    rmse = np.sqrt(np.mean(residuals**2))

    return r_squared, rmse


def fit_and_evaluate(wavenumbers, intensity, func, p0=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", OptimizeWarning)
        try:
            with np.errstate(
                divide="ignore", invalid="ignore", over="ignore", under="ignore"
            ):
                popt, pcov = curve_fit(
                    func, wavenumbers, intensity, p0=p0, bounds=(0, np.inf)
                )
                y_pred = func(wavenumbers, *popt)
                r_squared, rmse = calculate_metrics(intensity, y_pred)
                std_errors = np.sqrt(np.diag(pcov))  # stderr of param estimates
                return popt, std_errors, r_squared, rmse
        except Exception:
            if p0 is not None:
                popt_length = len(p0)
            else:
                popt_length = len(func.__code__.co_varnames) - 1  # exclude x
            return (
                np.full(popt_length, np.nan),
                np.full(popt_length, np.nan),
                np.nan,
                np.nan,
            )


def pfo_fit(df_cumulative_peak_area):
    fit_result_frames = []
    df_cumulative_peak_area = df_cumulative_peak_area.sort_values(
        ["Peak_Name", "Time (s)"]
    ).reset_index(drop=True)
    df_cumulative_peak_area["original_index"] = df_cumulative_peak_area.groupby(
        "Peak_Name"
    ).cumcount()

    for peak_name, group in df_cumulative_peak_area.groupby("Peak_Name"):
        fit_results = []
        group = group.reset_index(drop=True)

        if len(group) < 5:
            df_cumulative_peak_area.drop("original_index", axis=1, inplace=True)
            return df_cumulative_peak_area

        for i in range(5, len(group)):
            time_s = np.array(group["Time (s)"].iloc[: i + 1])
            # y = np.array(group['Cumulative_PdCO_mol'].iloc[:i+1])
            cumulative_peak_area = np.array(group["Cumulative_Peak_Area"].iloc[: i + 1])
            current_row = group.iloc[i]

            (
                popt_pfo_decay,
                std_errors_pfo_decay,
                r_squared_pfo_decay,
                rmse_pfo_decay,
            ) = fit_and_evaluate(
                time_s, cumulative_peak_area, pfo_decay, p0=[1e-4, 1e-6, 0.1]
            )

            ka_pfo_decay, kd_pfo_decay, q_pfo_decay = popt_pfo_decay
            ka_stderr_pfo_decay, kd_stderr_pfo_decay, q_stderr_pfo_decay = (
                std_errors_pfo_decay
            )

            result = {
                "Peak_Name": peak_name,
                "Time (s)": current_row["Time (s)"],
                "original_index": current_row["original_index"],
                "ka_s-1": ka_pfo_decay,
                "ka_stderr": ka_stderr_pfo_decay,
                "kd_s-1": kd_pfo_decay,
                "kd_stderr": kd_stderr_pfo_decay,
                "qe_mol": q_pfo_decay,
                "qe_stderr": q_stderr_pfo_decay,
                "r^2": r_squared_pfo_decay,
                "rmse": rmse_pfo_decay,
            }
            fit_results.append(result)

        if fit_results:
            df = pd.DataFrame(fit_results)
            fit_result_frames.append(df)

    if fit_result_frames:
        df_pfo_fit_results = pd.concat(fit_result_frames, ignore_index=True)

        # Now merge with all columns present
        df_cpa_pfo = pd.merge(
            df_cumulative_peak_area,
            df_pfo_fit_results,
            on=["Peak_Name", "Time (s)", "original_index"],
            how="left",
        )

        df_cpa_pfo.drop("original_index", axis=1, inplace=True)
        df_cpa_pfo = df_cpa_pfo.sort_values(["Peak_Name", "Delta_Group"]).reset_index(
            drop=True
        )
        return df_cpa_pfo
    return None


def import_calibration_data(folder_name, calibration_dir):
    calibration_frames = []
    df_calibration_data = None

    if folder_name == "nn1120-2_pd_ceo2_000":
        skip_files = [
            "allData",
            "000-003",
            "000-005",
            "000-007",
            "000-009",
            "000-011",
            "000-013",
            "000-014",
            "000-016",
            "000-017",
        ]
        try:
            for file in glob.glob(os.path.join(calibration_dir, "*")):
                if any(string in file for string in skip_files):
                    continue
                df = pd.read_csv(file)
                calibration_frames.append(df)

            df_calibration_data = pd.concat(calibration_frames, ignore_index=True)
        except Exception:
            return None

    if folder_name == "nn1120-3_pd_ceo2_000":
        skip_files = [
            "allData",
            "000-005",
            "000-007",
            "000-009",
            "000-010",
            "000-012",
        ]
        try:
            for file in glob.glob(os.path.join(calibration_dir, "*")):
                if any(string in file for string in skip_files):
                    continue
                df = pd.read_csv(file)
                calibration_frames.append(df)

            df_calibration_data = pd.concat(calibration_frames, ignore_index=True)
        except Exception:
            return None

    # clean data
    if df_calibration_data is None:
        return None

    try:
        df_calibration_data["Peak_Area"] = df_calibration_data["Peak_Area"] * -1
        df_calibration_data["Peak_Area"] = df_calibration_data["Peak_Area"].mask(
            df_calibration_data["Peak_Area"] < 0, 0
        )

        mask = (
            (df_calibration_data["Peak_Area"] >= 0)
            & (df_calibration_data["Peak_Area"] <= 0.05)
            & (df_calibration_data["co_moles"] >= 0)
            & (df_calibration_data["co_moles"] > 2.5e-10)
            & ~(
                (df_calibration_data["Peak_Area"] == 0)
                & (df_calibration_data["co_moles"] > 1e-9)
            )
        )
        df_calibration_data = df_calibration_data[mask]

        # find slope between carbonyl area and moles
        x = df_calibration_data["Peak_Area"]
        y = df_calibration_data["co_moles"]
        popt, pcov = curve_fit(linfunc, x, y)
        slope, intercept = popt

        df_calibration_data["co_moles"] = df_calibration_data["co_moles"] - intercept
        y = df_calibration_data["co_moles"]
        popt, pcov = curve_fit(linfunc_no_intercept, x, y)
        peak_area_mole_carbonyl_slope = popt

        # output calibration data
        output = os.path.join(calibration_dir, folder_name + "_allData.csv")
        df_calibration_data.to_csv(output, index=False)
        return x, y, peak_area_mole_carbonyl_slope, pcov
    except Exception:
        return None


def calibration_statistics(
    calibration_peak_area, calibration_moles, peak_area_mole_carbonyl_slope, pcov
):
    if calibration_peak_area is None or len(calibration_peak_area) < 2:
        return None, np.nan
    y_pred = linfunc_no_intercept(
        calibration_peak_area, peak_area_mole_carbonyl_slope
    )  # predicted y-values
    std_errors = np.sqrt(np.diag(pcov))  # stderr for parameters
    residuals = calibration_moles - y_pred
    see = np.sqrt(np.mean(residuals**2))  # stderr for estimate
    ss_tot = np.sum(
        calibration_moles**2
    )  # total sum of squares when passed through origin
    ss_res = np.sum(residuals**2)  # residual sum of squares
    r_squared = 1 - (ss_res / ss_tot)
    rmse = np.sqrt(np.mean(residuals**2))

    # Calculate the critical value for the t-distribution
    dof = len(calibration_peak_area) - 2  # degrees of freedom
    confidence_level = 0.975  # for a 95% confidence level
    t_critical = t.ppf(confidence_level, dof)

    # Calculate the standard error
    pred_stderr = see * np.sqrt(
        1
        + 1 / len(calibration_peak_area)
        + (calibration_peak_area - np.mean(calibration_peak_area)) ** 2
        / np.sum((calibration_peak_area - np.mean(calibration_peak_area)) ** 2)
    )

    # Calculate the prediction interval
    pred_interval = (
        t_critical
        * see
        * np.sqrt(
            1
            + 1 / len(calibration_peak_area)
            + (calibration_peak_area - np.mean(calibration_peak_area)) ** 2
            / np.sum((calibration_peak_area - np.mean(calibration_peak_area)) ** 2)
        )
    )

    y_pred_lower = y_pred - pred_interval
    y_pred_upper = y_pred + pred_interval

    return see, r_squared


def save_peak_parameters(
    peak_fit_records,
    file_name,
    save_dir,
    calibration_peak_area,
    peak_area_mole_carbonyl_slope,
    see,
):
    # save peak parameters for each file
    df_fit_peaks = pd.DataFrame(peak_fit_records)
    try:
        df_fit_peaks["PdCO_mol"] = linfunc_no_intercept(
            df_fit_peaks["Peak_Area"], peak_area_mole_carbonyl_slope
        )
        df_fit_peaks["PdCO_mol_stderr"] = see * np.sqrt(
            1
            + 1 / len(calibration_peak_area)
            + (df_fit_peaks["Peak_Area"] - np.mean(calibration_peak_area)) ** 2
            / np.sum((calibration_peak_area - np.mean(calibration_peak_area)) ** 2)
        )
    except Exception:
        pass
    filename = f"{file_name}_CarbonylPeakFitParams.csv"
    path = os.path.join(save_dir, filename)
    save_data(new_data=df_fit_peaks, file_path=path, axis=0)
    return path


def save_peak_area_versus_time(path, file_name, save_dir, sum_areas_peaks):
    cumulative_area_rows = []
    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"Error reading peak parameter file {path}: {e}")
        return

    cumulative_area_delta1 = None
    cumulative_integral_delta1 = None
    time_sec_delta1 = None
    cumulative_pdco_delta1 = None
    cumulative_stderr_delta1 = None

    for (peak_name, delta_group), group in df.groupby(["Peak_Name", "Delta_Group"]):
        if delta_group == "delta1":
            cumulative_area_delta1 = (
                group[group["Delta_Group"] == "delta1"]["Peak_Area"].iloc[:2].sum()
            )
            cumulative_integral_delta1 = (
                group[group["Delta_Group"] == "delta1"]["Data_Integral"].iloc[:2].sum()
            )
            time_sec_delta1 = (
                group[group["Delta_Group"] == "delta1"]["Time_Delta (s)"].iloc[:2].sum()
            )
            try:
                cumulative_pdco_delta1 = (
                    group[group["Delta_Group"] == "delta1"]["PdCO_mol"].iloc[:2].sum()
                )
                cumulative_stderr_sumSqrs_delta1 = (
                    group[group["Delta_Group"] == "delta1"]["PdCO_mol_stderr"].iloc[:2]
                    ** 2
                ).sum()
                cumulative_stderr_delta1 = np.sqrt(cumulative_stderr_sumSqrs_delta1)
            except Exception:
                pass
            continue

        if cumulative_area_delta1 is None:
            continue
        cumulative_area = cumulative_area_delta1
        cumulative_integral = cumulative_integral_delta1
        time_sec = time_sec_delta1
        cumulative_pdco = cumulative_pdco_delta1
        cumulative_stderr = cumulative_stderr_delta1

        for index, row in group.iterrows():
            cumulative_area += np.nan_to_num(row["Peak_Area"])
            cumulative_integral += np.nan_to_num(row["Data_Integral"])
            time_sec += row["Time_Delta (s)"]
            try:
                cumulative_pdco += np.nan_to_num(row["PdCO_mol"])
                cumulative_stderr += np.sqrt(np.nan_to_num(row["PdCO_mol_stderr"]) ** 2)
            except Exception:
                pass

            row_payload = {
                "File": row["File"],
                "Delta_Group": row["Delta_Group"],
                "Peak_Name": peak_name,
                "Peak_Center": row["Center"],
                "Time (s)": time_sec,
                "Cumulative_Peak_Area": cumulative_area,
                "Cumulative_Integral": cumulative_integral,
            }
            if cumulative_pdco is not None:
                row_payload["Cumulative_PdCO_mol"] = cumulative_pdco
            if cumulative_stderr is not None:
                row_payload["Cumul_PdCO_mol_stderr"] = cumulative_stderr
            cumulative_area_rows.append(row_payload)

    df_cumulative_areas = pd.DataFrame(cumulative_area_rows)
    if df_cumulative_areas.empty or "Peak_Name" not in df_cumulative_areas.columns:
        df_peak_area_output = df_cumulative_areas
        filename = f"{file_name}_CarbonylPeakArea.csv"
        path = os.path.join(save_dir, filename)
        df_peak_area_output.to_csv(path, index=False)
        return

    df_monomer_peaks = df_cumulative_areas[
        df_cumulative_areas["Peak_Name"].isin(sum_areas_peaks)
    ]
    if all(
        col in df_cumulative_areas.columns
        for col in ["Delta_Group", "Time (s)", "Peak_Name", "Cumulative_Peak_Area"]
    ):
        grouped = df_monomer_peaks.groupby(["Delta_Group", "Time (s)"])
        monomer_rows = []
        for (delta_group, time_s), group in grouped:
            summed_area = group["Cumulative_Peak_Area"].sum()
            file_val = group["File"].iloc[0] if "File" in group else ""
            row = {
                "File": file_val,
                "Delta_Group": delta_group,
                "Peak_Name": "monomer_sum",
                "Time (s)": time_s,
                "Cumulative_Peak_Area": summed_area,
            }
            for col in df_cumulative_areas.columns:
                if col not in row:
                    row[col] = ""
            monomer_rows.append(row)
        # Append monomer_sum rows
        df_cumulative_areas = pd.concat(
            [df_cumulative_areas, pd.DataFrame(monomer_rows)], ignore_index=True
        )

    # --- Now run pfo_fit ONCE on the combined DataFrame ---
    if df_cumulative_areas.empty:
        df_peak_area_output = df_cumulative_areas
    else:
        try:
            df_peak_area_output = pfo_fit(df_cumulative_areas)
        except Exception as e:
            print(f"An error occurred during pfo_fit: {e}")
            df_peak_area_output = df_cumulative_areas
        if df_peak_area_output is None:
            df_peak_area_output = df_cumulative_areas

    # --- Save final DataFrame ---
    filename = f"{file_name}_CarbonylPeakArea.csv"
    path = os.path.join(save_dir, filename)
    df_peak_area_output.to_csv(path, index=False)


def save_peak_fit_residual(file_path, arr_subifg_roi, residual, file_name, save_dir):
    df = pd.DataFrame()
    df["Wavenumber (cm-1)"] = arr_subifg_roi[:, 0]
    df.reset_index(drop=True, inplace=True)
    df_key = pd.DataFrame({file_path.split("_")[-1]: residual})

    df = pd.concat([df] + [df_key], axis=1)
    filename = f"{file_name}_CarbonylFitResidual.csv"
    path = os.path.join(save_dir, filename)
    save_data(new_data=df, file_path=path, axis=1)


def save_baseline_data(
    file_path, arr_subifg_roi, baseline_std_distribution, file_name, save_dir
):
    df = pd.DataFrame()
    df["Wavenumber (cm-1)"] = arr_subifg_roi[:, 0]
    df_key = pd.DataFrame({file_path.split("_")[-1]: baseline_std_distribution})
    df.reset_index(drop=True, inplace=True)

    df = pd.concat([df] + [df_key], axis=1)
    filename = f"{file_name}_CarbonylFitBaseline.csv"
    path = os.path.join(save_dir, filename)
    save_data(new_data=df, file_path=path, axis=1)


def create_baseline(y, baseline_settings):
    # create baseline and subtract
    baseline_std_distribution = pybaselines.classification.std_distribution(
        y,
        half_window=baseline_settings.get("half_window", 10),
        interp_half_window=baseline_settings.get("interp_half_window", 5),
        fill_half_window=baseline_settings.get("fill_half_window", 6),
        num_std=baseline_settings.get("num_std", 1.1),
        smooth_half_window=baseline_settings.get("smooth_half_window"),
        weights=baseline_settings.get("weights"),
    )[0]
    baseline_corrected = y - baseline_std_distribution
    return baseline_corrected, baseline_std_distribution


def select_param_rule(peak, parameter_rules):
    default_rule = None
    for rule in parameter_rules:
        if rule.get("default"):
            default_rule = rule
            continue

        range_cm1 = rule.get("range_cm1")
        if not range_cm1 or len(range_cm1) != 2:
            continue

        lower, upper = range_cm1
        upper_inclusive = rule.get("upper_inclusive", False)
        if peak >= lower and (peak <= upper if upper_inclusive else peak < upper):
            return rule

    return default_rule


def resolve_center_offsets(rule, peak, iterator, peak_tmp):
    center_rule = rule.get("center", {})
    min_offset = center_rule.get("min_offset", -1)
    max_offset = center_rule.get("max_offset", 1)
    for case in rule.get("special_cases", []):
        condition = case.get("condition")
        if condition == "peak_tmp is not None":
            if peak_tmp is not None:
                center_rule = case.get("center", {})
                min_offset = center_rule.get("min_offset", min_offset)
                max_offset = center_rule.get("max_offset", max_offset)
                break

    return min_offset, max_offset


def voight_fit(file_path):
    """This function fits a voigt profile to the carbonyl peak in the subifg data."""

    voigt_settings = config.get_analysis_setting("analysis.voight_fit")

    def add_params(file_path, fit_params, peak, peak_name):  # /remove file_path
        parameter_rules = get_shifted_rules(voigt_settings)
        param_rule = select_param_rule(peak, parameter_rules)
        if param_rule is None:
            return None

        min_offset, max_offset = resolve_center_offsets(
            param_rule, peak, file_index, temp_peak
        )
        center_value = param_rule.get("center", {})  # /remove
        fit_params.add(
            f"center_{peak_name}",
            value=peak,
            min=peak + min_offset,
            max=peak + max_offset,
        )

        amplitude_rule = param_rule.get("amplitude", {})
        amplitude_value = amplitude_rule.get("value", 0.01)
        if "min" in amplitude_rule:
            fit_params.add(
                f"amplitude_{peak_name}",
                value=amplitude_value,
                min=amplitude_rule["min"],
            )
        else:
            fit_params.add(f"amplitude_{peak_name}", value=amplitude_value)

        sigma_rule = param_rule.get("sigma", {})
        fit_params.add(
            f"sigma_{peak_name}",
            value=sigma_rule.get("value", 5),
            min=sigma_rule.get("min", 2.55),
            max=sigma_rule.get("max", 6.37),
        )

        gamma_rule = param_rule.get("gamma", {})
        if "max" in gamma_rule:
            fit_params.add(
                f"gamma_{peak_name}",
                value=gamma_rule.get("value", 2),
                min=gamma_rule.get("min", 0),
                max=gamma_rule.get("max", 2.8),
            )
        else:
            fit_params.add(
                f"gamma_{peak_name}",
                value=gamma_rule.get("value", 2),
                min=gamma_rule.get("min", 0),
            )

        y0_rule = param_rule.get("y0", {})
        fit_params.add(
            f"y0_{peak_name}",
            value=y0_rule.get("value", 0),
            min=y0_rule.get("min", 0),
            vary=y0_rule.get("vary", False),
        )

        return None  # /return params???

    def peak_analysis(file_path, wavenumbers):
        composite_fit = np.zeros_like(wavenumbers)
        residual = np.zeros_like(wavenumbers)

        # find time delta
        sample_name = file_path.split("\\")[-1]

        sample_name_indices = (
            subifg_log["sample_name"]
            .index[subifg_log["sample_name"] == sample_name]
            .tolist()
        )
        if not sample_name_indices:
            print(f"Missing subifg log entry for {file_path}")
            time_delta = 0
        else:
            try:
                sample = subifg_log["sample"][sample_name_indices].iloc[0]

                background = subifg_log["background"][sample_name_indices].iloc[0]

                matching_rows = [
                    exp_params[exp_params["file_directory"] == path].index[0]
                    for path in [sample, background]
                ]

                time_delta = (
                    exp_params["datetime"][matching_rows[0]]
                    - exp_params["datetime"][matching_rows[1]]
                ).total_seconds()
            except Exception as e:
                print(f"Error resolving time delta for {file_path}: {e}")
                time_delta = 0

        delta_group = file_path.split("_")[-1].split(".")[0]

        # skip fitting if criteria not met
        avg_y = np.mean(abs(baseline_corrected))

        subifg_peak_settings = voigt_settings.get("find_peaks", {}).get("subifg", {})
        subifg_prominence = subifg_peak_settings.get("prominence", 0.0003)
        subifg_height_multiplier = subifg_peak_settings.get("height_multiplier", 3)

        peaks_pos, properties = find_peaks(
            baseline_corrected,
            prominence=subifg_prominence,
            height=subifg_height_multiplier * avg_y,
        )
        peak_wavenumbers_pos = arr_subifg_roi[:, 0][peaks_pos]

        peaks_neg, properties = find_peaks(
            -baseline_corrected,
            prominence=subifg_prominence,
            height=subifg_height_multiplier * avg_y,
        )
        peak_wavenumbers_neg = arr_subifg_roi[:, 0][peaks_neg]

        if len(peaks_pos) == 0 and len(peaks_neg) == 0:
            print("skipped: ", file_path)

            wavenumbers_pos = wavenumbers[baseline_corrected >= 0]
            baseline_corrected_pos = baseline_corrected[baseline_corrected >= 0]
            wavenumbers_neg = wavenumbers[baseline_corrected < 0]
            baseline_corrected_neg = baseline_corrected[baseline_corrected < 0]

            integral_pos = -np.trapezoid(baseline_corrected_pos, wavenumbers_pos)
            integral_neg = -np.trapezoid(baseline_corrected_neg, wavenumbers_neg)
            subifg_integral = integral_pos + integral_neg

            for i, peak in enumerate(peak_list_core):
                if (delta_file == "delta9") or (delta_file == "delta10"):
                    peak_data = {
                        "File": file_path.split("_")[-1],
                        "Delta_Group": delta_group,
                        "Peak_Name": f"Peak_{peak}",
                        "Peak_Value": peak_list[i],
                        "Data_Integral": subifg_integral,
                        "Time_Delta (s)": time_delta,
                        "Peak_Area": 0,
                    }

                else:
                    peak_data = {
                        "File": file_path.split("_")[-1],
                        "Delta_Group": delta_group,
                        "Peak_Name": f"Peak_{peak}",
                        "Peak_Value": peak_list[i],
                        "Data_Integral": subifg_integral,
                        "Time_Delta (s)": time_delta,
                        "Peak_Area": 0,  # added 03/12/25
                    }

                peak_fit_records.append(peak_data)

            return composite_fit, residual

        else:
            # fit peaks
            fit_result_bundle = peak_fit(
                fit_params, wavenumbers, baseline_corrected, peak_list_core
            )
            fitted_params = fit_result_bundle.params
            residual = fit_result_bundle.residual

            for i, peak in enumerate(peak_list_core):
                center = fitted_params[f"center_{peak}"].value
                amplitude = fitted_params[f"amplitude_{peak}"].value
                sigma = fitted_params[f"sigma_{peak}"].value
                gamma = fitted_params[f"gamma_{peak}"].value
                y0 = fitted_params[f"y0_{peak}"].value

                y_fit = Model(voigt_model).eval(
                    x=wavenumbers,
                    y0=y0,
                    center=center,
                    amplitude=amplitude,
                    sigma=sigma,
                    gamma=gamma,
                )

                peak_area = -trapezoid(y_fit, wavenumbers)

                wavenumbers_pos = wavenumbers[baseline_corrected >= 0]
                baseline_corrected_pos = baseline_corrected[baseline_corrected >= 0]
                wavenumbers_neg = wavenumbers[baseline_corrected < 0]
                baseline_corrected_neg = baseline_corrected[baseline_corrected < 0]

                integral_pos = -np.trapezoid(baseline_corrected_pos, wavenumbers_pos)
                integral_neg = -np.trapezoid(baseline_corrected_neg, wavenumbers_neg)
                subifg_integral = integral_pos + integral_neg
                # subifg_integral = -np.trapezoid(baseline_corrected, wavenumbers)

                fwhm_gaussian = 2 * sigma * np.sqrt(2 * np.log(2))
                fwhm_lorentz = 2 * gamma
                fwhm_voigt = (0.5346 * fwhm_lorentz) + np.sqrt(
                    (0.2166 * fwhm_lorentz**2) + fwhm_gaussian**2
                )

                peak_data = {
                    "File": file_path.split("_")[-1],
                    "Delta_Group": delta_group,
                    "Peak_Name": f"Peak_{peak}",
                    "Peak_Value": peak_list[i],
                    "Data_Integral": subifg_integral,
                    "Center": center,
                    "Amplitude": amplitude,
                    "Sigma": sigma,
                    "Gamma": gamma,
                    "Y0": y0,
                    "fwhm": fwhm_voigt,
                    "Time_Delta (s)": time_delta,
                    "Peak_Area": peak_area,
                }

                peak_fit_records.append(peak_data)
                composite_fit += y_fit

            return composite_fit, residual

    def manually_skip_files(delta_file, file_index):
        """these files have low S/N from empirical observation"""
        if ((delta_file == "delta1") and (int(file_index) > 2)) or delta_file in {
            "delta2",
            "delta3",
            "delta4",
        }:
            return True
        return False

    peak_list_core = get_peak_list(voigt_settings)
    if not peak_list_core:
        print(f"No peak list configured for {file_path}")
        return

    folder_name = os.path.basename(os.path.dirname(file_path))
    file_name = "_".join(os.path.basename(file_path).split("_")[:-1])
    file_index = file_path.split(".")[-1]
    delta_file = file_path.split("_")[-1].split(".")[0]

    if manually_skip_files(delta_file, file_index):
        return
    # /do these *_dir names reflect their contents?
    save_dir = config.get_path("data.peak_fit", folder_name)
    time_dir = config.get_path(
        "utility.subtract_ifg.read_params_output", folder_name, f"{file_name}.txt"
    )
    fsd_dir = config.get_path(
        "utility.subtract_ifg.fsd_output", folder_name, f"{file_name}.{file_index}"
    )
    subifg_log_dir = config.get_path(
        "utility.subtract_ifg.read_params_output",
        folder_name,
        f"{file_name}_subIFGfiles.txt",
    )
    calibration_dir = config.get_path(
        "calibration.root", folder_name, "CalibrationData"
    )

    try:
        arr_subifg_roi, arr_fsd_roi, subifg_log, exp_params = import_data(
            file_path, fsd_dir, subifg_log_dir, time_dir
        )
    except Exception as e:
        print(f"Error importing data for {file_path}: {e}")
        return
    calibration_result = import_calibration_data(folder_name, calibration_dir)
    if calibration_result is None:
        print("Calibration data is missing.")
        calibration_peak_area = None
        calibration_moles = None
        peak_area_mole_carbonyl_slope = None
        see = None
    else:
        (
            calibration_peak_area,
            calibration_moles,
            peak_area_mole_carbonyl_slope,
            pcov,
        ) = calibration_result
        see, r_squared = calibration_statistics(
            calibration_peak_area,
            calibration_moles,
            peak_area_mole_carbonyl_slope,
            pcov,
        )
    fsd_peak_indices = find_fsd_peaks(
        arr_fsd_roi,
        voigt_settings.get("baseline", {}),
        voigt_settings.get("find_peaks", {}).get("fsd", {}),
    )
    if len(fsd_peak_indices) == 0:
        print(f"No FSD peaks found for {file_path}")
        return

    wavenumbers = arr_subifg_roi[:, 0]
    intensity = arr_subifg_roi[:, 1]
    temp_peak = None
    peak_fit_records = []
    fit_params = Parameters()

    baseline_corrected, baseline_std_distribution = create_baseline(
        intensity, voigt_settings.get("baseline", {})
    )

    used_peaks = set()  # Keep track of used peaks to avoid duplicates
    peak_list = []

    for predefined_peak in peak_list_core:
        closest_peak = predefined_peak
        for found_peak in fsd_peak_indices:
            if (
                np.isclose(float(found_peak), float(predefined_peak), atol=5.0)
                and found_peak not in used_peaks
            ):
                closest_peak = found_peak
        peak_list.append(closest_peak)
        used_peaks.add(closest_peak)

    for peak in fsd_peak_indices:
        if np.isclose(peak, 2169.5, atol=0.5):
            temp_peak = peak
            break
        else:
            temp_peak = None

    # add fit parameters and fit
    for i, peak in enumerate(peak_list):
        peak_name = peak_list_core[i]
        add_params(file_path, fit_params, peak, peak_name)

    composite_fit, residual = peak_analysis(file_path, wavenumbers)

    path = save_peak_parameters(
        peak_fit_records,
        file_name,
        save_dir,
        calibration_peak_area,
        peak_area_mole_carbonyl_slope,
        see,
    )
    save_peak_area_versus_time(
        path,
        file_name,
        save_dir,
        [f"Peak_{peak}" for peak in get_shifted_monomer_peaks(voigt_settings)],
    )
    save_peak_fit_residual(file_path, arr_subifg_roi, residual, file_name, save_dir)
    save_baseline_data(
        file_path,
        arr_subifg_roi,
        baseline_std_distribution,
        file_name,
        save_dir,
    )


if __name__ == "__main__":
    file_directory = r"C:\Data\OpusConvert_subIFG_lgRfl\nn1120-3_pd_ceo2_003"
    name = r"20250923_064354_pd_ceo2_003-031"

    for file_name in os.listdir(file_directory):
        if name in file_name:
            file_path = os.path.join(file_directory, file_name)
            if os.path.isfile(file_path):
                try:
                    print(f"Processing {file_path}...")
                    voight_fit(file_path)
                except Exception as e:
                    print(e)
