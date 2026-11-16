"""Where the ``plot_*.py`` scripts read a dataset's fit outputs from.

One switch for all of them: ``data.plot_source`` in ``config/paths.yaml``.
``""`` reads the dataset root, ``<data.peak_fit>/<folder>/``; ``"_reprocess"``
reads ``<data.peak_fit>/<folder>/_reprocess/``. A ``subfolder`` argument
overrides the yaml for one call.
"""

from __future__ import annotations

from pathlib import Path

from src.core import config


def source_subfolder(subfolder: str | None = None) -> str:
    """``subfolder`` if given, else the yaml ``data.plot_source``."""
    if subfolder is not None:
        return subfolder
    return str(config.get_setting("data.plot_source") or "")


def source_dir(folder_name: str, subfolder: str | None = None) -> Path:
    """``<data.peak_fit>/<folder_name>/<subfolder>``, the folder the plots read."""
    return Path(config.get_path("data.peak_fit", folder_name)) / source_subfolder(
        subfolder
    )
