## main.py

from usb_control import USBControl
from network_messaging import NetworkMessaging
from gui import GUI
from script_executor import ScriptExecutor
from device_interface import DeviceInterface

class Main:
    """Main class to orchestrate the device control application."""

    def __init__(self):
        """Initializes the Main class with all necessary components."""
        self.usb_control = USBControl()
        self.network_messaging = NetworkMessaging()
        self.gui = GUI()
        self.script_executor = ScriptExecutor()
        self.device_interface = DeviceInterface()

    def run(self) -> None:
        """Runs the main application logic."""
        # Start the GUI interface
        self.gui.start_interface()

        # Load a script (for demonstration, we assume a script path)
        script_path = "path/to/script.txt"  # Example script path
        self.gui.load_script(script_path)

        # Execute a script (for demonstration, we assume a script content)
        script_content = "command1\ncommand2"  # Example script content
        self.script_executor.execute_script(script_content)

        # Initialize a device (for demonstration, we assume a device ID)
        device_id = "MKS_PDR2000"
        if self.usb_control.initialize_device(device_id):
            # Control specific devices
            self.device_interface.control_mks_pdr2000()
            self.device_interface.control_watlow()

        # Send a network message (for demonstration, we assume an IP and message)
        ip_address = "192.168.1.100"
        message = "Hello, Device!"
        if self.network_messaging.send_message(ip_address, message):
            # Receive a network message
            received_message = self.network_messaging.receive_message()
            print(f"Received message: {received_message}")

        # Manual control (for demonstration, we assume manual control is activated)
        self.gui.manual_control()

        # Read and write analog signals (for demonstration, we assume channel and value)
        channel = 1
        analog_value = self.usb_control.read_analog_input(channel)
        print(f"Analog input value: {analog_value}")

        output_value = 3.3  # Example output value
        if self.usb_control.write_analog_output(channel, output_value):
            print(f"Analog output set to: {output_value}")

if __name__ == "__main__":
    main_app = Main()
    main_app.run()
