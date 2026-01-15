# IR Spectroscopy Node - Directory Restructuring Plan

**Date**: 2026-01-14
**Status**: Planning Phase (READ-ONLY)
**Priority**: Safe migration with minimal disruption to running OPUS server

---

## Executive Summary

This plan outlines a safe, phased approach to professionalize the directory structure of the IR spectroscopy codebase. The primary challenge is that `opusWrapper.py` runs continuously as a ZMQ server and cannot be disrupted during experiments.

**Key Findings:**
- OPUS server runs continuously listening on `tcp://130.20.216.127:5555`
- 14+ hardcoded paths scattered across files (e.g., `C:\Data\OpusFiles\`, `X:/ms_calibrations/`)
- Extensive use of global variables (11+ in opusWrapper.py alone)
- No formal package structure currently exists
- Files imported via `sys.path.append(".")` rather than proper package structure

---

## Phase 0: Pre-Requisites & Safety Setup

### 0.1 Establish Version Control Baseline

**Goal**: Create instant rollback capability

```bash
# Commit current working state
git add .
git commit -m "baseline: production code before refactoring - Jan 2026"

# Tag for easy reference
git tag -a production-v0.1.0-baseline -m "Production baseline before directory restructuring"

# Verify
git log --oneline -1
git tag -l
```

**Success Criteria**:
- [ ] All files committed to git
- [ ] Tag `production-v0.1.0-baseline` created
- [ ] Can rollback via `git checkout production-v0.1.0-baseline`

### 0.2 Create Refactor Working Copy

**Goal**: Isolate all changes from production code

```bash
# Navigate to parent directory
cd C:\Users\labuser\CataVerse\

# Create refactor copy
xcopy /E /I /H ir-spectro-node ir-spectro-node-refactor\

# Verify copy completeness
diff /s ir-spectro-node ir-spectro-node-refactor | findstr "Differences"
# Should show minimal differences (only .git folder excluded)
```

**Working Structure During Refactoring**:
```
C:\Users\labuser\CataVerse\
├── ir-spectro-node\          ← PRODUCTION (OPUS server running here)
│   └── [running system]
└── ir-spectro-node-refactor\  ← REFACTOR (all changes here)
    └── [development work]
```

**Success Criteria**:
- [ ] Complete copy created in `ir-spectro-node-refactor\`
- [ ] Original `ir-spectro-node\` remains untouched
- [ ] OPUS server continues running from original location

---

## Phase 1: Target Directory Structure Design

### 1.1 Proposed Professional Structure

```
ir-spectro-node/
│
├── src/                          # Main source code package
│   ├── __init__.py               # Makes src a proper Python package
│   │
│   ├── core/                     # Core infrastructure
│   │   ├── __init__.py
│   │   ├── config.py             # Configuration management (new)
│   │   └── constants.py         # Application-wide constants
│   │
│   ├── instrument/                # OPUS instrument control
│   │   ├── __init__.py
│   │   ├── opus_wrapper.py      # From opusWrapper.py (refactored)
│   │   ├── opus_wrapper_v2.py   # From opusWrapper_v2.py
│   │   ├── opus_acquire.py     # From opusAcquire_4.py
│   │   └── pipe_command.py     # Extract PipeCommand function (new)
│   │
│   ├── analysis/                 # Data analysis & peak fitting
│   │   ├── __init__.py
│   │   ├── peak_fitting.py      # From ir_peakFit_carbonyl_v5.py
│   │   ├── isotopic_exchange.py  # Extracted from test.py
│   │   ├── calibration.py       # Calibration curve functions
│   │   └── kinetic_fitting.py  # PFO kinetic fitting (extract if needed)
│   │
│   └── utils/                   # Utility functions
│       ├── __init__.py
│       ├── file_ops.py          # From readParams.py, delete_files.py, rename_files.py
│       ├── subtract_ifg.py      # From subtractIFG.py
│       ├── tpd_postprocess.py  # From tpd_postProcess.py
│       └── data_io.py          # Generic I/O operations (new)
│
├── scripts/                      # Executable entry points
│   ├── run_server.py            # Starts OPUS ZMQ server
│   ├── run_peak_fit.py          # Executes peak fitting
│   ├── run_acquire.py           # Runs OPUS acquisition sequences
│   ├── run_isotopic_exchange.py # Isotopic exchange processing
│   └── main.py                # Unified CLI entry point
│
├── config/                      # Configuration files
│   ├── paths.yaml              # Path configurations (centralized)
│   ├── opus_settings.yaml      # OPUS-specific settings
│   └── calibration_params.yaml  # Fitting parameters
│
├── tests/                       # Test suite
│   ├── __init__.py
│   ├── conftest.py            # pytest fixtures
│   ├── test_instrument/
│   │   ├── __init__.py
│   │   ├── test_opus_wrapper.py
│   │   └── test_opus_acquire.py
│   ├── test_analysis/
│   │   ├── __init__.py
│   │   ├── test_peak_fitting.py
│   │   └── test_calibration.py
│   └── test_integration/
│       ├── __init__.py
│       └── test_workflows.py
│
├── docs/                        # Documentation
│   ├── architecture.md          # System architecture
│   ├── migration_guide.md       # Old → New structure mapping
│   ├── api_documentation.md    # Function/API documentation
│   └── calibration_guide.md    # Calibration procedures
│
├── arxiv/                       # Archive (preserve existing)
│   └── [all archived files remain]
│
├── .env.example                 # Environment variable template (new)
├── .env.local                   # Local environment (existing, add to .gitignore)
├── .gitignore
├── .python-version
├── pyproject.toml              # Updated for new structure
├── AGENTS.md                   # Existing, review for updates
├── README.md                   # To be enhanced
├── DIRECTORY_STRUCTURE.md        # Existing, update post-migration
└── REFACTORING_PLAN.md        # This file
```

### 1.2 File Migration Mapping

| Current File | New Location | Notes |
|--------------|---------------|--------|
| `opusWrapper.py` | `src/instrument/opus_wrapper.py` | Main server, refactor globals |
| `opusWrapper_v2.py` | `src/instrument/opus_wrapper_v2.py` | Alternate version |
| `opusAcquire_4.py` | `src/instrument/opus_acquire.py` | Acquisition sequences |
| `ir_peakFit_carbonyl_v5.py` | `src/analysis/peak_fitting.py` | Core fitting logic |
| `test.py` | `src/analysis/isotopic_exchange.py` | Extract integrate_irIsoXchg |
| `readParams.py` | `src/utils/file_ops.py` | Merge with other file utilities |
| `delete_files.py` | `src/utils/file_ops.py` | Merge |
| `rename_files.py` | `src/utils/file_ops.py` | Merge |
| `subtractIFG.py` | `src/utils/subtract_ifg.py` | Standalone utility |
| `tpd_postProcess.py` | `src/utils/tpd_postprocess.py` | TPD processing |
| `main.py` | `scripts/main.py` | Convert to proper entry point |
| `Norhoff.py` | `src/utils/norhoff.py` | Keep as utility |

---

## Phase 2: Configuration Consolidation

### 2.1 Centralize Path Configuration

**Problem**: 14+ hardcoded paths across files

**Solution**: Create `config/paths.yaml`

```yaml
# config/paths.yaml
# Path configuration for IR Spectroscopy Node
# Edit these paths to match your local setup

# Data directories
data:
  opus_files: "C:\\Data\\OpusFiles"
  opus_calibrations: "C:\\Data\\OpusCalibrations"
  opus_read_params: "C:\\Data\\OpusReadParams"

  opus_convert:
    lg_reflectance: "C:\\Data\\OpusConvert_lgRfl"
    sub_ifg: "C:\\Data\\OpusConvert_subIFG_lgRfl"
    ssc: "C:\\Data\\OpusConvert_SSC"
    fsd: "C:\\Data\\OpusConvert_fsd"

  peak_fit: "C:\\Data\\peakFit"

# Calibration directories
calibration:
  root: "X:/ms_calibrations"
  ir_root: "C:/Data/OpusCalibrations"
  output: "C:/Data/peakFit"

# Cloud/SFTP
sftp:
  copy_script: "C:\\sftp\\copybutton.bat"

# OPUS specific
opus:
  pipe: "\\\\.\\pipe\\OPUS"
  server:
    host: "130.20.216.127"
    port: 5555
```

### 2.2 Create Configuration Loader

**New File**: `src/core/config.py`

```python
# src/core/config.py
"""Configuration management for IR Spectroscopy Node."""

import os
import yaml
from pathlib import Path
from typing import Dict, Any

class Config:
    """Configuration manager with path resolution."""

    def __init__(self, config_path: str = None):
        """Initialize configuration from YAML file."""
        if config_path is None:
            # Default to config/paths.yaml relative to project root
            config_path = Path(__file__).parent.parent.parent / "config" / "paths.yaml"

        self.config_path = Path(config_path)
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value using dot notation (e.g., 'data.opus_files')."""
        keys = key_path.split('.')
        value = self._config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def get_path(self, key_path: str, *subfolders) -> Path:
        """Get and construct a path from configuration."""
        base_path = Path(self.get(key_path))

        if subfolders:
            return base_path.joinpath(*subfolders)

        return base_path

    def ensure_dirs(self, key_path: str, *subfolders) -> Path:
        """Get path and ensure directory exists."""
        path = self.get_path(key_path, *subfolders)
        path.mkdir(parents=True, exist_ok=True)
        return path

# Global config instance
_config: Config = None

def get_config() -> Config:
    """Get or create global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
```

### 2.3 Files Requiring Path Updates

**High Priority** (affects production):
- `src/instrument/opus_wrapper.py` - Lines 313-322 (define_paths function)
- `src/instrument/opus_acquire.py` - Lines 289, 291-293
- `src/analysis/peak_fitting.py` - Lines 849-862
- `src/analysis/isotopic_exchange.py` - Lines 361, 563

**Medium Priority** (utility functions):
- `src/utils/file_ops.py` - readParams.py content
- `src/utils/subtract_ifg.py` - subtractIFG.py lines 58-65

**Low Priority** (archive files):
- All files in `arxiv/` (can remain as-is)

---

## Phase 3: Implementation Steps (in Refactor Copy)

### 3.1 Create Directory Structure

**Script** (run in `ir-spectro-node-refactor\`):

```bash
# Create all directories
mkdir src
mkdir src\core src\instrument src\analysis src\utils
mkdir scripts tests
mkdir tests\test_instrument tests\test_analysis tests\test_integration
mkdir config docs

# Verify structure
tree /F /A
```

### 3.2 Create `__init__.py` Files

**Purpose**: Make directories proper Python packages

```bash
# Create empty __init__.py files
echo. > src\__init__.py
echo. > src\core\__init__.py
echo. > src\instrument\__init__.py
echo. > src\analysis\__init__.py
echo. > src\utils\__init__.py
echo. > scripts\__init__.py
echo. > tests\__init__.py
echo. > tests\test_instrument\__init__.py
echo. > tests\test_analysis\__init__.py
echo. > tests\test_integration\__init__.py
```

### 3.3 Move Files to New Locations

```bash
# Core files
# copy src\core\config.py src\core\
# (This file needs to be created first)

# Instrument files
copy opusWrapper.py src\instrument\opus_wrapper.py
copy opusWrapper_v2.py src\instrument\opus_wrapper_v2.py
copy opusAcquire_4.py src\instrument\opus_acquire.py

# Analysis files
copy ir_peakFit_carbonyl_v5.py src\analysis\peak_fitting.py
# test.py will be split and processed separately

# Utility files
# Merge readParams.py, delete_files.py, rename_files.py
copy readParams.py src\utils\file_ops.py
copy delete_files.py >> src\utils\file_ops.py
copy rename_files.py >> src\utils\file_ops.py

copy subtractIFG.py src\utils\subtract_ifg.py
copy tpd_postProcess.py src\utils\tpd_postprocess.py
copy Norhoff.py src\utils\norhoff.py

# Scripts
copy main.py scripts\main.py
```

### 3.4 Update Imports in Moved Files

**Pattern Changes Required**:

**Current**: `sys.path.append(".")` + `import ir_peakFit_carbonyl_v5 as fit`
**New**: `from src.analysis.peak_fitting import voight_fit as fit`

**Files to Update**:

1. **src/instrument/opus_wrapper.py**
   ```python
   # OLD (Line 2)
   import ir_peakFit_carbonyl_v5 as fit

   # NEW
   from src.analysis.peak_fitting import voight_fit as fit
   ```

2. **src/instrument/opus_acquire.py**
   - Remove `sys.path.append(".")`
   - Update local imports if any

3. **All files** - Update imports for moved utilities:
   ```python
   # When calling readParams functionality:
   # OLD: import readParams
   # NEW: from src.utils.file_ops import read_parameters
   ```

### 3.5 Create Entry Point Scripts

**scripts/run_server.py** (primary - must work with minimal changes):

```python
#!/usr/bin/env python
"""Entry point for OPUS ZMQ server."""

import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from src.instrument.opus_wrapper import run_server, main_tpd

if __name__ == "__main__":
    # For now, maintain backward compatibility
    # Can be refined later
    run_server()
```

**scripts/run_peak_fit.py**:

```python
#!/usr/bin/env python
"""Entry point for peak fitting."""

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from src.analysis.peak_fitting import voight_fit

if __name__ == "__main__":
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        voight_fit(file_path)
    else:
        print("Usage: python scripts/run_peak_fit.py <file_path>")
        sys.exit(1)
```

### 3.6 Create Configuration Files

**config/paths.yaml** (create from template in Section 2.1)

**Add pyyaml dependency**:
```toml
# Add to pyproject.toml
[project]
dependencies = [
    "lmfit>=1.3.4",
    "matplotlib>=3.10.8",
    "numpy>=2.4.1",
    "pandas>=2.3.3",
    "pybaselines>=1.2.1",
    "pyzmq>=27.1.0",
    "scipy>=1.17.0",
    "pyyaml>=6.0.1",  # NEW
]
```

### 3.7 Integrate Config System

**In each file using paths**, replace hardcoded values:

**Example in `src/instrument/opus_wrapper.py`**:

```python
# OLD (define_paths function, lines 300-330)
def define_paths():
    global path_OpusFiles
    path_OpusFiles = "C:\\Data\\OpusFiles\\" + foldername
    # ... more hardcoded paths

# NEW
from src.core.config import get_config

def define_paths():
    global path_OpusFiles, path_OpusCalibrations, ...

    config = get_config()

    path_OpusFiles = config.get_path("data.opus_files", foldername)
    path_OpusCalibrations = config.get_path("data.opus_calibrations", foldername)
    path_CalibrationData = config.get_path("calibration.output", foldername, "CalibrationData")
    # ... continue for all paths
```

### 3.8 Handle test.py Split

**File**: `test.py` contains multiple functions

**Action**: Split into multiple files:
- `src/analysis/isotopic_exchange.py` - `integrate_irIsoXchg()` function
- `src/analysis/calibration.py` - `generate_calibCurve()` and `generate_calibCurve_v2()`
- Keep any integration tests for later migration to `tests/`

### 3.9 Update pyproject.toml

```toml
[project]
name = "ir-spectro-node"
version = "0.2.0"  # Update version
description = "Infrared spectroscopy analysis and OPUS instrument control"
readme = "README.md"
requires-python = ">=3.12"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project.scripts]
# Optional: Create console entry points
ir-server = "scripts.run_server:main"
ir-fit = "scripts.run_peak_fit:main"
ir-acquire = "scripts.run_acquire:main"
```

---

## Phase 4: Validation & Testing

### 4.1 Static Validation

**Run in refactor directory**:

```bash
# Check syntax
python -m py_compile src/**/*.py
python -m py_compile scripts/**/*.py

