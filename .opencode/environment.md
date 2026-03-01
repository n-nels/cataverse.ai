# Environment and Build

 This document contains information on the development environment and build commands.

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

### Running the Application (Production)
```bash
# Ensure you are in the production repository
cd C:\Users\labuser\CataVerse\ir-spectro-node

# OPUS instrument control server (ZMQ)
python scripts\run_server.py

# Norhof LN2 pump control loop
python scripts\run_norhoff.py

# Peak fitting entry point
python scripts\run_peak_fit.py <path_to_input_file>
```

### Testing
```bash
# From the repository root
cd C:\Users\labuser\CataVerse\ir-spectro-node

# Basic import smoke tests (example)
python -m pytest tests -q  # if/when pytest tests are added
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

## Project-Specific Notes

### Key Dependencies
- lmfit (peak fitting)
- pandas, numpy (data processing)
- matplotlib (visualization)
- scipy (scientific computing)
- pybaselines (baseline correction)
- pyzmq (messaging)

---
## Development Environment

- Python: >=3.12
- Package manager: uv
- OS: Windows (due to OPUS integration)
- IDE: VSCode (configuration in `.vscode/`)
