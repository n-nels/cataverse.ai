# Directory Structure

Current layout of the CataVerse repository after cutover to the new architecture.

## Active Architecture

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
│   ├── MIGRATION.md
│   └── refactor_plan-5.md
├── main.py                    # active architecture entry point
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
    ├── experiments/
    │   ├── AGENTS.md
    │   ├── __init__.py
    │   ├── adsorption.py
    │   ├── automation/
    │   │   └── __init__.py
    │   ├── isotopic_exchange.py
    │   └── session.py
    ├── hardware/
    │   ├── AGENTS.md
    │   ├── __init__.py
    │   ├── analog_io.py
    │   ├── connections.py
    │   ├── mass_spec.py
    │   ├── power.py
    │   ├── pressure.py
    │   ├── spectrometer.py
    │   └── temperature.py
    ├── control/
    │   ├── AGENTS.md
    │   ├── __init__.py
    │   ├── gas_delivery.py
    │   ├── spectrometer_control.py
    │   ├── temperature_control.py
    │   └── valves.py
    └── datalog/
        ├── AGENTS.md
        ├── __init__.py
        ├── file_io.py
        ├── mass_spec_logger.py
        ├── pressure_logger.py
        └── temperature_logger.py
```

## Notes

### Active Architecture
- **config_loader.py**: Typed YAML configuration loader with frozen dataclasses
- **physics.py**: Centralized physics calculations (moles, pressures, adsorption)
- **hardware/**: Low-level device adapters (pressure, temperature, mass spec, analog I/O, spectrometer, power)
- **control/**: Control layer (valves, gas delivery, temperature control, spectrometer control)
- **datalog/**: Data logging (pressure, temperature, mass spec loggers, file I/O)
- **experiments/session.py**: Experiment session metadata manager
- **experiments/adsorption.py**: Adsorption experiment protocol using new architecture
- **experiments/isotopic_exchange.py**: Isotopic exchange calibration protocol using new architecture
- **main.py**: Active entry point using new architecture

### Migration Status
- Hardware validation completed.
- Legacy packages and transitional entrypoints removed.
