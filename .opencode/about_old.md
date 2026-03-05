# Instrument Control System

A comprehensive Python package for controlling laboratory instruments including serial devices, NI DAQ devices, network messaging, and experiment automation.

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
```devContainer
```

