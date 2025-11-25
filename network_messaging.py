## network_messaging.py

import zmq, json

class NetworkMessaging:
    """Class to handle network messaging using ZeroMQ."""

    def __init__(self, context: zmq.Context = None):
        """Initializes the NetworkMessaging with a ZeroMQ context.

        Args:
            context: An optional ZeroMQ context. If not provided, a new context will be created.
        """
        self.context = context if context is not None else zmq.Context()
        self.socket = self.context.socket(zmq.REQ)  # Using REQ-REP pattern for request-reply communication
        self.default_ip = "130.20.216.127" # local ip
        self.default_port = 5555 # random port

    def connect(self, ip: str = None, port: int = None) -> None:
        """Connects the socket to the specified IP and port.

        Args:
            ip: The IP address to connect to. Defaults to '130.20.216.127'.
            port: The port number to connect to. Defaults to 5555.
        """
        ip = ip if ip is not None else self.default_ip
        port = port if port is not None else self.default_port
        self.socket.connect(f"tcp://{ip}:{port}")
        print(f"Connected to {ip}:{port}")

    def send_message(self, message: dict,  ip: str = None ) -> bool:
        """Sends a message to the specified IP address.

        Args:
            ip: The IP address to send the message to.
            message: The message to send.

        Returns:
            A boolean indicating if the message was successfully sent.
        """
        try:
            # self.connect(ip)
            message_json = json.dumps(message)
            self.socket.send_string(message_json)
            # print(f"Sent message to {ip}: {message_json}")
            print(f"\nSent message: {message_json}\n")
            return True
        except zmq.ZMQError as e:
            print(f"Failed to send message to {ip}: {e}")
            return False

    def receive_message(self) -> str:
        """Receives a message from the connected socket.

        Returns:
            The received message as a string.
        """
        try:
            try:
                message = self.socket.recv_string()
                # print(f"Received message: {message}")
                return message
            except zmq.ZMQError as e:
                print(f"Failed to receive message: {e}")
                return ""
        except KeyboardInterrupt:
            print("Program interrupted. Exiting.")

if __name__ == "__main__":

    def run_client(message: dict): # this is derek's opusacquire in the old version
        messaging = NetworkMessaging()
        ip = "130.20.216.127"

        # Send a message
        success = messaging.send_message(ip, message)

        if success:
            # Receive reply
            reply = messaging.receive_message()
            print(f"Received reply from server: {reply}")

    # message = {'foldername': '1',
    #            'filename': '2',
    #            'acquire': True,
    #            'do_fit': True,
    #            'do_bckg' : False,
    #            'reset_fileids': False,
    #            'path_OpusFiles': False,
    #            'readme': False}
    message = {'test': 'test message'}
    
    run_client(message)