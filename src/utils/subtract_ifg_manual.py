import os, glob
from datetime import datetime
from ..core import config


def SaveAs(file, name, path):
    arr = PipeCommand(
        "COMMAND_LINE SaveAs ([" + file + ":lgRefl], {DAP='" + path + "',"
        "SAN='" + name + "', SEP=',', DPA=8, DPO=8,"
        "ADP='1', YON='0', OEX='0', X64='1'});",
        0,
    ).split(chr(10))


def LoadFile(file):
    arr = PipeCommand("LOAD_FILE" + file, 0).split(chr(10))
    return arr[1]


def UnloadFile(file):
    arr = PipeCommand("COMMAND_LINE Unload([" + file + ":Spec], {})", 0).split(chr(10))


def SpectrumFromInterferogram(meas, bckg):
    arr = PipeCommand(
        "COMMAND_LINE SpecFromIfgs ([" + meas + ":IgSm], [" + bckg + ":IgSm], {"
        "PPF='LRF', CPF=0})",
        0,
    ).split(chr(10))


def PipeCommand(cmd, show):
    if show & 1:
        print(cmd)
    hPipe.write(bytes(cmd + "\r\n", "utf-8"))
    data = hPipe.read(1000)
    Mystr = data.decode("utf-8")
    total = Mystr
    if show & 2:
        print(total, "\n")
    return total


def ReadMultipleParameters(file, block, name):
    arr = PipeCommand("READ_FROM_FILE " + file, 0).split(chr(10))
    if arr[0] == "OK":
        arr = PipeCommand("READ_FROM_BLOCK " + block, 0).split(chr(10))
        if arr[0] == "OK":
            arr = PipeCommand("READ_MULTIPLE_PARAMETERS " + name, 0).split(chr(10))
            if arr[0] == "OK":
                return arr
    else:
        print("Reading parameter" + name + "failed")


def delete_files(directory, opus_filename):
    pattern = os.path.join(directory, opus_filename + "_*")
    files = glob.glob(pattern)
    for file in files:
        if "README" in file or "subIFG" not in file:
            continue
        try:
            if os.path.isfile(file):
                os.unlink(file)
                print(f"Deleted file: {file}")
        except Exception as e:
            print(f"Error deleting {file}: {e}")


def Deconvolute(file):
    arr = PipeCommand(
        "COMMAND_LINE Deconvolution([" + file + ":lgRefl], {"
        "DEE=1000, DES=4000, DSP='LO', DWR=0, DNR=0.5, DEF=876719.515768})",
        0,
    ).split(chr(10))


# specify file & folder
opus_filename = "20260108_220047_pd_ceo2_003-093"
folder_name = "nn1120-3_pd_ceo2_003\\"

# define paths
path_OpusFiles = os.path.join(
    config.get_path("data.opus_files"), folder_name, opus_filename + ".*"
)
path_subIFG = config.get_path("utility.subtract_ifg.sub_ifg_output", folder_name)
path_readParams = config.get_path(
    "utility.subtract_ifg.read_params_output", folder_name
)
path_lgRfl = config.get_path("utility.subtract_ifg.lg_refl_output", folder_name)
path_cloud = config.get_setting("utility.cloud_copy_script")

# create text files
subIFG_files = os.path.join(path_readParams, opus_filename + "_subIFGfiles.txt")
read_params = os.path.join(path_readParams, opus_filename + ".txt")

files = glob.glob(path_OpusFiles)
files.sort

hPipe = open(r"\\.\pipe\OPUS", "r+b", 0)
processed_files = set()

# # subtract interferograms
delete_files(path_subIFG, opus_filename)
# delete_files(path_readParams, opus_filename)  ## this only deletes the subIfG file, not the readme.
# delete_files(path_lgRfl, opus_filename)  ## this does not work b/c of the function rules..Delete FSD too!
for step in range(1, 11):  # 21 for agglomeration
    start = 0 if step == 1 else 2
    # stop = 10 * step if step <= 4 else len(files)  # for agglomeration
    stop = len(files)

    for i in range(start + step, stop, step):
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
                file_ids[0].split('.')[-1][:-3]
            }"
            sub_ifg_list.append((name, files[i], files[i - step]))
            SaveAs(file_ids[0], name, path_subIFG)

            for file in file_ids:
                UnloadFile(file)
            processed_files.add(pair)

            with open(subIFG_files, "a") as txtFile:
                for z in sub_ifg_list:
                    txtFile.write(f"{z}\n")

            print("Processed files")
            print(file_ids[0], file_ids[1], "\n")


# write read params file
for file in files:
    fileid = LoadFile(file)
    file_name = fileid.split("\\")[-1][:-3]

    instParams = ReadMultipleParameters(fileid, "lgRefl", "DATTIMPKANSS")
    dat_in = datetime.strptime(instParams[1][4:], "%d/%m/%Y").date()
    dat_out = dat_in.strftime("%m/%d/%Y")
    dat = datetime.strptime(dat_out, "%m/%d/%Y").date()

    tim = datetime.strptime(instParams[2][4:].split()[0], "%H:%M:%S.%f")
    pka = instParams[3][4:]
    nss = instParams[4][4:]

    with open(read_params, "a") as file:
        file.write(f"{fileid}, {dat}, {tim.time()}, {pka}, {nss}\n")

    SaveAs(fileid, file_name, path_lgRfl)
    UnloadFile(fileid)


#### for redoing fsd with different parameters############
folder = r"C:\Data\OpusFiles\nn1120-3_pd_ceo2_003\\*"
path_fsd = "C:\\Data\\OpusConvert_fsd\\nn1120-3_pd_ceo2_003\\"

files = glob.glob(folder)

for file in files:
    if "isoX" in file:
        continue
    if opus_filename not in file:
        continue

    fileid = LoadFile(file)
    file_name = fileid.split("\\")[-1][:-3]

    Deconvolute(fileid)
    SaveAs(fileid, file_name, path_fsd)
    UnloadFile(fileid)
