import os, time
from datetime import datetime, timedelta

def PumpOn():
    
    # pump on
    with open(os.path.join(folder_path, pump_on), 'w'):
        pass
    
    start_time = datetime.now()
    print(f"\nStart pumping: '{start_time}'")
    time.sleep(wait_time)
    
    end_time = datetime.now()
    next_cycle = end_time + timedelta(seconds=cycle_time)
    
    # pump off
    with open(os.path.join(folder_path, pump_off), 'w'):
        pass

    print(f"End pumping: '{end_time}'\nNext cycle: '{next_cycle}'")
    time.sleep(cycle_time)

# Specify the folder path
folder_path = 'C:\\NorhofLN2pump\\'

# Specify the file name
pump_on = 'pon.txt'
pump_off = 'pof.txt'

# Specify cyle and wait times
cycle_time = 5 * 3600 # h * s/h (default is 7 hours)
wait_time = 20 * 60 # min * s/min

# Run indefinitely
try:
    while True:
        PumpOn()
except KeyboardInterrupt:
    print("Program interrupted. Exiting.")