# Verify imports
python -c "from src.instrument.opus_wrapper import run_server"
python -c "from src.analysis.peak_fitting import voight_fit"
python -c "from src.utils.file_ops import read_parameters"

# Check for circular dependencies
python -c "import sys; sys.path.insert(0, 'src'); import src.instrument.opus_wrapper"
```

**Success Criteria**:
- [ ] No syntax errors
- [ ] All imports resolve
- [ ] No circular dependency warnings

### 4.2 Configuration Testing

```bash
# Test config loading
python -c "from src.core.config import get_config; c = get_config(); print(c.get('data.opus_files'))"

# Verify paths exist
python -c "from src.core.config import get_config; c = get_config(); print(c.get_path('data.opus_files').exists())"
```

**Success Criteria**:
- [ ] Config file loads without error
- [ ] Paths resolve correctly
- [ ] Can construct paths with subfolders

### 4.3 Functional Testing (Non-Disruptive)

**Test 1**: Peak fitting with sample data
```bash
cd C:\Users\labuser\CataVerse\ir-spectro-node-refactor
python scripts\run_peak_fit.py "path\to\sample.csv"
```

**Test 2**: Utility functions
```bash
python -c "from src.utils.file_ops import read_parameters; print('OK')"
python -c "from src.utils.subtract_ifg import SpectrumFromInterferogram; print('OK')"
```

**Test 3**: OPUS wrapper import (without starting server)
```bash
python -c "from src.instrument.opus_wrapper import PipeCommand, CheckInstrumentStatus; print('OK')"
```

### 4.4 OPUS Server Testing (Brief Disruption)

**Schedule**: When user signals safe window

```bash
# 1. Stop running server (in original location)
# Use taskkill or Ctrl+C in terminal running opusWrapper.py

