## network_messaging.py

import zmq

class NetworkMessaging:
    """Class to handle network messaging using ZeroMQ."""

    def __init__(self, context: zmq.Context = None):
        """Initializes the NetworkMessaging with a ZeroMQ context.

        Args:
            context: An optional ZeroMQ context. If not provided, a new context will be created.
        """
        self.context = context if context is not None else zmq.Context()
        self.socket = self.context.socket(zmq.REQ)  # Using REQ-REP pattern for request-reply communication
        self.default_ip = "127.0.0.1"
        self.default_port = 5555

    def connect(self, ip: str = None, port: int = None) -> None:
        """Connects the socket to the specified IP and port.

        Args:
            ip: The IP address to connect to. Defaults to '127.0.0.1'.
            port: The port number to connect to. Defaults to 5555.
        """
        ip = ip if ip is not None else self.default_ip
        port = port if port is not None else self.default_port
        self.socket.connect(f"tcp://{ip}:{port}")
        print(f"Connected to {ip}:{port}")

    def send_message(self, ip: str, message: str) -> bool:
        """Sends a message to the specified IP address.

        Args:
            ip: The IP address to send the message to.
            message: The message to send.

        Returns:
            A boolean indicating if the message was successfully sent.
        """
        try:
            self.connect(ip)
            self.socket.send_string(message)
            print(f"Sent message to {ip}: {message}")
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
            message = self.socket.recv_string()
            print(f"Received message: {message}")
            return message
        except zmq.ZMQError as e:
            print(f"Failed to receive message: {e}")
            return ""
