import os
import sys
import math
import json
import time
from ZMQMessenger import ZMQMessenger
import opusAcquire_carbonylCalibration

def Connect(publisher_port, subscriber_port, subscriber_ip):
    global subscriber
    global publisher

    publisher = ZMQMessenger("localhost", publisher_port, "PUB", "Opus")
    subscriber = ZMQMessenger(subscriber_ip, subscriber_port, "SUB", "Opus")
    publisher.CreateSocketPair(subscriber)

def MessageHandler(header):
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
        fileid = opusAcquire_carbonylCalibration.main_v2(sample, folder) # need to wait until script is finished
        while fileid is None:
            time.sleep(0.1)

        if len(all_fileids) > 0:
            while fileid == all_fileids[-1]:
                time.sleep(0.1)
        
        all_fileids.append(fileid)
        print(all_fileids)
        # need to bring in processed file stuff in here to actually make this work
        opusAcquire_carbonylCalibration.Subtract_ifg(all_fileids)
        publisher.SendText(str(fileid))
        # for i in range(5):
        #     time.sleep(1)
        #     print(i)
        #     publisher.SendText("wrapper " +str(i))
       
        # publisher.SendText("Script Complete") # create the return message

    except Exception as e:
        print(e)


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

sys.path.append(".")
root_directory = "c:\\"
subscriber = None

labnet_server='we48123'  # serphos computer
fileid = None
all_fileids = []

if __name__ == "__main__":
    main()
