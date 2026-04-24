from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

GateCheck = Literal["ruff", "bandit", "ast_policy"]
GateSeverity = Literal["error", "warning"]


@dataclass(frozen=True)
class GateFinding:
    check: GateCheck
    severity: GateSeverity
    path: str
    line: int | None
    rule: str
    message: str

    def to_dict(self) -> dict:
        return {
            "check": self.check,
            "severity": self.severity,
            "path": self.path,
            "line": self.line,
            "rule": self.rule,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> GateFinding:
        return cls(
            check=raw["check"],
            severity=raw["severity"],
            path=raw["path"],
            line=raw.get("line"),
            rule=raw["rule"],
            message=raw["message"],
        )


@dataclass(frozen=True)
class GateReport:
    passed: bool
    findings: tuple[GateFinding, ...]
    ran_at: datetime
    duration_ms: int

    @property
    def errors(self) -> tuple[GateFinding, ...]:
        return tuple(f for f in self.findings if f.severity == "error")

    @property
    def warnings(self) -> tuple[GateFinding, ...]:
        return tuple(f for f in self.findings if f.severity == "warning")

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "findings": [f.to_dict() for f in self.findings],
            "ran_at": self.ran_at.isoformat(),
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> GateReport:
        return cls(
            passed=raw["passed"],
            findings=tuple(GateFinding.from_dict(f) for f in raw["findings"]),
            ran_at=datetime.fromisoformat(raw["ran_at"]),
            duration_ms=raw["duration_ms"],
        )
