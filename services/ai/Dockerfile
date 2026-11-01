FROM ghcr.io/astral-sh/uv:0.11.6 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /uvx /bin/
WORKDIR /workspace
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
