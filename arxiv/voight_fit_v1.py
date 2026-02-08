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
                for file in glob.glob(os.path.join(calibration_dir, "*")):
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
                for file in glob.glob(os.path.join(calibration_dir, "*")):
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

    root_dir = config.get_path("data.root")
    folder_name = os.path.basename(os.path.dirname(file_path))
    file_name = "_".join(os.path.basename(file_path).split("_")[:-1])
    iterator = file_path.split(".")[-1]
    delta_file = file_path.split("_")[-1].split(".")[0]

    if manually_skip_files(delta_file, iterator):
        return

    save_dir = config.get_path("data.peak_fit", folder_name)
    time_dir = config.get_path(
        "utility.subtract_ifg.read_params_output", folder_name, f"{file_name}.txt"
    )
    fsd_dir = config.get_path(
        "utility.subtract_ifg.fsd_output", folder_name, f"{file_name}.{iterator}"
    )
    subIFG_log_dir = config.get_path(
        "utility.subtract_ifg.read_params_output",
        folder_name,
        f"{file_name}_subIFGfiles.txt",
    )
    calibration_dir = config.get_path(
        "calibration.root", folder_name, "CalibrationData"
    )

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
