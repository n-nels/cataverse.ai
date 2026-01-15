
import os, glob, sys, math, json, time
import subprocess
from datetime import datetime, timedelta
from ZMQMessenger import ZMQMessenger


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
            print("Connection to instrument is OK.\n")
            return True
        if (number == 3):
            print("Instrument warnings and alarms present. Nevertheless measurements are possible.\n")
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
                        "XPP='" + XpmPath + "', NAM='" + SampleName + "." + n + "',"
                        "SNM='" + SampleName + "',"
                        "PTH='" + path_OpusFiles + "'" + addParams + "});", 1
                        ).split(chr(10))
    return arr[2]

def DoSampleMeasurement_nss(nss_value, m, n):
    add_params = f', NSS={nss_value}'
    arr = PipeCommand("COMMAND_LINE MeasureSample (, {EXP='" + XpmName + "', "
                                "XPP='" + XpmPath + "', NAM='" + SampleName + "." + n + "',"
                                "SNM='" + SampleName + "',"
                                "PTH='" + path_OpusFiles + "'" + add_params + "});", 1
                                ).split(chr(10))
    m += 1
    n = str(m).zfill(4)
    return arr[2]

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
                        "SAN='" + name + "', SEP=',', DPA=8, DPO=8, "
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

def SpectrumFromInterferogram(meas, bckg):
    arr = PipeCommand("COMMAND_LINE SpecFromIfgs ([" + meas + ":IgSm], [" + bckg + ":IgSm], {"
                        "PPF='LRF', CPF=0})", 0).split(chr(10))

def Subtract_ifg(files):

    global processed_files

    if len(files) <= 1:
        processed_files = set()
        return
            
    sub_ifg_list = []
    for step in range(1, 11):

        start = 0 if step == 1 else 2

        for i in range(start + step, len(files), step):
    
    # for step in range(1, 11):
    #     for i in range(step, len(files), step):

            pair = (files[i], files[i - step])

            if pair not in processed_files:
                file_ids = list(pair)
                sub_ifg_list = [] 
                
                SpectrumFromInterferogram(file_ids[0], file_ids[1])            
                name = f"{file_ids[0].split('\\')[-1][:-8]}_delta{step}.{
                            file_ids[0].split('.')[-1][:-3]}"
                sub_ifg_list.append((name, file_ids[0], file_ids[1]))
                SaveAs(file_ids[0], name, path_subIFG)
                
                for file in file_ids:
                    UnloadFile(file)
                for file in file_ids:
                    LoadFile(file.split('"')[1])
                processed_files.add(pair)

                with open(subIFG_files, 'a') as txtFile:
                    for z in sub_ifg_list:
                        txtFile.write(f'{z}\n')

def UnloadFile(file):
    arr = PipeCommand("COMMAND_LINE Unload([" + file + ":Spec], {})", 0).split(chr(10))

def main_tpd(sample_name, folder_name, repeat, delay, nss_value, do_bckg):
    print("\nStart of program...")
    
    global hPipe
    global DefaultPrintout
    global XpmPath
    global XpmName
    global SampleName
    global FileName
    global path_OpusFiles
    global n  # opus iterator

    XpmName = 'ncnels_v2.xpm'
    DefaultPrintout = 3 # set bit to 1, 2, or 3 to print out pipe commands, return strings, or both
    hPipe = open(r'\\.\pipe\OPUS', 'r+b', 0)
    SampleName = sample_name
    path_OpusFiles = "C:\\Data\\OpusFiles\\" + folder_name

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
    paths = [path_OpusFiles]
    for path in paths:
        if not os.path.exists(path):
            os.makedirs(path)

    # Define filename
    now = datetime.now()
    formatted_time = now.strftime("%Y%m%d_%H%M%S")
    FileName = formatted_time + "_" + SampleName

    # Collect spectra
    j = 0
    m = 0
    all_fileids = []
    for i in range(len(delay)):
        for k in range(repeat[j]):
            
            n = str(m).zfill(4)
            now = datetime.now()
            fileid = DoSampleMeasurement_nss(nss_value, m, n)

            UnloadFile(fileid)

            m += 1
            delta = datetime.now() - now
            time_wait = delay[i] - delta.total_seconds()
            if time_wait < 0:
                continue
            time.sleep(time_wait)
        j += 1

