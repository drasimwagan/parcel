from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from parcel_cli.main import app

runner = CliRunner()


def test_scaffolds_expected_files(tmp_path: Path) -> None:
    result = runner.invoke(app, ["new-module", "demo", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.stdout

    root = tmp_path / "demo"
    assert (root / "pyproject.toml").exists()
    assert (root / "README.md").exists()
    src = root / "src" / "parcel_mod_demo"
    assert (src / "__init__.py").exists()
    assert (src / "models.py").exists()
    assert (src / "router.py").exists()
    assert (src / "alembic.ini").exists()
    assert (src / "alembic" / "env.py").exists()
    assert (src / "alembic" / "script.py.mako").exists()
    assert (src / "alembic" / "versions" / "0001_init.py").exists()
    assert (src / "templates" / "demo" / "index.html").exists()
    assert (root / "tests" / "test_smoke.py").exists()

    pyproj = (root / "pyproject.toml").read_text()
    assert 'name = "parcel-mod-demo"' in pyproj
    assert "parcel_mod_demo:module" in pyproj

    init = (src / "__init__.py").read_text()
    assert 'name="demo"' in init


def test_rejects_bad_name(tmp_path: Path) -> None:
    result = runner.invoke(app, ["new-module", "Bad-Name", "--path", str(tmp_path)])
    assert result.exit_code != 0
    combined = (result.stdout or "") + (result.stderr or "")
    assert "snake_case" in combined.lower()


def test_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    result = runner.invoke(app, ["new-module", "demo", "--path", str(tmp_path)])
    assert result.exit_code != 0


def test_force_overwrites(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "stale.txt").write_text("x")
    result = runner.invoke(app, ["new-module", "demo", "--path", str(tmp_path), "--force"])
    assert result.exit_code == 0
    assert not (tmp_path / "demo" / "stale.txt").exists()
    assert (tmp_path / "demo" / "pyproject.toml").exists()


def test_compound_name_generates_valid_pascal_class(tmp_path: Path) -> None:
    result = runner.invoke(app, ["new-module", "my_mod", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    models = (tmp_path / "my_mod" / "src" / "parcel_mod_my_mod" / "models.py").read_text()
    assert "class MyModBase" in models
