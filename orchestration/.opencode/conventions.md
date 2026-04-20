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

---

## Error Handling

Don't add `try/except` blocks unless the failure requires a specific recovery action. This is a single-user system with an established workflow — if something hits an exception, the experiment likely failed and that's useful information. Verbose error handling obscures that signal.

During the refactor: do not introduce new `try/except` blocks without user confirmation.

---

## Paths

Use `pathlib.Path` for all path construction — both config-loaded and runtime-built. No hardcoded string paths.

```python
from pathlib import Path

# From config
data_dir = Path(config["paths"]["data_directory"])

# Built at runtime
readme_path = data_dir / folder_name / f"{file_name}_README.md"
```

---

## Functions

- Docstrings on all public functions.
- Keep functions single-purpose.
- Names should indicate action and object: `deliver_gas_to_mfld`, `set_temperature`.

---

## Comments

- Minimal. Only for non-obvious logic.
- Don't comment out code — delete it. Git has history.