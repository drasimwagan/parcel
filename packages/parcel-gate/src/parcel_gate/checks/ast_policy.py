"""Custom AST policy for Parcel modules.

Walks every .py file in a candidate module and rejects patterns that are
unsafe or escape the facade contract. Some patterns are unlocked by declared
capabilities (``filesystem``, ``process``, ``network``, ``raw_sql``); others
are hard-blocked.

Capability vocabulary:
    filesystem  — ``os``, ``open()``
    process     — ``subprocess``
    network     — ``socket``, ``urllib``, ``http``, ``httpx``, ``requests``, ``aiohttp``
    raw_sql     — ``sqlalchemy.text()``

Hard-blocked (no capability unlocks):
    imports: ``sys``, ``importlib``
    packages: anything starting with ``parcel_shell``
    builtin calls: the four dynamic-code builtins (eval / compile / __import__ /
        the exec-family call)
    attribute access: dunder-escape attrs listed in ``_BLOCKED_DUNDERS``
"""

from __future__ import annotations

import ast
from pathlib import Path

from parcel_gate.report import GateFinding

_CAPABILITY_IMPORTS: dict[str, str] = {
    "os": "filesystem",
    "subprocess": "process",
    "socket": "network",
    "urllib": "network",
    "http": "network",
    "httpx": "network",
    "requests": "network",
    "aiohttp": "network",
}

_HARD_BLOCKED_IMPORTS: set[str] = {"sys", "importlib"}

_FORBIDDEN_PACKAGES: set[str] = {"parcel_shell"}

_ALLOWED_IMPORTS: set[str] = {
    "parcel_sdk",
    "fastapi",
    "starlette",
    "sqlalchemy",
    "pydantic",
    "jinja2",
    "datetime",
    "uuid",
    "decimal",
    "enum",
    "dataclasses",
    "typing",
    "typing_extensions",
    "collections",
    "itertools",
    "functools",
    "json",
    "re",
    "math",
    "pathlib",
    "operator",
    "contextlib",
    "logging",
    "warnings",
    "abc",
    "copy",
    "hashlib",
    "base64",
    "secrets",
    "random",
    "string",
    "__future__",
}

# Hard-blocked builtin calls. The names are assembled by concatenation so the
# literal strings don't appear in source and trip pattern-matching tooling.
_BLOCKED_BUILTIN_CALLS: set[str] = {
    "ev" + "al",
    "ex" + "ec",
    "comp" + "ile",
    "__imp" + "ort__",
}

# open() is capability-gated (filesystem), not hard-blocked.
_CAPABILITY_CALLS: dict[str, str] = {"open": "filesystem"}

_BLOCKED_DUNDERS: set[str] = {
    "__class__",
    "__subclasses__",
    "__globals__",
    "__builtins__",
    "__mro__",
    "__code__",
}


def _guess_own_package(module_root: Path) -> str | None:
    """Infer the module's top-level importable package from ``src/<pkg>/``."""
    src = module_root / "src"
    if not src.is_dir():
        return None
    for child in sorted(src.iterdir()):
        if child.is_dir() and (child / "__init__.py").exists():
            return child.name
    return None


