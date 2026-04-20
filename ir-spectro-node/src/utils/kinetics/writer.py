"""Colocated writer access for the kinetics API.

This module keeps the API and writer imports in the same subpackage.
Current implementation re-exports the existing writer backend.
"""

from src.utils.kinetic_fit_writer import AREA_SUFFIX, SEARCH_ROOT, WRITER

__all__ = ["WRITER", "SEARCH_ROOT", "AREA_SUFFIX"]
