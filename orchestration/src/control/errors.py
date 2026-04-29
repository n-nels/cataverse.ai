"""Control-layer exceptions for safety and operational errors.

These exceptions are raised by control-layer modules when safety limits
are exceeded or operational invariants are violated.  The experiment layer
or ``main.py`` catches them and triggers a safe-shutdown sequence.
"""

from __future__ import annotations


class SafetyLimitExceeded(Exception):
    """A hardware safety limit was exceeded during an operation.

    Attributes:
        actuator_id: The actuator or device involved (if applicable).
        measured: The measured value that exceeded the limit.
        limit: The configured safety limit.
        detail: Human-readable description of the violation.
    """

    def __init__(
        self,
        detail: str,
        *,
        actuator_id: str | None = None,
        measured: float | None = None,
        limit: float | None = None,
    ) -> None:
        self.actuator_id = actuator_id
        self.measured = measured
        self.limit = limit
        self.detail = detail
        super().__init__(detail)
