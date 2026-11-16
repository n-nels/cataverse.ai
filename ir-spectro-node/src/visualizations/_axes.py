"""Shared axis helpers for the ``ir_fitting`` plots.

Kept in one place because ``plot_individual_fit`` and ``plot_baseline`` both need
identical windowed rescaling, and the two must agree -- a zoom that scales y
differently between the fit view and the baseline view makes them impossible to
compare by eye.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from matplotlib.ticker import AutoMinorLocator, MaxNLocator, MultipleLocator

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


# (span in cm-1, major tick, minor tick). First row whose span covers the window
# wins; the last row is the fallback for anything narrower.
_X_TICK_STEPS = ((300.0, 50.0, 10.0), (100.0, 25.0, 5.0), (0.0, 10.0, 2.0))


def apply_reference_grid(ax, xlim: tuple[float, float]) -> None:
    """Put a read-off grid on an axes: major + minor ticks on both axes.

    These figures are judged by eye against specific wavenumbers -- an anchor at
    1955, a band at 1795, a seam at the cut -- and the default four or five
    ticks across a 500 cm-1 span make that a guess. Tick density is chosen from
    the window width so a zoom gets finer lines rather than the same five:
    50/10 cm-1 over the full ROI, 25/5 in the middle, 10/2 on a tight zoom.

    y is left to a denser :class:`MaxNLocator` rather than a fixed step, because
    the scale differs between the raw and subtracted panels and between files.

    Call it **after** the y limits are set (``rescale_y_to_window``), since the
    locator is applied to whatever range the axes ends up with.
    """
    span = abs(float(xlim[0]) - float(xlim[1]))
    for threshold, major, minor in _X_TICK_STEPS:
        if span > threshold:
            break
    ax.xaxis.set_major_locator(MultipleLocator(major))
    ax.xaxis.set_minor_locator(MultipleLocator(minor))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=10, steps=[1, 2, 2.5, 5, 10]))
    ax.yaxis.set_minor_locator(AutoMinorLocator(2))

    # Under the traces: a grid drawn over a 1.1pt line reads as a dashed trace.
    ax.set_axisbelow(True)
    ax.grid(which="major", color="0.75", linewidth=0.5, alpha=0.6)
    ax.grid(which="minor", color="0.85", linewidth=0.4, alpha=0.4)
    ax.tick_params(which="major", labelsize=7, length=3.5)
    ax.tick_params(which="minor", length=2)
