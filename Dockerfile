FROM python:3.12-slim

WORKDIR /app

# Install build tools needed for asyncpg compilation
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY aos/ ./aos/
COPY aos/db/migrations/ ./aos/db/migrations/
COPY alembic.ini ./

RUN pip install --no-cache-dir -e ".[server]"

EXPOSE 8000
