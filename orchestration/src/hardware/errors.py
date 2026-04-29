"""Hardware-layer exception hierarchy.

These exceptions are raised by hardware adapters when unrecoverable failures
occur. The control or experiment layer catches them and triggers a safe-shutdown
sequence (close gas valves, stop heating, turn on chiller, close log files).

Hierarchy::

    HardwareError
    ├── HardwareConnectionError   — device not connected or connection lost
    ├── HardwareReadError         — failed to read from a device
    ├── HardwareMappingError      — unknown actuator ID or channel mapping
    └── ThermocoupleFault         — thermocouple malfunction detected by Watlow
"""


class HardwareError(Exception):
    """Base exception for all hardware-layer errors."""


class HardwareConnectionError(HardwareError):
    """Raised when a hardware device is not connected or the connection is lost."""


class HardwareReadError(HardwareError):
    """Raised when a read operation on a hardware device fails."""


class HardwareMappingError(HardwareError):
    """Raised when an actuator ID or channel mapping is unknown."""


class ThermocoupleFault(HardwareError):
    """Raised when the Watlow controller detects a thermocouple malfunction."""
