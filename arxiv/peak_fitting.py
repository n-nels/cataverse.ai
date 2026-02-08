import os, time, glob, re, warnings, ast
from core import config
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
from datetime import datetime
import matplotlib.pyplot as plt


def voight_fit(file_path):
    """This function fits a voigt profile to the carbonyl peak in the subIFG data."""

    def add_milliseconds(time_str):
        if "." not in time_str:
            return time_str + ".000000"
        else:
            return time_str

    def voigt_model(x, y0, amplitude, center, sigma, gamma):
        return y0 + (amplitude * voigt_profile(x - center, sigma, gamma))

    def combined_voigt(x, params):
        w = np.zeros_like(x)
        for peak in peakList_core:
            center = params[f"center_{peak}"].value
            amplitude = params[f"amplitude_{peak}"].value
            sigma = params[f"sigma_{peak}"].value
            gamma = params[f"gamma_{peak}"].value
            y0 = params[f"y0_{peak}"].value
            w += Model(voigt_model).eval(
                x=x, y0=y0, center=center, amplitude=amplitude, sigma=sigma, gamma=gamma
            )
        return w

    def objective(params):
        return combined_voigt(x, params) - y_bs_1

    def peak_fit():
        minimizer = Minimizer(objective, params)
        result = minimizer.minimize()
        return result

    def add_params(file_path, params, peak, peak_name):
        if (peak <= 2201) and (peak >= 2191):
            params.add(f"center_{peak_name}", value=peak, min=peak - 2, max=peak + 2)
            params.add(f"amplitude_{peak_name}", value=0.01, min=0)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 2181) and (peak >= 2171):
            params.add(f"center_{peak_name}", value=peak, min=peak - 2, max=peak + 2)
            params.add(f"amplitude_{peak_name}", value=0.01, min=0)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 2161) and (peak >= 2151):
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=0.01, min=0)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 2151) and (peak >= 2141):
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 2141) and (peak >= 2130):
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 2130) and (peak >= 2120):
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 2120) and (peak >= 2108):
            if peak_tmp is None:
                params.add(
                    f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1
                )
                params.add(f"amplitude_{peak_name}", value=0.01)
                params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
                params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
                params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

            elif (
                peak_tmp is None and peak == 2113 and int(file_path.split(".")[-1]) > 12
            ):
                params.add(
                    f"center_{peak_name}", value=peak, min=peak - 3, max=peak + 1
                )
                params.add(f"amplitude_{peak_name}", value=0.01)
                params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
                params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
                params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

            else:
                params.add(
                    f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 3
                )
                params.add(f"amplitude_{peak_name}", value=0.01)
                params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
                params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
                params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 2108) and (peak >= 2098):
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 2098) and (peak >= 2088):
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=-0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 2088) and (peak >= 2078):
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 2078) and (peak >= 2068):
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 2067) and (peak >= 2057):
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 2055) and (peak >= 2045):
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 2045) and (peak >= 2035):
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 2035) and (peak >= 2025):
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 2020) and (peak >= 2010):
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 2005) and (peak >= 1995):
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 1993) and (peak >= 1983):
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 1980) and (peak >= 1970):
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 1800) and (peak >= 1790):
            params.add(f"center_{peak_name}", value=peak, min=peak - 5, max=peak + 5)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=26)
            params.add(f"gamma_{peak_name}", value=2, min=0)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        elif (peak < 1780) and (peak >= 1770):
            params.add(f"center_{peak_name}", value=peak, min=peak - 5, max=peak + 5)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=26)
            params.add(f"gamma_{peak_name}", value=2, min=0)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        else:
            params.add(f"center_{peak_name}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak_name}", value=0.01)
            params.add(f"sigma_{peak_name}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak_name}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak_name}", value=0, min=0, vary=False)

        return None

    def peak_analysis(file_path, x):
        composite_fit = np.zeros_like(x)
        residual = np.zeros_like(x)

        # find time delta
        sample_name = file_path.split("\\")[-1]

        index_sample_name = (
            subIFG_log["sample_name"]
            .index[subIFG_log["sample_name"] == sample_name]
            .tolist()
        )

        sample = subIFG_log["sample"][index_sample_name].iloc[0]

        background = subIFG_log["background"][index_sample_name].iloc[0]

        matching_rows = [
            exp_params[exp_params["file_directory"] == path].index[0]
            for path in [sample, background]
        ]

        time_delta = (
            exp_params["DateTime"][matching_rows[0]]
            - exp_params["DateTime"][matching_rows[1]]
        ).total_seconds()

        delta_group = file_path.split("_")[-1].split(".")[0]

        # skip fitting if criteria not met
        avg_y = np.mean(abs(y_bs_1))

        peaks_pos, properties = find_peaks(y_bs_1, prominence=0.0003, height=3 * avg_y)
        peak_wavenumbers_pos = arr_subIFG_roi[:, 0][peaks_pos]

        peaks_neg, properties = find_peaks(-y_bs_1, prominence=0.0003, height=3 * avg_y)
        peak_wavenumbers_neg = arr_subIFG_roi[:, 0][peaks_neg]

        if len(peaks_pos) == 0 and len(peaks_neg) == 0:
            print("skipped: ", file_path)

            x_pos = x[y_bs_1 >= 0]
            y_bs_1_pos = y_bs_1[y_bs_1 >= 0]
            x_neg = x[y_bs_1 < 0]
            y_bs_1_neg = y_bs_1[y_bs_1 < 0]

            integral_pos = -np.trapezoid(y_bs_1_pos, x_pos)
            integral_neg = -np.trapezoid(y_bs_1_neg, x_neg)
            data_integral = integral_pos + integral_neg

            for i, peak in enumerate(peakList_core):
                if (delta_file == "delta9") or (delta_file == "delta10"):
                    peak_data = {
                        "File": file_path.split("_")[-1],
                        "Delta_Group": delta_group,
                        "Peak_Name": f"Peak_{peak}",
                        "Peak_Value": peakList[i],
                        "Data_Integral": data_integral,
                        "Time_Delta (s)": time_delta,
                        "Peak_Area": 0,
                    }

                else:
                    peak_data = {
                        "File": file_path.split("_")[-1],
                        "Delta_Group": delta_group,
                        "Peak_Name": f"Peak_{peak}",
                        "Peak_Value": peakList[i],
                        "Data_Integral": data_integral,
                        "Time_Delta (s)": time_delta,
                        "Peak_Area": 0,  # added 03/12/25
                    }

                fit_peak_data.append(peak_data)

            return composite_fit, residual

        else:
            # fit peaks
            result = peak_fit()
            fitted_params = result.params
            residual = result.residual

            for i, peak in enumerate(peakList_core):
                center = fitted_params[f"center_{peak}"].value
                amplitude = fitted_params[f"amplitude_{peak}"].value
                sigma = fitted_params[f"sigma_{peak}"].value
                gamma = fitted_params[f"gamma_{peak}"].value
                y0 = fitted_params[f"y0_{peak}"].value

                y_fit = Model(voigt_model).eval(
                    x=x,
                    y0=y0,
                    center=center,
                    amplitude=amplitude,
                    sigma=sigma,
                    gamma=gamma,
                )

                peak_area = -trapezoid(y_fit, x)

                x_pos = x[y_bs_1 >= 0]
                y_bs_1_pos = y_bs_1[y_bs_1 >= 0]
                x_neg = x[y_bs_1 < 0]
                y_bs_1_neg = y_bs_1[y_bs_1 < 0]

                integral_pos = -np.trapezoid(y_bs_1_pos, x_pos)
                integral_neg = -np.trapezoid(y_bs_1_neg, x_neg)
                data_integral = integral_pos + integral_neg
                # data_integral = -np.trapezoid(y_bs_1, x)

                fwhm_gaussian = 2 * sigma * np.sqrt(2 * np.log(2))
                fwhm_lorentz = 2 * gamma
                fwhm_voigt = (0.5346 * fwhm_lorentz) + np.sqrt(
                    (0.2166 * fwhm_lorentz**2) + fwhm_gaussian**2
                )

                peak_data = {
                    "File": file_path.split("_")[-1],
                    "Delta_Group": delta_group,
                    "Peak_Name": f"Peak_{peak}",
                    "Peak_Value": peakList[i],
                    "Data_Integral": data_integral,
                    "Center": center,
                    "Amplitude": amplitude,
                    "Sigma": sigma,
                    "Gamma": gamma,
                    "Y0": y0,
                    "fwhm": fwhm_voigt,
                    "Time_Delta (s)": time_delta,
                    "Peak_Area": peak_area,
                }

                fit_peak_data.append(peak_data)
                composite_fit += y_fit

            return composite_fit, residual

    def save_data(new_data, file_path, axis):
        if os.path.isfile(file_path):
            try:
                existing_data = pd.read_csv(file_path, header=0)
            except Exception as e:
                existing_data = pd.DataFrame()
                print(e)
            if "Wavenumber (cm-1)" in existing_data.columns:
                new_data = new_data.drop(columns=["Wavenumber (cm-1)"])
            combined_data = pd.concat(
                [existing_data, new_data], axis=axis, ignore_index=False
            )
            try:
                combined_data = combined_data.sort_values(by=["Peak_Name", "File"])
            except Exception as e:
                pass
        else:
            combined_data = new_data

        combined_data.to_csv(file_path, index=False)

    def import_data():
        # import subIFG data
        df_subIFG = pd.read_csv(file_path, header=None)
        df_subIFG_roi = df_subIFG.loc[(df_subIFG[0] >= 1750) & (df_subIFG[0] <= 2250)]
        arr_subIFG_roi = df_subIFG_roi.values  # 2050 and 2250 previously

        # import fsd data
        df_fsd = pd.read_csv(fsd_dir, header=None)
        df_fsd_roi = df_fsd.loc[(df_fsd[0] >= 1750) & (df_fsd[0] <= 2250)]
        arr_fsd_roi = df_fsd_roi.values

        # import subIFG file log
        subIFG_log = pd.read_csv(
            subIFG_log_dir, header=None, names=["sample_name", "sample", "background"]
        )

        subIFG_log["sample_name"] = (
            subIFG_log["sample_name"]
            .str.replace(r"[\'\(\)]", "", regex=True)
            .str.strip()
        )

        subIFG_log["sample"] = (
            subIFG_log["sample"]
            .str.extract(r'([^\s\'"]+)')
            .replace(r"\\\\", r"\\", regex=True)
        )

        subIFG_log["background"] = (
            subIFG_log["background"]
            .str.extract(r'([^\s\'"]+)')
            .replace(r"\\\\", r"\\", regex=True)
        )

        # import experimental parameters
        exp_params = pd.read_csv(
            time_dir,
            header=None,
            names=["file_directory", "Date", "Time", "PKA", "NSS"],
        )

        exp_params["file_directory"] = exp_params["file_directory"].apply(
            lambda x: x.split()[0].strip("\"'")
        )

        exp_params["Time"] = exp_params["Time"].str.strip()

        exp_params["Time"] = exp_params["Time"].apply(add_milliseconds)

        exp_params["DateTime"] = pd.to_datetime(
            exp_params["Date"] + " " + exp_params["Time"],
            format=" %Y-%m-%d %H:%M:%S.%f",
            errors="coerce",
        )

        exp_params["DateTime"] = exp_params["DateTime"].fillna(
            pd.to_datetime(exp_params["Time"], format="%H:%M:%S.", errors="coerce")
        )

        return arr_subIFG_roi, arr_fsd_roi, subIFG_log, exp_params

    def find_fsd_peaks():
        x = arr_fsd_roi[:, 0]
        fsd = arr_fsd_roi[:, 1].T

        # fsd_mask = (1800 < x) & (x < 2100)
        # fsd_baseline = np.mean(fsd[fsd_mask]) # create a baseline
        # fsd_bs = fsd - fsd_baseline

        fsd_baseline = pybaselines.classification.std_distribution(
            fsd,
            half_window=10,
            interp_half_window=5,
            fill_half_window=6,
            num_std=1.1,
            smooth_half_window=None,
            weights=None,
        )[0]
        fsd_bs = fsd - fsd_baseline

        peaks, properties = find_peaks(fsd_bs, prominence=0.0001, height=0.003)
        peak_wavenumbers = x[peaks]

        return peaks

    def linfunc(x, a, b):
        return a * x + b

    def linfunc_no_intercept(x, a):
        return a * x

    def pfo_fit(df_cpa):
        def pfo_decay(t, k_a, k_d, qe):  # pseudo first order with decay
            return (qe * (1 - np.exp(-k_a * t))) * np.exp(-k_d * t)

        def calculate_metrics(y, y_pred):
            residuals = y - y_pred
            ss_tot = np.sum((y - np.mean(y)) ** 2)  # total sum of squares
            ss_res = np.sum(residuals**2)  # residual sum of squares

            r_squared = 1 - (ss_res / ss_tot)
            rmse = np.sqrt(np.mean(residuals**2))

            return r_squared, rmse

        def fit_and_evaluate(x, y, func, p0=None):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", OptimizeWarning)
                try:
                    with np.errstate(
                        divide="ignore", invalid="ignore", over="ignore", under="ignore"
                    ):
                        popt, pcov = curve_fit(func, x, y, p0=p0, bounds=(0, np.inf))
                        y_pred = func(x, *popt)
                        r_squared, rmse = calculate_metrics(y, y_pred)
                        std_errors = np.sqrt(np.diag(pcov))  # stderr of param estimates
                        return popt, std_errors, r_squared, rmse
                except Exception as e:
                    # print(f"An error occurred: {e}")
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

        dfs = []
        df_cpa = df_cpa.sort_values(["Peak_Name", "Time (s)"]).reset_index(drop=True)
        df_cpa["original_index"] = df_cpa.groupby("Peak_Name").cumcount()

        for peak_name, group in df_cpa.groupby("Peak_Name"):
            fit_results = []
            group = group.reset_index(drop=True)

            if len(group) < 5:
                df_cpa.drop("original_index", axis=1, inplace=True)
                return df_cpa

            for i in range(5, len(group)):
                x = np.array(group["Time (s)"].iloc[: i + 1])
                # y = np.array(group['Cumulative_PdCO_mol'].iloc[:i+1])
                y = np.array(group["Cumulative_Peak_Area"].iloc[: i + 1])
                current_row = group.iloc[i]

                # popt_pfo_decay, std_errors_pfo_decay, r_squared_pfo_decay, \
                #     rmse_pfo_decay = fit_and_evaluate(x, y, pfo_decay, p0=[1e-6, 1e-8, 1e-9]) # for cumulative_PdCO_mol
                (
                    popt_pfo_decay,
                    std_errors_pfo_decay,
                    r_squared_pfo_decay,
                    rmse_pfo_decay,
                ) = fit_and_evaluate(
                    x, y, pfo_decay, p0=[1e-4, 1e-6, 0.1]
                )  # for cumulative_peak_area

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
                dfs.append(df)

        if dfs:
            df_pfo_fits = pd.concat(dfs, ignore_index=True)

            # Now merge with all columns present
            df_cpa_pfo = pd.merge(
                df_cpa,  # Use the same df_cpa that already has original_index
                df_pfo_fits,
                on=["Peak_Name", "Time (s)", "original_index"],
                how="left",
            )

            df_cpa_pfo.drop("original_index", axis=1, inplace=True)
            df_cpa_pfo = df_cpa_pfo.sort_values(
                ["Peak_Name", "Delta_Group"]
            ).reset_index(drop=True)
            return df_cpa_pfo

    def import_calibration_data():
        dfs = []

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
                for file in glob.glob(calibration_dir + "*"):
                    if any(string in file for string in skip_files):
                        continue
                    df = pd.read_csv(file)
                    dfs.append(df)

                df_calibration_data = pd.concat(dfs, ignore_index=True)
            except Exception as e:
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
                for file in glob.glob(calibration_dir + "*"):
                    if any(string in file for string in skip_files):
                        continue
                    df = pd.read_csv(file)
                    dfs.append(df)

                df_calibration_data = pd.concat(dfs, ignore_index=True)
            except Exception as e:
                return None

        # clean data
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

            df_calibration_data["co_moles"] = (
                df_calibration_data["co_moles"] - intercept
            )
            y = df_calibration_data["co_moles"]
            popt, pcov = curve_fit(linfunc_no_intercept, x, y)
            peakArea_moleCarbonyl_slope = popt

            # output calibration data
            output = os.path.join(calibration_dir, folder_name + "_allData.csv")
            df_calibration_data.to_csv(output, index=False)
            return x, y, peakArea_moleCarbonyl_slope, pcov
        except Exception as e:
            return None

    def calibration_statistics():
        y_pred = linfunc_no_intercept(
            x1, peakArea_moleCarbonyl_slope
        )  # predicted y-values
        std_errors = np.sqrt(np.diag(pcov))  # stderr for parameters
        residuals = y1 - y_pred
        see = np.sqrt(np.mean(residuals**2))  # stderr for estimate
        ss_tot = np.sum(y1**2)  # total sum of squares when passed through origin
        ss_res = np.sum(residuals**2)  # residual sum of squares
        r_squared = 1 - (ss_res / ss_tot)
        rmse = np.sqrt(np.mean(residuals**2))

        # Calculate the critical value for the t-distribution
        dof = len(x1) - 2  # degrees of freedom
        confidence_level = 0.975  # for a 95% confidence level
        t_critical = t.ppf(confidence_level, dof)

        # Calculate the standard error
        pred_stderr = see * np.sqrt(
            1 + 1 / len(x1) + (x1 - np.mean(x1)) ** 2 / np.sum((x1 - np.mean(x1)) ** 2)
        )

        # Calculate the prediction interval
        pred_interval = (
            t_critical
            * see
            * np.sqrt(
                1
                + 1 / len(x1)
                + (x1 - np.mean(x1)) ** 2 / np.sum((x1 - np.mean(x1)) ** 2)
            )
        )

        y_pred_lower = y_pred - pred_interval
        y_pred_upper = y_pred + pred_interval

        return see, r_squared

    def save_peak_parameters():
        # save peak parameters for each file
        df_fit_peaks = pd.DataFrame(fit_peak_data)
        try:
            df_fit_peaks["PdCO_mol"] = linfunc_no_intercept(
                df_fit_peaks["Peak_Area"], peakArea_moleCarbonyl_slope
            )
            df_fit_peaks["PdCO_mol_stderr"] = see * np.sqrt(
                1
                + 1 / len(x1)
                + (df_fit_peaks["Peak_Area"] - np.mean(x1)) ** 2
                / np.sum((x1 - np.mean(x1)) ** 2)
            )
        except Exception as e:
            pass
        filename = f"{file_name}_CarbonylPeakFitParams.csv"
        path = os.path.join(save_dir, filename)
        save_data(new_data=df_fit_peaks, file_path=path, axis=0)
        return path

    def save_peak_area_versus_time(path):
        sum_areas_list = []
        df = pd.read_csv(path)

        for (peak_name, delta_group), group in df.groupby(["Peak_Name", "Delta_Group"]):
            if delta_group == "delta1":
                cumulative_area_delta1 = (
                    group[group["Delta_Group"] == "delta1"]["Peak_Area"].iloc[:2].sum()
                )
                cumulative_integral_delta1 = (
                    group[group["Delta_Group"] == "delta1"]["Data_Integral"]
                    .iloc[:2]
                    .sum()
                )
                time_sec_delta1 = (
                    group[group["Delta_Group"] == "delta1"]["Time_Delta (s)"]
                    .iloc[:2]
                    .sum()
                )
                try:
                    cumulative_PdCO_delta1 = (
                        group[group["Delta_Group"] == "delta1"]["PdCO_mol"]
                        .iloc[:2]
                        .sum()
                    )
                    cumulative_stderr_sumSqrs_delta1 = (
                        group[group["Delta_Group"] == "delta1"]["PdCO_mol_stderr"].iloc[
                            :2
                        ]
                        ** 2
                    ).sum()
                    cumulative_stderr_delta1 = np.sqrt(cumulative_stderr_sumSqrs_delta1)
                except Exception as e:
                    pass
                continue

            cumulative_area = cumulative_area_delta1
            cumulative_integral = cumulative_integral_delta1
            time_sec = time_sec_delta1
            try:
                cumulative_PdCO = cumulative_PdCO_delta1
                cumulative_stderr = cumulative_stderr_delta1
            except Exception as e:
                pass

            for index, row in group.iterrows():
                cumulative_area += np.nan_to_num(row["Peak_Area"])
                cumulative_integral += np.nan_to_num(row["Data_Integral"])
                time_sec += row["Time_Delta (s)"]
                try:
                    cumulative_PdCO += np.nan_to_num(row["PdCO_mol"])
                    cumulative_stderr += np.sqrt(
                        np.nan_to_num(row["PdCO_mol_stderr"]) ** 2
                    )
                except Exception as e:
                    pass

                try:
                    sum_areas_list.append(
                        {
                            "File": row["File"],
                            "Delta_Group": row["Delta_Group"],
                            "Peak_Name": peak_name,
                            "Peak_Center": row["Center"],
                            "Time (s)": time_sec,
                            "Cumulative_Peak_Area": cumulative_area,
                            "Cumulative_Integral": cumulative_integral,
                            "Cumulative_PdCO_mol": cumulative_PdCO,
                            "Cumul_PdCO_mol_stderr": cumulative_stderr,
                        }
                    )
                except Exception as e:
                    sum_areas_list.append(
                        {
                            "File": row["File"],
                            "Delta_Group": row["Delta_Group"],
                            "Peak_Name": peak_name,
                            "Peak_Center": row["Center"],
                            "Time (s)": time_sec,
                            "Cumulative_Peak_Area": cumulative_area,
                            "Cumulative_Integral": cumulative_integral,
                        }
                    )

        df_sum_areas = pd.DataFrame(sum_areas_list)

        # try:
        #     df_sum_areas_pfo = pfo_fit(df_sum_areas)
        #     filename = f'{file_name}_CarbonylPeakArea.csv'
        #     path = os.path.join(save_dir, filename)
        #     df_sum_areas_pfo.to_csv(path, index=False)
        # except Exception as e:
        #     print(f"An error occurred during pfo_fit: {e}")
        #     filename = f'{file_name}_CarbonylPeakArea.csv'
        #     path = os.path.join(save_dir, filename)
        #     df_sum_areas.to_csv(path, index=False)

        # monomer_peaks = ['Peak_2093', 'Peak_2103', 'Peak_2113', 'Peak_2125']
        # df_monomer = df_sum_areas[df_sum_areas['Peak_Name'].isin(monomer_peaks)]
        # # Only proceed if required columns exist
        # if all(col in df_sum_areas.columns for col in ['Delta_Group', 'Time (s)', 'Peak_Name', 'Cumulative_Peak_Area']):
        #     grouped = df_monomer.groupby(['Delta_Group', 'Time (s)'])
        #     monomer_rows = []
        #     for (delta_group, time_s), group in grouped:
        #         summed_area = group['Cumulative_Peak_Area'].sum()
        #         file_val = group['File'].iloc[0] if 'File' in group else ''
        #         row = {
        #             'File': file_val,
        #             'Delta_Group': delta_group,
        #             'Peak_Name': 'monomer_sum',
        #             'Time (s)': time_s,
        #             'Cumulative_Peak_Area': summed_area,
        #         }
        #         # Add all other columns as blank
        #         for col in df_sum_areas.columns:
        #             if col not in row:
        #                 row[col] = ''
        #         monomer_rows.append(row)
        #     # Append to DataFrame and save again
        #     df_out = pd.concat([df_sum_areas, pd.DataFrame(monomer_rows)], ignore_index=True)
        #     df_out.to_csv(path, index=False)

        monomer_peaks = ["Peak_2093", "Peak_2103", "Peak_2113", "Peak_2125"]
        df_monomer = df_sum_areas[df_sum_areas["Peak_Name"].isin(monomer_peaks)]
        if all(
            col in df_sum_areas.columns
            for col in ["Delta_Group", "Time (s)", "Peak_Name", "Cumulative_Peak_Area"]
        ):
            grouped = df_monomer.groupby(["Delta_Group", "Time (s)"])
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
                for col in df_sum_areas.columns:
                    if col not in row:
                        row[col] = ""
                monomer_rows.append(row)
            # Append monomer_sum rows
            df_sum_areas = pd.concat(
                [df_sum_areas, pd.DataFrame(monomer_rows)], ignore_index=True
            )

        # --- Now run pfo_fit ONCE on the combined DataFrame ---
        try:
            df_out = pfo_fit(df_sum_areas)
        except Exception as e:
            print(f"An error occurred during pfo_fit: {e}")
            df_out = df_sum_areas

        # --- Save final DataFrame ---
        filename = f"{file_name}_CarbonylPeakArea.csv"
        path = os.path.join(save_dir, filename)
        df_out.to_csv(path, index=False)

    def save_peak_fit_residual():
        df = pd.DataFrame()
        df["Wavenumber (cm-1)"] = arr_subIFG_roi[:, 0]
        df.reset_index(drop=True, inplace=True)
        df_key = pd.DataFrame({file_path.split("_")[-1]: residual})

        df = pd.concat([df] + [df_key], axis=1)
        filename = f"{file_name}_CarbonylFitResidual.csv"
        path = os.path.join(save_dir, filename)
        save_data(new_data=df, file_path=path, axis=1)

    def save_baseline_data():
        df = pd.DataFrame()
        df["Wavenumber (cm-1)"] = arr_subIFG_roi[:, 0]
        df_key = pd.DataFrame({file_path.split("_")[-1]: bsln_stdDis})
        df.reset_index(drop=True, inplace=True)

        df = pd.concat([df] + [df_key], axis=1)
        filename = f"{file_name}_CarbonylFitBaseline.csv"
        path = os.path.join(save_dir, filename)
        save_data(new_data=df, file_path=path, axis=1)

    def manually_skip_files(delta_file, iterator):
        # need to do peak heights before this
        if ((delta_file == "delta1") and (int(iterator) > 2)) or delta_file in {
            "delta2",
            "delta3",
            "delta4",
        }:
            return True

    def create_baseline(y):
        # create baseline and subtract
        bsln_stdDis = pybaselines.classification.std_distribution(
            y,
            half_window=10,
            interp_half_window=5,
            fill_half_window=6,
            num_std=1.1,
            smooth_half_window=None,
            weights=None,
        )[0]
        y_bs_1 = y - bsln_stdDis
        return y_bs_1, bsln_stdDis

    # 12CO  ### need to change add_params
    # peakList_core = [2186, 2175, 2163, 2148, 2136, 2125, 2112, 2100, 2090,
    #                  2080, 2065, 2050, 2038, 2025]

    # 13CO
    peakList_core = [
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

    root_dir = "\\".join(file_path.split("\\")[:2])
    folder_name = file_path.split("\\")[-2]
    file_name = "_".join((file_path.split("\\")[-1]).split("_")[:-1])
    iterator = file_path.split(".")[-1]
    delta_file = file_path.split("_")[-1].split(".")[0]

    if manually_skip_files(delta_file, iterator):
        return

    save_dir = os.path.join(root_dir, "peakFit", folder_name)
    time_dir = os.path.join(root_dir, "OpusReadParams", folder_name, f"{file_name}.txt")
    fsd_dir = os.path.join(
        root_dir, "OpusConvert_fsd\\", folder_name, f"{file_name}.{iterator}"
    )
    subIFG_log_dir = os.path.join(
        root_dir, "OpusReadParams", folder_name, f"{file_name}_subIFGfiles.txt"
    )
    calibration_dir = os.path.join("X:\\peakFit", folder_name, "CalibrationData\\")

    arr_subIFG_roi, arr_fsd_roi, subIFG_log, exp_params = import_data()
    result = import_calibration_data()
    if result is None:
        print("Calibration data is missing.")
    else:
        x1, y1, peakArea_moleCarbonyl_slope, pcov = result
        see, r_squared = calibration_statistics()
    fsd_peaks = find_fsd_peaks()

    x = arr_subIFG_roi[:, 0]
    y = arr_subIFG_roi[:, 1]
    peak_tmp = None
    fit_peak_data = []
    params = Parameters()

    y_bs_1, bsln_stdDis = create_baseline(y)

    used_peaks = set()  # Keep track of used peaks to avoid duplicates
    peakList = []

    for predefined_peak in peakList_core:
        closest_peak = predefined_peak
        for found_peak in fsd_peaks:
            if (
                np.isclose(float(found_peak), float(predefined_peak), atol=5.0)
                and found_peak not in used_peaks
            ):
                closest_peak = found_peak
        peakList.append(closest_peak)
        used_peaks.add(closest_peak)

    for peak in fsd_peaks:
        if np.isclose(peak, 2169.5, atol=0.5):
            peak_tmp = peak
            break
        else:
            peak_tmp = None

    # add fit parameters and fit
    for i, peak in enumerate(peakList):
        peak_name = peakList_core[i]
        add_params(file_path, params, peak, peak_name)

    composite_fit, residual = peak_analysis(file_path, x)

    path = save_peak_parameters()
    save_peak_area_versus_time(path)
    save_peak_fit_residual()
    save_baseline_data()

def reprocess_sum_peak_area():
    """This function applies the calibration data to the peak area data and saves the results."""

    def save_peak_area_versus_time(path):
        sum_areas_list = []
        df = pd.read_csv(path)
        for (peak_name, delta_group), group in df.groupby(["Peak_Name", "Delta_Group"]):
            if delta_group == "delta1":
                delta1_sum = (
                    group[group["Delta_Group"] == "delta1"]["Peak_Area"].iloc[:2].sum()
                )
                delta1_integral = (
                    group[group["Delta_Group"] == "delta1"]["Data_Integral"]
                    .iloc[:2]
                    .sum()
                )
                delta1_time = (
                    group[group["Delta_Group"] == "delta1"]["Time_Delta (s)"]
                    .iloc[:2]
                    .sum()
                )
                delta1_PdCO = (
                    group[group["Delta_Group"] == "delta1"]["PdCO_mol"].iloc[:2].sum()
                )
                delta1_stderr_sumSqrs = (
                    group[group["Delta_Group"] == "delta1"]["PdCO_mol_stderr"].iloc[:2]
                    ** 2
                ).sum()

                cumulative_area = delta1_sum
                cumulative_integral = delta1_integral
                cumulative_PdCO = delta1_PdCO
                cumulative_stderr = np.sqrt(delta1_stderr_sumSqrs)
                time_sec = delta1_time
                continue

            else:
                cumulative_area = delta1_sum
                cumulative_integral = delta1_integral
                cumulative_PdCO = delta1_PdCO
                cumulative_stderr = np.sqrt(delta1_stderr_sumSqrs)
                time_sec = 0

            for index, row in group.iterrows():
                cumulative_area += np.nan_to_num(row["Peak_Area"])
                cumulative_integral += np.nan_to_num(row["Data_Integral"])
                cumulative_PdCO += np.nan_to_num(row["PdCO_mol"])
                cumulative_stderr += np.sqrt(np.nan_to_num(row["PdCO_mol_stderr"]) ** 2)
                time_sec += row["Time_Delta (s)"]

                sum_areas_list.append(
                    {
                        "File": row["File"],
                        "Delta_Group": row["Delta_Group"],
                        "Peak_Name": peak_name,
                        "Peak_Center": row["Center"],
                        "Time (s)": time_sec,
                        "Cumulative_Peak_Area": cumulative_area,
                        "Cumulative_Integral": cumulative_integral,
                        "Cumulative_PdCO_mol": cumulative_PdCO,
                        "Cumul_PdCO_mol_stderr": cumulative_stderr,
                    }
                )

        df_sum_areas = pd.DataFrame(sum_areas_list)
        filename = file_name.replace(
            "CarbonylPeakFitParams.csv", "CarbonylPeakArea.csv"
        )
        path = os.path.join(save_dir, filename)
        df_sum_areas.to_csv(path, index=False)

    def linfunc_no_intercept(x, a):
        return a * x

    def import_calibration_data(folder_name):
        dfs = []

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
                for file in glob.glob(calibration_dir + "*"):
                    if any(string in file for string in skip_files):
                        continue
                    df = pd.read_csv(file)
                    dfs.append(df)

                df_calibration_data = pd.concat(dfs, ignore_index=True)
            except Exception as e:
                return None

        if folder_name == "nn1120-3_pd_ceo2_000":
            skip_files = ["allData", "000-005"]
            try:
                for file in glob.glob(calibration_dir + "*"):
                    if any(string in file for string in skip_files):
                        continue
                    df = pd.read_csv(file)
                    dfs.append(df)

                df_calibration_data = pd.concat(dfs, ignore_index=True)
            except Exception as e:
                return None

        # clean data
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
        peakArea_moleCarbonyl_slope = popt

        # output calibration data
        output = os.path.join(calibration_dir, folder_name + "_allData.csv")
        df_calibration_data.to_csv(output, index=False)
        return x, y, peakArea_moleCarbonyl_slope, pcov

    def calibration_statistics():
        y_pred = linfunc_no_intercept(
            x1, peakArea_moleCarbonyl_slope
        )  # predicted y-values
        std_errors = np.sqrt(np.diag(pcov))  # stderr for parameters
        residuals = y1 - y_pred
        see = np.sqrt(np.mean(residuals**2))  # stderr for estimate
        ss_tot = np.sum(y1**2)  # total sum of squares when passed through origin
        ss_res = np.sum(residuals**2)  # residual sum of squares
        r_squared = 1 - (ss_res / ss_tot)
        rmse = np.sqrt(np.mean(residuals**2))

        # Calculate the critical value for the t-distribution
        dof = len(x1) - 2  # degrees of freedom
        confidence_level = 0.975  # for a 95% confidence level
        t_critical = t.ppf(confidence_level, dof)

        # Calculate the standard error
        pred_stderr = see * np.sqrt(
            1 + 1 / len(x1) + (x1 - np.mean(x1)) ** 2 / np.sum((x1 - np.mean(x1)) ** 2)
        )

        # Calculate the prediction interval
        pred_interval = (
            t_critical
            * see
            * np.sqrt(
                1
                + 1 / len(x1)
                + (x1 - np.mean(x1)) ** 2 / np.sum((x1 - np.mean(x1)) ** 2)
            )
        )

        y_pred_lower = y_pred - pred_interval
        y_pred_upper = y_pred + pred_interval

        return see, r_squared

    def save_peak_parameters(fit_peak_data):
        # save peak parameters for each file
        df_fit_peaks = pd.read_csv(fit_peak_data)
        try:
            df_fit_peaks["PdCO_mol"] = linfunc_no_intercept(
                df_fit_peaks["Peak_Area"], peakArea_moleCarbonyl_slope
            )
            df_fit_peaks["PdCO_mol_stderr"] = see * np.sqrt(
                1
                + 1 / len(x1)
                + (df_fit_peaks["Peak_Area"] - np.mean(x1)) ** 2
                / np.sum((x1 - np.mean(x1)) ** 2)
            )
        except Exception as e:
            pass
        filename = full_file_path.split("\\")[-1]
        path = os.path.join(save_dir, filename)
        df_fit_peaks.to_csv(path, index=False)
        return path

    def linfunc(x, a, b):
        return a * x + b

    file_dir = r"C:\Data\peakFit\nn1120-2_pd_ceo2_000"
    save_dir = r"X:\peakFit\test"
    calibration_dir = r"X:\peakFit\nn1120-2_pd_ceo2_000\CalibrationData\\"
    folder_name = file_dir.split("\\")[-1]

    x1, y1, peakArea_moleCarbonyl_slope, pcov = import_calibration_data(folder_name)
    see, r_squared = calibration_statistics()

    for file_name in os.listdir(file_dir):
        if "CarbonylPeakFitParams" in file_name:
            full_file_path = os.path.join(file_dir, file_name)
            if os.path.isfile(full_file_path):
                path = save_peak_parameters(full_file_path)
                save_peak_area_versus_time(path)

def kinetic_fit(file_path):
    """This is an older version that fits all the data, not row by row"""

    def pfo_decay(t, k_a, k_d, qe):  # pseudo first order with decay
        return (qe * (1 - np.exp(-k_a * t))) * np.exp(-k_d * t)

    def extract_readme(readme):
        with open(readme, "r", encoding="utf-8") as file:
            readme_content = file.read()

        main_pattern = re.compile(r"##\s(\w+).*?Value:\s([^\n]+)", re.DOTALL)
        sub_pattern = re.compile(r"\*\*(\w+)\*\*.*?Value:\s([^\n]+)", re.DOTALL)

        main_matches = main_pattern.findall(readme_content)
        for match in main_matches:
            heading, value = match
            expParams[heading.strip()] = value.strip()

        sub_matches = sub_pattern.findall(readme_content)
        for match in sub_matches:
            heading, value = match
            expParams[heading.strip()] = value.strip()

        return expParams

    def calculate_metrics(y, y_pred):
        residuals = y - y_pred
        ss_tot = np.sum((y - np.mean(y)) ** 2)  # total sum of squares
        ss_res = np.sum(residuals**2)  # residual sum of squares

        r_squared = 1 - (ss_res / ss_tot)
        rmse = np.sqrt(np.mean(residuals**2))

        return r_squared, rmse

    def fit_and_evaluate(x, y, func, p0=None):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", OptimizeWarning)
            try:
                popt, pcov = curve_fit(func, x, y, p0=p0)
                y_pred = func(x, *popt)
                r_squared, rmse = calculate_metrics(y, y_pred)
                std_errors = np.sqrt(np.diag(pcov))  # stderr of param estimates
                return popt, std_errors, r_squared, rmse
            except Exception as e:
                print(f"An error occurred: {e}")
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

    root_dir = "\\".join(file_path.split("\\")[:2])
    folder_name = file_path.split("\\")[-2]
    file_name = "_".join((file_path.split("\\")[-1]).split("_")[:-1])

    expParams = {}
    R = 8.3145e-03  # kJ/K-mol
    T = 298  # K

    expParams = extract_readme(file_path)
    file = file_path.replace("README.md", "CarbonylPeakArea.csv")
    df_cpa = pd.read_csv(file)

    pd_moles = float(expParams["pd_loading"]) / 100 * float(expParams["mass"]) / 106.42
    p_co_calc = float(expParams["exp_pressure_calc"])
    if p_co_calc == 0:
        p_co_meas = float((ast.literal_eval(expParams["exp_pressure_meas"]))[1])
        p_co_calc = p_co_meas

    for peak_name, group in df_cpa.groupby("Peak_Name"):
        if peak_name not in ["Peak_2113"]:
            continue

        # fit adsorption kinetic equations to data
        x = (group["Time (s)"]).values
        y = (group["Cumulative_PdCO_mol"]).values
        y_error = group["Cumul_PdCO_mol_stderr"]

        popt_pfo_decay, std_errors_pfo_decay, r_squared_pfo_decay, rmse_pfo_decay = (
            fit_and_evaluate(x, y, pfo_decay, p0=[1e-6, 1e-8, 1e-9])
        )
        ka_pfo_decay, kd_pfo_decay, q_pfo_decay = popt_pfo_decay
        ka_stderr_pfo_decay, kd_stderr_pfo_decay, q_stderr_pfo_decay = (
            std_errors_pfo_decay
        )

        # extract equilibrium constants from fits
        K_pfo_decay = q_pfo_decay / ((pd_moles - q_pfo_decay) * (p_co_calc / 760))
        center = group["Peak_Center"].mean()

        fit_results = {
            "peak_name": peak_name,
            "expDuration_s": group["Time (s)"].iloc[-1],
            "peak_center": center,
            "ka_s-1": ka_pfo_decay,
            "ka_stderr": ka_stderr_pfo_decay,
            "kd_s-1": kd_pfo_decay,
            "kd_stderr": kd_stderr_pfo_decay,
            "qe_mol": q_pfo_decay,
            "qe_stderr": q_stderr_pfo_decay,
            "K_eq": K_pfo_decay,
            "dG_kJmol-1": -R * T * np.log(K_pfo_decay),
            "r^2": r_squared_pfo_decay,
            "rmse": rmse_pfo_decay,
        }

    return file_name, expParams, fit_results, x, y

def pfo_fit_by_row(file_path):
    """This function fits the pseudo first order kinetic model to the data by row."""

    def pfo_decay(t, k_a, k_d, qe):  # pseudo first order with decay
        return (qe * (1 - np.exp(-k_a * t))) * np.exp(-k_d * t)

    def calculate_metrics(y, y_pred):
        residuals = y - y_pred
        ss_tot = np.sum((y - np.mean(y)) ** 2)  # total sum of squares
        ss_res = np.sum(residuals**2)  # residual sum of squares

        r_squared = 1 - (ss_res / ss_tot)
        rmse = np.sqrt(np.mean(residuals**2))

        return r_squared, rmse

    def fit_and_evaluate(x, y, func, p0=None):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", OptimizeWarning)
            try:
                popt, pcov = curve_fit(func, x, y, p0=p0, bounds=(0, np.inf))
                y_pred = func(x, *popt)
                r_squared, rmse = calculate_metrics(y, y_pred)
                std_errors = np.sqrt(np.diag(pcov))  # stderr of param estimates
                return popt, std_errors, r_squared, rmse
            except Exception as e:
                print(f"An error occurred: {e}")
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

    # root_dir = '\\'.join(file_path.split('\\')[:2])
    # folder_name = file_path.split('\\')[-2]
    # file_name = '_'.join((file_path.split('\\')[-1]).split('_')[:-1])
    # file_cpa = f"{root_dir}\\peakFit\\{folder_name}\\{file_name}_CarbonylPeakArea.csv"
    # df_cpa = pd.read_csv(file_cpa)
    df_cpa = pd.read_csv(file_path)
    try:
        df_cpa = df_cpa.drop(
            columns=[
                "ka_s-1",
                "ka_stderr",
                "kd_s-1",
                "kd_stderr",
                "qe_mol",
                "qe_stderr",
                "r^2",
                "rmse",
            ]
        )
    except KeyError:
        pass
    dfs = []

    df_cpa = df_cpa.sort_values(["Peak_Name", "Time (s)"]).reset_index(drop=True)
    df_cpa["original_index"] = df_cpa.groupby("Peak_Name").cumcount()

    for peak_name, group in df_cpa.groupby("Peak_Name"):
        fit_results = []
        group = group.reset_index(drop=True)

        for i in range(2, len(group)):
            x = np.array(group["Time (s)"].iloc[: i + 1])
            # y = np.array(group['Cumulative_PdCO_mol'].iloc[:i+1])
            y = np.array(group["Cumulative_Peak_Area"].iloc[: i + 1])
            current_row = group.iloc[i]

            # popt_pfo_decay, std_errors_pfo_decay, r_squared_pfo_decay, \
            #     rmse_pfo_decay = fit_and_evaluate(x, y, pfo_decay, p0=[1e-6, 1e-8, 1e-9])
            (
                popt_pfo_decay,
                std_errors_pfo_decay,
                r_squared_pfo_decay,
                rmse_pfo_decay,
            ) = fit_and_evaluate(x, y, pfo_decay, p0=[1e-4, 1e-6, 0.1])

            ka_pfo_decay, kd_pfo_decay, q_pfo_decay = popt_pfo_decay
            ka_stderr_pfo_decay, kd_stderr_pfo_decay, q_stderr_pfo_decay = (
                std_errors_pfo_decay
            )

            result = {
                "Peak_Name": peak_name,
                "Time (s)": current_row["Time (s)"],
                "original_index": current_row[
                    "original_index"
                ],  # Use the index from the sorted df
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
            dfs.append(df)

    if dfs:
        df_pfo_fits = pd.concat(dfs, ignore_index=True)

        # Now merge with all columns present
        df_cpa_pfo = pd.merge(
            df_cpa,  # Use the same df_cpa that already has original_index
            df_pfo_fits,
            on=["Peak_Name", "Time (s)", "original_index"],
            how="left",
        )

        df_cpa_pfo.drop("original_index", axis=1, inplace=True)
        filename = file_path.split("\\")[-1]
        path = os.path.join("X:\\peakFit\\_test", f"{filename}")
        df_cpa_pfo.to_csv(path, index=False)

def readme_to_csv(file_path):
    """This function converts the README.md file to a csv file."""

    def extract_readme(readme):
        with open(readme, "r", encoding="utf-8") as file:
            readme_content = file.read()

        main_pattern = re.compile(r"##\s(\w+).*?Value:\s([^\n]+)", re.DOTALL)
        sub_pattern = re.compile(r"\*\*(\w+)\*\*.*?Value:\s([^\n]+)", re.DOTALL)

        main_matches = main_pattern.findall(readme_content)
        for match in main_matches:
            heading, value = match
            expParams[heading.strip()] = value.strip()

        sub_matches = sub_pattern.findall(readme_content)
        for match in sub_matches:
            heading, value = match
            expParams[heading.strip()] = value.strip()

        return expParams

    root_dir = "\\".join(file_path.split("\\")[:2])
    folder_name = file_path.split("\\")[-2]
    file_name = "_".join((file_path.split("\\")[-1]).split("_")[:-1])

    expParams = {}
    R = 8.3145e-03  # kJ/K-mol
    T = 298  # K

    expParams = extract_readme(file_path)
    expParams = {key: [value] for key, value in expParams.items()}
    df = pd.DataFrame(expParams)
    file = file_path.replace("README.md", "expParams.csv")
    df.to_csv(file, index=False)

def peak_heights(file_path):
    """This function extracts peak heights from the data."""

    def add_milliseconds(time_str):
        if "." not in time_str:
            return time_str + ".000000"
        else:
            return time_str

    def import_time():
        exp_params = pd.read_csv(
            time_dir,
            header=None,
            names=["file_directory", "Date", "Time", "PKA", "NSS"],
        )

        exp_params["file_directory"] = exp_params["file_directory"].apply(
            lambda x: x.split()[0].strip("\"'")
        )

        exp_params["iterator"] = exp_params["file_directory"].apply(
            lambda x: x.split(".")[-1]
        )

        exp_params["Time"] = exp_params["Time"].str.strip()

        exp_params["Time"] = exp_params["Time"].apply(add_milliseconds)

        exp_params["DateTime"] = pd.to_datetime(
            exp_params["Date"] + " " + exp_params["Time"],
            format=" %Y-%m-%d %H:%M:%S.%f",
            errors="coerce",
        )

        exp_params["DateTime"] = exp_params["DateTime"].fillna(
            pd.to_datetime(exp_params["Time"], format="%H:%M:%S.", errors="coerce")
        )

        return exp_params

    def find_time():
        time_ref = exp_params.iloc[0]["DateTime"]
        time_val = exp_params[exp_params["iterator"] == iterator]["DateTime"].iloc[0]
        result = time_val - time_ref

        return result.total_seconds()

    def import_data(dir):
        df = pd.read_csv(dir, header=None)
        arr = df.values
        hydroxyl = (arr[:, 0] >= 3000) & (
            arr[:, 0] <= 3900
        )  # change to 2200 and reprocess
        carbonate = (arr[:, 0] >= 1000) & (arr[:, 0] <= 1700)

        arr_hydroxyl = arr[hydroxyl]
        arr_carbonate = arr[carbonate]

        return arr_carbonate, arr_hydroxyl

    def peak_find(arr, prominence, peak_height, peaks_heights):
        x = arr[:, 0]
        y = arr[:, 1]

        if dtype == "subifg":
            if (delta_file == "delta1") and (int(iterator) > 2):
                return

            if (
                (delta_file == "delta2")
                or (delta_file == "delta3")
                or (delta_file == "delta4")
            ):
                return

        baseline = pybaselines.classification.std_distribution(
            y,
            half_window=10,
            interp_half_window=5,
            fill_half_window=6,
            num_std=1.1,
            smooth_half_window=None,
            weights=None,
        )[0]
        y_bs = y - baseline

        peaks, properties = find_peaks(y_bs, prominence=prominence, height=peak_height)

        peak_wavenumbers = x[peaks]
        peak_heights = properties["peak_heights"]
        t_val = find_time()

        if dtype == "subifg":
            for wnum, height in zip(peak_wavenumbers, peak_heights):
                result = {
                    "file": str(f"{file_name}_{delta_file}.{iterator}"),
                    "time (s)": t_val,
                    "peak": wnum,
                    "height": height,
                }

                peaks_heights.append(result)
        else:
            for wnum, height in zip(peak_wavenumbers, peak_heights):
                result = {
                    "file": str(f"{file_name}.{iterator}"),
                    "time (s)": t_val,
                    "peak": wnum,
                    "height": height,
                }

                peaks_heights.append(result)

        return peaks_heights

    def save_peak_heights(data, dtype):
        df = pd.DataFrame(data)
        if df.empty:
            return
        filename = f"{file_name}_{dtype}PeakHeight.csv"
        path = os.path.join(save_dir, filename)
        save(new_data=df, filename=path, axis=0)

    def save(new_data, filename, axis):
        if os.path.isfile(filename):
            try:
                existing_data = pd.read_csv(filename, header=0, dtype={"file": str})
            except Exception as e:
                existing_data = pd.DataFrame()
                print(e)

            if dtype == "subifg":
                search_string = f"{file_name}_{delta_file}.{iterator}"
                if existing_data["file"].str.contains(search_string, na=False).any():
                    return
                combined_data = pd.concat(
                    [existing_data, new_data], axis=axis, ignore_index=False
                )

                try:
                    combined_data = combined_data.sort_values(by=["file", "peak"])
                except Exception as e:
                    print(e)
                combined_data.to_csv(filename, index=False)
                return

            if "file" in existing_data.columns:
                if any(existing_data["file"].str.contains(f".{iterator}", na=False)):
                    return

            combined_data = pd.concat(
                [existing_data, new_data], axis=axis, ignore_index=False
            )
            try:
                combined_data = combined_data.sort_values(by=["file", "peak"])
            except Exception as e:
                print(e)
        else:
            combined_data = new_data

        combined_data.to_csv(filename, index=False)

    root_dir = "\\".join(file_path.split("\\")[:2])
    folder_name = file_path.split("\\")[-2]
    file_name = "_".join((file_path.split("\\")[-1]).split("_")[:-1])
    iterator = file_path.split(".")[-1]
    time_dir = os.path.join(root_dir, "OpusReadParams", folder_name, f"{file_name}.txt")
    delta_file = file_path.split("_")[-1].split(".")[0]

    save_dir = os.path.join(root_dir, "peakFit", folder_name)
    fsd_dir = os.path.join(
        root_dir, "OpusConvert_fsd\\", folder_name, f"{file_name}.{iterator}"
    )
    lgrfl_dir = os.path.join(
        root_dir, "OpusConvert_lgRfl", folder_name, f"{file_name}.{iterator}"
    )

    arr_fsd_carbonate, arr_fsd_hydroxyl = import_data(fsd_dir)
    arr_lgRfl_carbonate, arr_lgRfl_hydroxyl = import_data(lgrfl_dir)
    exp_params = import_time()
    arr_subifg_carbonate, arr_subifg_hydroxyl = import_data(file_path)
    dtype = None

    fsd_peaks_heights = []
    peak_find(
        arr=arr_fsd_hydroxyl,
        prominence=0.0001,
        peak_height=0.01,
        peaks_heights=fsd_peaks_heights,
    )
    peak_find(
        arr=arr_fsd_carbonate,
        prominence=0.001,
        peak_height=0.01,
        peaks_heights=fsd_peaks_heights,
    )
    save_peak_heights(data=fsd_peaks_heights, dtype="fsd")

    lgrfl_peaks_heights = []
    peak_find(
        arr=arr_lgRfl_hydroxyl,
        prominence=0.0002,
        peak_height=0.001,
        peaks_heights=lgrfl_peaks_heights,
    )
    peak_find(
        arr=arr_lgRfl_carbonate,
        prominence=0.0002,
        peak_height=0.001,
        peaks_heights=lgrfl_peaks_heights,
    )
    save_peak_heights(data=lgrfl_peaks_heights, dtype="lgrfl")

    subifg_peaks_heights = []
    dtype = "subifg"
    peak_find(
        arr=arr_subifg_hydroxyl,
        prominence=0.0001,
        peak_height=0.001,
        peaks_heights=subifg_peaks_heights,
    )
    peak_find(
        arr=arr_subifg_carbonate,
        prominence=0.0001,
        peak_height=0.001,
        peaks_heights=subifg_peaks_heights,
    )
    save_peak_heights(data=subifg_peaks_heights, dtype=dtype)

def integrate_irIsoXchg(file_path):
    """This function integrates the IR isotopic exchange spectra to find the area under the curve."""

    def voigt_model(x, y0, amplitude, center, sigma, gamma):
        return y0 + (amplitude * voigt_profile(x - center, sigma, gamma))

    def combined_voigt(x, params):
        w = np.zeros_like(x)
        for peak in peak_list:
            center = params[f"center_{peak}"].value
            amplitude = params[f"amplitude_{peak}"].value
            sigma = params[f"sigma_{peak}"].value
            gamma = params[f"gamma_{peak}"].value
            y0 = params[f"y0_{peak}"].value
            w += Model(voigt_model).eval(
                x=x, y0=y0, center=center, amplitude=amplitude, sigma=sigma, gamma=gamma
            )
        return w

    def objective(params):
        return combined_voigt(x, params) - y_bs_1

    def peak_fit():
        minimizer = Minimizer(objective, params)
        result = minimizer.minimize()
        return result

    def add_params(params, peak):
        if peak == 2185:
            params.add(f"center_{peak}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak}", value=0.01)
            params.add(f"sigma_{peak}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak}", value=0, min=0, vary=False)

        elif peak == 2175:
            params.add(f"center_{peak}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak}", value=0.01)
            params.add(f"sigma_{peak}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak}", value=0, min=0, vary=False)

        elif peak == 2162:
            params.add(f"center_{peak}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak}", value=0.01, min=0)
            params.add(f"sigma_{peak}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak}", value=0, min=0, vary=False)

        elif peak == 2136:
            params.add(f"center_{peak}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak}", value=0.01)
            params.add(f"sigma_{peak}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak}", value=0, min=0, vary=False)

        elif peak == 2126:
            params.add(f"center_{peak}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak}", value=0.01)
            params.add(f"sigma_{peak}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak}", value=0, min=0, vary=False)

        elif peak == 2112:
            params.add(f"center_{peak}", value=peak, min=peak - 1, max=peak + 1)
            params.add(f"amplitude_{peak}", value=0.01)
            params.add(f"sigma_{peak}", value=5, min=2.55, max=6.37)
            params.add(f"gamma_{peak}", value=2, min=0, max=2.8)
            params.add(f"y0_{peak}", value=0, min=0, vary=False)

        return None

    def peak_analysis(file_path, x):
        composite_fit = np.zeros_like(x)
        residual = np.zeros_like(x)

        # fit peaks
        result = peak_fit()
        fitted_params = result.params
        residual = result.residual

        for i, peak in enumerate(peak_list):
            center = fitted_params[f"center_{peak}"].value
            amplitude = fitted_params[f"amplitude_{peak}"].value
            sigma = fitted_params[f"sigma_{peak}"].value
            gamma = fitted_params[f"gamma_{peak}"].value
            y0 = fitted_params[f"y0_{peak}"].value

            y_fit = Model(voigt_model).eval(
                x=x, y0=y0, center=center, amplitude=amplitude, sigma=sigma, gamma=gamma
            )
            peak_area = -trapezoid(y_fit, x)
            carbonyl_integral = -np.trapezoid(y_bs_1[integral_mask], x[integral_mask])

            fwhm_gaussian = 2 * sigma * np.sqrt(2 * np.log(2))
            fwhm_lorentz = 2 * gamma
            fwhm_voigt = (0.5346 * fwhm_lorentz) + np.sqrt(
                (0.2166 * fwhm_lorentz**2) + fwhm_gaussian**2
            )

            peak_data = {
                "File": file_path,
                "Peak_Name": f"Peak_{peak}",
                "Peak_Value": peak_list[i],
                "Carbonyl_Integral": carbonyl_integral,
                "Center": center,
                "Amplitude": amplitude,
                "Sigma": sigma,
                "Gamma": gamma,
                "Y0": y0,
                "fwhm": fwhm_voigt,
                "Peak_Area": peak_area,
            }

            fit_peak_data.append(peak_data)
            composite_fit += y_fit

        return composite_fit, residual

    def save_data(new_data, file_path, axis):
        if os.path.isfile(file_path):
            try:
                existing_data = pd.read_csv(file_path, header=0)
            except Exception as e:
                existing_data = pd.DataFrame()
                print(e)
            if "Wavenumber (cm-1)" in existing_data.columns:
                new_data = new_data.drop(columns=["Wavenumber (cm-1)"])
            combined_data = pd.concat(
                [existing_data, new_data], axis=axis, ignore_index=False
            )
            try:
                combined_data = combined_data.sort_values(by=["Peak_Name", "File"])
            except Exception as e:
                pass
        else:
            combined_data = new_data

        combined_data.to_csv(file_path, index=False)

    def import_data():
        # import subIFG data
        df_subIFG = pd.read_csv(file_path, header=None)
        df_subIFG_roi = df_subIFG.loc[(df_subIFG[0] >= 1750) & (df_subIFG[0] <= 2250)]
        arr_subIFG_roi = df_subIFG_roi.values  # 2050 and 2250 previously

        # import subIFG file log
        subIFG_log = pd.read_csv(
            subIFG_log_dir, header=None, names=["sample_name", "sample", "background"]
        )

        subIFG_log["sample_name"] = (
            subIFG_log["sample_name"]
            .str.replace(r"[\'\(\)]", "", regex=True)
            .str.strip()
        )

        subIFG_log["sample"] = (
            subIFG_log["sample"]
            .str.extract(r'([^\s\'"]+)')
            .replace(r"\\\\", r"\\", regex=True)
        )

        subIFG_log["background"] = (
            subIFG_log["background"]
            .str.extract(r'([^\s\'"]+)')
            .replace(r"\\\\", r"\\", regex=True)
        )

        return arr_subIFG_roi, subIFG_log

    def save_peak_parameters():
        df_fit_peaks = pd.DataFrame(fit_peak_data)
        filename = f"{file_name[:-2]}_CarbonylPeakFitParams.csv"
        path = os.path.join(save_dir, filename)
        save_data(new_data=df_fit_peaks, file_path=path, axis=0)
        return path

    def save_peak_fit_residual():
        df = pd.DataFrame()
        df["Wavenumber (cm-1)"] = arr_subIFG_roi[:, 0]
        df.reset_index(drop=True, inplace=True)
        df_key = pd.DataFrame({"_".join(file_path.split("_")[-3:]): residual})

        df = pd.concat([df] + [df_key], axis=1)
        filename = f"{file_name[:-2]}_CarbonylFitResidual.csv"
        path = os.path.join(save_dir, filename)
        save_data(new_data=df, file_path=path, axis=1)

    def save_baseline_data():
        df = pd.DataFrame()
        df["Wavenumber (cm-1)"] = arr_subIFG_roi[:, 0]
        df_key = pd.DataFrame({"_".join(file_path.split("_")[-3:]): bsln_stdDis})
        df.reset_index(drop=True, inplace=True)

        df = pd.concat([df] + [df_key], axis=1)
        filename = f"{file_name[:-2]}_CarbonylFitBaseline.csv"
        path = os.path.join(save_dir, filename)
        save_data(new_data=df, file_path=path, axis=1)

    def create_baseline(y):
        # create baseline and subtract
        bsln_stdDis = pybaselines.classification.std_distribution(
            y,
            half_window=10,
            interp_half_window=5,
            fill_half_window=6,
            num_std=1.1,
            smooth_half_window=None,
            weights=None,
        )[0]
        y_bs_1 = y - bsln_stdDis
        return y_bs_1, bsln_stdDis

    peak_list = [2185, 2175, 2162, 2136, 2126, 2112]

    root_dir = "\\".join(file_path.split("\\")[:2])
    folder_name = file_path.split("\\")[-2]
    file_name = "_".join((file_path.split("\\")[-1]).split("_")[:-1])

    save_dir = os.path.join(root_dir, "OpusCalibrations", folder_name)
    subIFG_log_dir = os.path.join(
        root_dir, "OpusReadParams", folder_name, f"{file_name}_subIFGfiles.txt"
    )

    arr_subIFG_roi, subIFG_log = import_data()

    x = arr_subIFG_roi[:, 0]
    y = arr_subIFG_roi[:, 1]
    fit_peak_data = []
    integral_mask = (x >= 2095) & (x <= 2130)  # important for calibration
    params = Parameters()

    y_bs_1, bsln_stdDis = create_baseline(y)

    # add fit parameters and fit
    for i, peak in enumerate(peak_list):
        add_params(params, peak)

    composite_fit, residual = peak_analysis(file_path, x)

    save_peak_parameters()
    save_peak_fit_residual()
    save_baseline_data()

def integrate_msIsoXchg(folder_name, files_isoX):
    """This function integrates the MS isotopic exchange spectra to find the area under the curve."""

    def polyfunc(x, a, b, c, d):
        return a + b * x + c * x**2 + d * x**3

    def import_baseline_calibration_data():
        """Import the data from the specified directory."""
        df_mz2928_const = pd.read_csv(dir_mz2928_const)
        df_mz2945_const = pd.read_csv(dir_mz2945_const)

        mz2928_high = np.array(df_mz2928_const["poly_coef_high"][:4])
        mz2928_low = np.array(df_mz2928_const["poly_coef_low"][:4])
        mz2945_const = df_mz2945_const["lin_coef"][0]

        ddIG_filter = 0.225  # empirically deterimined

        return mz2928_high, mz2928_low, mz2945_const, ddIG_filter

    def import_isoXchg_data(files_isoX):
        """Import the isotopic exchange data from the specified directory."""
        dict_isoX = {}
        for path in files_isoX:
            key = path
            if "integrals" in key or "moles" in key or "msCalib" in key:
                continue

            data = pd.read_csv(path)
            data["Timestamp"] = pd.to_datetime(
                data["Timestamp"], format="%m/%d/%y %H:%M:%S.%f"
            )
            data["Relative Time (s)"] = (
                data["Timestamp"] - data["Timestamp"].iloc[0]
            ).dt.total_seconds()
            data["ddIG"] = data["IG"].diff().diff()
            dict_isoX[key] = data

        file_prefix = next(iter(dict_isoX)).split("\\")[-1].split(".")[0]
        file_prefix = "_".join(file_prefix.split("_")[:-1])

        return dict_isoX, file_prefix

    def import_msCalib_data(files_isoX):
        """Import the isotopic exchange data from the specified directory."""
        dict_msCalib = {}
        for path in files_isoX:
            key = path
            if "integrals" in key or "moles" in key or "isoX" in key:
                continue

            data = pd.read_csv(path)
            data["Timestamp"] = pd.to_datetime(
                data["Timestamp"], format="%m/%d/%y %H:%M:%S.%f"
            )
            data["Relative Time (s)"] = (
                data["Timestamp"] - data["Timestamp"].iloc[0]
            ).dt.total_seconds()
            data["ddIG"] = data["IG"].diff().diff()
            dict_msCalib[key] = data

        try:
            file_prefix = next(iter(dict_msCalib)).split("\\")[-1].split(".")[0]
            file_prefix = "_".join(file_prefix.split("_")[:-1])
            return dict_msCalib, file_prefix
        except Exception as e:
            return None, None

    def integrate_isoX_data(
        dict_isoX, mz2928_high, mz2928_low, mz2945_const, ddIG_filter
    ):
        """Integrate the net m/z=29 data."""
        keys = []
        integral_vals = []
        for key, df in dict_isoX.items():
            mz29_corrected = []
            for index, row in df.iterrows():
                if row["IG"] < 0.7 or pd.isna(row["IG"]):
                    value = 0

                elif abs(row["ddIG"]) < ddIG_filter:
                    value = row["V1_I_29"] - (
                        (row["V1_I_45"] * mz2945_const)
                        + (row["V1_I_28"] * (polyfunc(row["IG"], *mz2928_low)))
                    )

                elif abs(row["ddIG"]) > ddIG_filter:
                    value = row["V1_I_29"] - (
                        (row["V1_I_45"] * mz2945_const)
                        + (row["V1_I_28"] * (polyfunc(row["IG"], *mz2928_high)))
                    )

                # else:
                #     value = row['V1_I_29'] - ((row['V1_I_45'] * mz2945_const) + (
                #         row['V1_I_28']*(0.011544314814814827)))

                mz29_corrected.append(value)

            df["mz29_corrected"] = mz29_corrected

            keys.append(key.split("\\")[-1])
            integral = trapezoid(df["mz29_corrected"], df["Relative Time (s)"])
            integral_vals.append(integral)

        df_output_isoX = pd.DataFrame(
            {"Filename": keys, "integral_vals": integral_vals}
        )

        return df_output_isoX
        # # calculate net m/z=29 signal for blank
        # keys = []
        # integral_vals = []
        # for key, df in dict_mz2928_const.items():

        #     mz29_corrected = []

        #     for index, row in df.iterrows():

        #         if row['IG'] < 0.7:
        #             value = 0

        #         elif(abs(row['ddIG']) < ddIG_filter):
        #             value = row['V1_I_29'] - ((row['V1_I_45'] * mz2945_const) + (
        #                 row['V1_I_28']*(polyfunc(row['IG'], *mz2928_low))))

        #         elif(abs(row['ddIG']) > ddIG_filter):
        #             value = row['V1_I_29'] - ((row['V1_I_45'] * mz2945_const) + (
        #                     row['V1_I_28']*(polyfunc(row['IG'], *mz2928_high))))

        #         mz29_corrected.append(value)

        #     df['mz29_corrected'] = mz29_corrected

        #     keys.append(key)
        #     integral = trapz(df['mz29_corrected'], df['Relative Time (s)'])
        #     integral_vals.append(integral)
        #     # plt.plot(df['Relative Time (s)'], df['mz29_corrected'])
        #     # plt.title(key)
        #     # plt.show()

    def save_data(file_prefix, df_output_isoX, save_dir):
        """Save the data to the specified directory."""
        filename = f"{file_prefix}_integrals.csv"
        df_output_isoX.to_csv(f"{folder_name}/{filename}", index=False)

    root_dir = "X:/ms_calibrations/"
    base_calibrations_dir = f"{root_dir}base_calibrations/"

    dir_mz2928_const = (
        f"{base_calibrations_dir}mz2928_matrixCoef.csv"  # mz=29/28 matrix constant
    )
    dir_mz2945_const = (
        f"{base_calibrations_dir}mz2945_matrixCoef.csv"  # mz=29/45 matrix constant
    )

    mz2928_high, mz2928_low, mz2945_const, ddIG_filter = (
        import_baseline_calibration_data()
    )

    dict_isoX, file_prefix = import_isoXchg_data(files_isoX)
    df = integrate_isoX_data(
        dict_isoX, mz2928_high, mz2928_low, mz2945_const, ddIG_filter
    )
    save_data(file_prefix, df, folder_name)

    dict_msCalib, file_prefix = import_msCalib_data(files_isoX)
    if dict_msCalib is None:
        return
    df = integrate_isoX_data(
        dict_msCalib, mz2928_high, mz2928_low, mz2945_const, ddIG_filter
    )
    if df.empty:
        return
    save_data(file_prefix, df, folder_name)

def generate_calibCurve(folder_name):
    """This function generates a file that contains the integral carbonyl band area
    and the corresponding 13CO moles obtained from ms calibration files."""

    def linfunc(x, a, b):  # for calibration curve
        return a * x + b

    def linfunc_no_intercept(x, a):  # for calibration curve
        return a * x

    def split_keys(key):
        fileid = key.split("\\")[-1].split(".")[0]
        return fileid

    def split_file(file):
        name = file.split("\\")[-1].split(".")[0]
        fileid = "_".join(name.split("_")[:-1])
        return fileid

    def import_calibration_files():
        files_ir = glob.glob(f"{dir_ir_root}{folder_name}/*_CarbonylPeakFitParams.csv")
        files_ms = glob.glob(f"{dir_ms_root}{folder_name}/*isoX_integrals.csv")
        files_msCalib = glob.glob(f"{dir_msCalib}/*")

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
            dfs = []
            # ir data
            for file in files_ir:
                if any(string in file for string in skip_files):
                    continue
                df = pd.read_csv(file)
                dfs.append(df)
            df_carbonyl_isoX = pd.concat(dfs, ignore_index=True)

            dfs = []
            # ms data
            for file in files_ms:
                if any(string in file for string in skip_files):
                    continue
                df = pd.read_csv(file)
                dfs.append(df)
            df_mz29_isoX = pd.concat(dfs, ignore_index=True)

        else:
            dfs = []
            # ir data
            for file in files_ir:
                df = pd.read_csv(file)
                dfs.append(df)
            df_carbonyl_isoX = pd.concat(dfs, ignore_index=True)

            dfs = []
            # ms data
            for file in files_ms:
                df = pd.read_csv(file)
                dfs.append(df)
            df_mz29_isoX = pd.concat(dfs, ignore_index=True)

        # clean data
        df_carbonyl_isoX["Peak_Area"] = df_carbonyl_isoX["Peak_Area"] * -1
        df_carbonyl_isoX["Peak_Area"] = df_carbonyl_isoX["Peak_Area"].mask(
            df_carbonyl_isoX["Peak_Area"] < 0, 0
        )

        df_carbonyl_isoX["Carbonyl_Integral"] = (
            df_carbonyl_isoX["Carbonyl_Integral"] * -1
        )
        df_carbonyl_isoX["Carbonyl_Integral"] = df_carbonyl_isoX[
            "Carbonyl_Integral"
        ].mask(df_carbonyl_isoX["Carbonyl_Integral"] < 0, 0)

        integrals_file = None
        moles_file = None

        if folder_name == "nn1120-2_pd_ceo2_000":
            df_mz29_mol13CO = pd.read_csv(dir_msCalib)
        else:
            dfs = []
            for file in files_msCalib:
                if file.endswith("_msCalib_integrals.csv"):
                    df = pd.read_csv(file)
                    dfs.append(df)
            df_integrals = pd.concat(dfs, ignore_index=True)

            dfs = []
            for file in files_msCalib:
                if file.endswith("_msCalib_moles.csv"):
                    df = pd.read_csv(file)
                    dfs.append(df)
            df_moles = pd.concat(dfs, ignore_index=True)

            # df_integrals = pd.read_csv(integrals_file)
            # df_moles = pd.read_csv(moles_file)
            # df_mz29_mol13CO = pd.merge(df_integrals, df_moles, on='Filename') # mass spec calibration data
            df_mz29_mol13CO = pd.concat([df_integrals, df_moles], axis=1)

        return df_carbonyl_isoX, df_mz29_isoX, df_mz29_mol13CO

    def ms_integral_to_moles() -> None:
        # find slope for m/z=29 signal and 13CO moles
        x = df_mz29_mol13CO["integral_vals"]
        try:
            y = df_mz29_mol13CO["13CO_Moles"]
        except:
            y = df_mz29_mol13CO["co_moles"]

        popt, pcov = curve_fit(linfunc, x, y)
        mz29_mol13CO_slope = popt[0]
        mz29_mol13CO_intercept = popt[1]

        # convert MS integrals from isotopic exchange to moles
        df_mz29_isoX["co_moles"] = (
            df_mz29_isoX["integral_vals"] * mz29_mol13CO_slope + mz29_mol13CO_intercept
        )
        return None

    def merge_ms_ir(df_carbonyl_isoX, df_mz29_isoX) -> tuple:
        # merge IR and MS dataframes on filename
        df = df_carbonyl_isoX[
            df_carbonyl_isoX["Peak_Name"].isin(["Peak_2112", "Peak_2126", "Peak_2136"])
        ]
        df_carbonyl_isoX = (
            df.groupby("File")
            .agg({"Carbonyl_Integral": "first", "Peak_Area": "sum"})
            .reset_index()
        )

        # normalize filname and drop
        df_carbonyl_isoX["filename"] = df_carbonyl_isoX["File"].apply(split_file)
        df_carbonyl_isoX = df_carbonyl_isoX.drop(columns=["File"], inplace=False)
        try:
            df_mz29_isoX["filename"] = df_mz29_isoX["keys"].dropna().apply(split_keys)
            df_mz29_isoX = df_mz29_isoX.drop(columns=["keys"], inplace=False)
        except:
            df_mz29_isoX["filename"] = df_mz29_isoX["Filename"].apply(split_keys)
            df_mz29_isoX = df_mz29_isoX.drop(columns=["Filename"], inplace=False)

        df_isoX = pd.merge(df_carbonyl_isoX, df_mz29_isoX, on="filename", how="outer")
        # df_isoX = df_isoX.dropna()

        if folder_name == "nn1120-2_pd_ceo2_000":  # clean data
            mask = (
                (df_isoX["Peak_Area"] >= 0)
                & (df_isoX["Peak_Area"] <= 0.04)
                & (df_isoX["co_moles"] >= 0)
                & (df_isoX["co_moles"] > 2.5e-10)
                & ~((df_isoX["Peak_Area"] == 0) & (df_isoX["co_moles"] > 1e-9))
            )

            df_isoX = df_isoX[mask]

        mask = (df_isoX["integral_vals"] < 0) | (df_isoX["co_moles"] < 0)
        df_isoX = df_isoX[~mask]

        x_peakArea = df_isoX["Peak_Area"]
        x_carbonylIntegral = df_isoX["Carbonyl_Integral"]
        y = df_isoX["co_moles"]

        popt_peakArea = curve_fit(linfunc, x_peakArea, y)
        popt_carbonylIntegral = curve_fit(linfunc, x_carbonylIntegral, y)

        # scalar offset
        y_peakArea = y - popt_peakArea[0][1]
        y_carbonylIntegral = y - popt_carbonylIntegral[0][1]

        df_isoX["co_moles_paOffset"] = y_peakArea
        df_isoX["co_moles_ciOffset"] = y_carbonylIntegral

        return x_peakArea, x_carbonylIntegral, y_peakArea, y_carbonylIntegral, df_isoX

    def stat_params(x, y, popt):
        y_pred = linfunc_no_intercept(x, popt[0])  # Calculate the predicted y-values
        std_errors = np.sqrt(
            np.diag(popt[1])
        )  # Calculate the standard errors of the parameter estimates
        residuals = y - y_pred
        see = np.sqrt(np.mean(residuals**2))  # standard error of the estimate
        ss_tot = np.sum((y - np.mean(y)) ** 2)  # total sum of squares
        ss_res = np.sum(residuals**2)  # residual sum of squares
        r_squared = 1 - (ss_res / ss_tot)  # r-squared
        rmse = np.sqrt(np.mean(residuals**2))

        # Calculate the critical value for the t-distribution
        dof = len(x) - 2  # degrees of freedom
        confidence_level = 0.975  # for a 95% confidence level
        t_critical = t.ppf(confidence_level, dof)

        # Calculate the standard error
        pred_stderr = see * np.sqrt(
            1 + 1 / len(x) + (x - np.mean(x)) ** 2 / np.sum((x - np.mean(x)) ** 2)
        )

        # Calculate the prediction interval
        pred_interval = (
            t_critical
            * see
            * np.sqrt(
                1 + 1 / len(x) + (x - np.mean(x)) ** 2 / np.sum((x - np.mean(x)) ** 2)
            )
        )

        return {
            "slope": popt[0],
            "std_errors": std_errors,
            "see": see,
            "r_squared": r_squared,
            "rmse": rmse,
            "y_pred": y_pred,
        }

    dir_ms_root = "X:/ms_calibrations/"  # ms calibration files
    dir_ir_root = "C:/Data/OpusCalibrations/"  # ir calibration files

    # dir_ms = f'{dir_ms_root}{folder_name}/'
    # dir_ir = f'{dir_ir_root}{folder_name}/*_CarbonylPeakFitParams.csv'
    dir_msCalib = f"{dir_ms_root}{folder_name}"  # mz=29 and 13CO moles relation in 12CO matrix data
    dir_save = f"C:/Data/peakFit/{folder_name}/CalibrationData"

    if folder_name == "nn1120-2_pd_ceo2_000":
        dir_msCalib = (
            f"{dir_ms_root}base_calibrations/13CO_msCalib_12COmatrix/"
            "mz29_mol13CO_calibration.csv"
        )

    df_carbonyl_isoX, df_mz29_isoX, df_mz29_mol13CO = import_calibration_files()
    ms_integral_to_moles()
    x_peakArea, x_carbonylIntegral, y_peakArea, y_carbonylIntegral, df_isoX = (
        merge_ms_ir(df_carbonyl_isoX, df_mz29_isoX)
    )

    popt_peakArea = curve_fit(linfunc_no_intercept, x_peakArea, y_peakArea)
    popt_carbonylIntegral = curve_fit(
        linfunc_no_intercept, x_carbonylIntegral, y_carbonylIntegral
    )

    peakArea_stats = stat_params(x_peakArea, y_peakArea, popt_peakArea)
    carbonylIntegral_stats = stat_params(
        x_carbonylIntegral, y_carbonylIntegral, popt_carbonylIntegral
    )

    file_prefix = folder_name
    filename = f"{file_prefix}_calibrationCurve.csv"
    path = os.path.join(dir_save, filename)
    df_isoX.to_csv(path, index=False)

    filename = f"{file_prefix}_msCalib_all.csv"
    path = os.path.join(f"{dir_msCalib}", filename)
    df_mz29_mol13CO.to_csv(path, index=False)

    """sae df_mz29_mol13CO to csv"""

    print("Peak Area stats:", peakArea_stats)
    print("Carbonyl Integral stats:", carbonylIntegral_stats)

def plot_spectrum_fit(file_path):
    def voigt_model(x, y0, amplitude, center, sigma, gamma):
        return y0 + (amplitude * voigt_profile(x - center, sigma, gamma))

    root_dir = "\\".join(file_path.split("\\")[:2])
    folder_name = file_path.split("\\")[-2]
    file_name = file_path.split("\\")[-1]

    fitParams_dir = os.path.join(root_dir, "peakFit", folder_name)

    try:
        df_fitParams = pd.read_csv(
            f"{fitParams_dir}\\{file_name}_CarbonylPeakFitParams.csv"
        )
    except FileNotFoundError:
        print(
            f"File {file_name}_CarbonylPeakFitParams.csv not found in {fitParams_dir}."
        )
        return
    df_baseline = pd.read_csv(f"{fitParams_dir}\\{file_name}_CarbonylFitBaseline.csv")
    df_residual = pd.read_csv(f"{fitParams_dir}\\{file_name}_CarbonylFitResidual.csv")

    arr = df_baseline.values
    x_limits = (round(arr[0, 0], 4), round(arr[-1, 0], 4))
    x = np.linspace(x_limits[0], x_limits[1], arr[:, 0].size)

    # group files by delta file
    delta_groups = {}
    subIfg_files = sorted(
        glob.glob(f"{root_dir}\\OpusConvert_subIFG_lgRfl\\{folder_name}\\{file_name}*")
    )
    for file in subIfg_files:
        delta_file = file.split("_")[-1].split(".")[0]
        if delta_file not in [
            "delta5",
            "delta6",
            "delta7",
            "delta8",
            "delta9",
            "delta10",
        ]:
            continue
        if delta_file not in delta_groups.keys():
            delta_groups[delta_file] = []
        delta_groups[delta_file].append(file)

    # sum subIFG data for each delta group
    delta_group_data = {}
    delta_group_residual = {}
    for delta_file, files in delta_groups.items():
        arr_subIFG = np.zeros_like(x)
        arr_residual = np.zeros_like(x)
        for file in files:
            iterator = file.split(".")[-1]
            try:
                arr_bs = df_baseline[f"{delta_file}.{iterator}"].values
                arr_res = df_residual[f"{delta_file}.{iterator}"].values
            except KeyError:
                print(f"Key {delta_file}.{iterator} not found in {file}.")
                continue
            df = pd.read_csv(file, header=None)
            arr = df.loc[
                (round(df[0], 4) >= x_limits[1]) & (round(df[0], 4) <= x_limits[0])
            ].values[:, 1]
            arr_subIFG += arr - arr_bs
            arr_residual += arr_res
        delta_group_data[delta_file] = arr_subIFG
        delta_group_residual[delta_file] = arr_residual

    # Reconstruct the cumulative Voigt peak for each group
    delta_group_fit = {}
    df_fitParams = df_fitParams.dropna(
        subset=["Y0", "Amplitude", "Center", "Sigma", "Gamma"]
    )
    for delta_group, group in df_fitParams.groupby("Delta_Group"):
        y = np.zeros_like(x)
        for index, row in group.iterrows():
            y += voigt_model(
                x,
                row["Y0"],
                row["Amplitude"],
                row["Center"],
                row["Sigma"],
                row["Gamma"],
            )
        delta_group_fit[delta_group] = y

    # Reconstruct the individual Voigt peak for each group
    peaks_data = {}
    for (delta_group, peak_name), group in df_fitParams.groupby(
        ["Delta_Group", "Peak_Name"]
    ):
        if not delta_group in peaks_data.keys():
            peaks_data[delta_group] = {}
        y = np.zeros_like(x)
        for index, row in group.iterrows():
            y += voigt_model(
                x,
                row["Y0"],
                row["Amplitude"],
                row["Center"],
                row["Sigma"],
                row["Gamma"],
            )
            peaks_data[delta_group][peak_name] = y

    peaks = [
        "Peak_2093",
        "Peak_2103",
        "Peak_2113",
        "Peak_2125",
        "Peak_2136",
        "Peak_2146",
        "Peak_2156",
    ]
    for delta_group, arr in delta_group_data.items():
        fig, ax = plt.subplots(figsize=(4, 4))
        ax.plot(x, arr, linestyle="-", color="black", label=f"{delta_group} fit")
        ax.plot(
            x,
            delta_group_fit[delta_group],
            linestyle="-",
            color="red",
            linewidth=1,
            label=f"{delta_group} data",
        )
        ax.plot(
            x,
            delta_group_residual[delta_group],
            linestyle="-",
            color="blue",
            linewidth=1,
            label=f"{delta_group} residual",
        )
        for peak in peaks:
            ax.plot(
                x,
                peaks_data[delta_group][peak],
                linestyle="--",
                linewidth=1,
                label=peak,
            )

        ax.set_xlabel("Wavenumber (cm-1)")
        ax.set_ylabel("Log Reflectance")
        ax.legend(loc="upper right", bbox_to_anchor=(1, 1))
        ax.invert_xaxis()
        ax.set_xlim([2250, 1750])

        # save figure
        file_path = os.path.join("C:\\Figures", folder_name)
        if not os.path.exists(file_path):
            os.makedirs(file_path)
        plt.savefig(
            f"C:\\Figures\\{folder_name}\\{file_name}_{delta_group}.tiff",
            dpi=800,
            bbox_inches="tight",
        )
        plt.close()

if __name__ == "__main__":

    def process_all_voight_fit():
        file_directory = r"C:\Data\OpusConvert_subIFG_lgRfl\nn1120-3_pd_ceo2_003"
        name = r"20260108_220047_pd_ceo2_003-093"

        for file_name in os.listdir(file_directory):
            if name in file_name:  # need to delete the files in peakFit if they exist
                file_path = os.path.join(file_directory, file_name)
                if os.path.isfile(file_path):
                    try:
                        voight_fit(file_path)
                    except Exception as e:
                        print(e)

    def process_all_kinetic_fit():
        file_directory = r"X:\peakFit\nn1120-2_pd_ceo2_000"
        data_container_list = []

        for file_name in os.listdir(file_directory):
            if "README.md" in file_name:
                file_path = os.path.join(file_directory, file_name)
                if os.path.isfile(file_path):
                    try:
                        filename, expParams, fit_results, x, y = kinetic_fit(file_path)
                        data_container = {
                            "filename": filename,
                            "expParams": expParams,
                            "fit_results": fit_results,
                            "x_data": x,
                            "y_data": y,
                        }
                        data_container_list.append(data_container)
                    except Exception as e:
                        print(e)

    def process_all_pfo_fit():
        dir = r"C:\Data\peakFit\nn1120-3_pd_ceo2_003"
        # dir = r"X:\peakFit\nn1120-2_pd_ceo2_000"
        for file in os.listdir(dir):
            if file != "20251212_211840_pd_ceo2_003-077_CarbonylPeakArea.csv":
                continue
            if "CarbonylPeakArea.csv" in file:
                path = os.path.join(dir, file)
                pfo_fit_by_row(path)

    def process_all_monomer_sum_and_fit(
        src_folder=r"C:\Data\peakFit\nn1120-3_pd_ceo2_003",
        dst_folder=r"X:\peakFit\test",
    ):
        """
        For each *_CarbonylPeakArea.csv in src_folder:
        - Sum Cumulative_Peak_Area for monomer peaks at each Delta_Group and Time (s)
        - Add as a new row with Peak_Name='monomer_sum'
        - All other columns blank except File, Delta_Group, Peak_Name, Time (s), Cumulative_Peak_Area
        - Save to dst_folder and run pfo_fit_by_row
        """
        import os
        import pandas as pd

        monomer_peaks = ["Peak_2093", "Peak_2103", "Peak_2113", "Peak_2125"]

        if not os.path.exists(dst_folder):
            os.makedirs(dst_folder)

        for fname in os.listdir(src_folder):
            if fname.endswith("_CarbonylPeakArea.csv"):
                if fname != "20250804_085906_pd_ceo2_003-002_CarbonylPeakArea.csv":
                    continue
                fpath = os.path.join(src_folder, fname)
                df = pd.read_csv(fpath)

                # Only process if all required columns exist
                if not all(
                    col in df.columns
                    for col in [
                        "Delta_Group",
                        "Time (s)",
                        "Peak_Name",
                        "Cumulative_Peak_Area",
                    ]
                ):
                    continue

                # Group by Delta_Group and Time (s) for monomer peaks
                grouped = df[df["Peak_Name"].isin(monomer_peaks)].groupby(
                    ["Delta_Group", "Time (s)"]
                )
                monomer_rows = []
                for (delta_group, time_s), group in grouped:
                    summed_area = group["Cumulative_Peak_Area"].sum()
                    # Use first File value if present, else blank
                    file_val = group["File"].iloc[0] if "File" in group else ""
                    # Build row with only the required columns
                    row = {
                        "File": file_val,
                        "Delta_Group": delta_group,
                        "Peak_Name": "monomer_sum",
                        "Time (s)": time_s,
                        "Cumulative_Peak_Area": summed_area,
                    }
                    # Add all other columns as blank
                    for col in df.columns:
                        if col not in row:
                            row[col] = ""
                    monomer_rows.append(row)

                # Append to DataFrame
                df_out = pd.concat([df, pd.DataFrame(monomer_rows)], ignore_index=True)
                # Save to destination folder
                out_path = os.path.join(dst_folder, fname)
                df_out.to_csv(out_path, index=False)
                print(f"Processed and saved: {out_path}")

                # Now fit the monomer_sum using pfo_fit_by_row
                try:
                    pfo_fit_by_row(out_path)
                    print(f"Fitted monomer_sum and saved: {os.path.basename(out_path)}")
                except Exception as e:
                    print(f"Error fitting {out_path}: {e}")

    def process_all_readme_to_csv():
        file_directory = r"X:\peakFit\nn1120-3_pd_ceo2_003"

        for file_name in os.listdir(file_directory):
            if "README.md" in file_name:
                file_path = os.path.join(file_directory, file_name)
                if os.path.isfile(file_path):
                    try:
                        readme_to_csv(file_path)
                    except Exception as e:
                        print(e)

    def process_all_peak_heights():
        file_dir = r"C:\Data\OpusConvert_subIFG_lgRfl\nn1120-3_pd_ceo2_003"

        for file_name in os.listdir(file_dir):
            if "isoX" in file_name:
                continue
            if "20260108_220047_pd_ceo2_003-093" not in file_name:
                continue
            full_file_path = os.path.join(file_dir, file_name)
            if os.path.isfile(full_file_path):
                peak_heights(full_file_path)

    def process_all_integrateIsoX():
        """need to delete existing files in OpusCalibrations first otherwise it will append"""

        save_dir = r"C:\Data\OpusCalibrations\nn1120-3_pd_ceo2_000"
        file_dir = r"C:\Data\OpusConvert_subIFG_lgRfl\nn1120-3_pd_ceo2_000"

        # List all processed files in save_dir
        processed_files = set(
            "_".join(file_name.split("_")[:-1]) for file_name in os.listdir(save_dir)
        )

        # List all files to process in file_dir
        files_to_process = [
            os.path.join(file_dir, file_name)
            for file_name in os.listdir(file_dir)
            if "isoX" in file_name
            and os.path.isfile(os.path.join(file_dir, file_name))
            and "_".join(file_name.split("_")[:-2]) not in processed_files
        ]

        for file_path in files_to_process:
            integrate_irIsoXchg(file_path)

    def process_all_integrate_msISoXchg(folder_name, filename):
        dir_isoX = f"{folder_name}\\{filename}*"  # isotopic exchange data
        files_isoX = sorted(glob.glob(dir_isoX))

        integrate_msIsoXchg(folder_name, files_isoX)

        # for file in os.listdir(folder_name):
        #     file = "_".join(file.split('_')[:-1])
        #     integrate_msIsoXchg(folder_name, file)

    def process_all_generate_calibCurve():
        folder_name = "nn1120-3_pd_ceo2_000"
        generate_calibCurve(folder_name)

    def process_all_plot_spectrum_fit():
        """need to change like IR_voightReconstruct_plt"""
        folder = r"nn1120-3_pd_ceo2_003"
        file_directory = f"C:\\Data\\OpusConvert_subIFG_lgRfl\\{folder}"
        figure_directory = f"C:\\Figures\\{folder}"
        unique_names = set()

        if folder == "nn1120-2_pd_ceo2_000":
            exclude_name = ["000-032"]
        else:
            exclude_name = []

        for file in os.listdir(figure_directory):
            name = "_".join(file.split("_")[:-1])
            exclude_name.append(name)

        for file_name in os.listdir(file_directory):
            name = "_".join(file_name.split("_")[:-1])
            unique_names.add(name)
        for name in sorted(unique_names):
            if any(excluded in name for excluded in exclude_name):
                continue
            plot_spectrum_fit(f"{file_directory}\\{name}")

    """once the calibration files are in place in peakFit, then can modify voight and reprocess scripts to just reference those
        but will need to pass an argument to not process until calibration files are in place"""

    process_all_voight_fit()
    process_all_peak_heights()
    # process_all_readme_to_csv()
    # process_all_pfo_fit()
    # process_all_spectrum_fit()
    # reprocess_sum_peak_area() # better make sure this is the same as voight_fit
    # process_all_monomer_sum_and_fit()

    # process_all_integrateIsoX()
    # process_all_integrate_msISoXchg(folder_name=r"X:\ms_calibrations\nn1120-3_pd_ceo2_000",
    #                                 filename=r"20250331_073028_pd_ceo2_000-012")
    # process_all_generate_calibCurve()

    # integrate_irIsoXchg(r"C:\Data\OpusConvert_subIFG_lgRfl\nn1120-3_pd_ceo2_000\20250314_215031_pd_ceo2_000-005_isoX_0_delta1.0001")

    """troubleshoot pfo_fit"""
    # pfo_fit(r"C:\Data\OpusConvert_subIFG_lgRfl\nn1120-2_pd_ceo2_000\20250218_063825_pd_ceo2_000-034_delta1.0001")

    """troubleshoot voight fit"""
    # files = [
    #     '20250324_121256_pd_ceo2_000-009_delta1.0001',
    #     '20250324_121256_pd_ceo2_000-009_delta1.0002',
    #     '20250324_121256_pd_ceo2_000-009_delta5.0007',
    #     '20250324_121256_pd_ceo2_000-009_delta6.0014',
    # ]

    # for file in files:
    #     voight_fit(f"C:\\Data\\OpusConvert_subIFG_lgRfl\\nn1120-3_pd_ceo2_000\\{file}")

    """convert single readme to csv"""
    readme_to_csv(
        r"X:\peakFit\nn1120-3_pd_ceo2_003\20260108_220047_pd_ceo2_003-093_README.md"
    )

    """plot spectrum fit"""
    # file_path = r"C:\Data\OpusConvert_subIFG_lgRfl\nn1120-3_pd_ceo2_001\20250510_153806_pd_ceo2_001-022_delta10.0022"
    # plot_spectrum_fit(file_path)
    # process_all_plot_spectrum_fit()