# 2. Test new server starts without errors
cd ir-spectro-node-refactor
python scripts\run_server.py

# 3. If successful, test client connection
# Use existing client or simple test script

# 4. Stop test server

# 5. Restore original server if needed
cd ../ir-spectro-node
python opusWrapper.py
```

**Success Criteria**:
- [ ] Server binds to `tcp://130.20.216.127:5555`
- [ ] Responds to DIAG_STATUS command
- [ ] Can receive JSON messages via ZMQ

---

## Phase 5: Migration to Production

### 5.1 Pre-Migration Checklist

- [ ] All tests pass in refactor directory
- [ ] Config system verified working
- [ ] Import errors resolved
- [ ] OPUS server tested successfully
- [ ] Git status clean in refactor directory
- [ ] Original OPUS server running normally
- [ ] Backup timestamp noted

### 5.2 Swap Procedure (Recommended)

**Step 1**: Backup current production
```bash
cd C:\Users\labuser\CataVerse
ren ir-spectro-node ir-spectro-node-backup-20260114
```

**Step 2**: Promote refactor to production
```bash
ren ir-spectro-node-refactor ir-spectro-node
```

**Step 3**: Verify new structure
```bash
cd ir-spectro-node
dir src
dir config
dir scripts
```

**Step 4**: Restart OPUS server
```bash
# Update any shortcuts/scripts to point to new location
python scripts\run_server.py
```

