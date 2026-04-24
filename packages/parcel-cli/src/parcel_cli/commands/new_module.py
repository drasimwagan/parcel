from __future__ import annotations

import re
import shutil
from pathlib import Path

import typer

from parcel_cli.scaffold import template_files as T

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def new_module(
    name: str = typer.Argument(..., help="Module name (snake_case)."),
    path: str = typer.Option("./modules", "--path", help="Destination directory."),
    force: bool = typer.Option(False, "--force", help="Overwrite if target exists."),
) -> None:
    """Scaffold a new Parcel module at <path>/<name>/."""
    if not _NAME_RE.match(name):
        typer.echo(
            f"error: module name must be snake_case [a-z][a-z0-9_]* (got {name!r})",
            err=True,
        )
        raise typer.Exit(2)

    root = Path(path) / name
    if root.exists():
        if not force:
            typer.echo(f"error: {root} already exists (use --force to overwrite)", err=True)
            raise typer.Exit(2)
        shutil.rmtree(root)

    _write_tree(root, name)
    typer.echo(f"created {root}")
    typer.echo("next steps:")
    typer.echo("  uv sync --all-packages")
    typer.echo(f"  uv run parcel install {root}")
    typer.echo("  uv run parcel dev")


def _pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _write_tree(root: Path, name: str) -> None:
    pkg = f"parcel_mod_{name}"
    src = root / "src" / pkg
    alembic_dir = src / "alembic"
    (alembic_dir / "versions").mkdir(parents=True, exist_ok=True)
    (src / "templates" / name).mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)

    ctx = {"name": name, "pascal": _pascal(name)}

    (root / "pyproject.toml").write_text(T.PYPROJECT.format(**ctx))
    (root / "README.md").write_text(T.README.format(**ctx))

    (src / "alembic.ini").write_text(T.ALEMBIC_INI.format(**ctx))
    (alembic_dir / "env.py").write_text(T.ALEMBIC_ENV_PY.format(**ctx))
    (alembic_dir / "script.py.mako").write_text(T.ALEMBIC_SCRIPT_MAKO)
    (alembic_dir / "versions" / "0001_init.py").write_text(T.INIT_MIGRATION.format(**ctx))

    (src / "__init__.py").write_text(T.INIT_PY.format(**ctx))
    (src / "models.py").write_text(T.MODELS_PY.format(**ctx))
    (src / "router.py").write_text(T.ROUTER_PY.format(**ctx))
    (src / "templates" / name / "index.html").write_text(T.INDEX_HTML.format(**ctx))

    (root / "tests" / "__init__.py").write_text("")
    (root / "tests" / "test_smoke.py").write_text(T.TEST_SMOKE.format(**ctx))
