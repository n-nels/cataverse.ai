
import os, time, glob, re, warnings, ast
import ir_peakFit_carbonyl_v5 as fit
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

def integrate_irIsoXchg(file_path):
    """This function integrates the IR isotopic exchange spectra to find the area under the curve."""
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
        return combined_voigt(x, params) - y_bs_1

    def peak_fit():
        minimizer = Minimizer(objective, params)
        result = minimizer.minimize()
        return result

    def add_params(params, peak):

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

    def peak_analysis(file_path, x):

        composite_fit = np.zeros_like(x)
        residual = np.zeros_like(x)

        # fit peaks
        result = peak_fit()
        fitted_params = result.params
        residual = result.residual

        for i, peak in enumerate(peak_list):
            center = fitted_params[f'center_{peak}'].value
            amplitude = fitted_params[f'amplitude_{peak}'].value
            sigma = fitted_params[f'sigma_{peak}'].value
            gamma = fitted_params[f'gamma_{peak}'].value
            y0 = fitted_params[f'y0_{peak}'].value

            y_fit = Model(voigt_model).eval(x=x, y0=y0, center=center,
                                            amplitude=amplitude, sigma=sigma,
                                            gamma=gamma)
            peak_area = -trapezoid(y_fit, x)
            carbonyl_integral = -np.trapezoid(y_bs_1[integral_mask], x[integral_mask])

            fwhm_gaussian = 2*sigma*np.sqrt(2*np.log(2))
            fwhm_lorentz = 2*gamma
            fwhm_voigt = (0.5346*fwhm_lorentz) + np.sqrt((
                0.2166*fwhm_lorentz**2) + fwhm_gaussian**2)

            peak_data = {
                'File': file_path,
                'Peak_Name': f'Peak_{peak}',
                'Peak_Value': peak_list[i],
                'Carbonyl_Integral': carbonyl_integral,
                'Center': center,
                'Amplitude': amplitude,
                'Sigma': sigma,
                'Gamma': gamma,
                'Y0': y0,
                'fwhm': fwhm_voigt,
                'Peak_Area': peak_area
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
            if 'Wavenumber (cm-1)' in existing_data.columns:
                new_data = new_data.drop(columns=['Wavenumber (cm-1)'])
            combined_data = pd.concat([existing_data, new_data], axis=axis, ignore_index=False)
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
        df_subIFG_roi = df_subIFG.loc[(df_subIFG[0] >= 1750) & (
                                        df_subIFG[0] <= 2250)]
        arr_subIFG_roi = df_subIFG_roi.values  # 2050 and 2250 previously

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

        return arr_subIFG_roi, subIFG_log

    def save_peak_parameters():
        # save peak parameters for each file
        df_fit_peaks = pd.DataFrame(fit_peak_data)
        filename = f'{'_'.join(file_name.split('_')[:-1])}_CarbonylPeakFitParams.csv'
        path = os.path.join(dir_save, filename)
        save_data(new_data=df_fit_peaks, file_path=path, axis=0)
        return path

    def save_peak_fit_residual():
        df = pd.DataFrame()
        df['Wavenumber (cm-1)'] = arr_subIFG_roi[:, 0]
        df.reset_index(drop=True, inplace=True)
        df_key = pd.DataFrame({'_'.join(file_path.split("_")[-3:]): residual})

        df = pd.concat([df] + [df_key], axis=1)
        filename = f'{'_'.join(file_name.split('_')[:-1])}_CarbonylFitResidual.csv'
        path = os.path.join(dir_save, filename)
        save_data(new_data=df, file_path=path, axis=1)

    def save_baseline_data():

        df = pd.DataFrame()
        df['Wavenumber (cm-1)'] = arr_subIFG_roi[:, 0]
        df_key = pd.DataFrame({'_'.join(file_path.split("_")[-3:]): bsln_stdDis})
        df.reset_index(drop=True, inplace=True)

        df = pd.concat([df] + [df_key], axis=1)
        filename = f'{'_'.join(file_name.split('_')[:-1])}_CarbonylFitBaseline.csv'
        path = os.path.join(dir_save, filename)
        save_data(new_data=df, file_path=path, axis=1)
    
    def create_baseline(y):
        # create baseline and subtract        
        bsln_stdDis = pybaselines.classification.std_distribution(y, half_window=10,
                    interp_half_window=5, fill_half_window=6, num_std=1.1,
                    smooth_half_window=None, weights=None)[0]
        y_bs_1 = y - bsln_stdDis
        return y_bs_1, bsln_stdDis

    peak_list = [2185, 2175, 2162, 2136, 2126, 2112]

    root_dir = '\\'.join(file_path.split('\\')[:2]) 
    folder_name = file_path.split('\\')[-2]
    file_name = '_'.join((file_path.split('\\')[-1]).split('_')[:-1])

    dir_save = os.path.join(root_dir, 'OpusCalibrations', folder_name)
    subIFG_log_dir = os.path.join(root_dir, 'OpusReadParams', folder_name, f"{file_name}_subIFGfiles.txt")

    arr_subIFG_roi, subIFG_log = import_data()

    x = arr_subIFG_roi[:, 0]
    y = arr_subIFG_roi[:, 1]
    fit_peak_data = []
    integral_mask = (x >= 2095) & (x <= 2130) # important for calibration
    params = Parameters()

    y_bs_1, bsln_stdDis = create_baseline(y)

    # add fit parameters and fit
    for i, peak in enumerate(peak_list):
        add_params(params, peak)

    composite_fit, residual = peak_analysis(file_path, x)

    save_peak_parameters() # need to create directory if saving in opusCalibrations
    save_peak_fit_residual()
    save_baseline_data()

def generate_calibCurve(folder_name, file_name):
    """This function generates a file that contains the integral carbonyl band area
     and the corresponding 13CO moles obtained from ms calibration files."""
    def linfunc(x, a, b):  # for calibration curve
        return a*x + b

    def linfunc_no_intercept(x, a):  # for scalar offset
        return a*x

    def split_keys(key):
        fileid = key.split('\\')[-1].split('.')[0]
        return fileid

    def split_file(file):
        name = file.split('\\')[-1].split('.')[0]
        fileid = '_'.join(name.split('_')[:-1])
        return fileid

    def import_calibration_files():
        # import calibration files
        df_carbonyl_isoX = pd.read_csv(dir_ir)
        df_mz29_isoX = pd.read_csv(dir_ms)

        integrals_file = None
        moles_file = None

        if folder_name == 'nn1120-2_pd_ceo2_000':
            df_mz29_mol13CO = pd.read_csv(dir_msCalib)
        else:
            files = glob.glob(f"{dir_msCalib}/*")
            for file in files:
                if file.endswith('_msCalib_integrals.csv'):
                    integrals_file = file
                elif file.endswith('_msCalib_moles.csv'):
                    moles_file = file
                if integrals_file and moles_file:
                    break
            
            df_integrals = pd.read_csv(integrals_file)
            df_moles = pd.read_csv(moles_file)
            df_mz29_mol13CO = pd.merge(df_integrals, df_moles, on='Filename')
        
        return df_carbonyl_isoX, df_mz29_isoX, df_mz29_mol13CO

    def ms_integral_to_moles()->None:
        # find slope for m/z=29 signal and 13CO moles
        x = df_mz29_mol13CO['integral_vals']
        y = df_mz29_mol13CO['13CO_Moles']
        
        popt, pcov = curve_fit(linfunc_no_intercept, x, y)
        mz29_mol13CO_slope = popt
        
        # convert MS integrals from isotopic exchange to moles
        df_mz29_isoX['co_moles'] = df_mz29_isoX['integral_vals'] * mz29_mol13CO_slope
        return None

    def merge_ms_ir()->tuple:
        # merge IR and MS dataframes on filename
        df = df_carbonyl_isoX[df_carbonyl_isoX['Peak_Name'].isin([
            'Peak_2112', 'Peak_2126', 'Peak_2136'])]
        grouped_df = df.groupby('File').agg({'Carbonyl_Integral': 'first', 'Peak_Area': 'sum'}).reset_index()

        grouped_df['filename'] = grouped_df['File'].apply(split_file)
        df_mz29_isoX['filename'] = df_mz29_isoX['keys'].apply(split_keys)
        
        df_isoX = pd.merge(grouped_df, df_mz29_isoX, on='filename', how='outer')
        df_isoX = df_isoX.fillna(0)

        x_peakArea = -df_isoX['Peak_Area']
        x_carbonylIntegral = -df_isoX['Carbonyl_Integral']
        y = df_isoX['co_moles']
        
        return x_peakArea, x_carbonylIntegral, y, df_isoX

    def stat_params(x, y, popt):
        
        y_pred = linfunc_no_intercept(x, popt[0]) # Calculate the predicted y-values
        std_errors = np.sqrt(np.diag(popt[1])) # Calculate the standard errors of the parameter estimates
        residuals = y - y_pred
        see = np.sqrt(np.mean(residuals**2)) # standard error of the estimate
        ss_tot = np.sum((y - np.mean(y))**2) # total sum of squares
        ss_res = np.sum(residuals**2) # residual sum of squares
        r_squared = 1 - (ss_res / ss_tot) # r-squared
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
    
        return {
            'slope': popt[0],
            'std_errors': std_errors,
            'see': see,
            'r_squared': r_squared,
            'rmse': rmse,
            'y_pred': y_pred,
            }       

    dir_ms_root = 'X:/ms_calibrations/' # ms calibration files
    dir_ir_root = 'C:/Data/OpusCalibrations/' # ir calibration files
    
    dir_ms = f'{dir_ms_root}{folder_name}/{file_name}_integrals.csv'
    dir_ir = f'{dir_ir_root}{folder_name}/{file_name}_CarbonylPeakFitParams.csv'
    dir_msCalib = f"{dir_ms_root}{folder_name}" # mz=29 and 13CO moles relation in 12CO matrix data
    dir_save = f"C:/Data/peakFit/{folder_name}/CalibrationData"
    
    if folder_name == 'nn1120-2_pd_ceo2_000':
        dir_msCalib = (f'{dir_ms_root}base_calibrations/13CO_msCalib_12COmatrix/'
                        'mz29_mol13CO_calibration.csv')
    
    df_carbonyl_isoX, df_mz29_isoX, df_mz29_mol13CO = import_calibration_files()
    ms_integral_to_moles()
    x_peakArea, x_carbonylIntegral, y, df_isoX = merge_ms_ir() 

    popt_peakArea = curve_fit(linfunc_no_intercept, x_peakArea, y)
    popt_carbonylIntegral = curve_fit(linfunc_no_intercept, x_carbonylIntegral, y)

    peakArea_stats = stat_params(x_peakArea, y, popt_peakArea)
    carbonylIntegral_stats = stat_params(x_carbonylIntegral, y, popt_carbonylIntegral)   

    file_prefix = '_'.join(file_name.split('_')[:-1])
    filename = f'{file_prefix}_calibrationCurve.csv'
    path = os.path.join(dir_save, filename)
    df_isoX.to_csv(path, index=False)
    
    print('Peak Area stats:', peakArea_stats)
    print('Carbonyl Integral stats:', carbonylIntegral_stats)

def generate_calibCurve_v2(folder_name):
    """This function generates a file that contains the integral carbonyl band area
     and the corresponding 13CO moles obtained from ms calibration files."""
    def linfunc(x, a, b):  # for calibration curve
        return a*x + b

    def linfunc_no_intercept(x, a):  # for calibration curve
        return  a*x

    def split_keys(key):
        fileid = key.split('\\')[-1].split('.')[0]
        return fileid

    def split_file(file):
        name = file.split('\\')[-1].split('.')[0]
        fileid = '_'.join(name.split('_')[:-1])
        return fileid

    def import_calibration_files():
        files_ir = glob.glob(f"{dir_ir_root}{folder_name}/*_CarbonylPeakFitParams.csv")
        files_ms = glob.glob(f"{dir_ms_root}{folder_name}/*_integrals.csv")
        
        if folder_name == 'nn1120-2_pd_ceo2_000':

            skip_files = ['allData', '000-003', '000-005', '000-007', '000-009', '000-011', '000-013', '000-014',
                        '000-016', '000-017']
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

        #clean data
        df_carbonyl_isoX['Peak_Area'] = df_carbonyl_isoX['Peak_Area'] * -1
        df_carbonyl_isoX['Peak_Area'] = df_carbonyl_isoX['Peak_Area'].mask(
            df_carbonyl_isoX['Peak_Area'] < 0, 0)
        
        df_carbonyl_isoX['Carbonyl_Integral'] = df_carbonyl_isoX['Carbonyl_Integral'] * -1
        df_carbonyl_isoX['Carbonyl_Integral'] = df_carbonyl_isoX['Carbonyl_Integral'].mask(
            df_carbonyl_isoX['Carbonyl_Integral'] < 0, 0)

        integrals_file = None
        moles_file = None

        if folder_name == 'nn1120-2_pd_ceo2_000':
            df_mz29_mol13CO = pd.read_csv(dir_msCalib)
        else:
            files = glob.glob(f"{dir_msCalib}/*")
            for file in files:
                if file.endswith('_msCalib_integrals.csv'):
                    integrals_file = file
                elif file.endswith('_msCalib_moles.csv'):
                    moles_file = file
                if integrals_file and moles_file:
                    break
            
            df_integrals = pd.read_csv(integrals_file)
            df_moles = pd.read_csv(moles_file)
            df_mz29_mol13CO = pd.merge(df_integrals, df_moles, on='Filename')
        
        return df_carbonyl_isoX, df_mz29_isoX, df_mz29_mol13CO

    def ms_integral_to_moles()->None:
        # find slope for m/z=29 signal and 13CO moles
        x = df_mz29_mol13CO['integral_vals']
        try:
            y = df_mz29_mol13CO['13CO_Moles']
        except:
            y = df_mz29_mol13CO['co_moles']
        
        popt, pcov = curve_fit(linfunc_no_intercept, x, y)
        mz29_mol13CO_slope = popt
        
        # convert MS integrals from isotopic exchange to moles
        df_mz29_isoX['co_moles'] = df_mz29_isoX['integral_vals'] * mz29_mol13CO_slope
        return None

    def merge_ms_ir(df_carbonyl_isoX, df_mz29_isoX)->tuple:
        # merge IR and MS dataframes on filename
        df = df_carbonyl_isoX[df_carbonyl_isoX['Peak_Name'].isin([
            'Peak_2112', 'Peak_2126', 'Peak_2136'])]
        df_carbonyl_isoX = df.groupby('File').agg({'Carbonyl_Integral': 'first', 'Peak_Area': 'sum'}).reset_index()

        df_carbonyl_isoX['filename'] = df_carbonyl_isoX['File'].apply(split_file)
        df_mz29_isoX['filename'] = df_mz29_isoX['keys'].dropna().apply(split_keys)
        
        df_isoX = pd.merge(df_carbonyl_isoX, df_mz29_isoX, on='filename', how='outer')
        df_isoX = df_isoX.dropna()

        if folder_name == 'nn1120-2_pd_ceo2_000': # clean data
            mask = (df_isoX['Peak_Area'] >= 0) & (df_isoX['Peak_Area'] <= 0.04) &\
                (df_isoX['co_moles'] >= 0) & (df_isoX['co_moles'] > 2.5e-10) &\
                ~((df_isoX['Peak_Area'] == 0) & (df_isoX['co_moles'] > 1e-9))
            
            df_isoX = df_isoX[mask]

        x_peakArea = df_isoX['Peak_Area']
        x_carbonylIntegral = df_isoX['Carbonyl_Integral']
        y = df_isoX['co_moles']

        popt_peakArea = curve_fit(linfunc, x_peakArea, y)
        popt_carbonylIntegral = curve_fit(linfunc, x_carbonylIntegral, y)

        # scalar offset
        y_peakArea = y - popt_peakArea[0][1]
        y_carbonylIntegral = y - popt_carbonylIntegral[0][1] 
        
        df_isoX['co_moles_paOffset'] = y_peakArea
        df_isoX['co_moles_ciOffset'] = y_carbonylIntegral

        return x_peakArea, x_carbonylIntegral, y_peakArea, y_carbonylIntegral, df_isoX

    def stat_params(x, y, popt):
        
        y_pred = linfunc_no_intercept(x, popt[0]) # Calculate the predicted y-values
        std_errors = np.sqrt(np.diag(popt[1])) # Calculate the standard errors of the parameter estimates
        residuals = y - y_pred
        see = np.sqrt(np.mean(residuals**2)) # standard error of the estimate
        ss_tot = np.sum((y - np.mean(y))**2) # total sum of squares
        ss_res = np.sum(residuals**2) # residual sum of squares
        r_squared = 1 - (ss_res / ss_tot) # r-squared
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
    
        return {
            'slope': popt[0],
            'std_errors': std_errors,
            'see': see,
            'r_squared': r_squared,
            'rmse': rmse,
            'y_pred': y_pred,
            }       

    dir_ms_root = 'X:/ms_calibrations/' # ms calibration files
    dir_ir_root = 'C:/Data/OpusCalibrations/' # ir calibration files
    
    dir_ms = f'{dir_ms_root}{folder_name}/'
    dir_ir = f'{dir_ir_root}{folder_name}/*_CarbonylPeakFitParams.csv'
    dir_msCalib = f"{dir_ms_root}{folder_name}" # mz=29 and 13CO moles relation in 12CO matrix data
    dir_save = f"C:/Data/peakFit/{folder_name}/CalibrationData"
    
    if folder_name == 'nn1120-2_pd_ceo2_000':
        dir_msCalib = (f'{dir_ms_root}base_calibrations/13CO_msCalib_12COmatrix/'
                        'mz29_mol13CO_calibration.csv')
    
    df_carbonyl_isoX, df_mz29_isoX, df_mz29_mol13CO = import_calibration_files()
    ms_integral_to_moles()
    x_peakArea, x_carbonylIntegral, y_peakArea, y_carbonylIntegral, df_isoX = merge_ms_ir(df_carbonyl_isoX, df_mz29_isoX) 

    popt_peakArea = curve_fit(linfunc_no_intercept, x_peakArea, y_peakArea)
    popt_carbonylIntegral = curve_fit(linfunc_no_intercept, x_carbonylIntegral, y_carbonylIntegral)

    peakArea_stats = stat_params(x_peakArea, y_peakArea, popt_peakArea)
    carbonylIntegral_stats = stat_params(x_carbonylIntegral, y_carbonylIntegral, popt_carbonylIntegral) 

    file_prefix = folder_name
    filename = f'{file_prefix}_calibrationCurve.csv'
    path = os.path.join(dir_save, filename)
    df_isoX.to_csv(path, index=False)
    
    print('Peak Area stats:', peakArea_stats)
    print('Carbonyl Integral stats:', carbonylIntegral_stats)


if __name__ == '__main__':
       
    def process_all_integrateIsoX():
        dir_save = r"C:\Data\OpusCalibrations\nn1120-2_pd_ceo2_000"
        file_dir = r"C:\Data\OpusConvert_subIFG_lgRfl\nn1120-2_pd_ceo2_000"

        # List all processed files in dir_save
        processed_files = set("_".join(file_name.split("_")[:-1]) for file_name in os.listdir(dir_save))

        # List all files to process in file_dir
        files_to_process = [
            os.path.join(file_dir, file_name) for file_name in os.listdir(file_dir) if 'isoX' in file_name and os.path.isfile(os.path.join(file_dir, file_name))
            and "_".join(file_name.split("_")[:-2]) not in processed_files]
        
        for file_path in files_to_process:
            integrate_irIsoXchg(file_path)

    # process_all_integrateIsoX()

    # folder_name = 'nn1120-2_pd_ceo2_000'
    # generate_calibCurve_v2(folder_name)




