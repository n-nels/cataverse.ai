import os, glob
from datetime import datetime

def LoadFile(file):
    arr = PipeCommand("LOAD_FILE" + file, 0).split(chr(10))
    return arr[1]

def UnloadFile(file):
    arr = PipeCommand("COMMAND_LINE Unload([" + file + ":Spec], {})", 0).split(chr(10))

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


# specify file & folder
opus_filename = '20240610_164543_NN2031_04PdCe_111'
folder_name = 'NN2031_04PdCe_COAds\\'

path_OpusFiles = "C:\\Data\\OpusFiles\\" + folder_name + opus_filename + ".*"
path_readParams = "C:\\Data\\OpusReadParams\\" + folder_name

files = glob.glob(path_OpusFiles)
files.sort

hPipe = open(r'\\.\pipe\OPUS', 'r+b', 0)

read_params = os.path.join(path_readParams, opus_filename + '.txt')

for file in files:

    fileid = LoadFile(file)
    file_name = fileid.split('\\')[-1][:-3]

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