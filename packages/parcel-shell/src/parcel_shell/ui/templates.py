from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import jinja2
from fastapi.templating import Jinja2Templates

_SHELL_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_DASHBOARDS_DIR = Path(__file__).resolve().parents[1] / "dashboards" / "templates"
_REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports" / "templates"
_WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / "workflows" / "templates"


@lru_cache(maxsize=1)
def get_templates() -> Jinja2Templates:
    """Shell-only Jinja2Templates. Module templates are mounted dynamically via
    :func:`add_template_dir`, which mutates the underlying loader search path.
    """
    tpl = Jinja2Templates(directory=str(_SHELL_TEMPLATES_DIR))
    # Swap in a ChoiceLoader so we can prepend module template dirs at runtime.
    tpl.env.loader = jinja2.ChoiceLoader(
        [
            jinja2.FileSystemLoader(str(_SHELL_TEMPLATES_DIR)),
            jinja2.FileSystemLoader(str(_DASHBOARDS_DIR)),
            jinja2.FileSystemLoader(str(_REPORTS_DIR)),
            jinja2.FileSystemLoader(str(_WORKFLOWS_DIR)),
        ]
    )
    # Expose active_href() so templates can pick the single sidebar item to highlight.
    from parcel_shell.ui.sidebar import active_href

    tpl.env.globals["active_href"] = active_href
    return tpl


def add_template_dir(directory: Path) -> None:
    """Prepend ``directory`` to the Jinja loader chain, if not already present."""
    tpl = get_templates()
    loader = tpl.env.loader
    assert isinstance(loader, jinja2.ChoiceLoader)
    as_str = str(directory)
    for existing in loader.loaders:
        if isinstance(existing, jinja2.FileSystemLoader) and as_str in existing.searchpath:
            return
    loader.loaders = [jinja2.FileSystemLoader(as_str), *loader.loaders]
