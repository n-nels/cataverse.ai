
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

def integrate_msIsoXchg(folder_name, file_name):
    """This function integrates the MS isotopic exchange spectra to find the area under the curve."""
    def polyfunc(x, a, b, c, d):
        return(a + b*x + c*x**2 + d*x**3)
        
    def import_baseline_calibration_data():
        """Import the data from the specified directory."""
        df_mz2928_const = pd.read_csv(dir_mz2928_const)
        df_mz2945_const = pd.read_csv(dir_mz2945_const)
        
        mz2928_high = np.array(df_mz2928_const['poly_coef_high'][:4])
        mz2928_low = np.array(df_mz2928_const['poly_coef_low'][:4])
        mz2945_const = df_mz2945_const['lin_coef'][0]
        
        ddIG_filter = 0.225  # empirically deterimined
        
        return mz2928_high, mz2928_low, mz2945_const, ddIG_filter
    
    def import_isoXchg_data(files_isoX):
        """Import the isotopic exchange data from the specified directory."""
        dict_isoX = {}
        for path in files_isoX:
            key = path
            if 'integrals' in key:
                continue
            
            data = pd.read_csv(path)
            data['Timestamp'] = pd.to_datetime(data['Timestamp'], format='%m/%d/%y %H:%M:%S.%f')
            data['Relative Time (s)'] = (
                data['Timestamp'] -
                data['Timestamp'].iloc[0]).dt.total_seconds()
            data['ddIG'] = data['IG'].diff().diff()
            dict_isoX[key] = data
        
        file_prefix = key.split('\\')[-1].split('.')[0]
        file_prefix = '_'.join(file_prefix.split('_')[:-1]) 
        
        return dict_isoX, file_prefix

    def integrate_isoX_data(dict_isoX, mz2928_high, mz2928_low, mz2945_const, ddIG_filter):
        """Integrate the net m/z=29 data."""
        keys = []
        integral_vals = []
        for key, df in dict_isoX.items():
            mz29_corrected = []
            for index, row in df.iterrows():
                if row['IG'] < 0.7 or pd.isna(row['IG']):
                    value = 0
        
                elif(abs(row['ddIG']) < ddIG_filter):
                    value = row['V1_I_29'] - ((row['V1_I_45'] * mz2945_const) + (
                        row['V1_I_28']*(polyfunc(row['IG'], *mz2928_low))))
        
                elif(abs(row['ddIG']) > ddIG_filter):
                    value = row['V1_I_29'] - ((row['V1_I_45'] * mz2945_const) + (
                            row['V1_I_28']*(polyfunc(row['IG'], *mz2928_high))))
                
                # else:
                #     value = row['V1_I_29'] - ((row['V1_I_45'] * mz2945_const) + (
                #         row['V1_I_28']*(0.011544314814814827)))
                
                mz29_corrected.append(value)
        
            df['mz29_corrected'] = mz29_corrected
        
            keys.append(key)
            integral = trapezoid(df['mz29_corrected'], df['Relative Time (s)'])
            integral_vals.append(integral)
        
        df_output_isoX = pd.DataFrame({
            'keys': keys,
            'integral_vals': integral_vals})
        
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
        filename = f'{file_prefix}_integrals.csv'
        df_output_isoX.to_csv(f"{folder_name}/{filename}", index=False)

    root_dir = 'X:/ms_calibrations/'
    base_calibrations_dir = f"{root_dir}base_calibrations/"
    save_dir = f'{root_dir}{folder_name}'
    
    dir_mz2928_const = f"{base_calibrations_dir}mz2928_matrixCoef.csv" # mz=29/28 matrix constant
    dir_mz2945_const = f"{base_calibrations_dir}mz2945_matrixCoef.csv" # mz=29/45 matrix constant
    
    dir_isoX = f'{folder_name}/{file_name}*'  # isotopic exchange data
    files_isoX = sorted(glob.glob(dir_isoX))

    mz2928_high, mz2928_low, mz2945_const, ddIG_filter = import_baseline_calibration_data()
    dict_isoX, file_prefix = import_isoXchg_data(files_isoX)

    df = integrate_isoX_data(dict_isoX, mz2928_high, mz2928_low, mz2945_const, ddIG_filter)
    save_data(file_prefix, df, folder_name)


if __name__ == "__main__":

    def process_all_integrate_msISoXchg():
        """this is inefficient b/c it loops through each file, but globs them in the function"""
        folder_name = r"X:\ms_calibrations\nn1120-3_pd_ceo2_000"

        for file in os.listdir(folder_name):
            file = "_".join(file.split('_')[:-1])
            integrate_msIsoXchg(folder_name, file)
    
    process_all_integrate_msISoXchg()
