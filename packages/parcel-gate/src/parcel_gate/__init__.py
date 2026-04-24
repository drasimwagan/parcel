"""Parcel static-analysis gate.

Public entry point is :func:`run_gate`; see :mod:`parcel_gate.runner`.
"""

from __future__ import annotations

from parcel_gate.report import GateCheck, GateFinding, GateReport, GateSeverity
from parcel_gate.runner import GateError, run_gate

__all__ = [
    "GateCheck",
    "GateError",
    "GateFinding",
    "GateReport",
    "GateSeverity",
    "__version__",
    "run_gate",
]
__version__ = "0.1.0"
