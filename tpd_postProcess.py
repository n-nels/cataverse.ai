import os, glob
from datetime import datetime


def SaveAs(file, name, path):
    arr = PipeCommand("COMMAND_LINE SaveAs ([" + file + ":lgRefl], {DAP='" + path + "',"
                        "SAN='" + name + "', SEP=',', DPA=8, DPO=8,"
                        "ADP='1', YON='0', OEX='0', X64='1'});", 0).split(chr(10))

def LoadFile(file):
    arr = PipeCommand("LOAD_FILE" + file, 0).split(chr(10))
    return arr[1]

def UnloadFile(file):
    arr = PipeCommand("COMMAND_LINE Unload([" + file + ":Spec], {})", 0).split(chr(10))

def SpectrumFromInterferogram(meas, bckg):
    arr = PipeCommand("COMMAND_LINE SpecFromIfgs ([" + meas + ":IgSm], [" + bckg + ":IgSm], {"
                        "PPF='LRF', CPF=0})", 0).split(chr(10))

def PipeCommand(cmd, show):
    if (show & 1) : print (cmd)
    hPipe.write(bytes(cmd + '\r\n', 'utf-8'))
    data = hPipe.read(1000)
    Mystr = data.decode('utf-8')
    total = Mystr
    if show & 2: print (total, '\n')
    return total

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

def Subtract_ifg(files):

    for step in range(1, 11):
        for i in range(step, len(files), step):

            pair = (files[i], files[i - step])

            if pair not in processed_files:
                file_pair = list(pair)
                file_ids = []
                sub_ifg_list = []
                
                for spectrum in file_pair:
                    file_id = LoadFile(spectrum)
                    file_ids.append(file_id)   
                
                SpectrumFromInterferogram(file_ids[0], file_ids[1])            
                name = f"{file_ids[0].split('\\')[-1][:-8]}_delta{step}.{
                            file_ids[0].split('.')[-1][:-3]}"
                sub_ifg_list.append((name, files[i], files[i - step]))
                SaveAs(file_ids[0], name, path_subIFG)
                
                for file in file_ids:
                    UnloadFile(file)
                processed_files.add(pair)

                with open(subIFG_files, 'a') as txtFile:
                    for z in sub_ifg_list:
                        txtFile.write(f'{z}\n')   
                        
                print('Processed files')
                print(file_ids[0], file_ids[1], '\n')

def Deconvolute(file):
    arr = PipeCommand("COMMAND_LINE Deconvolution([" + file + ":lgRefl], {"
                      "DEE=1800, DES=2220, DSP='LO', DWR=0, DNR=0.5, DEF=876719.515768})", 0).split(chr(10))

def tpd_postProcess(opus_filename, folder_name):

    global hPipe
    global DefaultPrintout
    global path_OpusFiles
    global path_lgRfl
    global path_subIFG
    global path_ScSm
    global path_fsd
    global path_readParams
    global processed_files
    global subIFG_files

    DefaultPrintout = 3
    hPipe = open(r'\\.\pipe\OPUS', 'r+b', 0)

    path_OpusFiles = "C:\\Data\\OpusFiles\\" + folder_name + opus_filename + ".*"
    path_subIFG = "C:\\Data\\OpusConvert_subIFG_lgRfl\\" + folder_name
    path_readParams = "C:\\Data\\OpusReadParams\\" + folder_name
    path_lgRfl = "C:\\Data\\OpusConvert_lgRfl\\" + folder_name
    path_ScSm = "C:\\Data\\OpusConvert_SSC\\" + folder_name
    path_fsd = "C:\\Data\\OpusConvert_fsd\\" + folder_name

    # Create experimental parameter files
    read_params = os.path.join(path_readParams, opus_filename + '.txt')
    # Create subIFG file
    subIFG_files = os.path.join(path_readParams, opus_filename + '_subIFGfiles.txt')

    files = glob.glob(path_OpusFiles)
    files.sort
    processed_files = set()  # for subIFG

    Subtract_ifg(files)

    for file in files:

        fileid = LoadFile(file)
        file_name = fileid.split('\\')[-1][:-3]

        SaveAs(fileid, file_name, path_lgRfl)            
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

        UnloadFile(fileid)

# specify file & folder
opus_filename = '20240629_092716_NN2031_04PdCe_116_evac'
folder_name = 'NN2031_04PdCe_COAds\\'

tpd_postProcess(opus_filename, folder_name)