**Step 5**: Integration test
- Run full measurement cycle
- Verify data paths resolve
- Check ZMQ communication
- Test peak fitting on acquired data

### 5.3 Rollback Procedure (If Needed)

```bash
# 1. Stop problematic server
# Ctrl+C or taskkill

# 2. Restore backup
cd C:\Users\labuser\CataVerse
ren ir-spectro-node ir-spectro-node-failed-20260114
ren ir-spectro-node-backup-20260114 ir-spectro-node

# 3. Restart original server
cd ir-spectro-node
python opusWrapper.py
```

**Maximum Downtime**: 2-3 minutes during swap

### 5.4 Gradual Migration Alternative

**If swap is too risky**:

1. Keep both directories active
2. Route new experiments to new structure
3. Maintain backup for 2-4 weeks
4. Decommission old structure after validation period

---

## Phase 6: Post-Migration Tasks

### 6.1 Documentation Updates

**Update AGENTS.md**:
- Reflect new import patterns
- Update build commands
- Document new directory structure

**Update README.md**:
- Installation instructions
- Configuration guide
- Quick start examples

**Create docs/migration_guide.md**:
- Old → New file mapping
- Import path changes
- Breaking changes

### 6.2 Clean Up

**After 2 weeks of successful operation**:
```bash
# Delete backup directories
rmdir /s /q ir-spectro-node-failed-20260114 2>nul
rmdir /s /q ir-spectro-node-backup-20260114
```

