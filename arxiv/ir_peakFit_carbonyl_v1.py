import os
import pandas as pd
import numpy as np
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class NewFileHandler(FileSystemEventHandler):
    def __init__(self, folder_to_watch, processed_files_log, output_csv, filename):
        self.folder_to_watch = folder_to_watch
        self.processed_files_log = processed_files_log
        self.output_csv = output_csv
        self.filename = filename

        log_dir = os.path.dirname(processed_files_log)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        self.processed_files = self.load_processed_files()
        self.process_existing_files()

    def load_processed_files(self):
        if os.path.exists(self.processed_files_log):
            with open(self.processed_files_log, 'r') as f:
                return set(f.read().splitlines())
        return set()

    def process_existing_files(self):
        for file_name in os.listdir(self.folder_to_watch):
            file_path = os.path.join(self.folder_to_watch, file_name)
            if self.filename in file_name and file_path not in self.processed_files:
                self.processed_files.add(file_path)
                self.process_file(file_path)
                with open(self.processed_files_log, 'a') as f:
                    f.write(file_path + '\n')

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = event.src_path
        file_name = os.path.basename(file_path)

        if file_path not in self.processed_files:
            self.processed_files.add(file_path)
            self.process_file(file_path)
            with open(self.processed_files_log, 'a') as f:
                f.write(file_path + '\n')

    def process_file(self, file_path):
        # Load the data and fit it using your function
        # Example: fitted_data = fit_peaks_to_data(file_path)
        data = pd.read_csv(file_path)  # Replace with your data loading code
        fitted_data = my_fitting_function(data)  # Replace with your fitting function

        # Append the processed data to the output CSV
        if os.path.exists(self.output_csv):
            fitted_data.to_csv(self.output_csv, mode='a', header=False, index=False)
        else:
            fitted_data.to_csv(self.output_csv, index=False)

