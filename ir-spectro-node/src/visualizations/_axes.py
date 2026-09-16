"""Shared axis helpers for the ``ir_fitting`` plots.

Kept in one place because ``plot_individual_fit`` and ``plot_baseline`` both need
identical windowed rescaling, and the two must agree -- a zoom that scales y
differently between the fit view and the baseline view makes them impossible to
compare by eye.
"""

from __future__ import annotations

import numpy as np


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
