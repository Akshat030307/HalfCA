# Half CA API. Built on the VPS by deploy/compose.yml; the dependency layer is cached
# so a code-only redeploy rebuilds in seconds.
FROM python:3.12-slim

# WeasyPrint (PDF report) needs Pango, HarfBuzz and at least one font.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.12.7

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    HALFCA_DATA_DIR=/app/data \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY halfca ./halfca
RUN uv sync --frozen --no-dev

COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh \
    && useradd --create-home --uid 1000 halfca \
    && mkdir -p /app/data \
    && chown -R halfca:halfca /app/data
USER halfca

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "halfca.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
