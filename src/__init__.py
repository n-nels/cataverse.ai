"""
Instrument Control System Package

A comprehensive package for controlling laboratory instruments including:
- Serial device communication
- NI DAQ device management
- Network messaging
- Experiment protocols
- Data logging and processing

Usage:
    from instrument_control import v_tot, notebook, metal, support, mass
    from instrument_control import SerialDevices, ActuatorManager, device_map
    from instrument_control import ActuatorControl, InstrumentOperations
"""

__version__ = "1.0.0"
__author__ = "nick nelson"

# Import and expose core classes and functions
from .core.config import (
    chiller_id,
    mass,
    metal,
    metal_density,
    metal_load,
    notebook,
    support,
    support_sa,
    v_tot,
    variac_id,
    variac_id_vsl,
)
from .devices.network.network_messaging import NetworkMessaging
from .devices.ni_daq.ni_usb6009_devices import NI_USB6009, ActuatorManager, device_map
from .devices.serial.serial_devices import SerialDevices
from .experiments.protocols.experiment_protocols import (
    adsorption_experiment,
    experiment_parameters,
    isotopic_exchange_calibration,
)
from .operations.actuator_control import ActuatorControl
from .operations.instrument_operations import InstrumentOperations

__all__ = [
    # Core configuration
    'v_tot', 'notebook', 'metal', 'support', 'mass', 'metal_load', 'metal_density', 'support_sa', 'chiller_id', 'variac_id', 'variac_id_vsl',
    
    # Device classes
    'SerialDevices', 'NI_USB6009', 'ActuatorManager', 'device_map', 'NetworkMessaging',
    
    # Operation classes
    'ActuatorControl', 'InstrumentOperations',
    
    # Experiment classes and functions
    'experiment_parameters', 'isotopic_exchange_calibration', 'adsorption_experiment'
]