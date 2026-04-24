"""Parcel static-analysis gate.

Public entry point is :func:`run_gate`; see :mod:`parcel_gate.runner`.
"""

from __future__ import annotations

from parcel_gate.report import GateCheck, GateFinding, GateReport, GateSeverity

__all__ = [
    "GateCheck",
    "GateFinding",
    "GateReport",
    "GateSeverity",
    "__version__",
]
__version__ = "0.1.0"