**Archive refactor artifacts**:
- Keep initial git tag
- Archive any intermediate experiment logs
- Document migration in project history

### 6.3 Git Workflow Establishment

```bash
# Create develop branch
git checkout -b develop

# Create feature branches for future work
git checkout -b feature/add-tests
git checkout -b feature/refactor-globals
```

---

## Risk Assessment & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|-------|------------|----------|------------|
| Import path errors | High | High | Test imports thoroughly before migration |
| OPUS server won't start | Medium | Critical | Brief test window before swap |
| Path resolution failures | Medium | Medium | Validate config system early |
| Lost data during swap | Low | Critical | Backup strategy, verify copy |
| Breaking changes for clients | Medium | Medium | Preserve ZMQ interface, document changes |
| Version control merge conflicts | Low | Medium | Work in isolated refactor copy |

---

## Success Criteria

### Phase Completion Checklist

**Phase 0**: [ ] Baseline established, refactor copy created
**Phase 1**: [ ] New structure defined, migration mapping complete
**Phase 2**: [ ] Config system created, hardcoded paths identified
**Phase 3**: [ ] Files moved, imports updated, entry points created
**Phase 4**: [ ] All tests pass, server verified
**Phase 5**: [ ] Production swap successful, OPUS server running
**Phase 6**: [ ] Documentation updated, backup cleaned up