def my_fitting_function(data):
    # Replace this with your actual fitting function
    # Return a DataFrame with the fitting results
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

        if (peak <= 2211) and (peak >= 2201):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01, min=0)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)     

        elif (peak < 2201) and (peak >= 2191):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)    

        elif (peak < 2191) and (peak >= 2180):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2180) and (peak >= 2170):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2170) and (peak >= 2158):  # previously 2156.5

            if peak_tmp is None:

                params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                        max=peak + 1)
                params.add(f'amplitude_{peak_name}', value=0.01)
                params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
                params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
                params.add(f'y0_{peak_name}', value=0, min=0, vary=False)
            
            elif peak_tmp is None and peak == 2163 and \
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


        elif (peak < 2158) and (peak >= 2148):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2148) and (peak >= 2138):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=-0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2138) and (peak >= 2128):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2128) and (peak >= 2118):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2117) and (peak >= 2107):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2105) and (peak >= 2095):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2095) and (peak >= 2085):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2085) and (peak >= 2075):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2070) and (peak >= 2060):
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

        elif (peak < 2043) and (peak >= 2033):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 2030) and (peak >= 2020):
            params.add(f'center_{peak_name}', value=peak, min=peak - 1,
                    max=peak + 1)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=6.37)
            params.add(f'gamma_{peak_name}', value=2, min=0, max=2.8)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 1850) and (peak >= 1840):
            params.add(f'center_{peak_name}', value=peak, min=peak - 5,
                    max=peak + 5)
            params.add(f'amplitude_{peak_name}', value=0.01)
            params.add(f'sigma_{peak_name}', value=5, min=2.55, max=26)
            params.add(f'gamma_{peak_name}', value=2, min=0)
            params.add(f'y0_{peak_name}', value=0, min=0, vary=False)

        elif (peak < 1830) and (peak >= 1820):
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

    def peak_analysis(file_path, params, x, x_plot):

        fitted_peaks = np.zeros_like(x_plot)

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
                'cumulative_fit': np.zeros_like(x_plot),
                'cumulative_residual': np.zeros_like(x),
                'cumulative_subIFG': np.zeros_like(x_plot)
                }

        # skip fitting if criteria not met
        avg_y = np.mean(abs(y_bs_1))

        peaks_pos, properties = find_peaks(y_bs_1, prominence=0.0003,
                                        height=3*avg_y)
        peak_wavenumbers_pos = df_subIFG_roi['Wavenumber'].values[peaks_pos]
        
        peaks_neg, properties = find_peaks(-y_bs_1, prominence=0.0003,
                                        height=3*avg_y)
        peak_wavenumbers_neg = df_subIFG_roi['Wavenumber'].values[peaks_neg]

        if len(peaks_pos) == 0 and len(peaks_neg) == 0:
            print('skipped: ', file_path)

            x_pos = x[y_bs_1 >= 0]
            y_bs_1_pos = y_bs_1[y_bs_1 >= 0]
            x_neg = x[y_bs_1 < 0]
            y_bs_1_neg = y_bs_1[y_bs_1 < 0]

            integral_pos = -np.trapz(y_bs_1_pos, x_pos)
            integral_neg = -np.trapz(y_bs_1_neg, x_neg)
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

            # cumulative_data_dict[delta_group][
            #     'cumulative_fit'] += fitted_peaks

            # cumulative_data_dict[delta_group][
            #     'cumulative_subIFG'] += y_bs_1

            return fitted_peaks

        else:

            # fit peaks
            result = peak_fit(file_path)
            fitted_params = result.params
            residual = result.residual

            # report_filename = 'fit_report.txt'
            # with open(report_filename, 'w') as report_file:
            #     print(fit_report(result), file=report_file)

            plt.plot(x, y_bs_1, '-o', label=(
                f'Spectrum {file_path.split("_")[-1]}'))
            plt.plot(peak_wavenumbers_pos, y_bs_1[peaks_pos], "x")
            plt.plot(peak_wavenumbers_neg, y_bs_1[peaks_neg], "x")

            for i, peak in enumerate(peakList_core):
                center = fitted_params[f'center_{peak}'].value
                amplitude = fitted_params[f'amplitude_{peak}'].value
                sigma = fitted_params[f'sigma_{peak}'].value
                gamma = fitted_params[f'gamma_{peak}'].value
                y0 = fitted_params[f'y0_{peak}'].value

                y_fit = Model(voigt_model).eval(x=x_plot, y0=y0, center=center,
                                                amplitude=amplitude, sigma=sigma,
                                                gamma=gamma)

                peak_area = -trapz(y_fit, x_plot)

                x_pos = x[y_bs_1 >= 0]
                y_bs_1_pos = y_bs_1[y_bs_1 >= 0]
                x_neg = x[y_bs_1 < 0]
                y_bs_1_neg = y_bs_1[y_bs_1 < 0]

                integral_pos = -np.trapz(y_bs_1_pos, x_pos)
                integral_neg = -np.trapz(y_bs_1_neg, x_neg)
                data_integral = integral_pos + integral_neg
                # data_integral = -np.trapz(y_bs_1, x)

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
                plt.plot(x_plot, y_fit)  # , label=f'Fitted Peak {peak}')

            residual_data = {'key': (file_path.split("_")[
                -1]), 'residual': residual}
            residuals.append(residual_data)

            plt.plot(x_plot, fitted_peaks)  # , label='composite fit')
            plt.plot(x, residual)  # , label='residual')
            # plt.plot(x, bsln_asls_1, label='baseline')
            plt.xlabel('Wavenumber (cm-1)')
            plt.ylabel('log(Reflectance)')
            plt.gca().invert_xaxis()
            plt.minorticks_on()
            plt.grid(which='major', linestyle='-', linewidth='0.5', color='black')
            plt.grid(which='minor', linestyle=':', linewidth='0.5', color='gray')
            plt.gca().yaxis.set_minor_locator(plt.MultipleLocator(1))
            plt.legend()
            plt.show()

            cumulative_data_dict[delta_group][
                'cumulative_fit'] += fitted_peaks
            cumulative_data_dict[delta_group][
                'cumulative_residual'] += residual
            cumulative_data_dict[delta_group][
                'cumulative_subIFG'] += y_bs_1

            return fitted_peaks
    
    # =============================================================================
    # Import data
    # ============================================================================

    time_filename = opus_filename + '.txt'

    subIFG_filename = opus_filename + '_subIFGfiles.txt'

    time_dir = (root_dir + 'OpusReadParams/' + folder_name + time_filename)

    # save_dir = ('//PNL/Projects/LDRD2023_Nelson/')

    save_dir = 'Z:/'

    fsd_dir = (root_dir + 'OpusConvert_fsd/' + folder_name + opus_filename + '.*')

    subIFG_log_dir = (root_dir + 'OpusReadParams/' + folder_name + subIFG_filename)

    subIFG_dir = (root_dir + 'OpusConvert_subIFG_lgRfl/' + folder_name +
                opus_filename + '_*')

    lgRfl_dir = (root_dir + 'OpusConvert_lgRfl/' + folder_name
                + opus_filename + '.*')

    subIFG_files = glob.glob(subIFG_dir)
    subIFG_files.sort()

    lgRfl_files = glob.glob(lgRfl_dir)
    lgRfl_files.sort()

    fsd_files = glob.glob(fsd_dir)
    fsd_files.sort()


    # import lgRfl data
    df_lgRfl = pd.read_csv(lgRfl_files[0], header=None, names=[
        'Wavenumber', '.' + lgRfl_files[0].split('.')[-1]])

    dfs = [df_lgRfl] + [pd.read_csv(file, header=None, usecols=[1], names=[
        '.' + file.split('.')[-1]]) for file in lgRfl_files[1:]]

    df_lgRfl = pd.concat(dfs, axis=1)
    arr_lgRfl = df_lgRfl.values

    df_lgRfl_roi = df_lgRfl.loc[(df_lgRfl['Wavenumber'] >= 1750) & (
                                    df_lgRfl['Wavenumber'] <= 2250)]

    arr_lgRfl_roi = df_lgRfl_roi.values


    # import subIFG data
    df_subIFG = pd.read_csv(subIFG_files[0], header=None,
                            names=['Wavenumber', subIFG_files[0].split('_')[-1]])
    dfs = [df_subIFG] + [pd.read_csv(file, header=None,
                                    usecols=[1], names=[file.split('_')[-1]])
                        for file in subIFG_files[1:]]
    df_subIFG = pd.concat(dfs, axis=1)
    arr_subIFG = df_subIFG.values
    df_subIFG_roi = df_subIFG.loc[(df_subIFG['Wavenumber'] >= 1750) & (
                                    df_subIFG['Wavenumber'] <= 2250)]
    arr_subIFG_roi = df_subIFG_roi.values  # 2050 and 2250 previously


    # import fsd data
    df_fsd = pd.read_csv(fsd_files[0], header=None, names=[
        'Wavenumber', '.' + fsd_files[0].split('.')[-1]])

    dfs = [df_fsd] + [pd.read_csv(file, header=None, usecols=[1], names=[
        '.' + file.split('.')[-1]]) for file in fsd_files[1:]]

    df_fsd = pd.concat(dfs, axis=1)
    arr_fsd = df_fsd.values

    df_fsd_roi = df_fsd.loc[(df_fsd['Wavenumber'] >= 1750) & (
                                    df_fsd['Wavenumber'] <= 2250)]

    arr_fsd_roi = df_fsd_roi.values


    # find fsd peaks
    x = arr_fsd_roi[:, 0]
    fsd_mask = x < 2100
    fsd_peaks_list = []

    for fsd in arr_fsd_roi[:, 1:].T:

        fsd_baseline = np.mean(fsd[fsd_mask])
        fsd_bs = fsd - fsd_baseline

        peaks, properties = find_peaks(fsd_bs, prominence=0.0001,
                                    height=0.003)
        peak_wavenumbers = df_fsd_roi['Wavenumber'].values[peaks]

        fsd_peaks_list.append(peak_wavenumbers)

        # print("Peaks are at indices:", peaks)
        # print("Peaks are at:", peak_wavenumbers)
        # print("Peak properties:", properties)
        # plt.plot(df_fsd_roi["Wavenumber"], fsd)
        # plt.plot(peak_wavenumbers, fsd[peaks], "x")
        # plt.show()

    # find average peak values
    avg_arr_length = round(
        sum(len(array) for array in fsd_peaks_list) / (len(fsd_peaks_list)))

    filtered_arrs = [
        array for array in fsd_peaks_list if len(array) == avg_arr_length
        ]

    stack_arrs = np.vstack(filtered_arrs)
    avg_fsd = np.mean(stack_arrs, axis=0)

    fsd_peaks_dict = {
        file: fsd_peaks_list[i] for i, file in enumerate(fsd_files)
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

    residuals = []
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
    peakList_core = [2206, 2196, 2186, 2175, 2163, 2153, 2123, 2112,
                    2100, 2090, 2080, 2065, 2050, 2038, 2025, 1845, 1825]


    j = 0
    x = arr_subIFG_roi[:, j]
    x_plot = np.linspace(max(x), min(x), int(arr_subIFG_roi.shape[0]))
    # baseline_mask = (x < 2100) | (x > 2200)
    delta1_counter = 0
    peakList_prev = []

    for file_path in subIFG_files:
        
        delta_file = file_path.split("_")[-1].split('.')[0]
        
        # # manually skip files    
        if (delta_file == 'delta1'):

            delta1_counter += 1
            
            if delta1_counter > 2:
                j += 1
                continue
        
        # if (delta_file != 'delta10') and (delta_file != 'delta1'):
        #     j += 1
        #     continue

        if (delta_file == 'delta2') or (delta_file == 'delta3') or \
                (delta_file == 'delta4'):
            j += 1
            continue
            
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

        for fsd, peak_list in fsd_peaks_dict.items():
            if fsd.split('.')[-1] == subIFG_log['sample'][index].split('.')[-1]:
                found_peaks = peak_list
                break

        used_peaks = set()  # Keep track of used peaks to avoid duplicates
        peakList = []

        for predefined_peak in peakList_core:

            closest_peak = next(
                (found_peak for found_peak in found_peaks 
                if np.isclose(found_peak, predefined_peak, atol=5.0) and 
                found_peak not in used_peaks), predefined_peak)

            peakList.append(closest_peak)
            used_peaks.add(closest_peak)

        for peak in found_peaks:
            if (np.isclose(peak, 2169.5, atol=0.5)):
                peak_tmp = peak
                break
            else:
                peak_tmp = None
        
        # for i, peak in enumerate(peakList):
        #     if len(peakList_prev) == 0:
        #         break
        #     elif peak == peakList_core[i]:
        #         peakList[i] = peakList_prev[i]

        # add fit parameters and fit
        for i, peak in enumerate(peakList):
            peak_name = peakList_core[i]
            add_params(file_path, params, peak, peak_name)

        fitted_peaks = peak_analysis(
            file_path, params, x, x_plot)
        
        peakList_prev = peakList

        j += 1

    # =============================================================================
    # Save fit parameters
    # =============================================================================

    # save peak parameters for each file
    df_fit_peaks = pd.DataFrame(fit_peak_data)
    df_fit_peaks_sorted = df_fit_peaks.sort_values(by=["Peak_Name", "File"])
    base_filename = os.path.splitext(os.path.basename(subIFG_dir)[:-2])[0]
    filename = f'{base_filename}_CarbonylPeakFitParams.csv'
    path = os.path.join(save_dir, filename)
    df_fit_peaks_sorted.to_csv(path, index=False)


    # save peak area versus time
    sum_areas_list = []
    for (peak_name, delta_group), group in df_fit_peaks_sorted.groupby([
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
            cumulative_area = delta1_sum
            cumulative_integral = delta1_integral
            time_sec = 0

        for index, row in group.iterrows():

            # if abs(row['Peak_Area']) < 0.004:

            #     cumulative_area += 0
            #     cumulative_integral += np.nan_to_num(row['Data_Integral'])
            #     time_sec += row['Time_Delta (s)']

            # else:
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
    filename = f'{base_filename}_CarbonylPeakArea.csv'
    path = os.path.join(save_dir, filename)
    df_sum_areas.to_csv(path, index=False)


    # save peak fit residuals
    filename = f'{base_filename}_CarbonylFitResidual.csv'
    path = os.path.join(save_dir, filename)
    df = pd.DataFrame()
    df['Wavenumber (cm-1)'] = df_subIFG_roi['Wavenumber']
    residuals_sorted = sorted(residuals, key=lambda x: x['key'])

    dfs = []
    for data in residuals_sorted:
        key = data['key']
        value = data['residual']
        df_key = pd.DataFrame({key: value})
        dfs.append(df_key)

    df.reset_index(drop=True, inplace=True)
    for df_key in dfs:
        df_key.reset_index(drop=True, inplace=True)

    for key, data in cumulative_data_dict.items():

        temp_df = pd.DataFrame({
            key + '_fit': data['cumulative_fit'],
            key + '_residual': data['cumulative_residual'],
            key + '_data': data['cumulative_subIFG']
        })

        dfs.append(temp_df)

    df = pd.concat([df] + dfs, axis=1)
    df.to_csv(path, index=False)


    # save baselines
    filename = f'{base_filename}_CarbonylFitBaseline.csv'
    path = os.path.join(save_dir, filename)
    df = pd.DataFrame()
    df['Wavenumber (cm-1)'] = df_subIFG_roi['Wavenumber']
    baselines_sorted = sorted(baselines, key=lambda x: x['key'])

    dfs = []
    for data in baselines_sorted:
        key = data['key']
        value = data['baseline']
        df_key = pd.DataFrame({key: value})
        dfs.append(df_key)

    df.reset_index(drop=True, inplace=True)
    for df_key in dfs:
        df_key.reset_index(drop=True, inplace=True)
    df = pd.concat([df] + dfs, axis=1)
    df.to_csv(path, index=False)


    # save the raw roi spectra
    filename = f'{base_filename}_CarbonylSpectra_raw.csv'
    path = os.path.join(save_dir, filename)
    df_lgRfl_roi.to_csv(path, index=False)


    # save the subIFG spectra that were used to fit
    filename = f'{base_filename}_CarbonylSpectra_subIFG.csv'
    path = os.path.join(save_dir, filename)
    df_subIFG_roi.to_csv(path, index=False)

    # save the raw spectra
    filename = f'{base_filename}_FullSpectra_raw.csv'
    path = os.path.join(save_dir, filename)
    df_lgRfl.to_csv(path, index=False)
    return data

if __name__ == "__main__":
    folder_to_watch = r"C:\Data\OpusConvert_lgRfl\test"
    log_directory = r"C:\Data\OpusConvert_lgRfl\test"
    processed_files_log = os.path.join(log_directory, "processed_files.log")
    output_csv = "fitted_data.csv"
    filename = 'huh.txt'

    event_handler = NewFileHandler(folder_to_watch, processed_files_log, output_csv, filename)
    observer = Observer()
    observer.schedule(event_handler, folder_to_watch, recursive=False)
    observer.start()

    try:
        while True:
            pass
    except KeyboardInterrupt:
        observer.stop()
    observer.join()