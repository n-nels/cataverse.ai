import os
import sys
import math
import json
import time
from ZMQMessenger import ZMQMessenger


sys.path.append(".")
root_directory = "c:\\"
subscriber = None

labnet_server='we48123'  # serphos computer


def Connect(publisher_port, subscriber_port, subscriber_ip):
    global subscriber
    global publisher

    publisher = ZMQMessenger("localhost", publisher_port, "PUB", "Opus")
    subscriber = ZMQMessenger(subscriber_ip, subscriber_port, "SUB", "Opus")
    publisher.CreateSocketPair(subscriber)


def MessageHandler(header):
    print("PyJEM handle message")

    try:
        print("MESSAGE:")
        print(header)

        if "message" not in header.keys():
            print("missing message")
            return

        params = header["parameters"]
        sample = params["sample_name"]
        folder = params["folder_name"]

        # call to opus here:
        # opusAcquire_4.main(sample, folder)
        for i in range(5):
            time.sleep(1)
            print(i)
            publisher.SendText("wrapper " +str(i))

        # create the return message
        
        publisher.SendText("Script Complete")

    except Exception as e:
        print(e)

def Version():
    return "3/12/24"

def main():

    print("OpusWrapper version: " + Version())

    # start the messenger
    # note these are the reverse of the control connections
    # publisher_port, subscriber_port, subscriber_ip
    Connect(6666, 6667, labnet_server)

    # count = 0
    
    started = False

    while not started:
        header = subscriber.GetHeader("StartScript")
        if header is not None:
            MessageHandler(header)
            started = False
        
        time.sleep(0.5)


if __name__ == "__main__":
    main()
