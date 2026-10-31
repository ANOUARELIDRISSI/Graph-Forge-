FROM python:3.12-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev --group bigdata
COPY src ./src
COPY data ./data
COPY frontend ./frontend
COPY scripts ./scripts
ENV PYTHONPATH=/app/src
CMD ["uv", "run", "--no-sync", "uvicorn", "moroccan_crawler.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