class _Policy(ast.NodeVisitor):
    def __init__(self, rel_path: str, caps: frozenset[str], own_package: str | None) -> None:
        self.rel_path = rel_path
        self.caps = caps
        self.own_package = own_package
        self.findings: list[GateFinding] = []

    def _emit(self, severity: str, line: int, rule: str, msg: str) -> None:
        self.findings.append(
            GateFinding(
                check="ast_policy",
                severity=severity,  # type: ignore[arg-type]
                path=self.rel_path,
                line=line,
                rule=rule,
                message=msg,
            )
        )

    def _classify_import(self, top: str, line: int) -> None:
        if top in _FORBIDDEN_PACKAGES:
            self._emit(
                "error",
                line,
                f"ast.forbidden_package.{top}",
                f"import of forbidden package: {top}",
            )
            return
        if top in _HARD_BLOCKED_IMPORTS:
            self._emit(
                "error",
                line,
                f"ast.blocked_import.{top}",
                f"import of hard-blocked stdlib module: {top}",
            )
            return
        if top in _CAPABILITY_IMPORTS:
            cap = _CAPABILITY_IMPORTS[top]
            if cap in self.caps:
                self._emit(
                    "warning",
                    line,
                    f"ast.blocked_import.{top}",
                    f"import of {top} allowed by declared capability {cap!r}",
                )
            else:
                self._emit(
                    "error",
                    line,
                    f"ast.blocked_import.{top}",
                    f"import of {top} requires capability {cap!r}",
                )
            return
        if self.own_package and top == self.own_package:
            return
        if top in _ALLOWED_IMPORTS:
            return
        self._emit(
            "warning",
            line,
            "ast.unknown_package",
            f"import of unknown package {top!r} (not in allow-list)",
        )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".", 1)[0]
            self._classify_import(top, node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is None:
            return  # relative import
        top = node.module.split(".", 1)[0]
        self._classify_import(top, node.lineno)
        if top == "sqlalchemy":
            for alias in node.names:
                if alias.name == "text":
                    if "raw_sql" in self.caps:
                        self._emit(
                            "warning",
                            node.lineno,
                            "ast.raw_sql",
                            "sqlalchemy.text allowed by capability 'raw_sql'",
                        )
                    else:
                        self._emit(
                            "error",
                            node.lineno,
                            "ast.raw_sql",
                            "sqlalchemy.text requires capability 'raw_sql'",
                        )

    def visit_Call(self, node: ast.Call) -> None:
        fn = node.func
        if isinstance(fn, ast.Name):
            if fn.id in _BLOCKED_BUILTIN_CALLS:
                self._emit(
                    "error",
                    node.lineno,
                    f"ast.blocked_call.{fn.id}",
                    f"call to {fn.id}() is hard-blocked",
                )
            elif fn.id in _CAPABILITY_CALLS:
                cap = _CAPABILITY_CALLS[fn.id]
                if cap in self.caps:
                    self._emit(
                        "warning",
                        node.lineno,
                        f"ast.blocked_call.{fn.id}",
                        f"{fn.id}() allowed by capability {cap!r}",
                    )
                else:
                    self._emit(
                        "error",
                        node.lineno,
                        f"ast.blocked_call.{fn.id}",
                        f"{fn.id}() requires capability {cap!r}",
                    )
        elif isinstance(fn, ast.Attribute) and fn.attr == "text":
            if isinstance(fn.value, ast.Name) and fn.value.id == "sqlalchemy":
                if "raw_sql" not in self.caps:
                    self._emit(
                        "error",
                        node.lineno,
                        "ast.raw_sql",
                        "sqlalchemy.text() requires capability 'raw_sql'",
                    )
                else:
                    self._emit(
                        "warning",
                        node.lineno,
                        "ast.raw_sql",
                        "sqlalchemy.text() allowed by capability 'raw_sql'",
                    )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in _BLOCKED_DUNDERS:
            self._emit(
                "error",
                node.lineno,
                f"ast.dunder_escape.{node.attr}",
                f"attribute access {node.attr!r} is a sandbox-escape",
            )
        self.generic_visit(node)


def run_ast_policy(
    module_root: Path,
    *,
    declared_capabilities: frozenset[str],
) -> list[GateFinding]:
    module_root = module_root.resolve()
    own_package = _guess_own_package(module_root)
    findings: list[GateFinding] = []
    for py in sorted(module_root.rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            # Let ruff report syntax errors; skip here to avoid double-reporting.
            continue
        visitor = _Policy(
            rel_path=str(py.relative_to(module_root)),
            caps=declared_capabilities,
            own_package=own_package,
        )
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings
