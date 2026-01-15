# IR Spectroscopy Node - Directory Structure

**Project**: IR Spectroscopy Node
**Version**: 0.1.0
**Python**: >=3.12
**Purpose**: Infrared spectroscopy analysis and OPUS instrument control for carbonyl peak fitting

---

## Directory Tree

```
ir-spectro-node/
│
├── .env.local                         # Environment variables (local config)
├── .gitignore                         # Git ignore patterns
├── .python-version                    # Python version specification
├── pyproject.toml                     # Project configuration and dependencies
├── uv.lock                            # UV package manager lock file
├── README.md                          # Project documentation
├── main.py                            # Main entry point (Hello World)
│
├── .git/                              # Git repository metadata
│   ├── hooks/                         # Git hooks
│   ├── info/                          # Git repository info
│   ├── objects/                       # Git object storage
│   │   ├── info/
│   │   ├── pack/
│   │   └── ...                       # Git objects
│   └── refs/                          # Git references
│       ├── heads/
│       └── tags/
│
├── .venv/                             # Python virtual environment
│   ├── Include/                       # C header files
│   ├── Lib/                           # Installed packages
│   │   └── site-packages/
│   │       ├── lmfit/                # Peak fitting library
│   │       ├── matplotlib/            # Plotting library
│   │       ├── numpy/                # Numerical computing
│   │       ├── pandas/               # Data analysis
│   │       ├── pybaselines/          # Baseline correction
│   │       ├── pyzmq/                # ZeroMQ messaging
│   │       ├── scipy/                # Scientific computing
│   │       └── ...                   # Other dependencies
│   ├── Scripts/                       # Executable scripts
│   └── share/                         # Shared files
│
├── .vscode/                           # VSCode configuration
│   ├── launch.json                    # Debug configurations
│   └── settings.json                  # Editor settings
│
├── __pycache__/                       # Python bytecode cache
│
├── arxiv/                             # Archive - Historical versions
│   ├── callProgram.py                # Legacy program calling script
│   ├── import random.py              # Random import utility
│   ├── integrate_msIsoXchg.py       # MS isotopic exchange integration
│   ├── ir_isoX_calib.py              # IR isotopic exchange calibration
│   ├── IR_ms_calibCurve.py           # IR/MS calibration curve
│   ├── ir_peakAreaMoleConvert.py    # Peak area to mole conversion
│   ├── ir_peakFit_carbonyl_v1.py    # Peak fitting v1 (archived)
│   ├── ir_peakFit_carbonyl_v2.py    # Peak fitting v2 (archived)
│   ├── ir_peakFit_carbonyl_v3.py    # Peak fitting v3 (archived)
│   ├── ir_peakFit_carbonyl_v4.py    # Peak fitting v4 (archived)
│   ├── labNotebook.py               # Lab notebook utilities
│   ├── opusAcquire_1.py             # OPUS acquisition v1
│   ├── opusAcquire_2.py             # OPUS acquisition v2
│   ├── opusAcquire_4_derek.py       # OPUS acquisition v4 (Derek's)
│   ├── opusAcquire_carbonylQuant.py # Carbonyl quantification
│   ├── opusAcquire_multipleNSS.py   # Multiple NSS acquisition
│   ├── OpusWrapper.py               # OPUS wrapper v1 (archived)
│   ├── OpusWrapper_v2.py            # OPUS wrapper v2 (archived)
│   ├── opusWrapper_derek.py         # OPUS wrapper (Derek's)
│   ├── opusWrapper_v3.py            # OPUS wrapper v3
│   ├── SaveAs_ScSm.py               # Save format converter
│   └── ZMQMessenger_derek.py        # ZMQ messenger (Derek's)
│
├── delete_files.py                    # File deletion utility
├── ir_peakFit_carbonyl_v5.py         # Main peak fitting script (current)
│   # Functions: voight_fit() - Voigt profile fitting for carbonyl peaks
│
├── opusWrapper.py                     # OPUS instrument control wrapper
│   # Functions: CheckInstrumentStatus(), Deconvolute(), DoBackgroundMeasurement()
│   #           DoSampleMeasurement_nss(), PipeCommand()
│
├── opusWrapper_v2.py                  # OPUS wrapper v2
│
├── subtractIFG.py                     # Interferogram subtraction utility
├── tpd_postProcess.py                 # TPD post-processing
├── Norhoff.py                         # Norhoff script
│
├── readParams.py                      # Parameter reading utility
├── rename_files.py                    # File renaming utility
│
├── test.py                            # Testing script
│   # Functions: integrate_irIsoXchg() - IR isotopic exchange integration
│
└── null                               # Null/placeholder file
```

---

## Key Dependencies

```toml
[dependencies]
lmfit         >= 1.3.4   # Peak fitting and curve fitting
matplotlib    >= 3.10.8  # Data visualization
numpy         >= 2.4.1   # Numerical computing
pandas        >= 2.3.3   # Data manipulation
pybaselines   >= 1.2.1   # Baseline correction algorithms
pyzmq         >= 27.1.0  # ZeroMQ messaging for instrument control
scipy         >= 1.17.0  # Scientific computing
```

---

## Project Structure Notes

### Main Scripts

- **ir_peakFit_carbonyl_v5.py**: Current active version for Voigt profile fitting
- **opusWrapper.py**: Main instrument control interface using OPUS commands
- **test.py**: Integration testing for IR isotopic exchange
- **main.py**: Entry point (currently placeholder)

### Archive (arxiv/)

Contains historical versions of scripts:
- Peak fitting evolution (v1 → v5)
- OPUS wrapper iterations (v1 → v3)
- Various utility scripts for different workflows

### Configuration

- **.vscode/**: VSCode launch and settings
- **pyproject.toml**: Modern Python project configuration (replaces setup.py)
- **uv.lock**: Dependency lock file for reproducible builds (UV package manager)

---

*Generated on: 2026-01-14*
*Total Files: ~30 main scripts + dependencies*
