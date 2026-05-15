import os
import glob

# # Input directory and filename
# directory_path = 'C:\\Data\\OpusConvert_fsd\\NN2019_04PdCe_COAds\\'
# filename = '20240612_165116_NN2031_04PdCe_111.*'



# file_list = glob.glob(os.path.join(directory_path + filename))

# for filename in file_list:
    
#     new_filename = filename.replace('226', '26') 
#     old_file_path = os.path.join(directory_path, filename)
#     new_file_path = os.path.join(directory_path, new_filename)
#     os.rename(old_file_path, new_file_path)


folder_name = 'nn1120-3_pd_ceo2_004\\'
old_filename = '20260505_063850_pd_ceo2_004-018*'
new_filename = '20260505_063850_pd_ceo2_004-018.'

path_OpusFiles = "C:\\Data\\OpusFiles\\" + folder_name
path_lgRfl = "C:\\Data\\OpusConvert_lgRfl\\" + folder_name
path_ScSm = "C:\\Data\\OpusConvert_SSC\\" + folder_name
path_fsd = "C:\\Data\\OpusConvert_fsd\\" + folder_name

paths = [path_ScSm, path_lgRfl, path_OpusFiles, path_fsd]

for path in paths:

    m = 0
    file_list = glob.glob(os.path.join(path + old_filename))

    for file in file_list:

        # suffix = file.split('.')[-1]
        n = str(m).zfill(4)
        new_name = file.replace(file.split('\\')[-1], new_filename + str(n))
        os.rename(file, new_name)
        m += 1

        # print(new_name)
        # print(file)
