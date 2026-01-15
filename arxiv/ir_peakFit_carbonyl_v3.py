import os
import pandas as pd
import numpy as np
import pybaselines
from lmfit import Model
from lmfit import Parameters, Minimizer
from scipy.signal import find_peaks
from scipy.special import voigt_profile
from scipy.integrate import trapezoid
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import argparse
import time
import concurrent.futures



def voight_fit(file_path):

    def add_milliseconds(time_str):
        if '.' not in time_str:
            return time_str + '.000000'
        else:
            return time_str

    def voigt_model(x, y0, amplitude, center, sigma, gamma):
        return y0 + (amplitude * voigt_profile(x - center, sigma, gamma))

    def combined_voigt(x, params):
        w = np.zeros_like(x)
        for peak in peakList_core:
            center = params[f'center_{peak}'].value
            amplitude = params[f'amplitude_{peak}'].value
            sigma = params[f'sigma_{peak}'].value
            gamma = params[f'gamma_{peak}'].value
            y0 = params[f'y0_{peak}'].value
            w += Model(voigt_model).eval(x=x, y0=y0, center=center,
                                        amplitude=amplitude, sigma=sigma,
                                        gamma=gamma)
        return w

    def objective(params):
        return combined_voigt(x, params) - y_bs_1

    def peak_fit(file_path):
        minimizer = Minimizer(objective, params)
        result = minimizer.minimize()
        return result

    def add_params(file_path, params, peak, peak_name):

        if (peak <= 2161) and (peak >= 2151):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01, min=0)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)     

        elif (peak < 2151) and (peak >= 2141):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)    

        elif (peak < 2141) and (peak >= 2130):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2130) and (peak >= 2120):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2120) and (peak >= 2108):

            if peak_tmp is None:

                params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                        max=peak + 1)
                params.add(f'amplitude_{peak_name}', value=0.01)
                params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
                params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
                params.add(f'y0_{peak_name}', value=0, min=0, vary=False)
            
            elif peak_tmp is None and peak == 2113 and \
                    int(file_path.split('.')[-1]) > 12:
                
                params.add(f'center_{peak_name}', value=peak, min=peak - 3,
                        max=peak + 1)
                params.add(f'amplitude_{peak_name}', value=0.01)
                params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
                params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
                params.add(f'y0_{peak_name}', value=0, min=0, vary=False)
                
            else:

                params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                        max=peak + 3)
                params.add(f'amplitude_{peak_name}', value=0.01)
                params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
                params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
                params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2108) and (peak >= 2098):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2098) and (peak >= 2088):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=-0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2088) and (peak >= 2078):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2078) and (peak >= 2068):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2067) and (peak >= 2057):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2055) and (peak >= 2045):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2045) and (peak >= 2035):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2035) and (peak >= 2025):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2020) and (peak >= 2010):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2005) and (peak >= 1995):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 1993) and (peak >= 1983):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 1980) and (peak >= 1970):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 1800) and (peak >= 1790):
            params.add(f'center_{peak_name}', value=peak, min=peak - 5,
                    max=peak + 5)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=26)
            params.add(f'gamma_{peak_name}', value=2, min=0)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 1780) and (peak >= 1770):
            params.add(f'center_{peak_name}', value=peak, min=peak - 5,
                    max=peak + 5)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=26)
            params.add(f'gamma_{peak_name}', value=2, min=0)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        else:
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        return None

    def peak_analysis(file_path, params, x):

        fitted_peaks = np.zeros_like(x)

        # find time delta
        sample_name = file_path.split('\\')[-1]

        index_sample_name = subIFG_log['sample_name'].index[
            subIFG_log['sample_name'] == sample_name].tolist()

        sample = subIFG_log['sample'][index_sample_name].iloc[0]

        background = subIFG_log['background'][index_sample_name].iloc[0]

        matching_rows = [exp_params[exp_params['file_directory'] == path].index[
            0] for path in [sample, background]]

        time_delta = (exp_params['DateTime'][
            matching_rows[0]] - exp_params['DateTime'][
                matching_rows[1]]).total_seconds()

        # create dictionary for each delta group
        delta_group = file_path.split("_")[-1].split(".")[0]
        if delta_group not in cumulative_data_dict:
            cumulative_data_dict[delta_group] = {
                'cumulative_fit': np.zeros_like(x),
                'cumulative_residual': np.zeros_like(x),
                'cumulative_subIFG': np.zeros_like(x)
                }

        # skip fitting if criteria not met
        avg_y = np.mean(abs(y_bs_1))

        peaks_pos, properties = find_peaks(y_bs_1, prominence=0.0003,
                                        height=3*avg_y)
        peak_wavenumbers_pos = df_subIFG_roi[0].values[peaks_pos]
        
        peaks_neg, properties = find_peaks(-y_bs_1, prominence=0.0003,
                                        height=3*avg_y)
        peak_wavenumbers_neg = df_subIFG_roi[0].values[peaks_neg]

        if len(peaks_pos) == 0 and len(peaks_neg) == 0:
            print('skipped: ', file_path)

            x_pos = x[y_bs_1 >= 0]
            y_bs_1_pos = y_bs_1[y_bs_1 >= 0]
            x_neg = x[y_bs_1 < 0]
            y_bs_1_neg = y_bs_1[y_bs_1 < 0]

            integral_pos = -np.trapezoid(y_bs_1_pos, x_pos)
            integral_neg = -np.trapezoid(y_bs_1_neg, x_neg)
            data_integral = integral_pos + integral_neg

            for i, peak in enumerate(peakList_core):

                if (delta_file == 'delta9') or (delta_file == 'delta10'):
                    peak_data = {
                        'File': file_path.split("_")[-1],
                        'Delta_Group': delta_group,
                        'Peak_Name': f'Peak_{peak}',
                        'Peak_Value': peakList[i],
                        'Data_Integral': data_integral,
                        'Time_Delta (s)': time_delta,
                        'Peak_Area': 0
                    }

                    fit_peak_data.append(peak_data)

                else:
                    peak_data = {
                        'File': file_path.split("_")[-1],
                        'Delta_Group': delta_group,
                        'Peak_Name': f'Peak_{peak}',
                        'Peak_Value': peakList[i],
                        'Data_Integral': data_integral,
                        'Time_Delta (s)': time_delta,
                    }

                    fit_peak_data.append(peak_data)

            return fitted_peaks

        else:

            # fit peaks
            result = peak_fit(file_path)
            fitted_params = result.params
            residual = result.residual

            # report_filename = 'fit_report.txt'
            # with open(report_filename, 'w') as report_file:
            #     print(fit_report(result), file=report_file)

            for i, peak in enumerate(peakList_core):
                center = fitted_params[f'center_{peak}'].value
                amplitude = fitted_params[f'amplitude_{peak}'].value
                sigma = fitted_params[f'sigma_{peak}'].value
                gamma = fitted_params[f'gamma_{peak}'].value
                y0 = fitted_params[f'y0_{peak}'].value

                y_fit = Model(voigt_model).eval(x=x, y0=y0, center=center,
                                                amplitude=amplitude, sigma=sigma,
                                                gamma=gamma)

                peak_area = -trapezoid(y_fit, x)

                x_pos = x[y_bs_1 >= 0]
                y_bs_1_pos = y_bs_1[y_bs_1 >= 0]
                x_neg = x[y_bs_1 < 0]
                y_bs_1_neg = y_bs_1[y_bs_1 < 0]

                integral_pos = -np.trapezoid(y_bs_1_pos, x_pos)
                integral_neg = -np.trapezoid(y_bs_1_neg, x_neg)
                data_integral = integral_pos + integral_neg
                # data_integral = -np.trapezoid(y_bs_1, x)

                fwhm_gaussian = 2*sigma*np.sqrt(2*np.log(2))
                fwhm_lorentz = 2*gamma
                fwhm_voigt = (0.5346*fwhm_lorentz) + np.sqrt((
                    0.2166*fwhm_lorentz**2) + fwhm_gaussian**2)

                peak_data = {
                    'File': file_path.split("_")[-1],
                    'Delta_Group': delta_group,
                    'Peak_Name': f'Peak_{peak}',
                    'Peak_Value': peakList[i],
                    'Data_Integral': data_integral,
                    'Center': center,
                    'Amplitude': amplitude,
                    'Sigma': sigma,
                    'Gamma': gamma,
                    'Y0': y0,
                    'fwhm': fwhm_voigt,
                    'Time_Delta (s)': time_delta,
                    'Peak_Area': peak_area
                }

                fit_peak_data.append(peak_data)
                fitted_peaks += y_fit

            residual_data = {'key': (file_path.split("_")[
                -1]), 'residual': residual}
            residuals.append(residual_data)

            cumulative_data_dict[delta_group][
                'cumulative_fit'] += fitted_peaks
            cumulative_data_dict[delta_group][
                'cumulative_residual'] += residual
            cumulative_data_dict[delta_group][
                'cumulative_subIFG'] += y_bs_1

            return fitted_peaks

    def save_data(new_data, file_path, axis):

        if os.path.isfile(file_path):
            try:
                existing_data = pd.read_csv(file_path, header=0)
            except Exception as e:
                existing_data = pd.DataFrame()
                print(e)
            if 'Wavenumber (cm-1)' in existing_data.columns:
                new_data = new_data.drop(columns=['Wavenumber (cm-1)'])
            combined_data = pd.concat([existing_data, new_data], axis=axis, ignore_index=False)
            try:
                combined_data = combined_data.sort_values(by=["Peak_Name", "File"])
            except Exception as e:
                print(e)
        else:
            combined_data = new_data

        combined_data.to_csv(file_path, index=False)

    
    root_dir = '\\'.join(file_path.split('\\')[:2]) 
    folder_name = file_path.split('\\')[-2]
    file_name = '_'.join((file_path.split('\\')[-1]).split('_')[:-1])
    iterator = file_path.split('.')[-1]

    save_dir = os.path.join(root_dir, 'peakFit', folder_name)
    time_dir = os.path.join(root_dir, 'OpusReadParams', folder_name, f"{file_name}.txt")
    fsd_dir = os.path.join(root_dir, 'OpusConvert_fsd/', folder_name, f"{file_name}.{iterator}")
    lgRfl_dir = os.path.join(root_dir, 'OpusConvert_lgRfl', folder_name, f"{file_name}.{iterator}")
    subIFG_log_dir = os.path.join(
         root_dir, 'OpusReadParams', folder_name, f"{file_name}_subIFGfiles.txt")


    # import lgRfl data
    df_lgRfl = pd.read_csv(lgRfl_dir, header=None)
    df_lgRfl_roi = df_lgRfl.loc[(df_lgRfl[0] >= 1750) & (
                                    df_lgRfl[0] <= 2250)]

    # import subIFG data
    df_subIFG = pd.read_csv(file_path, header=None)
    df_subIFG_roi = df_subIFG.loc[(df_subIFG[0] >= 1750) & (
                                    df_subIFG[0] <= 2250)]
    arr_subIFG_roi = df_subIFG_roi.values  # 2050 and 2250 previously

    # import fsd data
    df_fsd = pd.read_csv(fsd_dir, header=None)
    df_fsd_roi = df_fsd.loc[(df_fsd[0] >= 1750) & (
                                    df_fsd[0] <= 2250)]
    arr_fsd_roi = df_fsd_roi.values


    # find fsd peaks
    x = arr_fsd_roi[:, 0]
    fsd = arr_fsd_roi[:, 1].T    
    fsd_mask = x < 2100

    fsd_baseline = np.mean(fsd[fsd_mask])
    fsd_bs = fsd - fsd_baseline

    peaks, properties = find_peaks(fsd_bs, prominence=0.0001,
                                height=0.003)
    peak_wavenumbers = df_fsd_roi[0].values[peaks]

    fsd_peaks_dict = {
        f"{file_name}.{iterator}": peak_wavenumbers
        }


    # import subIFG file log
    subIFG_log = pd.read_csv(subIFG_log_dir, header=None, names=[
        'sample_name', 'sample', 'background'])

    subIFG_log['sample_name'] = subIFG_log[
        'sample_name'].str.replace(r'[\'\(\)]', '', regex=True).str.strip()

    subIFG_log['sample'] = subIFG_log['sample'].str.extract(r'([^\s\'"]+)'). \
        replace(r'\\\\', r'\\', regex=True)

    subIFG_log['background'] = subIFG_log[
        'background'].str.extract(r'([^\s\'"]+)'). \
        replace(r'\\\\', r'\\', regex=True)


    # import experimental parameters
    exp_params = pd.read_csv(time_dir, header=None, names=[
        'file_directory', 'Date', 'Time', 'PKA', 'NSS'])

    exp_params['file_directory'] = exp_params[
        'file_directory'].apply(lambda x: x.split()[0].strip('"\''))

    exp_params['Time'] = exp_params['Time'].str.strip()

    exp_params['Time'] = exp_params['Time'].apply(add_milliseconds)

    exp_params['DateTime'] = pd.to_datetime(exp_params['Date'] + ' ' + exp_params[
        'Time'], format=' %Y-%m-%d %H:%M:%S.%f', errors='coerce')

    exp_params['DateTime'] = exp_params['DateTime'].fillna(pd.to_datetime(
        exp_params['Time'], format='%H:%M:%S.', errors='coerce'))
    
    # =============================================================================
    # Peak Analyzer
    # =============================================================================

    residuals = []  # THESE LISTS ARE NOT NEEDED. CAN JUST GO GLOBAL
    fit_peak_data = []
    cumulative_data_dict = {}
    baselines = []
    peak_tmp = None

    # 2177, 2168, 2163, 2157 for 114
    # 12CO
    # peakList for NN2031 series
    # peakList_core = [2186, 2175, 2163, 2148, 2136, 2125, 2112, 2100, 2090,
    #                  2080, 2065, 2050, 2038, 2025]

    # peakList for NN2050 series
    # peakList_core = [2206, 2196, 2186, 2175, 2163, 2153, 2123, 2112,
    #                 2100, 2090, 2080, 2065, 2050, 2038, 2025, 1845, 1825]

    # 13CO
    peakList_core = [2156, 2146, 2136, 2125, 2113, 2103, 2073, 2062, 2050,
                 2040, 2030, 2015, 2000, 1988, 1975, 1795, 1775]


    j = 0
    x = arr_subIFG_roi[:, j]
    # baseline_mask = (x < 2100) | (x > 2200)
    delta1_counter = 0
        
    delta_file = file_path.split("_")[-1].split('.')[0]
    opus_iter = file_path.split("_")[-1].split('.')[-1]
    
    # # manually skip files    
    if (delta_file == 'delta1') and (int(opus_iter) > 2):
        return
        delta1_counter += 1 # requires class
        
        if delta1_counter > 2:
            return

    if (delta_file == 'delta2') or (delta_file == 'delta3') or \
            (delta_file == 'delta4'):
        return
        
    params = Parameters()
    y = arr_subIFG_roi[:, j + 1]

    # create baseline and subtract
    # # good for only isolated Pd-CO, fails for agglomeration
    # bsln_asls_1 = pybaselines.whittaker.asls(  # as of 06/28/2024
    #         y, lam=1e7, diff_order=1, p=0.5, tol=1e-6)[0]
    # y_bs_0 = y - bsln_asls_1
    # baseline = np.mean(y_bs_0[baseline_mask])    # center data around y = 0
    # y_bs_1 = y_bs_0 - baseline
    
    # # good for agglomeration 10/01/2024
    bsln_stdDis = pybaselines.classification.std_distribution(y, half_window=10,
                interp_half_window=5, fill_half_window=6, num_std=1.1,
                smooth_half_window=None, weights=None)[0]
    y_bs_1 = y - bsln_stdDis

    baseline_data = {'key': (file_path.split("_")[
        -1]), 'baseline': bsln_stdDis}
    baselines.append(baseline_data)

    # # baseline testing    
    # bsln_test = pybaselines.misc.beads(y, freq_cutoff=0.005, lam_0=1.0,
    #            lam_1=1.0, lam_2=1.0, asymmetry=1.0, filter_type=1,
    #            cost_function=2, max_iter=50, tol=0.01, eps_0=1e-06,
    #            eps_1=1e-06, fit_parabola=True, smooth_half_window=None)[0]

    # bsln_test = pybaselines.classification.dietrich(y, smooth_half_window=None,
    #                 num_std=1.6, interp_half_window=5, poly_order=5,
    #                 max_iter=50, tol=0.001, weights=None, return_coef=False,
    #                 min_length=2)[0]

    # bsln_test = pybaselines.classification.fabc(y, lam=1e6,
    #                 scale=None, num_std=5, diff_order=2, min_length=2,
    #                 weights=None, weights_as_mask=False,)[0]
    
    # bsln_test = pybaselines.whittaker.aspls(y, lam=1e7, diff_order=2,
    #                 max_iter=100, tol=0.001, weights=None, alpha=None)[0]
    
    # bsln_test = pybaselines.polynomial.goldindec(y, poly_order=2, tol=0.001,
    #              max_iter=250, weights=None, cost_function='asymmetric_indec',
    #              peak_ratio=0.5, alpha_factor=0.99, tol_2=0.001, tol_3=1e-06,
    #              max_iter_2=100, return_coef=False)[0]
    
    # y_bs_1 = y - bsln_test
    
    # plt.plot(x, y)
    # plt.plot(x, bsln_test)
    # plt.plot(x, bsln_stdDis)
    # plt.plot(x, y_bs_1)
    # plt.show()
    # j += 1
    # continue

    # # testing peak detection
    # avg_y = np.mean(abs(y_bs_1))
    # peaks_pos, properties = find_peaks(y_bs_1, prominence=0.0003,
    #                                 height=3*avg_y)

    # peak_wavenumbers_pos = df_subIFG_roi['Wavenumber'].values[peaks_pos]
    
    # peaks_neg, properties = find_peaks(-y_bs_1, prominence=0.0003,
    #                                 height=3*avg_y)
    
    # peak_wavenumbers_neg = df_subIFG_roi['Wavenumber'].values[peaks_neg]
    
    # plt.plot(peak_wavenumbers_pos, y_bs_1[peaks_pos], "x")
    # plt.plot(peak_wavenumbers_neg, y_bs_1[peaks_neg], "x")
    # plt.show()
    
    # if len(peaks_pos) == 0 and len(peaks_neg) == 0:
    #     print('skipped: ', file_path)
    #     j += 1
    #     continue
    # j += 1

    # load peaks
    index = (subIFG_log['sample_name'] == file_path.split('\\')[-1]).argmax()

    for fsd, peak_list in fsd_peaks_dict.items():  # remove all this
        if fsd.split('.')[-1] == subIFG_log['sample'][index].split('.')[-1]:
            found_peaks = peak_list
            break

    used_peaks = set()  # Keep track of used peaks to avoid duplicates
    peakList = []

    for predefined_peak in peakList_core:
        closest_peak = predefined_peak
        for found_peak in found_peaks:
            if (np.isclose(float(found_peak), float(predefined_peak), atol=5.0) and 
                found_peak not in used_peaks):
                closest_peak = found_peak
        peakList.append(closest_peak)
        used_peaks.add(closest_peak)

    for peak in found_peaks:
        if (np.isclose(peak, 2169.5, atol=0.5)):
            peak_tmp = peak
            break
        else:
            peak_tmp = None
    
    # add fit parameters and fit
    for i, peak in enumerate(peakList):
        peak_name = peakList_core[i]
        add_params(file_path, params, peak, peak_name)

    fitted_peaks = peak_analysis(
        file_path, params, x)

    # =============================================================================
    # Save fit parameters
    # =============================================================================

    # save peak parameters for each file
    df_fit_peaks = pd.DataFrame(fit_peak_data)
    df_fit_peaks_sorted = df_fit_peaks.sort_values(by=["Peak_Name", "File"])
    filename = f'{file_name}_CarbonylPeakFitParams.csv'
    path = os.path.join(save_dir, filename)
    save_data(new_data=df_fit_peaks_sorted, file_path=path, axis=0)

    # save peak area versus time
    sum_areas_list = []
    df = pd.read_csv(path)
    for (peak_name, delta_group), group in df.groupby([
            'Peak_Name', 'Delta_Group']):

        if delta_group == 'delta1':

            delta1_sum = group[group[
                'Delta_Group'] == 'delta1']['Peak_Area'].iloc[:2].sum()

            delta1_integral = group[group[
                'Delta_Group'] == 'delta1']['Data_Integral'].iloc[:2].sum()

            delta1_time = group[group[
                'Delta_Group'] == 'delta1']['Time_Delta (s)'].iloc[:2].sum()

            cumulative_area = delta1_sum
            cumulative_integral = delta1_integral
            time_sec = delta1_time
            continue
            
        else:
            try:
                cumulative_area = group[group[
                    'Delta_Group'] == 'delta1']['Peak_Area'].iloc[:2].sum()
                # cumulative_area = delta1_sum
                cumulative_integral = group[group[
                'Delta_Group'] == 'delta1']['Data_Integral'].iloc[:2].sum()
                cumulative_integral = delta1_integral
                time_sec = 0
            except Exception as e:
                print(e)

        for index, row in group.iterrows():

            cumulative_area += np.nan_to_num(row['Peak_Area'])
            cumulative_integral += np.nan_to_num(row['Data_Integral'])
            time_sec += row['Time_Delta (s)']

            sum_areas_list.append({
                'File': row['File'],
                'Delta_Group': row['Delta_Group'],
                'Peak_Name': peak_name,
                'Time (s)': time_sec,
                'Cumulative_Peak_Area': cumulative_area,
                'Cumulative_Integral': cumulative_integral
            })

    df_sum_areas = pd.DataFrame(sum_areas_list)
    filename = f'{file_name}_CarbonylPeakArea.csv'
    path = os.path.join(save_dir, filename)
    save_data(new_data=df_sum_areas, file_path=path, axis=1)

    # save peak fit residuals
    dfs = []
    df = pd.DataFrame()
    df['Wavenumber (cm-1)'] = df_subIFG_roi[0]
    df.reset_index(drop=True, inplace=True)

    key = residuals[0]['key']
    value = residuals[0]['residual']
    df_key = pd.DataFrame({key: value})

    # for key, data in cumulative_data_dict.items():
    #     temp_df = pd.DataFrame({
    #         key + '_fit': data['cumulative_fit'],
    #         key + '_residual': data['cumulative_residual'],
    #         key + '_data': data['cumulative_subIFG']
    #     })
    #     dfs.append(temp_df)

    df = pd.concat([df] + [df_key], axis=1)
    filename = f'{file_name}_CarbonylFitResidual.csv'
    path = os.path.join(save_dir, filename)
    save_data(new_data=df, file_path=path, axis=1)

    # save baselines
    df = pd.DataFrame()
    df['Wavenumber (cm-1)'] = df_subIFG_roi[0]
    # dfs = []

    key = baselines[0]['key']
    value = baselines[0]['baseline']
    df_key = pd.DataFrame({key: value})
    df.reset_index(drop=True, inplace=True)

    df = pd.concat([df] + [df_key], axis=1)
    filename = f'{file_name}_CarbonylFitBaseline.csv'
    path = os.path.join(save_dir, filename)
    save_data(new_data=df, file_path=path, axis=1)

def process_file(file_path):
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        print('peak fitting file:\n', file_path)
        executor.submit(voight_fit, file_path)

def main(file_path):
    if os.path.isfile(file_path):
        process_file(file_path)
    else:
        print("Please specify a directory to watch.")

if __name__ == "__main__":
    file_path = r"C:\Data\OpusConvert_subIFG_lgRfl\test\20241230_073902_pd_ceo2_000-012_delta1.0001"
    file_path2 = r"C:\Data\OpusConvert_subIFG_lgRfl\test\20241230_073902_pd_ceo2_000-012_delta1.0002"
    file_path3 = r"C:\Data\OpusConvert_subIFG_lgRfl\test\20241230_073902_pd_ceo2_000-012_delta10.0082"
    main(file_path3)
