
import os
import time
import subprocess
from datetime import datetime, timedelta


def CheckInstrumentStatus():
    result = PipeCommand('DIAG_STATUS', 1)
    arr = result.split(chr(10))
    if (arr[0] == 'OK'):
        number = int(arr[1])
        if (number == -1):
            print("No instrument connected. Check 'Measure/Setup optics and services'.\n")
            return False
        if (number == 1):
            print("Instrument warnings present. Nevertheless measurements are possible.\n")
            return True
        if (number == 2):
            print("Instrument errors present. Measurement not possible.\n")
            return False
        if (number == 0):
            print("Connectin to instrument is OK.\n")
            return True
    print("DIAG_STATUS was not successful.\n")
    return False

def Deconvolute(file):
    arr = PipeCommand("COMMAND_LINE Deconvolution([" + file + ":lgRefl], {"
                      "DEE=1800, DES=2220, DSP='LO', DWR=0, DNR=0.5, DEF=876719.515768})", 0).split(chr(10))

def DoBackgroundMeasurement(do_bckg):
    if (do_bckg == 0):
        arr = PipeCommand('TAKE_REFERENCE ' + XpmPath + '\\' + XpmName, 3).split(chr(10))
        return True
    else:
        return False

def DoSampleMeasurement(addParams): # Default NSS=256
    
    arr = PipeCommand("COMMAND_LINE MeasureSample (, {EXP='" + XpmName + "', "
                        "XPP='" + XpmPath + "', NAM='" + FileName + "." + n + "',"
                        "SNM='" + SampleName + "',"
                        "PTH='" + path_OpusFiles + "'" + addParams + "});", 1
                        ).split(chr(10))
    return arr[2]

def DoSampleMeasurement_nss(nss_values, m, n):
    file_list = []
    for nss_value in nss_values:
        add_params = f', NSS={nss_value}'
        arr = PipeCommand("COMMAND_LINE MeasureSample (, {EXP='" + XpmName + "', "
                                    "XPP='" + XpmPath + "', NAM='" + FileName + "." + n + "',"
                                    "SNM='" + SampleName + "',"
                                    "PTH='" + path_OpusFiles + "'" + add_params + "});", 1
                                    ).split(chr(10))
        file_list.append(arr[2])
        m += 1
        n = str(m).zfill(4)
    return file_list

def GetExperimentPath():
    arr = PipeCommand('GET_OPUSPATH', 1).split(chr(10))
    if (arr[0] == 'OK'):
        return arr[1] + '\\XPM'
    return ''

def GetVersion():
    return (PipeCommand('GET_VERSION_EXTENDED', 3) != "")

def LoadFile(file):
    arr = PipeCommand("LOAD_FILE" + file, 0).split(chr(10))

def OpenOpus():
    import subprocess, time

    # Replace 'path_to_opus.exe' with the actual path to the OPUS executable
    opus_exe_path = 'C:\\Program Files\\Bruker\\OPUS_8.7.10\\Opus.exe /LANGUAGE=ENGLISH /OPUSPIPE=ON /DIRECTLOGINPASSWORD=Admin@OPUS'

    try:
        # Attempt to open OPUS
        process = subprocess.Popen(opus_exe_path)
        time.sleep(10)
    except FileNotFoundError:
        print("OPUS executable not found. Please provide the correct path.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")

def PipeCommand(cmd, show):
    if (show == -1) : show = DefaultPrintout
    # print out the command or not and show the result
    if (show & 1) : print (cmd)
    hPipe.write(bytes(cmd + '\r\n', 'utf-8'))
    data = hPipe.read(1000)
    Mystr = data.decode('utf-8')
    total = Mystr
    if show & 2: print (total, '\n')
    return total

def ReadParameter(file, block, name):
    arr = PipeCommand("FILE_PARAMETERS", 0).split(chr(10))
    if (arr[0] == 'OK'):
        arr = PipeCommand("READ_FROM_FILE " + file, 0).split(chr(10))
        # print('read_from_file arr is', '\n', arr)
        if (arr[0] == 'OK'):
            arr = PipeCommand("READ_FROM_BLOCK " + block, 0).split(chr(10))
            # print("read_from_block arr is", '\n', arr)
            if (arr[0] == 'OK'):
                arr = PipeCommand("READ_PARAMETER " + name, 0).split(chr(10))
                # print('read_paramater arr is', '\n', arr)
                if (arr[0] == 'OK'):
                    return arr[1]
    else:
        print("Reading parameter" + name + "failed")

def ReadMultipleParameters(file, block, name):
    arr = PipeCommand("READ_FROM_FILE " + file, 0).split(chr(10))
    if (arr[0] == 'OK'):
        arr = PipeCommand("READ_FROM_BLOCK " + block, 0).split(chr(10))
        if (arr[0] == 'OK'):
            arr = PipeCommand("READ_MULTIPLE_PARAMETERS " + name, 0).split(chr(10))
            if (arr[0] == 'OK'):
                return arr
    else:
        print("Reading parameter" + name + "failed")

