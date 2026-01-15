import os, sys, time, threading, zmq, json, queue
import ir_peakFit_carbonyl_v5 as fit
from datetime import datetime

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
                      "DEE=1000, DES=4000, DSP='LO', DWR=0, DNR=0.5, DEF=876719.515768})", 0).split(chr(10))

def DoBackgroundMeasurement():
    arr = PipeCommand('TAKE_REFERENCE ' + XpmPath + '\\' + XpmName, 1).split(chr(10))

def DoSampleMeasurement_nss(nss_value, n):
    add_params = f', NSS={nss_value}'
    try:
        arr = PipeCommand("COMMAND_LINE MeasureSample (, {EXP='" + XpmName + "', "
                                    "XPP='" + XpmPath + "', NAM='" + filename + "." + n + "',"
                                    "SNM='" + filename + "',"
                                    "PTH='" + path_OpusFiles + "'" + add_params + "});", 1
                                    ).split(chr(10))
        return arr[2]
   
    except Exception as e:
        define_paths()
        arr = PipeCommand("COMMAND_LINE MeasureSample (, {EXP='" + XpmName + "', "
                            "XPP='" + XpmPath + "', NAM='" + filename + "." + n + "',"
                            "SNM='" + filename + "',"
                            "PTH='" + path_OpusFiles + "'" + add_params + "});", 1
                            ).split(chr(10))
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
                
                if do_fit: 
                    peak_fit(path_subIFG + "\\" + name)

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

def opusAcquire():
    global n, all_fileids # if this fails, pass all_fileids as an argument and do not declare it as global

    # Collect spectra
    fileid = DoSampleMeasurement_nss(nss_value, n)
    all_fileids.append(fileid)
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
    
    Subtract_ifg(all_fileids)
    
    # if delay[i] >= 1800:
    #     subprocess.run([path_cloud], shell=True)

    for file in all_fileids[:-10]:
        UnloadFile(file)  
    # hPipe.close()
    return fileid

def peak_fit(file):
    """Add a file to the processing queue."""
    file_queue.put(file)
    print(f"Queued file for processing: {file}")

def peak_fit_worker():
    """Worker function to process files from the queue."""
    while True:
        file = file_queue.get()
        if file is None:  # Exit signal
            break

        try:
            if 'isoX' in file:
                fit.integrate_irIsoXchg(file)
            else:
                fit.voight_fit(file)
                fit.peak_heights(file)
            print(f"Processed file: {file}")
        except Exception as e:
            print(f"Error processing file {file}: {e}")
        finally:
            file_queue.task_done()  # Mark the task as done

def define_paths():
    global path_OpusFiles
    global path_OpusCalibrations # for IR isotopic exchange data
    global path_CalibrationData # processed isotopic exchange calibration data
    global path_lgRfl
    global path_subIFG
    global path_ScSm
    global path_fsd
    global path_readParams
    global path_cloud
    global read_params
    global subIFG_files

    path_OpusFiles = "C:\\Data\\OpusFiles\\" + foldername
    path_OpusCalibrations = f"C:\\Data\\OpusCalibrations\\{foldername}"
    path_CalibrationData = f"C:\\Data\\peakFit\\{foldername}\\CalibrationData"
    path_lgRfl = "C:\\Data\\OpusConvert_lgRfl\\" + foldername
    path_subIFG = "C:\\Data\\OpusConvert_subIFG_lgRfl\\" + foldername
    path_ScSm = "C:\\Data\\OpusConvert_SSC\\" + foldername
    path_fsd = "C:\\Data\\OpusConvert_fsd\\" + foldername
    path_readParams = "C:\\Data\\OpusReadParams\\" + foldername
    path_peakFit = "C:\\Data\\PeakFit\\" + foldername
    path_cloud = r"C:\sftp\copybutton.bat"

    paths = [path_ScSm, path_lgRfl, path_OpusFiles, path_readParams, path_subIFG, path_fsd, path_peakFit, path_OpusCalibrations]
    for path in paths:
        if not os.path.exists(path):
            os.makedirs(path)

    read_params = os.path.join(path_readParams, filename + '.txt')
    subIFG_files = os.path.join(path_readParams, filename + '_subIFGfiles.txt')

