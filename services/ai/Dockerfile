FROM ghcr.io/astral-sh/uv:0.11.6@sha256:b1e699368d24c57cda93c338a57a8c5a119009ba809305cc8e86986d4a006754 AS uv
FROM python:3.12-slim@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54
COPY --from=uv /uv /uvx /bin/
WORKDIR /workspace
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim tesseract-ocr-chi-tra \
    && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
COPY services/ai/pyproject.toml services/ai/uv.lock ./services/ai/
COPY services/ai/src ./services/ai/src
COPY contracts/schemas ./contracts/schemas
COPY services/ai/tools/local_backend_e2e.py services/ai/tools/browser_e2e_server.py ./services/ai/tools/
RUN uv sync --project services/ai --frozen --no-dev
ENV PATH="/workspace/services/ai/.venv/bin:$PATH"
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "knowflow_ai.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
