
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

def GetExperimentPath():
    arr = PipeCommand('GET_OPUSPATH', 1).split(chr(10))
    if (arr[0] == 'OK'):
        return arr[1] + '\\XPM'
    return ''

def GetVersion():
    return (PipeCommand('GET_VERSION_EXTENDED', 3) != "")

def LoadFile(fileid, n):
    arr = PipeCommand("COMMAND_LINE Load (0, {DAP='" + path_OpusFiles + "',"
                      "DAF='" + FileName + "." + n + "'})", 0).split(chr(10))

def OpenOpus():
    import subprocess, time

    # Replace 'path_to_opus.exe' with the actual path to the OPUS executable
    opus_exe_path = 'C:\Program Files\Bruker\OPUS_8.7.10\\Opus.exe /LANGUAGE=ENGLISH /OPUSPIPE=ON /DIRECTLOGINPASSWORD=Admin@OPUS'

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

def ReadParameter(fileid, block, name):
    arr = PipeCommand("FILE_PARAMETERS", 0).split(chr(10))
    if (arr[0] == 'OK'):
        arr = PipeCommand("READ_FROM_FILE " + fileid, 0).split(chr(10))
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

def SaveAs_lgRfl(fileid, n):
    arr = PipeCommand("COMMAND_LINE SaveAs ([" + fileid + ":lgRefl], {DAP='" + path_lgRfl + "',"
                        "SAN='" + FileName + "." + n + "', SEP=',', DPA=8, DPO=8,"
                        "ADP='1', YON='0', OEX='0', X64='1'});", 0).split(chr(10))
    if(arr[0] == 'OK'):
       print("Save lgRfl successful")
    else:
        print("Save lgRfl failed")

def SaveAs_ScSm(fileid, n):
    arr = PipeCommand("COMMAND_LINE SaveAs ([" + fileid + ":ScSm], {DAP='" + path_ScSm + "',"
                        "SAN='" + FileName + "." + n + "', SEP=',', DPA=8, DPO=8,"
                        "ADP='1', YON='0', OEX='0', X64='1'});", 0).split(chr(10))
    if(arr[0] == 'OK'):
       print("Save single channel successful")
    else:
        print("Save single channel failed")

def SaveAs_subIFG(fileid, n):
    arr = PipeCommand("COMMAND_LINE SaveAs ([" + fileid + ":lgRefl], {DAP='" + path_subIFG + "',"
                    "SAN='" + FileName + "." + n + "', SEP=',', DPA=8, DPO=8,"
                    "ADP='1', YON='0', OEX='0', X64='1'})", 0).split(chr(10))
    if(arr[0] == 'OK'):
        print("Save subtracted interoferrogram successful.")
    else:
        print("Save subtracted interoferrogram failed.")

def SubtractIFG(meas, bckg):
    array = PipeCommand("COMMAND_LINE SpecFromIfgs ([" + meas + ":IgSm], [" + bckg + ":IgSm], {"
                        "PPF='LRF', CPF=0})", 0).split(chr(10))

def UnloadFile(fileid):
    arr = PipeCommand("COMMAND_LINE Unload([" + fileid + ":Spec], {})", 0).split(chr(10))

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
    global FileName
    global path_readParams
    global path_cloud
    global n

    # Defining globals
    XpmName = 'ncnels_v2.xpm'
    DefaultPrintout = 3 # set bit to 1, 2, or 3 to print out pipe commands, return strings, or both
    hPipe = open(r'\\.\pipe\OPUS', 'r+b', 0)
    SampleName = sample_name
    path_OpusFiles = "C:\\Data\\OpusFiles\\" + folder_name
    path_lgRfl = "C:\\Data\\OpusConvert_lgRfl\\" + folder_name
    path_subIFG = "C:\\Data\\OpusConvert_subIFG_lgRfl\\" + folder_name
    path_ScSm = "C:\\Data\\OpusConvert_SSC\\" + folder_name
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
    paths = [path_ScSm, path_lgRfl, path_OpusFiles, path_readParams, path_subIFG]
    for path in paths:
        if not os.path.exists(path):
            os.makedirs(path)

    # Define filename
    now = datetime.now()
    formatted_time = now.strftime("%Y%m%d_%H%M%S")
    FileName = formatted_time + "_" + SampleName

    # Create experimental parameter files
    read_params = os.path.join(path_readParams, FileName + '.txt')
    exp_params = os.path.join(path_OpusFiles, FileName + '.txt')
    with open(exp_params, 'w') as file:
        for d, r in zip(delay, repeat):
            file.write(f'{d},{r}\n')

    # Collect spectra
    j = 0
    m = 0
    for i in range(len(delay)):
        for k in range(repeat[j]):
            n = str(m).zfill(4)
            now = datetime.now()
            
            fileid = DoSampleMeasurement('')

            SaveAs_lgRfl(fileid, n)            
            SaveAs_ScSm(fileid, n)
            
            if i == 0 and k == 0:
                UnloadFile(fileid)
            else:
                SubtractIFG(fileid, bckg)
                SaveAs_subIFG(fileid, n)
                UnloadFile(fileid)

            bckg = fileid
            LoadFile(bckg, n)

            dat = ReadParameter(fileid, 'lgRefl', 'DAT')
            dat_in = datetime.strptime(dat.split()[0],"%d/%m/%Y").date()
            dat_out = dat_in.strftime("%m/%d/%Y")
            dat = datetime.strptime(dat_out, "%m/%d/%Y").date()

            tim = ReadParameter(fileid, 'lgRefl', 'TIM')
            tim = datetime.strptime(tim.split()[0], "%H:%M:%S.%f")

            pka = ReadParameter(fileid, 'lgRefl', 'PKA')
            pka = pka.split()[0]

            nss = ReadParameter(fileid, 'lgRefl', 'NSS')
            nss = nss.split()[0]
            
            with open(read_params, 'a') as file:
                file.write(f'{FileName}.{n}, {dat}, {tim.time()}, {pka}, {nss}\n')

            measTime = datetime.combine(dat, tim.time())
            delay_time = timedelta(seconds=delay[i])
            next_meas = measTime + delay_time
            print('Spectrum ' + str(k) + ' of ' + str(repeat[j]) + ' for ' +
                   str(delay[i]/60) + ' minute delay')
            print("\nNext measurement at:\n" + str(next_meas) + "\n")
            
            m += 1
            # if delay[i] >= 1000:
            #     subprocess.run([path_cloud], shell=True)
            delta = datetime.now() - now
            time_wait = delay[i] - delta.total_seconds()
            time.sleep(time_wait)

        j += 1


repeat = [3, 2, 3, 7, 3, 100] # number of times to repeat
delay = [60, 240, 600, 1200, 3600, 7200] # delay (s) between repeats

do_bckg = 0 # 0 for yes, 1 for no

main('NN2015_04PdCe_COAds_9', 'NN2015_04PdCe_COAds') # sample name, folder name
