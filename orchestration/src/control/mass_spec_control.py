"""Thin control-layer wrapper for Extrel mass-spectrometer register operations.

This module keeps experiment code dependent on control-layer interfaces while
preserving the existing low-level register write behavior.
"""

from __future__ import annotations

from src.core.config_loader import ExtrelRegisterConfig
from src.hardware.mass_spec import ExtrelMassSpec


class MassSpecController:
    """Control-layer pass-through for Extrel register interactions."""

    def __init__(
        self,
        mass_spec: ExtrelMassSpec,
        registers: ExtrelRegisterConfig,
        stream_tags: list[str] | None = None,
    ) -> None:
        self.mass_spec = mass_spec
        self.registers = registers
        self.stream_tags: list[str] = stream_tags or [
            "V1_I_28", "V1_I_29", "V1_I_44", "V1_I_45",
        ]

    def write_register(self, address: int, value: int) -> bool:
        """Write one Extrel register via the hardware adapter."""

        return self.mass_spec.write_register(address=address, value=value)

    def read_registers(
        self, address: int, count: int = 1, unit: int = 1
    ) -> list[int] | None:
        """Read Extrel registers via the hardware adapter."""

        return self.mass_spec.read_registers(address=address, count=count, unit=unit)

    def start_sequence(self) -> bool:
        """Write configured Extrel sequence-start register/value."""

        return self.write_register(
            address=self.registers.sequence_start_address,
            value=self.registers.sequence_start_value,
        )

    def stop_sequence(self) -> bool:
        """Write configured Extrel sequence-stop register/value."""

        return self.write_register(
            address=self.registers.sequence_stop_address,
            value=self.registers.sequence_stop_value,
        )

    def mass_spec_adapter(self) -> ExtrelMassSpec:
        """Return underlying Extrel adapter for logger wiring."""

        return self.mass_spec
