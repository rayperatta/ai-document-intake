FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system deps for psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY samples/ ./samples/

# Install the package
RUN pip install --no-cache-dir -e ".[dev]"

# Default command (overridden by compose for api vs worker)
CMD ["uvicorn", "docintake.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
