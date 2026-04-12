# Directory Structure

Current refactored layout of the CataVerse repository showing both legacy and new architecture.

## New Architecture (v2)

```text
CataVerse-refactor/
├── .devcontainer/
├── .opencode/
├── .vscode/
├── AGENTS.md
├── config/
│   ├── devices.yaml
│   ├── paths.yaml
│   ├── sample.yaml
│   └── system.yaml
├── docs/
│   ├── directory_structure.md
│   ├── refactor_plan.md
│   └── refactor_plan-5.md
├── main.py                    # legacy — pending hardware validation
├── main_v2.py                 # new architecture entry point
├── opencode.json
├── pyproject.toml
├── tests/
│   ├── test_experiments/
│   │   ├── test_adsorption.py
│   │   └── test_session.py
│   ├── test_integration.py
│   └── ... (other test files)
├── uv.lock
└── src/
    ├── __init__.py
    ├── config_loader.py       # new typed config loader
    ├── physics.py             # centralized physics calculations
    ├── core/                  # legacy — pending hardware validation
    │   ├── AGENTS.md
    │   ├── __init__.py
    │   ├── config.py
    │   └── logging.py
    ├── devices/               # legacy — pending hardware validation
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
    │   ├── adsorption.py      # legacy — pending hardware validation
    │   ├── adsorption_v2.py   # new architecture
    │   ├── automation/
    │   │   └── __init__.py
    │   ├── isotopic_exchange.py      # legacy — pending hardware validation
    │   ├── isotopic_exchange_v2.py   # new architecture
    │   ├── parameters.py      # legacy — pending hardware validation
    │   └── session.py         # new architecture
    ├── operations/            # legacy — pending hardware validation
    │   ├── AGENTS.md
    │   ├── __init__.py
    │   ├── actuator_control.py
    │   └── instrument_operations.py
    ├── utils/                 # legacy — pending hardware validation
    │   ├── AGENTS.md
    │   ├── __init__.py
    │   └── data_logging.py
    ├── hardware/              # new architecture
    │   ├── AGENTS.md
    │   ├── __init__.py
    │   ├── analog_io.py
    │   ├── connections.py
    │   ├── mass_spec.py
    │   ├── power.py
    │   ├── pressure.py
    │   ├── spectrometer.py
    │   └── temperature.py
    ├── control/               # new architecture
    │   ├── AGENTS.md
    │   ├── __init__.py
    │   ├── gas_delivery.py
    │   ├── spectrometer_control.py
    │   ├── temperature_control.py
    │   └── valves.py
    └── datalog/               # new architecture
        ├── AGENTS.md
        ├── __init__.py
        ├── file_io.py
        ├── mass_spec_logger.py
        ├── pressure_logger.py
        └── temperature_logger.py
```

## Notes

### New Architecture (v2)
- **config_loader.py**: Typed YAML configuration loader with frozen dataclasses
- **physics.py**: Centralized physics calculations (moles, pressures, adsorption)
- **hardware/**: Low-level device adapters (pressure, temperature, mass spec, analog I/O, spectrometer, power)
- **control/**: Control layer (valves, gas delivery, temperature control, spectrometer control)
- **datalog/**: Data logging (pressure, temperature, mass spec loggers, file I/O)
- **experiments/session.py**: Experiment session metadata manager
- **experiments/adsorption_v2.py**: Adsorption experiment using new architecture
- **experiments/isotopic_exchange_v2.py**: Isotopic exchange calibration using new architecture
- **main_v2.py**: New entry point using v2 architecture

### Legacy Packages (pending hardware validation)
- **core/**: Legacy configuration and logging
- **devices/**: Legacy device drivers
- **operations/**: Legacy instrument operations and actuator control
- **utils/**: Legacy data logging utilities
- **experiments/adsorption.py**: Legacy adsorption experiment
- **experiments/isotopic_exchange.py**: Legacy isotopic exchange calibration
- **experiments/parameters.py**: Legacy experiment parameters
- **main.py**: Legacy entry point

### Migration Path
1. New architecture is built alongside legacy code
2. Hardware validation will verify new architecture works with physical devices
3. After validation, legacy packages will be removed
4. `main_v2.py` will replace `main.py`