def MessageHandler(message):
    global foldername, filename, all_fileids, do_fit, path_OpusFiles

    try:       
        foldername = message["foldername"]
        filename = message["filename"]
        do_bckg = message["do_bckg"]
        reset_fileids = message["reset_fileids"]
        do_fit = message["do_fit"]
 
        if do_bckg:
            DoBackgroundMeasurement()
            if reset_fileids:
                all_fileids = []
                define_paths()
                socket.send_string("Collected background and all_fileids reset")
        elif reset_fileids: 
            all_fileids = []
            define_paths()
            socket.send_string("all_fileids reset")
        else:
            fileid = opusAcquire()
            socket.send_string(str(fileid))

    except Exception as e:
        print("Error: ", e, '\nTrying to read other message keys...')
        try:
            readme = message["readme"]
            if readme:
                root_dir = r"X:\peakFit"
                fileid = all_fileids[-1]
                fileid = fileid[:-1]
                foldername = fileid.split('\\')[-2]
                filename = fileid.split('\\')[-1]
                sample_name = filename.rsplit('.', 1)[0]
                path = os.path.join(root_dir, foldername, sample_name)
                file_name = path + '_README.md'
                fit.readme_to_csv(file_name)
                socket.send_string("readme converted to .csv")
                print("readme converted to .csv")      
        except Exception:
            # try:
            #     new_path = message['path_OpusFiles']
            #     if new_path:
            #         define_paths()
            # except Exception as e:
            print("Error:", e)
            socket.send_string("Error: " + str(e))
            # hPipe.close()

def run_server():
    global socket

    context = zmq.Context()
    socket = context.socket(zmq.REP)  # Using REP for reply side
    socket.bind("tcp://130.20.216.127:5555")  # Bind to opus IP and random port

    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)

    print("Server is listening on 130.20.216.127...")
    try:
        while True:
            try:
                # Poll for events
                events = dict(poller.poll(timeout=1000))  # Polling timeout of 1000 ms

                if socket in events:
                    if events[socket] == zmq.POLLIN:
                        message_json = socket.recv_string()
                        message = json.loads(message_json)
                        if message:
                            print(f"\nReceived request:\n {message}\n")
                            MessageHandler(message)
                            # # Send reply back to client
                            # reply = "Message received"
                            # socket.send_string(reply)
                            # print(f"Sent reply: {reply}")
            except zmq.Again:
                continue
            except KeyboardInterrupt:
                print("Program interrupted. Exiting.")
                break
    finally:
        socket.close()
        context.term()


file_queue = queue.Queue()
sys.path.append(".")
root_directory = "c:\\"

all_fileids = [] 
nss_value = 256  # number of scans
n = str(0).zfill(4)  # filename convention

XpmName = 'ncnels_v2.xpm'
DefaultPrintout = 3 # set bit to 1, 2, or 3 to print out pipe commands, return strings, or both


if __name__ == "__main__":
    hPipe = open(r'\\.\pipe\OPUS', 'r+b', 0)
    XpmPath = GetExperimentPath()

    worker_thread = threading.Thread(target=peak_fit_worker, daemon=True)
    worker_thread.start()
    
    try:
        run_server()
    except Exception as e:
        print(f"Error running server: {e}")
    finally:
        # Stop the worker thread
        file_queue.put(None)  # Send exit signal
        worker_thread.join()
 
    # file = r'C:\Data\OpusConvert_subIFG_lgRfl\nn1120-3_pd_ceo2_000\20250320_212002_pd_ceo2_000-007_isoX_1_delta1.0001'
    # peak_fit(file)