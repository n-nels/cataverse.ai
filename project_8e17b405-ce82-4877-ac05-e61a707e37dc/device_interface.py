## device_interface.py

class DeviceInterface:
    """Class to control specific devices like MKS PDR2000 and Watlow controllers."""

    def __init__(self):
        """Initializes the DeviceInterface with default settings."""
        self.mks_device_id = "MKS_PDR2000"
        self.watlow_device_id = "WATLOW"

    def control_mks_pdr2000(self) -> None:
        """Controls the MKS PDR2000 device."""
        # Placeholder for actual control logic
        # Example: Send initialization command to MKS PDR2000
        print(f"Initializing and controlling device: {self.mks_device_id}")
        # Add specific commands and protocols for MKS PDR2000 here

    def control_watlow(self) -> None:
        """Controls the Watlow device."""
        # Placeholder for actual control logic
        # Example: Send initialization command to Watlow
        print(f"Initializing and controlling device: {self.watlow_device_id}")
        # Add specific commands and protocols for Watlow here
