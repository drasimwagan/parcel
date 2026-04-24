from __future__ import annotations

from pydantic import BaseModel


class GenerateRequest(BaseModel):
    prompt: str


class GenerateFailure(BaseModel):
    kind: str
    message: str
    gate_report: dict | None = None
    transcript: str | None = None
