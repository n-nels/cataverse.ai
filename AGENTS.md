# AGENTS.md - Instrument Control System

## Build/Test Commands
- **Run main experiment**: `python main.py`
- **Run new package experiment**: `python main_new.py`
- **Run test script**: `python test.py`
- **Install dependencies**: `pip install -r requirements.txt`
- **Install package dependencies**: `pip install pymodbus nidaqmx zmq pyserial`
- **Activate package environment**: `instrument_control_venv\Scripts\activate`
- **Run tests in venv**: `instrument_control_venv\Scripts\activate && python -m pytest tests/`

## Code Style Guidelines

### Imports
- Standard library imports first, then third-party, then local modules
- Use `from typing import List, Tuple, Optional` for type hints
- Keep import statements organized and avoid unused imports

### Formatting & Types
- Use descriptive variable names (e.g., `evac_temp`, `adsorbate_pressure`)
- Include type hints for function parameters and return values
- Use docstrings for all classes and public methods following the existing pattern
- Maintain consistent indentation (4 spaces)

### Naming Conventions
- Classes: PascalCase (e.g., `InstrumentOperations`, `ActuatorControl`)
- Functions/variables: snake_case (e.g., `deliver_gas_to_mfld`, `read_pressure`)
- Constants: UPPER_SNAKE_CASE (e.g., `R`, `V_TOT`, `CHILLER_ID`)
- Private methods: prefix with underscore

### Error Handling
- Use try-except blocks for device communication
- Include descriptive error messages with device names
- Implement connection recovery logic for serial devices
- Use sys.exit() for critical safety failures

### Device Safety
- Always check pressure limits before gas delivery
- Implement timeout mechanisms for long-running operations
- Include safety interlocks for critical actuators (TurboPump, MassSpec)
- Log all actuator state changes for debugging

### File Organization
- Keep device-specific logic in separate modules
- Use config.py for all constants and configuration
- Maintain data logging consistency across experiments
- Follow existing module structure for new features