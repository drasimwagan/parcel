"""Generator orchestration — prompt → provider → zip → sandbox (retry once)."""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import structlog
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.ai.provider import ClaudeProvider, PriorAttempt, ProviderError
from parcel_shell.config import Settings
from parcel_shell.sandbox import service as sandbox_service
from parcel_shell.sandbox.models import SandboxInstall

_log = structlog.get_logger("parcel_shell.ai.generator")


@dataclass(frozen=True)
class GenerationFailure:
    kind: Literal["provider_error", "no_files", "gate_rejected", "exceeded_retries"]
    message: str
    gate_report: dict | None = None
    transcript: str | None = None


def _zip_files(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buf.getvalue()


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


async def generate_module(
    prompt: str,
    *,
    provider: ClaudeProvider,
    db: AsyncSession,
    app: FastAPI,
    settings: Settings,
    max_attempts: int = 2,
) -> SandboxInstall | GenerationFailure:
    """Ask the provider for a module, sandbox it, retry once on gate rejection.

    Returns a :class:`SandboxInstall` on success, or a :class:`GenerationFailure`
    whose ``kind`` tells you where in the pipeline we stopped.
    """
    started = time.perf_counter()
    ph = _prompt_hash(prompt)
    prior: PriorAttempt | None = None
    last_report: dict | None = None
    last_transcript: str = ""

    for attempt in range(max_attempts):
        with tempfile.TemporaryDirectory() as tmp:
            working_dir = Path(tmp)
            try:
                generated = await provider.generate(prompt, working_dir, prior=prior)
            except ProviderError as exc:
                _log.info(
                    "ai.generate.provider_error",
                    prompt_hash=ph,
                    attempt=attempt,
                    error=str(exc),
                )
                return GenerationFailure(
                    kind="provider_error",
                    message=str(exc),
                    transcript=last_transcript or None,
                )

            last_transcript = generated.transcript
            if not generated.files:
                return GenerationFailure(
                    kind="no_files",
                    message="provider returned no files",
                    transcript=last_transcript,
                )

            zip_bytes = _zip_files(generated.files)
            try:
                row = await sandbox_service.create_sandbox(
                    db,
                    source_zip_bytes=zip_bytes,
                    app=app,
                    settings=settings,
                )
                dur = int((time.perf_counter() - started) * 1000)
                _log.info(
                    "ai.generate.success",
                    prompt_hash=ph,
                    attempt=attempt,
                    sandbox_id=str(row.id),
                    name=row.name,
                    total_duration_ms=dur,
                )
                return row
            except sandbox_service.GateRejected as exc:
                last_report = exc.report.to_dict()
                prior = PriorAttempt(
                    gate_report_json=json.dumps(last_report),
                    previous_files=generated.files,
                )
                _log.info(
                    "ai.generate.gate_rejected",
                    prompt_hash=ph,
                    attempt=attempt,
                    errors=len(exc.report.errors),
                )

    dur = int((time.perf_counter() - started) * 1000)
    _log.info(
        "ai.generate.exceeded_retries",
        prompt_hash=ph,
        attempts=max_attempts,
        total_duration_ms=dur,
    )
    return GenerationFailure(
        kind="exceeded_retries",
        message=f"gate rejected after {max_attempts} attempt(s)",
        gate_report=last_report,
        transcript=last_transcript,
    )
