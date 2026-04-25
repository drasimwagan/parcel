from __future__ import annotations


def worker() -> None:
    """Run the workflow worker (ARQ)."""
    from arq import run_worker
    from parcel_shell.config import get_settings
    from parcel_shell.workflows.worker import build_worker_settings

    settings = get_settings()
    worker_settings = build_worker_settings(settings)
    run_worker(worker_settings)
