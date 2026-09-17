"""Baseline variants for offline baseline experimentation.

One place defines what "a baseline to try" means: which slice of the spectrum
the algorithm sees, and what settings it runs with. Everything else --
``api.compare_baselines``, the plots -- consumes :class:`BaselineVariant` and
never calls ``create_baseline`` itself.

**This is the expansion point.** A new baseline behaviour gets a field on
:class:`BaselineVariant` and a branch in :meth:`BaselineVariant.compute`. The
two knobs wired up today are the ``std_distribution`` settings and the
wavenumber window; the anchored / two-segment ideas in ``spec.md`` section 14.4
belong here when they are built, not in a parallel module.
"""

from __future__ import annotations

import logging
import sys
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

path = Path(__file__).resolve().parents[3]
if str(path) not in sys.path:
    sys.path.append(str(path))

from src.analysis.spectral_fitting import create_baseline
from src.utils.ir_fitting import config as ir_config

LOGGER = logging.getLogger(__name__)

Window = tuple[float, float]

DEFAULT_WINDOW: Window = (2250.0, 1750.0)
"""``(high, low)`` cm-1, matching ``io.py::import_data``'s ROI.

Written high-to-low because that is the order the instrument writes and the
order the plots display.
"""

DEGENERATE_WARNING = "no baseline points"
"""Substring of the ``pybaselines`` warning that means the fit found nothing.

``std_distribution`` still *returns* an array in that case, so a degenerate
baseline plots as a plausible-looking curve. Confirmed to fire for
``num_std: 0.8`` on ``20260717_203829_pd_ceo2_000-008_delta10.0042``.
"""

JUDGED_FILES: tuple[tuple[str, str], ...] = (
    ("20260715_094622_pd_ceo2_000-007_delta10.0042", "bad"),
    ("20260717_203829_pd_ceo2_000-008_delta10.0042", "bad"),
    ("20260728_032548_pd_ceo2_000-012_delta10.0052", "bad"),
    ("20260806_105210_pd_ceo2_000-017_delta10.0022", "bad"),
    ("20260811_072450_pd_ceo2_000-021_delta10.0022", "bad"),
    ("20260825_052349_pd_ceo2_000-027_delta10.0052", "bad"),
    ("20260813_195617_pd_ceo2_000-022_delta10.0022", "good"),
    ("20260813_195617_pd_ceo2_000-022_delta10.0042", "good"),
)
"""subIFG files whose baselines were judged by eye (spec.md sections 14.2/14.3).

All from ``nn1120-4_pd_ceo2_000``. ``"good"`` is the section 14.3
counter-example. Every other file in the dataset is **unlabelled** -- not
known-good. Six files were looked at; they are not necessarily the only wrong
ones, and one good measurement is n=1.
"""

BASELINE_KEYS = ir_config.BASELINE_KEYS
"""Re-exported so callers can discover the settings without importing config."""


