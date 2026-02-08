import os
import shutil

def delete_files_in_test_folder(parent_directory):
    for root, dirs, files in os.walk(parent_directory):
        if 'test' in dirs:
            test_folder_path = os.path.join(root, 'test')
            
            # Confirm that the path is a directory
            if os.path.isdir(test_folder_path):
                # print(f"Deleting files in {test_folder_path}")
                
                # Delete all files in the 'Test' folder
                for file in os.listdir(test_folder_path):
                    file_path = os.path.join(test_folder_path, file)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as e:
                        print(f"Error deleting {file_path}: {e}")

                print(f"Files in {test_folder_path} deleted successfully.")
            else:
                print(f"{test_folder_path} is not a directory.")

# Replace 'C:\\Folder1' with the actual parent directory path
parent_directory = 'C:\\Data'
delete_files_in_test_folder(parent_directory)