def SaveAs(file, name, path):
    arr = PipeCommand("COMMAND_LINE SaveAs ([" + file + ":lgRefl], {DAP='" + path + "',"
                        "SAN='" + name + "', SEP=',', DPA=8, DPO=8,"
                        "ADP='1', YON='0', OEX='0', X64='1'});", 0).split(chr(10))
    # if(arr[0] == 'OK'):
    #    print("Save lgRfl successful")
    # else:
    #     print("Save lgRfl failed")

def SaveAs_ScSm(file, name):
    arr = PipeCommand("COMMAND_LINE SaveAs ([" + file + ":ScSm], {DAP='" + path_ScSm + "',"
                        "SAN='" + name + "', SEP=',', DPA=8, DPO=8,"
                        "ADP='1', YON='0', OEX='0', X64='1'});", 0).split(chr(10))
    # if(arr[0] == 'OK'):
    #    print("Save single channel successful")
    # else:
    #     print("Save single channel failed")

def SaveAs_subIFG(file, name):
    arr = PipeCommand("COMMAND_LINE SaveAs ([" + file + ":lgRefl], {DAP='" + path_subIFG + "',"
                    "SAN='" + name + "', SEP=',', DPA=8, DPO=8,"
                    "ADP='1', YON='0', OEX='0', X64='1'})", 0).split(chr(10))
    # if(arr[0] == 'OK'):
    #     print("Save subtracted interoferrogram successful.")
    # else:
    #     print("Save subtracted interoferrogram failed.")

def SpectrumFromInterferogram(meas, bckg):
    arr = PipeCommand("COMMAND_LINE SpecFromIfgs ([" + meas + ":IgSm], [" + bckg + ":IgSm], {"
                        "PPF='LRF', CPF=0})", 0).split(chr(10))

def Subtract_ifg(files):

    global processed_files

    subIFG_files = os.path.join(path_readParams, FileName + '_subIFGfiles.txt')
    if len(files) <= 1:
        processed_files = set()
        return
            
    sub_ifg_list = []
    for w in range(2, min(len(files) + 1, 12)):
        for a in range(len(nss_vals)):
            SpectrumFromInterferogram(files[-1][a], files[-w][a])
            name = f"{files[-1][a].split('\\')[-1][:-8]}_sub{w-1}.{
                        files[-1][a].split('.')[-1][:-3]}" #yymmddd_hhmmss_name_sub(subtractionInterval).wxyz
            sub_ifg_list.append((name, files[-1][a], files[-w][a]))
            SaveAs(files[-1][a], name, path_subIFG)
            UnloadFile(files[-1][a])
            LoadFile(files[-1][a].split('"')[1])
    # for step in range(1, 11):
    #     for i in range(step, len(files), step):
    #         pair = (files[i], files[i - step])

    #         if pair not in processed_files:
    #             # file_pair = tuple(pair)
    #             file_ids = list(pair)
    #             print(file_ids)
    #             print(file_ids[0])
    #             print(file_ids[1])
    #             sub_ifg_list = []
                
    #             # for spectrum in pair:
    #             #     file_id = LoadFile(spectrum)
    #             #     file_ids.append(file_id)   
                
    #             SpectrumFromInterferogram(file_ids[0], file_ids[1])            
    #             name = f"{file_ids[0].split('\\')[-1][:-8]}_delta{step}.{
    #                         file_ids[0].split('.')[-1][:-3]}"
    #             sub_ifg_list.append((name, files[i], files[i - step]))
    #             SaveAs(file_ids[0], name, path_subIFG)
                
    #             for file in file_ids:
    #                 UnloadFile(file)
    #             processed_files.add(pair)

    #             with open(subIFG_files, 'a') as txtFile:
    #                 for z in sub_ifg_list:
    #                     txtFile.write(f'{z}\n')

        
    with open(subIFG_files, 'a') as list:
        for z in sub_ifg_list:
            list.write(f'{z}\n')

def UnloadFile(file):
    arr = PipeCommand("COMMAND_LINE Unload([" + file + ":Spec], {})", 0).split(chr(10))

