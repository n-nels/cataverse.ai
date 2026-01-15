# -*- coding: utf-8 -*-
"""
Created on Tue Sep 26 13:04:29 2023

This script converts IR carbonyl peak areas to moles.

@author: nels721
"""

import glob, os, time, re
import pandas as pd
import numpy as np
from datetime import datetime
from scipy.optimize import curve_fit
from scipy.stats import t


def linfunc(x, a, b):
    return a*x + b

def linfunc_no_intercept(x, a):
    return a*x

def split_keys(key):
    name = key.split('\\')[-1].split('.')[0]
    fileid = '_'.join(name.split('_')[2:])
    return fileid

def split_file(file):
    name = '_'.join(file.split('_')[:-1])
    fileid = '_'.join(name.split('_')[2:])
    return fileid

def import_calibration_data():

    dfs= []
    skip_files = ['allData', '000-003', '000-005', '000-007', '000-011', '000-013', '000-014',
                '000-016', '000-017']
    for file in glob.glob(calibration_dir + '*'):
        if any(string in file for string in skip_files):
            continue
        df = pd.read_csv(file)
        dfs.append(df)

    df_calibration_data = pd.concat(dfs, ignore_index=True)

    #clean data
    if folder_name == 'nn1120-2_pd_ceo2_000':
        df_calibration_data['Peak_Area'] = df_calibration_data['Peak_Area'] * -1
        df_calibration_data['Peak_Area'] = df_calibration_data['Peak_Area'].mask(
            df_calibration_data['Peak_Area'] < 0, 0)


        mask = (df_calibration_data['Peak_Area'] >= 0) & (df_calibration_data['Peak_Area'] <= 0.05) &\
                (df_calibration_data['co_moles'] >= 0) & (df_calibration_data['co_moles'] > 2.5e-10) &\
                ~((df_calibration_data['Peak_Area'] == 0) & (df_calibration_data['co_moles'] > 1e-9))
        df_calibration_data = df_calibration_data[mask]

    # find slope between carbonyl area and moles 
    x = df_calibration_data['Peak_Area']
    y = df_calibration_data['co_moles']
    popt, pcov = curve_fit(linfunc, x, y)
    slope, intercept = popt

    df_calibration_data['co_moles'] = df_calibration_data['co_moles'] - intercept
    y = df_calibration_data['co_moles']
    popt, pcov = curve_fit(linfunc_no_intercept, x, y)
    peakArea_moleCarbonyl_slope = popt

    # output calibration data
    output = os.path.join(calibration_dir, folder_name + '_allData.csv')
    df_calibration_data.to_csv(output, index=False)
    return x, y, peakArea_moleCarbonyl_slope, pcov

def calibration_statistics():
    
    y_pred = linfunc_no_intercept(x, peakArea_moleCarbonyl_slope) # predicted y-values
    std_errors = np.sqrt(np.diag(pcov)) # stderr for parameters
    residuals = y - y_pred
    see = np.sqrt(np.mean(residuals**2)) # stderr for estimate
    ss_tot = np.sum(y**2) # total sum of squares when passed through origin
    ss_res = np.sum(residuals**2) # residual sum of squares
    r_squared = 1 - (ss_res / ss_tot)
    rmse = np.sqrt(np.mean(residuals**2))

    # Calculate the critical value for the t-distribution
    dof = len(x) - 2  # degrees of freedom
    confidence_level = 0.975  # for a 95% confidence level
    t_critical = t.ppf(confidence_level, dof)

    # Calculate the standard error
    pred_stderr = see * np.sqrt(1 + 1/len(x) + (
        x - np.mean(x))**2 / np.sum((x - np.mean(x))**2))

    # Calculate the prediction interval
    pred_interval = t_critical * see * np.sqrt(1 + 1/len(x) + (
        x - np.mean(x))**2 / np.sum((x - np.mean(x))**2))

    y_pred_lower = y_pred - pred_interval
    y_pred_upper = y_pred + pred_interval
    
    return see, r_squared


