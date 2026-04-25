from __future__ import annotations


def html_to_pdf(html: str, *, base_url: str) -> bytes:
    """Render an HTML string to PDF bytes using WeasyPrint.

    Imports WeasyPrint lazily so the shell still boots on dev machines that
    don't have the GTK native libs installed (Windows, in particular). The
    Docker image installs the libs; production never sees the import error.

    `base_url` resolves any relative `<img src>`, `<link href>`, etc. inside
    the HTML. Pass a `file://` URI when assets are on disk.
    """
    import weasyprint

    return weasyprint.HTML(string=html, base_url=base_url).write_pdf()
