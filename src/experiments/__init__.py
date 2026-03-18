"""
Experiment management module.

Contains experiment protocols, automation systems, and catalysis experiment frameworks.
"""

from .adsorption import adsorption_experiment
from .isotopic_exchange import isotopic_exchange_calibration
from .parameters import experiment_parameters

__all__ = [
    "experiment_parameters",
    "isotopic_exchange_calibration",
    "adsorption_experiment",
]
