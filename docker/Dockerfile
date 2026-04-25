# Parcel shell image.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl build-essential libpq-dev git \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy workspace definition first for better layer caching.
COPY pyproject.toml ./
COPY .python-version ./
COPY packages/ ./packages/
COPY modules/ ./modules/

COPY uv.lock ./

RUN uv sync --all-packages --frozen 2>/dev/null || uv sync --all-packages

# Install Chromium for the reports PDF engine (Playwright). The
# `--with-deps` flag installs the system libs Chromium needs at runtime
# (fonts, X libs, etc.) — Playwright's own apt list, kept up to date by
# Microsoft. ~250 MB image-size cost.
RUN uv run playwright install --with-deps chromium

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["serve"]
