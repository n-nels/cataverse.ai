# Directory Structure

Current layout of the CataVerse repository after cutover to the new architecture.

## Active Architecture

```text
cataverse.ai/orchestration/
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
│   ├── cleanup_plan.md
│   └── directory_structure.md
├── src/
│   ├── __init__.py
│   ├── config_loader.py       # typed config loader
│   ├── physics.py             # centralized physics calculations
│   ├── control/
│   │   ├── AGENTS.md
│   │   ├── __init__.py
│   │   ├── gas_delivery.py
│   │   ├── mass_spec_control.py
│   │   ├── spectrometer_control.py
│   │   ├── temperature_control.py
│   │   └── valves.py
│   ├── datalog/
│   │   ├── __init__.py
│   │   ├── file_io.py
│   │   ├── mass_spec_logger.py
│   │   ├── pressure_logger.py
│   │   └── temperature_logger.py
│   ├── experiments/
│   │   ├── AGENTS.md
│   │   ├── __init__.py
│   │   ├── adsorption.py
│   │   ├── isotopic_exchange.py
│   │   └── session.py
│   └── hardware/
│       ├── __init__.py
│       ├── analog_io.py
│       ├── connections.py
│       ├── mass_spec.py
│       ├── power.py
│       ├── pressure.py
│       ├── spectrometer.py
│       └── temperature.py
├── tests/
│   ├── conftest.py
│   ├── test_config_loader.py
│   ├── test_integration.py
│   ├── test_physics.py
│   ├── test_control/
│   ├── test_datalog/
│   ├── test_experiments/
│   └── test_hardware/
├── main.py                    # active architecture entry point
├── pyproject.toml
└── uv.lock
```

## Notes

### Active Architecture
- **config_loader.py**: Typed YAML configuration loader with frozen dataclasses
- **physics.py**: Centralized physics calculations (moles, pressures, adsorption)
- **hardware/**: Low-level device adapters (pressure, temperature, mass spec, analog I/O, spectrometer, power)
- **control/**: Control layer (valves, gas delivery, temperature control, spectrometer control, mass spec control)
- **datalog/**: Data logging (pressure, temperature, mass spec loggers, file I/O)
- **experiments/session.py**: Experiment session metadata manager
- **experiments/adsorption.py**: Adsorption experiment protocol using new architecture
- **experiments/isotopic_exchange.py**: Isotopic exchange calibration protocol using new architecture
- **main.py**: Active entry point using new architecture

### Migration Status
- Hardware validation completed.
- Legacy packages and transitional entrypoints removed.
- Cleanup plan tracking is in `docs/cleanup_plan.md`.
