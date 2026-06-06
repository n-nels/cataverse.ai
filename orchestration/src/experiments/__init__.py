"""Experiment protocol exports for the active architecture."""

__all__ = ["AdsorptionExperiment", "IsotopicExchangeCalibration", "ExperimentSession"]


def __getattr__(name: str):
    if name == "AdsorptionExperiment":
        from .adsorption import AdsorptionExperiment

        return AdsorptionExperiment
    if name == "IsotopicExchangeCalibration":
        from .isotopic_exchange import IsotopicExchangeCalibration

        return IsotopicExchangeCalibration
    if name == "ExperimentSession":
        from .session import ExperimentSession

        return ExperimentSession
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