### Final State Indicators

- [ ] Code organized into `src/`, `scripts/`, `tests/`, `config/`
- [ ] Zero hardcoded paths in active code
- [ ] Configuration loaded from YAML
- [ ] Proper Python package structure
- [ ] Entry points via scripts directory
- [ ] OPUS server running from new location
- [ ] All workflows functional
- [ ] Git workflow established for future work

---

## Appendices

### Appendix A: Hardcoded Path Inventory

| File | Line(s) | Path Type | Path |
|-------|-----------|------------|-------|
| opusWrapper.py | 313-322 | C:\Data\ | OpusFiles, OpusCalibrations, etc. |
| opusAcquire_4.py | 289, 291-293 | C:\Data\ | Same as above |
| ir_peakFit_carbonyl_v5.py | 849, 1889, 2099 | C:\Data\, X:/ | peakFit, ms_calibrations |
| test.py | 361, 563 | X:/ | ms_calibrations |
| subtractIFG.py | 58-65 | C:\Data\ | OpusFiles, subIFG, readParams |

### Appendix B: Global Variable Usage

**Files with extensive globals**:
1. `opusWrapper.py` - 11+ globals (hPipe, XpmPath, XpmName, etc.)
2. `opusAcquire_4.py` - Similar globals
3. Peak fitting files - Fewer globals, mostly constants

**Future Consideration**: Phase 2 of professionalization could address global variable refactoring to use dependency injection or class-based state management.

### Appendix C: Dependencies to Add

```toml
# Add to pyproject.toml
pyyaml >= 6.0.1  # Configuration management
```

### Appendix D: Import Migration Examples

**Before**:
```python
import os, sys
sys.path.append(".")
import ir_peakFit_carbonyl_v5 as fit
```

**After**:
```python
import sys
from pathlib import Path

src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from src.analysis.peak_fitting import voight_fit as fit
```

---

**End of Refactoring Plan**
