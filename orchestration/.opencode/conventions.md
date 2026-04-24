# Code Conventions

---

## Naming

- **Functions/methods:** `snake_case` — e.g. `read_pressure()`, `deliver_gas_to_mfld()`
- **Variables:** `snake_case` — domain abbreviations are fine (`p_mfld`, `v_tot`, `t_cell`).
- **Constants:** `UPPER_SNAKE_CASE` — e.g. `R`, `V_TOT`
- **Classes:** `PascalCase` — e.g. `ActuatorControl`, `SerialDevices`
- **Files:** `snake_case` — e.g. `actuator_control.py`, `serial_devices.py`

---

## Formatting

- 4 spaces, no tabs.
- Line length: ~100 characters, not strictly enforced.
- 2 blank lines between top-level definitions, 1 blank line between related blocks.
- Enforced by `ruff format`.

---

## Types

Type hints on all new and refactored code. Use Python 3.12+ syntax.

```python
def read_pressure(self, command: str = 'p') -> tuple[datetime, float, float]:
```

No `cast()` calls. If a value's type is narrower than its annotation at a given point, either (a) change the annotation, (b) add a runtime `if x is None: raise ...` guard that narrows the type for the type checker, or (c) coerce explicitly (`float(x)`, not `cast(float, x)`).

---

## Error Handling

Prefer raising named exceptions over silent failure. Unrecoverable hardware or safety conditions (missing connection, missing actuator mapping, thermocouple fault, safety limit exceeded) should raise a distinctive exception from the hardware or control error hierarchy. The experiment or `main.py` layer catches and handles cleanup.

Do not use `try/except` to swallow errors into sentinel return values (`None`, `{}`, `False`). Do not use `sys.exit` from adapters or controllers — raise and let the caller decide.

Keep `try/except` blocks narrow — catch specific exceptions, handle one thing. Broad `except Exception:` is acceptable only in long-running worker loops where the goal is to keep the thread alive across transient read failures; log the error at `logger.error` level before continuing.

---

## Paths

Use `pathlib.Path` for all path construction — both config-loaded and runtime-built. No hardcoded string paths. No `os.path.join` in new or refactored code.

```python
from pathlib import Path

# From typed config
data_dir = Path(config.paths.data_directory)

# Built at runtime
readme_path = data_dir / folder_name / f"{file_name}_README.md"
```

---

## Functions

- Docstrings on all public functions.
- Keep functions single-purpose.
- Names should indicate action and object: `deliver_gas_to_mfld`, `set_temperature`.
- Function names should describe behavior, not hardware model numbers (no `opus_vertex80` — prefer `send_opus_request`).

---

## Comments

- Minimal. Only for non-obvious logic.
- Don't comment out code — delete it. Git has history.