def main(sample_name, folder_name):
    print("\nStart of program...")
    
    global hPipe
    global DefaultPrintout
    global XpmPath
    global XpmName
    global SampleName
    global path_OpusFiles
    global path_lgRfl
    global path_subIFG
    global path_ScSm
    global path_fsd
    global FileName
    global path_readParams
    global path_cloud
    global n  # opus iterator

    # Defining globals
    XpmName = 'ncnels_v2.xpm'
    DefaultPrintout = 3 # set bit to 1, 2, or 3 to print out pipe commands, return strings, or both
    hPipe = open(r'\\.\pipe\OPUS', 'r+b', 0)
    SampleName = sample_name
    path_OpusFiles = "C:\\Data\\OpusFiles\\" + folder_name
    path_lgRfl = "C:\\Data\\OpusConvert_lgRfl\\" + folder_name
    path_subIFG = "C:\\Data\\OpusConvert_subIFG_lgRfl\\" + folder_name
    path_ScSm = "C:\\Data\\OpusConvert_SSC\\" + folder_name
    path_fsd = "C:\\Data\\OpusConvert_fsd\\" + folder_name
    path_readParams = "C:\\Data\\OpusReadParams"
    path_cloud = r"C:\sftp\copybutton.bat"

    # Check connection
    if (GetVersion() == False):
        # print("Attempting to open opus")
        # OpenOpus()
        # if (GetVersion() == False):
        print("Pipe connection failed.")
    
    # Check if OPUS is connected to an instrument
    if (CheckInstrumentStatus() == False): return

    # Read OPUS path from workspace
    XpmPath = GetExperimentPath()
    if (XpmPath == ''):
        print("Error on trying to evaluate the OPUS path.")
        return
    else:
        print("Ensure you have an experiment file defined in:\n" + XpmPath)
        print("The experiment file must have the name " + XpmName + ".\n")

    # Collect background
    if (DoBackgroundMeasurement(do_bckg) == False):
        print("Background measurement not taken.\n")
    else:
        print("Background measurement successfully performed.\n")

    # Check if directories exist
    paths = [path_ScSm, path_lgRfl, path_OpusFiles, path_readParams, path_subIFG, path_fsd]
    for path in paths:
        if not os.path.exists(path):
            os.makedirs(path)

    # Define filename
    now = datetime.now()
    formatted_time = now.strftime("%Y%m%d_%H%M%S")
    FileName = formatted_time + "_" + SampleName

    # Create experimental parameter files
    read_params = os.path.join(path_readParams, FileName + '.txt')
    # exp_params = os.path.join(path_OpusFiles, FileName + '.txt')
    # with open(exp_params, 'w') as file:
    #     for d, r in zip(delay, repeat):
    #         file.write(f'{d},{r}\n')

    # Collect spectra
    j = 0
    m = 0
    all_fileids = []
    for i in range(len(delay)):
        for k in range(repeat[j]):
            
            n = str(m).zfill(4)
            now = datetime.now()
            fileids = DoSampleMeasurement_nss(nss_vals, m, n)
            all_fileids.append(fileids)
            # Subtract_ifg(all_fileids)

            dat_list = []
            tim_list = []
            pka_list = []
            nss_list = []

            for fileid in fileids:
                
                file_name = fileid.split('\\')[-1][:-3]
                SaveAs(fileid, file_name, path_lgRfl)            
                SaveAs(fileid, file_name, path_ScSm)
                Deconvolute(fileid)
                SaveAs(fileid, file_name, path_fsd)
                UnloadFile(fileid)
                LoadFile(fileid.split('"')[1])

                instParams = ReadMultipleParameters(fileid, 'lgRefl', 'DATTIMPKANSS')
                dat_in = datetime.strptime(instParams[1][4:],"%d/%m/%Y").date()
                dat_out = dat_in.strftime("%m/%d/%Y")
                dat = datetime.strptime(dat_out, "%m/%d/%Y").date()
                dat_list.append(dat)

                tim = datetime.strptime(instParams[2][4:].split()[0], "%H:%M:%S.%f")
                tim_list.append(tim)

                pka = instParams[3][4:]
                pka_list.append(pka)
                
                nss = instParams[4][4:]
                nss_list.append(nss)
                
            with open(read_params, 'a') as file:
                for h, fileid in enumerate(fileids):
                    file.write(f'{fileid}, {dat_list[h]}, {tim_list[h].time()}, '
                                    f'{pka_list[h]}, {nss_list[h]}\n')
            
            if delay[i] >= 1800:
                subprocess.run([path_cloud], shell=True)
            
            measTime = datetime.combine(dat_list[0], tim_list[0].time())
            delay_time = timedelta(seconds=delay[i])
            next_meas = measTime + delay_time
            print('Spectrum ' + str(k) + ' of ' + str(repeat[j]) + ' for ' +
                   str(round(delay[i]/60, 2)) + ' minute delay')
            print("\nNext measurement at:\n" + str(next_meas) + "\n")
            
            for file_list in all_fileids[:-10]:
                for file in file_list:
                    UnloadFile(file)
            
            m += 1
            delta = datetime.now() - now
            time_wait = delay[i] - delta.total_seconds()
            if time_wait < 0:
                continue
            time.sleep(time_wait)

        j += 1


# repeat = [10, 5, 15, 200] # number of times to repeat
# delay = [60, 300, 600, 1800] # delay (s) between repeats
# nss_vals = [256]

# do_bckg = 0 # 0 for yes, 1 for no

# main('NN2019_04PdCe_5', 'NN2019_04PdCe_COAds') # sample name, folder name

repeat = [20] # number of times to repeat
delay = [30] # delay (s) between repeats
nss_vals = [256]

do_bckg = 1 # 0 for yes, 1 for no

main('test', 'test') # sample name, folder name