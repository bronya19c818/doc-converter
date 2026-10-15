# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DOC_CONVERTER_DATA_ROOT=/data \
    HOME=/data

RUN apt-get update \
    && apt-get install --no-install-recommends -y pandoc curl libreoffice-writer fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY --from=frontend-build /build/src/doc_converter/web/ ./src/doc_converter/web/
RUN pip install --no-cache-dir .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN useradd --create-home --uid 1000 appuser \
    && sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh \
    && chmod +x /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

USER appuser
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:8765/health || exit 1

CMD ["uvicorn", "doc_converter.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8765"]

