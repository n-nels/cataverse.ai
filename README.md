# Instrument Control System

A comprehensive Python package for controlling laboratory instruments including serial devices, NI DAQ devices, network messaging, and experiment automation.

## 🏗️ Package Structure

```
instrument_control/
├── instrument_control/          # Main package
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py
│   ├── devices/
│   │   ├── __init__.py
│   │   ├── serial/
│   │   │   ├── __init__.py
│   │   │   └── serial_devices.py
│   │   ├── ni_daq/
│   │   │   ├── __init__.py
│   │   │   └── ni_usb6009_devices.py
│   │   └── network/
│   │       ├── __init__.py
│   │       └── network_messaging.py
│   ├── experiments/
│   │   ├── __init__.py
│   │   ├── protocols/
│   │   │   ├── __init__.py
│   │   │   └── experiment_protocols.py
│   │   └── automation/
│   │       ├── __init__.py
│   │       └── catalysis_autolab/
│   ├── operations/
│   │   ├── __init__.py
│   │   ├── actuator_control.py
│   │   └── instrument_operations.py
│   └── utils/
│       ├── __init__.py
│       └── data_logging.py
├── instrument_control_venv/        # Virtual environment for package
├── legacy/                      # Original code (backup)
├── tests/                       # Test suite
├── docs/                        # Documentation
├── main_new.py                  # New entry point using package structure
└── main.py                      # Original entry point (still working)
```

## 🚀 Features

### Device Management
- **Serial Devices**: MKS pressure gauges, Watlow temperature controllers
- **NI DAQ Devices**: USB-6009 data acquisition and actuator control
- **Network Messaging**: ZeroMQ-based communication with spectrometers
- **Actuator Control**: Safe operation of valves and mass flow controllers

### Experiment Automation
- **Protocol Management**: Adsorption experiments, isotopic exchange calibration
- **Data Logging**: CSV-based logging with automatic directory creation
- **Parameter Management**: Material parameters, experiment tracking

### Safety Features
- **Pressure Safety**: Overpressure protection and automatic evacuation
- **Device Isolation**: Safe actuator control with interlocks
- **Temperature Monitoring**: Real-time temperature tracking and control

## 🛠️ Installation

### Prerequisites
```bash
# Core dependencies
pip install numpy pandas

# Hardware dependencies (for device communication)
pip install pymodbus nidaqmx zmq pyserial
```

### Setup
```bash
# Clone repository
git clone <repository-url>
cd instrument_control

# Create and activate virtual environment
python -m venv instrument_control_venv
instrument_control_venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## 🎯 Usage

### Basic Usage
```python
from instrument_control.core.config import v_tot, notebook, metal
from instrument_control.devices.serial.serial_devices import SerialDevices
from instrument_control.devices.ni_daq.ni_usb6009_devices import ActuatorManager
from instrument_control.operations.actuator_control import ActuatorControl
from instrument_control.experiments.protocols.experiment_protocols import experiment_parameters

# Initialize devices
serial = SerialDevices()
actuators = ActuatorManager(device_map)
actuator_control = ActuatorControl(actuators, serial)

# Run experiment
exp_params = experiment_parameters(notebook, mass, metal, metal_load, metal_density, support, support_sa, v_tot)
```

### Virtual Environment
The package includes a pre-configured virtual environment `instrument_control_venv/` with all required dependencies installed. Use:

```bash
# Activate the package environment
instrument_control_venv\Scripts\activate
```

## 📁 Development

### Project Structure
This project follows Python packaging best practices with clear separation of concerns:
- **Core**: Configuration and fundamental constants
- **Devices**: Hardware communication interfaces
- **Operations**: High-level instrument control
- **Experiments**: Experimental protocols and automation
- **Utils**: Shared utilities and data logging

### Testing
```bash
# Run tests (when implemented)
python -m pytest tests/

# Test package imports
python -c "from instrument_control.core.config import v_tot; print('Import successful')"
```

## 📄 License

[License](LICENSE)

## 🤝 Contributing

Contributions are welcome! Please ensure:
- Code follows the project's style guidelines
- All tests pass
- Documentation is updated as needed
- Use appropriate type hints

## 📞 Support

For questions, issues, or feature requests, please open an issue on the project repository.
