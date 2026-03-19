# Directory Structure

Current refactored layout of the CataVerse repository.

```text
CataVerse-refactor/
├── .devcontainer/
├── .opencode/
├── .vscode/
├── AGENTS.md
├── C:/
├── config/
│   ├── devices.yaml
│   ├── paths.yaml
│   ├── sample.yaml
│   └── system.yaml
├── data_processing.py
├── docs/
│   ├── directory_structure.md
│   └── refactor_plan.md
├── kasa_smartPlug.py
├── LICENSE
├── main.py
├── opencode.json
├── pyproject.toml
├── tests/
├── uv.lock
└── src/
    ├── __init__.py
    ├── core/
    │   ├── AGENTS.md
    │   ├── __init__.py
    │   ├── config.py
    │   └── logging.py
    ├── devices/
    │   ├── AGENTS.md
    │   ├── __init__.py
    │   ├── extrel_mass_spec.py
    │   ├── kasa_plugs.py
    │   ├── mks_pressure.py
    │   ├── network_messaging.py
    │   ├── ni_usb6009.py
    │   ├── serial_devices.py
    │   └── watlow_controller.py
    ├── experiments/
    │   ├── AGENTS.md
    │   ├── __init__.py
    │   ├── adsorption.py
    │   ├── automation/
    │   │   └── __init__.py
    │   ├── isotopic_exchange.py
    │   └── parameters.py
    ├── operations/
    │   ├── AGENTS.md
    │   ├── __init__.py
    │   ├── actuator_control.py
    │   ├── code_reviewer_old.md
    │   └── instrument_operations.py
    └── utils/
        ├── AGENTS.md
        ├── __init__.py
        └── data_logging.py
```

Notes:
- Device subpackages (`devices/serial`, `devices/ni_daq`, `devices/network`) were flattened into top-level device modules.
- Experiment protocol classes were split into dedicated modules:
  - `parameters.py`
  - `adsorption.py`
  - `isotopic_exchange.py`