Pd_grams = 0.0365
Pd_moles_per_gram = 3.1824e-06
Pd_moles = Pd_grams * Pd_moles_per_gram

R = 8.3145e-03  # kJ/K-mol
T = 298  # K

# delete later
file_path = r' C:\Data\OpusConvert_subIFG_lgRfl\nn1120-2_pd_ceo2_000\20250206_111432_pd_ceo2_000-028_delta7.0051'

# directories
root_dir = '\\'.join(file_path.split('\\')[:2]) 
folder_name = file_path.split('\\')[-2]
file_name = '_'.join((file_path.split('\\')[-1]).split('_')[:-1])
iterator = file_path.split('.')[-1]
delta_file = file_path.split("_")[-1].split('.')[0]

save_dir = os.path.join(root_dir, 'peakFit', folder_name)
time_dir = os.path.join(root_dir, 'OpusReadParams', folder_name, f"{file_name}.txt")
fsd_dir = os.path.join(root_dir, 'OpusConvert_fsd\\', folder_name, f"{file_name}.{iterator}")
subIFG_log_dir = os.path.join(
        root_dir, 'OpusReadParams', folder_name, f"{file_name}_subIFGfiles.txt")
# need to add this to ir_peakFit_carbonyl_v4.py
calibration_dir = os.path.join('X:\\OpusFiles', folder_name, 'CalibrationData\\')


x, y, peakArea_moleCarbonyl_slope, pcov = import_calibration_data()

see, r_squared = calibration_statistics()

# convert carbonyl area to moles
df_fit_peaks = pd.DataFrame()
df_fit_peaks['PdCO_mol'] = linfunc_no_intercept(df_fit_peaks['Peak_Area'], peakArea_moleCarbonyl_slope)
df_fit_peaks['PdCO_mol_stderr'] = see * np.sqrt(1 + 1/len(x) + (
            df_fit_peaks['Peak_Area'] - np.mean(x))**2 / np.sum((x - np.mean(x))**2))


# sum carbonyl peak moles
sum_PdCO = []
sum_PdCO_stderr = []
sum_theta = []
sum_theta_stderr = []

for (peak_name, delta_group), group in df_fit_peaks.groupby([
        'Peak_Name', 'Delta_Group']):

    if delta_group == 'delta1':

        delta1_PdCO = group['PdCO_mol'].iloc[:2].sum()

        delta1_stderr_sumSqrs = (group[
            'PdCO_mol_stderr'].iloc[:2]**2).sum()

        cumulative_PdCO = delta1_PdCO
        stderr_sumSqrs = delta1_stderr_sumSqrs
        continue

    else:
        cumulative_PdCO = delta1_PdCO
        stderr_sumSqrs = delta1_stderr_sumSqrs

    for index, row in group.iterrows():

        cumulative_PdCO += np.nan_to_num(row['PdCO_mol'])
        sum_PdCO.append(cumulative_PdCO)

        stderr_sumSqrs += np.nan_to_num(row['PdCO_mol_stderr'])**2
        sum_PdCO_stderr.append(np.sqrt(stderr_sumSqrs))



main_pattern = re.compile(
    r"##\s(.*?)\s- Description:.*?Value:\s([^\s]+)", re.DOTALL)

sub_pattern = re.compile(
    r"\*\*(.*?)\*\*.*?Value:\s([^\s]+)", re.DOTALL)

# ExperimentalParamFiles
expParam_files = [
    filename for filename in files if 'README.md' in filename
    ]

expParam_lookup = {
    "_".join(file.split('\\')[-1].split('_')[:-1]): file for file \
        in expParam_files}
    
# CarbonylPeakParams files
cpp_files = [
    filename for filename in files if 'CarbonylPeakFitParams.csv' in filename
    ]

