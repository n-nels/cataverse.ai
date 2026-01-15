# Agent Guidelines for IR Spectroscopy Node

This file provides guidelines for AI agents working on this IR spectroscopy analysis and OPUS instrument control project.

---

## Build/Lint/Test Commands

### Environment Setup
```bash
# Install dependencies (uses uv package manager)
uv sync

# Activate virtual environment
# Windows: .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
```

### Running the Application
```bash
# Main entry point
python main.py

# Peak fitting script
python ir_peakFit_carbonyl_v5.py

# OPUS instrument control server
python opusWrapper.py

# Integration testing
python test.py
```

### Testing
```bash
# Run specific test function (no framework currently configured)
python -c "from test import integrate_irIsoXchg; integrate_irIsoXchg('path/to/file.csv')"

# Run pytest (if added)
pytest test.py -v

# Run specific test with pytest
pytest test.py::test_function_name -v
```

### Code Quality
```bash
# Type checking (if mypy is added)
mypy *.py

# Linting (if ruff is added)
ruff check .

# Format (if ruff format is added)
ruff format .
```

---

## Code Style Guidelines

### Imports
- Standard library imports first, then third-party, then local modules
- Single-line imports preferred: `import numpy as np`, `import pandas as pd`
- Avoid `from module import *` except for specific cases
- Group related imports together

Example:
```python
import os
import time
import numpy as np
import pandas as pd
from scipy.signal import find_peaks
```

### Naming Conventions
- **Functions**: snake_case (e.g., `voight_fit()`, `DoSampleMeasurement()`)
- **Variables**: snake_case (e.g., `peak_area`, `file_name`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `XpmName`, `DefaultPrintout`)
- **Classes**: PascalCase (rarely used in this codebase)
- **File names**: snake_case (e.g., `ir_peakFit_carbonyl_v5.py`)

Note: The codebase has mixed conventions (e.g., `PipeCommand` uses PascalCase for functions). Follow snake_case for new code.

### Formatting
- 4 spaces for indentation (no tabs)
- Maximum line length not strictly enforced but keep reasonable (~100-120 chars)
- Blank lines between top-level functions (2 lines)
- One blank line between related code blocks

### Types
- Type hints are NOT used in the existing codebase
- Avoid adding type hints unless necessary for clarity
- If adding, use Python 3.12+ syntax

### Error Handling
- Use try-except blocks with explicit error messages
- Print errors with context: `print(f"Error: {e}")`
- Use specific exceptions when possible
- Return early on failure conditions

Example:
```python
try:
    df = pd.read_csv(file_path)
except Exception as e:
    print(f"Error reading {file_path}: {e}")
    return None
```

### Path Handling
- Use raw strings for Windows paths: `r'C:\Data\path'`
- Use `os.path.join()` for cross-platform compatibility
- Prefer forward slashes in string literals, convert as needed

### String Formatting
- Use f-strings for variable interpolation: `f'{variable}'`
- Use concatenation for static strings: `"prefix" + suffix`

### Functions
- Use docstrings for public functions (not consistently used)
- Keep functions focused and single-purpose
- Use descriptive names that indicate action and object

### Global Variables
- The codebase uses global variables extensively (e.g., `hPipe`, `XpmPath`)
- For new code, prefer passing parameters
- If using globals is necessary, document them at module level

### Comments
- Minimal inline comments (current style)
- Add comments only for non-obvious logic
- Comment out unused code with `#` at line start
- Avoid commenting out large blocks - delete instead

### File Organization
- Single-purpose files (e.g., `ir_peakFit_carbonyl_v5.py` for peak fitting)
- Archive old versions in `arxiv/` directory
- Keep utility functions together (e.g., `readParams.py`, `delete_files.py`)

### Scientific Computing Patterns
- Use NumPy arrays for numerical operations
- Use pandas DataFrames for tabular data
- Use scipy.optimize.curve_fit for fitting
- Use lmfit for complex parameter fitting
- Use pybaselines for baseline correction

### ZMQ Messaging
- Uses pyzmq for instrument control via named pipe
- REP/REQ pattern for server-client communication
- Handle timeouts and connection errors gracefully

---

## Project-Specific Notes

### Peak Fitting
- Primary script: `ir_peakFit_carbonyl_v5.py`
- Uses Voigt profile fitting for carbonyl peaks
- Peak lists are hardcoded for 13CO and 12CO isotopes
- Wavenumber range: 1750-2250 cm^-1

### OPUS Integration
- Controls Bruker OPUS instrument via named pipe: `\\.\pipe\OPUS`
- Functions in `opusWrapper.py` and `opusWrapper_v2.py`
- Commands sent via `PipeCommand()` function
- Experiment files (`.xpm`) stored in specific paths

### Data Paths
- Input data: `C:\Data\OpusFiles\`
- Processed data: `C:\Data\OpusConvert_*\`
- Output data: `C:\Data\peakFit\`
- Calibration data: `X:\peakFit\`

### Key Dependencies
- lmfit (peak fitting)
- pandas, numpy (data processing)
- matplotlib (visualization)
- scipy (scientific computing)
- pybaselines (baseline correction)
- pyzmq (messaging)

---

## Workflow Guidelines

1. **Modify existing code**: Follow the patterns in the file you're editing
2. **Add new features**: Create new file with descriptive name
3. **Refactor**: Maintain backward compatibility where possible
4. **Test changes**: Run the relevant script with sample data
5. **Document**: Add comments only for non-obvious logic
6. **Archive**: Move old versions to `arxiv/` before major changes

---

## Development Environment

- Python: >=3.12
- Package manager: uv
- OS: Windows (due to OPUS integration)
- IDE: VSCode (configuration in `.vscode/`)
