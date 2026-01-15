# -*- coding: utf-8 -*-
"""
Created on Tue Sep 26 13:04:29 2023

This script converts IR carbonyl peak areas to moles.

@author: nels721
"""

import os, time, glob, re, warnings, ast
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


def linfunc(x, a):  # for calibration curve
    return a*x

def split_keys(key):
    fileid = key.split('\\')[-1].split('.')[0]
    return fileid

def split_file(file):
    name = file.split('\\')[-1].split('.')[0]
    fileid = '_'.join(name.split('_')[:-1])
    return fileid

def create_calibCurve(folder_name, file_name):
    dir_ms_root = 'X:/ms_calibrations/'
    dir_ir_root = 'X:/OpusCalibrations/'
    
    # needs changed
    dir_ms = f'{dir_ms_root}/{folder_name}/{file_name}_integrals.csv'
    dir_ir = f'{dir_ir_root}/{folder_name}/{file_name}_carbonyl_integrals.csv'
    
    dir_baseCalib = (f'{dir_ms_root}base_calibrations/13CO_msCalib_12COmatrix/'
                    'mz29_mol13CO_calibration.csv')
    
    save_dir = 'X:/calibration_files/' # needs changed
    
    # =============================================================================
    # import calibration files
    # =============================================================================
    
    # fitted IR peaks from isotopic exchange
    df_carbonyl_isoX = pd.read_csv(dir_ir)
    
    # integral MS values from isotopic exchange
    df_mz29_isoX = pd.read_csv(dir_ms)
    
    # MS signal calibration for known amounts of 13CO
    df_mz29_mol13CO = pd.read_csv(dir_baseCalib)
    
    # =============================================================================
    # fit calibration files
    # =============================================================================
    
    # find slope for m/z=29 signal and 13CO moles
    x = df_mz29_mol13CO['integral_vals']
    y = df_mz29_mol13CO['co_moles']
    
    popt, pcov = curve_fit(linfunc, x, y)
    mz29_mol13CO_slope = popt
    
    # convert MS integrals from isotopic exchange to moles
    df_mz29_isoX['co_moles'] = df_mz29_isoX['integral_vals'] * mz29_mol13CO_slope
    
    # filter carbonyl bands
    df = df_carbonyl_isoX[df_carbonyl_isoX['Peak_Name'].isin([
        'Peak_2112', 'Peak_2126', 'Peak_2136'])]
    grouped_df = df.groupby('File')['Peak_Area'].sum().reset_index()
    
    # merge IR and MS dataframes on filename
    grouped_df['filename'] = grouped_df['File'].apply(split_file)
    df_mz29_isoX['filename'] = df_mz29_isoX['keys'].apply(split_keys)
    
    df_isoX = pd.merge(grouped_df, df_mz29_isoX, on='filename', how='outer')
    df_isoX = df_isoX.fillna(0)
    
    # find slope for isoX band area and 13CO moles
    x = -df_isoX['Peak_Area']
    y = df_isoX['co_moles']
    
    popt, pcov = curve_fit(linfunc, x, y)
    peakArea_molCO_slope = popt
    
    file_prefix = '_'.join(file_name.split('_')[:-1])
    filename = f'{file_prefix}_calibrationCurve.csv'
    path = os.path.join(save_dir, filename)
    df_isoX.to_csv(path, index=False)
    
    # =============================================================================
    # statistical parameters for M-CO area and CO moles best fit
    # =============================================================================
    
    # Calculate the predicted y-values
    y_pred = linfunc(x, peakArea_molCO_slope)
    
    # Calculate the standard errors of the parameter estimates
    std_errors = np.sqrt(np.diag(pcov))
    
    residuals = y - y_pred
    
    # standard error of the estimate
    see = np.sqrt(np.mean(residuals**2))
    
    # total sum of squares
    ss_tot = np.sum((y - np.mean(y))**2)
    
    # residual sum of squares
    ss_res = np.sum(residuals**2)
    
    # r-squared
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
    
    # sort the data for plot fill
    sort_idx = np.argsort(x)
    x_sorted = x[sort_idx]
    y_sorted = y[sort_idx]
    y_pred_sorted = y_pred[sort_idx]
    y_pred_lower_sorted = y_pred_lower[sort_idx]
    y_pred_upper_sorted = y_pred_upper[sort_idx]
    pred_stderr_sorted = pred_stderr[sort_idx]
    
    
    print('slope:', popt)
    print('Estimated covariance of the slope:', pcov)
    print('Standard error of the slope:', std_errors)
    print('Standard error of the estimate:', see)
    print('r-squared:', r_squared)
    print('rmse is ', rmse)


if __name__ == '__main__':
    pass