# CarbonylPeakArea files
cpa_files = [
    filename for filename in files if 'CarbonylPeakArea.csv' in filename]

# PressureGuageFiles
pg_files = [
    filename for filename in files if 'PressureData.csv' in filename]

cpa_lookup = {
    "_".join(file.split('\\')[-1].split('_')[:-1]): file for file in cpa_files
    }

for file in cpp_files:  # cpp_files[46:] for >101

    if filename not in file:
        continue

    if '_evac_' in file:
        continue

    expParams = {}
    expParam_id= "_".join(file.split('\\')[-1].split('_')[:-1])

    with open(expParam_lookup[expParam_id], 'r') as params:
        readme = params.read()

    # extract main
    main_matches = main_pattern.findall(readme)
    for match in main_matches:
        heading, value = match
        expParams[heading.strip()] = value.strip()

    p_co = float(expParams['P_cell_CO'])

    df_cpp = pd.read_csv(file)

    df_cpp['PdCO_mol'] = \
        linfunc(df_cpp['Peak_Area'], peakArea_molCO_slope)

    df_cpp['PdCO_mol_stderr'] = see * np.sqrt(1 + 1/len(x) + (
        df_cpp['Peak_Area'] - np.mean(x))**2 / np.sum(
            (x - np.mean(x))**2))   

    sum_PdCO = []
    sum_PdCO_stderr = []
    sum_theta = []
    sum_theta_stderr = []

    for (peak_name, delta_group), group in df_cpp.groupby([
            'Peak_Name', 'Delta_Group']):

        if delta_group == 'delta1':

            delta1_PdCO = group['PdCO_mol'].iloc[:2].sum()

            delta1_stderr_sumSqrs = (group[
                'PdCO_mol_stderr'].iloc[:2]**2).sum()

            cumulative_PdCO = delta1_PdCO
            stderr_sumSqrs = delta1_stderr_sumSqrs
            continue

        else:
            cumulative_PdCO = delta1_PdCO
            stderr_sumSqrs = delta1_stderr_sumSqrs

        for index, row in group.iterrows():

            cumulative_PdCO += np.nan_to_num(row['PdCO_mol'])
            sum_PdCO.append(cumulative_PdCO)

            stderr_sumSqrs += np.nan_to_num(row['PdCO_mol_stderr'])**2
            sum_PdCO_stderr.append(np.sqrt(stderr_sumSqrs))

    # append to CarbonylPeakArea files
    identifier = "_".join(file.split('\\')[-1].split('_')[:-1])
    
    df_cpa = pd.read_csv(cpa_lookup[identifier])

    df_cpa['Cumulative_PdCO_mol'] = pd.DataFrame(sum_PdCO)

    df_cpa['Cumul_PdCO_mol_stderr'] = pd.DataFrame(sum_PdCO_stderr)

    df_cpa['Cumulative_Coverage'] = df_cpa[
        'Cumulative_PdCO_mol'] / Pd_moles

    df_cpa['Cumul_Coverage_stderr'] = df_cpa[
        'Cumul_PdCO_mol_stderr'] / Pd_moles

    df_cpa['Q'] = (df_cpa['Cumulative_PdCO_mol']) / (
        (Pd_moles - df_cpa['Cumulative_PdCO_mol']) * (p_co / 760))

    df_cpa['Q_stderr'] = (df_cpa['Cumul_PdCO_mol_stderr'] / Pd_grams) / (
        Pd_moles_per_gram * (p_co / 760))

    df_cpa['dG (kJ/mol)'] = -R*T*np.log(df_cpa['Q'])

    df_cpa['dG_stderr'] = abs(-R*T / df_cpa['Q'] * df_cpa['Q_stderr'])

    # save files
    df_cpa.to_csv(cpa_lookup[identifier], index=False)
    print('Processed cpa: ', cpa_lookup[identifier])
    
    df_cpp.to_csv(file, index=False)
    print('Processed cpp: ', file)
