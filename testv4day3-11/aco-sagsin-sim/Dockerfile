FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl wget ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Poetry
RUN pip install --no-cache-dir poetry==1.8.3

COPY pyproject.toml README.md ./
RUN poetry config virtualenvs.create false \
 && poetry install --no-interaction --no-ansi

COPY . .

# Default command can be overridden by docker-compose
CMD ["uvicorn", "src.services.controller:app", "--host", "0.0.0.0", "--port", "8080"]
