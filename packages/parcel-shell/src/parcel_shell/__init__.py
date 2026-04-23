"""Parcel shell — FastAPI app hosting auth, RBAC, admin UI, module lifecycle, AI authoring."""

from __future__ import annotations

from parcel_shell.app import create_app

__all__ = ["__version__", "create_app"]
__version__ = "0.1.0"