@dataclass(frozen=True)
class BaselineVariant:
    """One baseline recipe: a data window plus algorithm settings.

    Args:
        label: Name shown in legends and the output CSV.
        settings: Overrides for ``std_distribution``, any of
            :data:`BASELINE_KEYS`. Keys left out keep their
            ``config/analysis.yaml`` value. An unknown key raises rather than
            being ignored -- ``create_baseline`` reads settings with
            ``.get(...)`` and falls back to a default, so a typo would silently
            run the *unmodified* baseline and look like a knob that does
            nothing.
        window: ``(high, low)`` cm-1 extent of the data handed to the
            algorithm. This genuinely changes the result everywhere, not just
            near the edges: ``create_baseline`` receives only ``y``, so the
            window *is* the array, and ``std_distribution`` classifies
            background points globally. Measured in spec.md section 14.8 --
            narrowing the top edge to 2200 moves the baseline by up to 13% of
            signal range on a file whose baseline is currently good.
    """

    label: str
    settings: dict = field(default_factory=dict)
    window: Window = DEFAULT_WINDOW

    @classmethod
    def coerce(cls, item: BaselineVariant | tuple) -> BaselineVariant:
        """Build a variant from itself or a ``(label, settings[, window])`` tuple.

        Tuples keep the calling code readable in a ``__main__`` block:

            [("current", {}), ("num_std 1.4", {"num_std": 1.4})]
        """
        if isinstance(item, cls):
            return item
        if not isinstance(item, (tuple, list)) or not 2 <= len(item) <= 3:
            raise TypeError(
                "each variant must be a BaselineVariant or a "
                f"(label, settings[, window]) tuple; got {item!r}"
            )
        return cls(*item)

    def __post_init__(self) -> None:
        high, low = self.window
        if not high > low:
            raise ValueError(
                f"window must be (high, low) with high > low; got {self.window!r}"
            )
        # Validate the settings eagerly so a typo surfaces when the variant is
        # declared, not partway through a batch.
        ir_config.get_baseline_settings(override=dict(self.settings) or None)

    @property
    def is_default_window(self) -> bool:
        """True when this variant uses the standard 1750-2250 ROI."""
        return tuple(self.window) == DEFAULT_WINDOW

    def resolved_settings(self, voigt_settings: dict | None = None) -> dict:
        """Return the full settings dict this variant will run with."""
        return ir_config.get_baseline_settings(
            voigt_settings, override=dict(self.settings) or None
        )

    def compute(
        self,
        intensity: np.ndarray,
        voigt_settings: dict | None = None,
    ) -> tuple[np.ndarray, bool]:
        """Return ``(baseline, degenerate)`` for an intensity array.

        ``degenerate`` is True when ``std_distribution`` reported that it found
        no baseline points. The returned array is still whatever it produced --
        callers must surface the flag, because the curve looks plausible.
        """
        settings = self.resolved_settings(voigt_settings)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _, values = create_baseline(intensity, settings)
        degenerate = any(DEGENERATE_WARNING in str(item.message) for item in caught)
        if degenerate:
            LOGGER.warning(
                "variant %r produced a degenerate baseline (no baseline points "
                "found); the curve is not meaningful",
                self.label,
            )
        return np.asarray(values, dtype=float), degenerate


def union_window(items: Sequence[Any]) -> Window:
    """Return the ``(high, low)`` window covering every item's ``window``.

    Accepts anything carrying a ``window`` attribute -- :class:`BaselineVariant`
    or :class:`~src.utils.ir_fitting.result_types.BaselineTrace` -- so the
    renderer and the orchestrator agree on display limits without one importing
    the other's types.

    Display limits come from the union rather than from any one variant, so a
    narrower variant's trace visibly *stops* instead of being cropped out of
    view -- which is the point of plotting a window change at all.
    """
    if not items:
        return DEFAULT_WINDOW
    return (
        max(item.window[0] for item in items),
        min(item.window[1] for item in items),
    )


def overlap_shift(
    x_reference: np.ndarray,
    y_reference: np.ndarray,
    x_variant: np.ndarray,
    y_variant: np.ndarray,
) -> tuple[float, Window]:
    """Max ``|variant - reference|`` over the wavenumbers the two share.

    Two variants with different windows produce arrays of different length, so
    they cannot be differenced elementwise. Both derive from the same file on
    the same grid, so intersecting on wavenumber value is exact -- and it is
    done by *value*, not by position, because wavenumbers descend and a
    narrower top edge drops samples from the **front** of the array. A
    positional head-slice would sit ~26 samples out of register at 2200 while
    still looking like the right length.

    Returns:
        ``(max absolute difference, (high, low) of the compared region)``.
    """
    low = max(float(x_reference.min()), float(x_variant.min()))
    high = min(float(x_reference.max()), float(x_variant.max()))
    if not high > low:
        raise ValueError(
            f"variant windows do not overlap: reference covers "
            f"{x_reference.min():.0f}-{x_reference.max():.0f}, variant covers "
            f"{x_variant.min():.0f}-{x_variant.max():.0f}"
        )

    mask_reference = (x_reference >= low) & (x_reference <= high)
    mask_variant = (x_variant >= low) & (x_variant <= high)
    if mask_reference.sum() != mask_variant.sum() or not np.allclose(
        x_reference[mask_reference], x_variant[mask_variant]
    ):
        raise ValueError(
            "the two variants are not on the same wavenumber grid over their "
            "overlap; they cannot be compared"
        )

    shift = float(np.abs(y_variant[mask_variant] - y_reference[mask_reference]).max())
    return shift, (high, low)


def signal_range(y: np.ndarray) -> float:
    """``max(y) - min(y)``, the denominator for reporting a baseline shift.

    Raw log-reflectance differences are ~1e-4 and unreadable on their own;
    dividing by the span makes files comparable. For scale, the 2040 cm-1 peak
    is about 20% of signal range in the files of :data:`JUDGED_FILES`.
    """
    span = float(np.nanmax(y) - np.nanmin(y))
    return span if span > 0 else float("nan")
