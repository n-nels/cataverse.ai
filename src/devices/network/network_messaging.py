## network_messaging.py

import json
import time

import zmq


class NetworkMessaging:
    """Class to handle network messaging using ZeroMQ."""

    def __init__(self, context: zmq.Context = None, rcv_timeout: int = 300000):
        """Initializes the NetworkMessaging with a ZeroMQ context.
        
        Args:
            context: An optional ZeroMQ context. If not provided, a new context will be created.
            rcv_timeout: Receive timeout in milliseconds (default 300000 milliseconds)
        """
        self.context = context if context is not None else zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, rcv_timeout)  # Set receive timeout
        self.rcv_timeout = rcv_timeout  # Store for reconnection
        self.default_ip = "130.20.216.127"
        self.default_port = 5555

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
    
    def reconnect(self, ip: str = None, port: int = None) -> None:
        """Reconnects the socket after a timeout or error.
        
        Args:
            ip: The IP address to connect to. Defaults to stored default.
            port: The port number to connect to. Defaults to stored default.
        """
        print("Reconnecting socket...")
        try:
            self.socket.setsockopt(zmq.LINGER, 0)  # Don't wait for pending messages
            self.socket.close()
            time.sleep(0.5)  # Give socket time to fully close
            print("Socket closed")
        except Exception as e:
            print(f"Error closing socket: {e}")
        
        print("Creating new socket...")
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, self.rcv_timeout)  # Use stored timeout
        self.connect(ip, port)
        print("Socket reconnected successfully")

    def send_message(self, message: dict) -> bool:
        """Sends a message to the specified IP address.

        Args:
            message: The message to send.

        Returns:
            A boolean indicating if the message was successfully sent.
        """
        try:
            message_json = json.dumps(message)
            self.socket.send_string(message_json)
            print(f"Sent message: {message_json}\n")
            return True
        except zmq.ZMQError as e:
            error_msg = str(e)
            print(f"Failed to send message: {error_msg}")
            
            # If socket is in invalid state, attempt immediate reconnection
            if "current state" in error_msg.lower() or "fsm" in error_msg.lower():
                print("Socket in invalid state detected - attempting auto-recovery...")
                try:
                    self.reconnect()
                    # Retry once after reconnection
                    print("Retrying message send...")
                    message_json = json.dumps(message)
                    self.socket.send_string(message_json)
                    print(f"Message sent successfully after reconnection: {message_json}")
                    return True
                except Exception as retry_err:
                    print(f"Reconnection and retry failed: {retry_err}")
                    return False
            return False

    def receive_message(self, timeout_ms: int = None) -> str:
        """Receives a message from the connected socket.
        
        Args:
            timeout_ms: Optional timeout in milliseconds. If not provided, uses socket default.
        
        Returns:
            The received message as a string, or empty string on timeout/error.
        """
        try:
            if timeout_ms is not None:
                old_timeout = self.socket.getsockopt(zmq.RCVTIMEO)
                self.socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
            
            message = self.socket.recv_string()
            
            # Restore original timeout if it was temporarily changed
            if timeout_ms is not None:
                self.socket.setsockopt(zmq.RCVTIMEO, old_timeout)
            
            return message
        except zmq.Again:
            timeout_sec = (timeout_ms if timeout_ms else self.rcv_timeout) / 1000
            print(f"Receive timeout: No response from server after {timeout_sec:.1f} seconds")
            print("Socket in invalid state - connection is corrupted")
            print("Next send will trigger automatic reconnection")
            return ""
        except zmq.ZMQError as e:
            print(f"Failed to receive message: {e}")
            return ""
        except KeyboardInterrupt:
            print("\nProgram interrupted by user. Exiting.")
            return ""

if __name__ == "__main__":

    def run_client(message: dict):
        messaging = NetworkMessaging()
        ip = "130.20.216.127"
        messaging.connect(ip=ip, port=5555)

        # Send a message
        success = messaging.send_message(message)

        if success:
            # Receive reply
            reply = messaging.receive_message()
            print(f"Received reply from server: {reply}")
            messaging.send_message(message)

    message = {'foldername': '_test',
               'filename': 'test',
               'do_fit': False,
               'do_bckg' : False,
               'reset_fileids': True,
               }
    run_client(message)
    time.sleep(30)

    message = {'foldername': '_test',
               'filename': 'test',
               'do_fit': False,
               'do_bckg' : False,
               'reset_fileids': True,
               'end_experiment': True}
    run_client(message)

