from __future__ import annotations

# Tiny page footer Chromium repeats on every printed page. We can't use the
# CSS Generated Content for Paged Media spec (`@top-center`, `@bottom-right`)
# because Chromium ignores it — that's a WeasyPrint/Prince extension. Instead
# Playwright exposes `header_template` / `footer_template` HTML with reserved
# `<span class="pageNumber">` / `<span class="totalPages">` tokens.
_FOOTER_TEMPLATE = (
    '<div style="font-size:9pt; color:#666; width:100%; '
    'text-align:right; padding-right:20mm; padding-bottom:6mm;">'
    'Page <span class="pageNumber"></span> / <span class="totalPages"></span>'
    "</div>"
)
_EMPTY_HEADER = '<div style="display:none;"></div>'


async def html_to_pdf(html: str) -> bytes:
    """Render an HTML string to PDF bytes using headless Chromium.

    Imports Playwright lazily so the shell still boots if the package or its
    bundled browser are missing on a dev machine. The Docker image installs
    both via `playwright install chromium`.

    Each call launches a short-lived Chromium process — fine at the volumes
    Phase 9 reports produce. If a single deployment ever serves enough PDF
    requests for startup latency to matter, swap to a long-lived browser in
    `app.state` and reuse contexts.

    The page size and margins come from the report's CSS `@page` rule via
    `prefer_css_page_size=True`. The footer page-counter is forced through
    Playwright because Chromium doesn't honour CSS GCPM.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page()
            await page.set_content(html, wait_until="load")
            return await page.pdf(
                prefer_css_page_size=True,
                print_background=True,
                display_header_footer=True,
                header_template=_EMPTY_HEADER,
                footer_template=_FOOTER_TEMPLATE,
            )
        finally:
            await browser.close()
