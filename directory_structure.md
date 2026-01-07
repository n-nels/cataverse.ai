# CataVerse Directory Structure

```
CataVerse/
├── .vscode/
│   └── launch.json
├── docs/
│   └── README.md
├── instrument_control/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py
│   ├── devices/
│   │   ├── __init__.py
│   │   ├── network/
│   │   │   ├── __init__.py
│   │   │   └── network_messaging.py
│   │   ├── ni_daq/
│   │   │   ├── __init__.py
│   │   │   └── ni_usb6009_devices.py
│   │   └── serial/
│   │       ├── __init__.py
│   │       └── serial_devices.py
│   ├── experiments/
│   │   ├── __init__.py
│   │   ├── automation/
│   │   │   └── __init__.py
│   │   └── protocols/
│   │       ├── __init__.py
│   │       └── experiment_protocols.py
│   ├── operations/
│   │   ├── __init__.py
│   │   ├── actuator_control.py
│   │   └── instrument_operations.py
│   └── utils/
│       ├── __init__.py
│       └── data_logging.py
├── legacy/
│   ├── catalysis_autolab/
│   │   ├── data/
│   │   │   ├── .DS_Store
│   │   │   ├── carb_history.csv
│   │   │   ├── exp_history.csv
│   │   │   ├── experiment_20250807_design_space.parquet
│   │   │   ├── fsd_history.csv
│   │   │   └── selected_experiments_20250807.csv
│   │   ├── .DS_Store
│   │   ├── data.py
│   │   ├── decision_engine.py
│   │   └── peak_feature_engr.py
│   ├── catalysis_autolab_bak/
│   │   ├── data/
│   │   │   ├── carb_history.csv
│   │   │   ├── exp_history.csv
│   │   │   ├── experiment_20250731_design_space.parquet
│   │   │   └── selected_experiments_20250731.csv
│   │   ├── carb_history.csv
│   │   ├── data.py
│   │   ├── decision_engine.py
│   │   ├── exp_history.csv
│   │   ├── fsd_history.csv
│   │   └── peak_feature_engr.py
│   ├── actuator_control.py
│   ├── config.py
│   ├── copy_files_agent.md
│   ├── data_logging.py
│   ├── experiment_protocols.py
│   ├── instrument_operations.py
│   ├── kasa_smartPlug.py
│   ├── main.py
│   ├── network_messaging.py
│   ├── ni_usb6009_devices.py
│   ├── README.md
│   ├── REFACTOR_COMPLETE.md
│   ├── serial_devices.py
│   └── test.py
├── tests/
│   ├── README.md
│   └── .dependencies.json
├── .gitignore
├── AGENTS.md
├── code_reviewer.md
├── data_processing.py
├── kasa_smartPlug.py
├── LICENSE
├── main.py
├── README.md
├── requirements.txt
```

## Directory Overview

### Root Files
- **main.py** - Main experiment entry point
- **requirements.txt** - Python dependencies
- **README.md** - Project documentation
- **AGENTS.md** - Development guidelines and commands

### instrument_control/
Main package structure for the refactored instrument control system:
- **core/** - Core configuration and initialization
- **devices/** - Device control modules (network, NI DAQ, serial)
- **experiments/** - Experiment automation and protocols
- **operations/** - High-level instrument and actuator operations
- **utils/** - Data logging utilities

### legacy/
Previous version of the catalysis autolab system:
- **catalysis_autolab/** - Recent legacy version with data
- **catalysis_autolab_bak/** - Backup version
- Various individual Python modules from the old structure

### tests/
Test suite for the instrument control system

Generated on: 2025-01-07