def opusAcquire(sample_name, folder_name, all_fileids):
    
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
    global path_readParams
    global path_cloud
    global subIFG_files
    global read_params
    global n  # opus iterator
    global do_bckg

    XpmName = 'ncnels_v2.xpm'
    DefaultPrintout = 3 # set bit to 1, 2, or 3 to print out pipe commands, return strings, or both
    hPipe = open(r'\\.\pipe\OPUS', 'r+b', 0)
    SampleName = sample_name
    path_OpusFiles = "C:\\Data\\OpusFiles\\" + folder_name
    path_lgRfl = "C:\\Data\\OpusConvert_lgRfl\\" + folder_name
    path_subIFG = "C:\\Data\\OpusConvert_subIFG_lgRfl\\" + folder_name
    path_ScSm = "C:\\Data\\OpusConvert_SSC\\" + folder_name
    path_fsd = "C:\\Data\\OpusConvert_fsd\\" + folder_name
    path_readParams = "C:\\Data\\OpusReadParams\\" + folder_name
    path_cloud = r"C:\sftp\copybutton.bat"
    
    XpmPath = GetExperimentPath()  # read opus path from workspace
    
    # Collect background
    if do_bckg == 0:
        if (GetVersion() == False):  # check connection
            print("Pipe connection failed.")

        if (CheckInstrumentStatus() == False): return  # check if OPUS is connected to an instrument

        DoBackgroundMeasurement(do_bckg)

        # Check if directories exist
        paths = [path_ScSm, path_lgRfl, path_OpusFiles, path_readParams, path_subIFG, path_fsd]
        for path in paths:
            if not os.path.exists(path):
                os.makedirs(path)

        do_bckg = 1

    # Create experimental parameter files
    read_params = os.path.join(path_readParams, sample_name + '.txt')
    subIFG_files = os.path.join(path_readParams, sample_name + '_subIFGfiles.txt')

    # Collect spectra
    n = str(m).zfill(4)
    fileid = DoSampleMeasurement_nss(nss_value, m, n)
    all_fileids.append(fileid)
    Subtract_ifg(all_fileids)
        
    file_name = fileid.split('\\')[-1][:-3]
    SaveAs(fileid, file_name, path_lgRfl)            
    SaveAs_ScSm(fileid, file_name)
    Deconvolute(fileid)
    SaveAs(fileid, file_name, path_fsd)
    UnloadFile(fileid)
    LoadFile(fileid.split('"')[1])

    instParams = ReadMultipleParameters(fileid, 'lgRefl', 'DATTIMPKANSS')
    dat_in = datetime.strptime(instParams[1][4:],"%d/%m/%Y").date()
    dat_out = dat_in.strftime("%m/%d/%Y")
    dat = datetime.strptime(dat_out, "%m/%d/%Y").date()

    tim = datetime.strptime(instParams[2][4:].split()[0], "%H:%M:%S.%f")

    pka = instParams[3][4:]
    
    nss = instParams[4][4:]
        
    with open(read_params, 'a') as file:
        file.write(f'{fileid}, {dat}, {tim.time()}, '
                        f'{pka}, {nss}\n')
    
    # if delay[i] >= 1800:
    #     subprocess.run([path_cloud], shell=True)

    for file in all_fileids[:-10]:
        UnloadFile(file)
    
    hPipe.close()
    return fileid

def Connect(publisher_port, subscriber_port, subscriber_ip):
    global subscriber
    global publisher

    publisher = ZMQMessenger("localhost", publisher_port, "PUB", "Opus")
    subscriber = ZMQMessenger(subscriber_ip, subscriber_port, "SUB", "Opus")
    publisher.CreateSocketPair(subscriber)

def MessageHandler(header):

    global all_fileids, do_bckg

    print("PyJEM handle message")

    try:
        print(header)

        if "message" not in header.keys():
            print("missing message")
            return

        params = header["parameters"]
        sample = params["sample_name"]
        folder = params["folder_name"]

        # call to opus here:     
        if sample == '0' and folder == '0':
            all_fileids = []
            do_bckg = 0
            publisher.SendText("all_fileids=do_bckg=0")
        elif sample == '1' and folder == '1':
            publisher.SendText("all_fileids=do_bckg=1")
        elif sample == '0' and folder == '1':
            all_fileids = []
            publisher.SendText("all_fileids=0, do_bckg=1")
        elif sample == '1' and folder == '0':
            do_bckg = 0
            publisher.SendText("all_fileids=1, do_bckg=0")
        else:
            fileid = opusAcquire(sample, folder, all_fileids)
            publisher.SendText(str(fileid))
        
        # publisher.SendText("Script Complete") # create the return message

    except Exception as e:
        print("Error: ", e)
        publisher.SendText(e)
        hPipe.close()

def main():

    try:
        # note these are the reverse of the control connections
        # publisher_port, subscriber_port, subscriber_ip
        Connect(6666, 6667, labnet_server)
        
        while True:
            header = subscriber.GetHeader("StartScript")
            if header is not None:
                MessageHandler(header)
        
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("Program interrupted. Exiting.")
        hPipe.close()


sys.path.append(".")
root_directory = "c:\\"
subscriber = None
labnet_server='we48123'  # serphos computer

all_fileids = [] 
m = 0  # opus iterator

nss_value = 256  # number of scans
do_bckg = None  # 0 for yes, 1 for no

if __name__ == "__main__":
    main()
