# -*- coding: utf-8 -*-
"""
Created on Wed Nov  1 10:54:05 2023

This script deconvolutes the spectrum used to relate IR signal to moles of 
CO adsorbed during isotopic exchange reaction. It outputs a file of the 
peak area integrals.

@author: nels721
"""


import os
import sys
import pandas as pd
import numpy as np
from lmfit import Model
from lmfit import Parameters, Minimizer
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from scipy.special import voigt_profile
from scipy.integrate import trapezoid


def integrate_irIsoXchg(files, folder_name):
    
    def voigt_model(x, y0, amplitude, center, sigma, gamma):
        return y0 + (amplitude * voigt_profile(x - center, sigma, gamma))
    
    def combined_voigt(x, params):
        w = np.zeros_like(x)
        for peak in peak_list:
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
        return combined_voigt(x, params) - y_bs
    
    def peak_fit(file_path):
        minimizer = Minimizer(objective, params)
        result = minimizer.minimize()
        return result
    
    def add_params(file_path, params, peak):
    
        if peak == 2185:
            params.add(f'center_{peak}', value=peak, min=peak - 1,
                        max=peak + 1)
            params.add(f'amplitude_{peak}', value=0.01)
            params.add(f'sigma_{peak}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak}', value=0, min=0, vary=False)
    
        elif peak == 2175:
            params.add(f'center_{peak}', value=peak, min=peak - 1,
                        max=peak + 1)
            params.add(f'amplitude_{peak}', value=0.01)
            params.add(f'sigma_{peak}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak}', value=0, min=0, vary=False)
    
        elif peak == 2162:
            params.add(f'center_{peak}', value=peak, min=peak - 1,
                        max=peak + 1)
            params.add(f'amplitude_{peak}', value=0.01, min=0)
            params.add(f'sigma_{peak}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak}', value=0, min=0, vary=False)
    
        elif peak == 2136:
              params.add(f'center_{peak}', value=peak, min=peak - 1,
                        max=peak + 1)
              params.add(f'amplitude_{peak}', value=0.01)
              params.add(f'sigma_{peak}', value=5, min=2.55, max=6.37)
              params.add(f'gamma_{peak}', value=2, min=0, max=2.8)
              params.add(f'y0_{peak}', value=0, min=0, vary=False)
    
        elif peak == 2126:
            params.add(f'center_{peak}', value=peak, min=peak - 1,
                        max=peak + 1)
            params.add(f'amplitude_{peak}', value=0.01)
            params.add(f'sigma_{peak}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak}', value=0, min=0, vary=False)
    
        elif peak == 2112:
        
            params.add(f'center_{peak}', value=peak, min=peak - 1,
                        max=peak + 1)
            params.add(f'amplitude_{peak}', value=0.01)
            params.add(f'sigma_{peak}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak}', value=0, min=0, vary=False)
    
        return None
    
    def peak_analysis(file_path, params, x, x_plot, peak_list):
    
        # fit peaks
        result = peak_fit(file_path)
        fitted_params = result.params
        residual = result.residual
    
        plt.plot(x, y_bs, '-o', label=(
            f'Spectrum {file_path.split("/")[-1]}'))
        fitted_peaks = np.zeros_like(x_plot)
    
        tmp_file = file_path.split('/')[-1].split('.')[0]
        if tmp_file not in cumulative_data_dict[tmp_file]:
            cumulative_data_dict[tmp_file] = {
                'cumulative_fit': np.zeros_like(x_plot),
                'cumulative_residual': np.zeros_like(x)
                }
    
        for peak in peak_list:
            center = fitted_params[f'center_{peak}'].value
            amplitude = fitted_params[f'amplitude_{peak}'].value
            sigma = fitted_params[f'sigma_{peak}'].value
            gamma = fitted_params[f'gamma_{peak}'].value
            y0 = fitted_params[f'y0_{peak}'].value
    
            y_fit = Model(voigt_model).eval(x=x_plot, y0=y0, center=center,
                                            amplitude=amplitude, sigma=sigma,
                                            gamma=gamma)
            peak_area = -trapezoid(y_fit, x_plot)
            data_integral = -np.trapz(y_bs_integral, x_integral)
            fwhm_gaussian = 2*sigma*np.sqrt(2*np.log(2))
            fwhm_lorentz = 2*gamma
            fwhm_voigt = (0.5346*fwhm_lorentz) + np.sqrt((
                0.2166*fwhm_lorentz**2) + fwhm_gaussian**2)
    
            peak_data = {
                'File': file_path.split("/")[-1],
                'Peak_Name': f'Peak_{peak}',
                'Data_Integral': data_integral,
                'Center': center,
                'Amplitude': amplitude,
                'Sigma': sigma,
                'Gamma': gamma,
                'Y0': y0,
                'fwhm': fwhm_voigt,
                'Peak_Area': peak_area
            }
    
            fit_peak_data.append(peak_data)
            fitted_peaks += y_fit
            plt.plot(x_plot, y_fit)  # , label=f'Fitted Peak {peak}')
    
        residual_data = {'key': (file_path.split("/")[
            -1]), 'residual': residual}
        residuals.append(residual_data)
    
        plt.plot(x_plot, fitted_peaks)  # , label='composite fit')
        plt.plot(x, residual)  # , label='residual')
        # plt.plot(x, baseline_value, label='baseline')
        plt.xlabel('Wavenumber (cm-1)')
        plt.ylabel('Log Reflectance')
        plt.gca().invert_xaxis()
        plt.minorticks_on()
        plt.grid(which='major', linestyle='-', linewidth='0.5', color='black')
        plt.grid(which='minor', linestyle=':', linewidth='0.5', color='gray')
        plt.gca().yaxis.set_minor_locator(plt.MultipleLocator(1))
        plt.legend()
        plt.show()
    
        cumulative_data_dict[file_path.split('/')[-1].split('.')[0]][
            'cumulative_fit'] += fitted_peaks
        cumulative_data_dict[file_path.split('/')[-1].split('.')[0]][
            'cumulative_residual'] += residual
    
        return fitted_peaks

    def save(df, filename):
        path = os.path.join(save_dir, filename)
        df.to_csv(path, index=False)
        path = os.path.join(ms_dir, filename)
        df.to_csv(path, index=False)


    # directories  
    ms_root = 'X:/ms_calibrations/'
    ms_dir = ms_root + folder_name + '_calibration/'
    opus_root = 'X:/OpusConvert_subIFG_lgRfl/'
    opus_dir = opus_root + folder_name +'_COAds/'
    save_dir = ('Z:/')

    
    # import data    
    calib_filepath = []   
    for file in files:
        filename = file
        path = opus_dir + file + '_delta1.0001'
        calib_filepath.append(path)
    
    # import lgRfl data
    df_lgRfl = pd.read_csv(calib_filepath[0], header=None, names=[
        'Wavenumber', calib_filepath[0].split('/')[-1]])
    
    dfs = [df_lgRfl] + [pd.read_csv(path, header=None, usecols=[1], names=[
        path.split('/')[-1]]) for path in calib_filepath[1:]]
    
    df_lgRfl = pd.concat(dfs, axis=1)
    
    df_lgRfl_roi = df_lgRfl.loc[(df_lgRfl['Wavenumber'] >= 2000) & (
                                    df_lgRfl['Wavenumber'] <= 2220)]
    
    arr_lgRfl_roi = df_lgRfl_roi.values

    
    # analyze peaks    
    residuals = []
    fit_peak_data = []
    
    peak_list = [2187, 2175, 2162, 2126, 2112]  #56-98
    peak_list = [2185, 2175, 2162, 2136, 2126, 2112]  # 121-

    cumulative_data_dict = {
        files[i].split('/')[-1].split('.')[0] + '_delta1': {}
        for i in range(len(files))}
    
    j = 0
    x = arr_lgRfl_roi[:, j]
    x_plot = np.linspace(max(x), min(x), int(arr_lgRfl_roi.shape[0]))
    baseline_value = np.zeros_like(x_plot)
    baseline_mask = (x < 2040) | (x > 2200)
    integral_mask = (x >= 2090) & (x <= 2140)
    x_integral = x[integral_mask]
    
    for file in calib_filepath:
    
        y = arr_lgRfl_roi[:, j + 1]
        baseline = np.mean(y[baseline_mask])
        y_bs = y - baseline
        baseline_value.fill(baseline)
    
        y_bs_integral = y_bs[integral_mask]
        params = Parameters()
    
        for peak in peak_list:
            add_params(file, params, peak)
    
        fitted_peaks = peak_analysis(
                    file, params, x, x_plot, peak_list)
    
        j += 1
    

    # save peak parameters for each file
    df_fit_peaks = pd.DataFrame(fit_peak_data)
    df_fit_peaks_sorted = df_fit_peaks.sort_values(by=["Peak_Name", "File"])
    filename = 'carbonyl_isoX_integrals.csv'
    save(df_fit_peaks_sorted, filename)
     
    # save peak fit residuals
    df = pd.DataFrame()
    df['Wavenumber (cm-1)'] = df_lgRfl_roi['Wavenumber']
    residuals_sorted = sorted(residuals, key=lambda x: x['key'])
    
    dfs = []
    for key, data in cumulative_data_dict.items():
    
        temp_df = pd.DataFrame({
            key + '_fit': data['cumulative_fit'],
            key + '_residual': data['cumulative_residual']
        })
    
        dfs.append(temp_df)
    
    df.reset_index(drop=True, inplace=True)
    for df_key in dfs:
        df_key.reset_index(drop=True, inplace=True)
        
    df = pd.concat([df] + dfs, axis=1)

    filename = 'carbonyl_isoX_fitResidual.csv'
    save(df, filename)
       
    # save the raw roi spectra
    filename = 'carbonyl_isoX_rawSpectra.csv'
    save(df_lgRfl_roi, filename)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        files = sys.argv[1]
        folder_name = sys.argv[2]
        integrate_irIsoXchg(files, folder_name)
    else:
        files = [
            '20241106_105710_NN2053_6',
            '20241106_164540_NN2053_7',
            '20241106_213107_NN2053_8',
            '20241107_044819_NN2053_9',
            '20241107_102742_NN2053_10',
            '20241107_163641_NN2053_11',
            '20241107_221613_NN2053_12',
            '20241108_073518_NN2053_13',
            '20241108_131506_NN2053_14',
            '20241108_184900_NN2053_15',
            '20241109_061529_NN2053_16'            
            ] 
        folder_name = 'NN2053_04PdCe'
        integrate_irIsoXchg(files, folder_name)