"""Hardware communication layer for the new CataVerse architecture.

This package contains low-level instrument adapters that operate on injected,
already-open connections (serial, modbus, DAQ, ZMQ, HTTP). It should expose
device read/write primitives without embedding higher-level experiment
sequencing logic.
"""
