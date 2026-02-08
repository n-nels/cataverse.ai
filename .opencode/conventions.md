# Code Conventions

This document outlines the coding style, naming, and formatting guidelines for the IR-Spectro-Node project.

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
- **Functions**: snake_case (e.g., `voight_fit()`)
- **Variables**: snake_case (e.g., `peak_area`, `file_name`)
- **Constants**: UPPER_SNAKE_CASE 
- **Classes**: PascalCase (rarely used in this codebase)
- **File names**: snake_case (e.g., `ir_peakFit_carbonyl_v5.py`)

Note: The codebase has mixed conventions (e.g., `PipeCommand` uses PascalCase for functions). Follow snake_case for new code.

### Formatting
- 4 spaces for indentation (no tabs)
- Maximum line length not strictly enforced but keep reasonable (~100-120 chars)
- Blank lines between top-level functions (2 lines)
- One blank line between related code blocks

### Types
- Type hints are encouraged for all new and refactored code to improve clarity and maintainability.
- Use modern Python 3.12+ syntax for type hints.

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
