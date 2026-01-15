import os, glob


def Deconvolute(file):
    arr = PipeCommand("COMMAND_LINE Deconvolution([" + file + ":lgRefl], {"
                      "DEE=1800, DES=2220, DSP='LO', DWR=0, DNR=0.5, DEF=876719.515768})", 0).split(chr(10))
    
def SaveAs(file, name, path):
    arr = PipeCommand("COMMAND_LINE SaveAs ([" + file + ":lgRefl], {DAP='" + path + "',"
                        "SAN='" + name + "', SEP=',', DPA=8, DPO=8,"
                        "ADP='1', YON='0', OEX='0', X64='1'});", 0).split(chr(10))

def SaveAs_ScSm(file, name):
    arr = PipeCommand("COMMAND_LINE SaveAs ([" + file + ":ScSm], {DAP='" + path_SSC + "',"
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


# specify file & folder
opus_filename = '20240726_162054_NN2031_04PdCe_142'
folder_name = 'NN2031_04PdCe_COAds\\'

path_OpusFiles = "C:\\Data\\OpusFiles\\" + folder_name + opus_filename + ".*"
path_SSC = "C:\\Data\\OpusConvert_SSC\\" + folder_name
path_lgRfl = "C:\\Data\\OpusConvert_lgRfl\\" + folder_name
path_fsd = "C:\\Data\\OpusConvert_fsd\\" + folder_name

files = glob.glob(path_OpusFiles)
files.sort

hPipe = open(r'\\.\pipe\OPUS', 'r+b', 0)

for file in files[:76]:
    file_id = LoadFile(file)
    file_name = file.split('\\')[-1]
    SaveAs(file_id, file_name, path_lgRfl)            
    SaveAs_ScSm(file_id, file_name)
    Deconvolute(file_id)
    SaveAs(file_id, file_name, path_fsd)
    UnloadFile(file_id)
    print('Processed files')
    print(file_id, '\n')

 
                     
