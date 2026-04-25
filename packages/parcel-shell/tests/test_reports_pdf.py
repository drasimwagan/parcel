from __future__ import annotations

import pytest

from parcel_shell.reports.pdf import html_to_pdf


def _weasyprint_loadable() -> bool:
    try:
        import weasyprint  # noqa: F401
    except OSError:
        # GTK native libs missing (typical on Windows dev). Docker has them.
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _weasyprint_loadable(),
    reason="WeasyPrint native libs (GTK) not available",
)


def test_html_to_pdf_returns_pdf_bytes() -> None:
    out = html_to_pdf(
        "<html><body><h1>Hello</h1></body></html>",
        base_url="file:///tmp/",
    )
    assert isinstance(out, bytes)
    assert out.startswith(b"%PDF-")
    assert len(out) > 100
