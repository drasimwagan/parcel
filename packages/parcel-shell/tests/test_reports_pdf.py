from __future__ import annotations

import pytest

from parcel_shell.reports.pdf import html_to_pdf

pytestmark = pytest.mark.asyncio


async def test_html_to_pdf_returns_pdf_bytes() -> None:
    out = await html_to_pdf("<html><body><h1>Hello</h1></body></html>")
    assert isinstance(out, bytes)
    assert out.startswith(b"%PDF-")
    assert len(out) > 100
