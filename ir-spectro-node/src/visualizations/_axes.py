"""Shared axis helpers for the ``ir_fitting`` plots.

Kept in one place because ``plot_individual_fit`` and ``plot_baseline`` both need
identical windowed rescaling, and the two must agree -- a zoom that scales y
differently between the fit view and the baseline view makes them impossible to
compare by eye.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

XLim = tuple[float, float]


def as_windows(xlim: XLim | Sequence[XLim]) -> list[XLim]:
    """Normalise ``xlim`` to a list of ``(high, low)`` windows.

    Accepts one range, ``(1900, 1750)``, or several,
    ``((1900, 1750), (2250, 1750))`` -- so a single call can emit both a zoomed
    and a full-range figure per file.
    """
    items = list(xlim)
    if not items:
        raise ValueError("xlim must contain at least one (high, low) range.")
    if len(items) == 2 and all(isinstance(value, (int, float)) for value in items):
        return [(float(items[0]), float(items[1]))]

    windows: list[XLim] = []
    for item in items:
        pair = tuple(item)
        if len(pair) != 2:
            raise ValueError(
                f"each xlim entry must be a (high, low) pair; got {item!r}"
            )
        windows.append((float(pair[0]), float(pair[1])))
    return windows


def rescale_y_to_window(
    ax,
    x: np.ndarray,
    xlim: tuple[float, float],
    margin: float = 0.1,
) -> None:
    """Set an axes' y limits from only the data inside ``xlim``.

    Matplotlib autoscales y over every plotted point, so at 1750-1900 the ~2100
    carbonyl peak -- roughly 30x the low-wavenumber signal -- flattens the whole
    figure to a line. Rescaling to the visible window is what makes the zoom
    worth having.

    Lines whose y data does not match ``x`` in shape are ignored, so axhline
    markers and other annotations do not drag the limits.
    """
    lower, upper = min(xlim), max(xlim)
    mask = (x >= lower) & (x <= upper)
    if not mask.any():
        return

    visible: list[np.ndarray] = []
    for line in ax.get_lines():
        y = np.asarray(line.get_ydata(), dtype=float)
        if y.shape != x.shape:
            continue
        visible.append(y[mask])
    if not visible:
        return

    values = np.concatenate(visible)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return

    low, high = float(values.min()), float(values.max())
    pad = (high - low) * margin or abs(high) * margin or 1e-6
    ax.set_ylim(low - pad, high + pad)
