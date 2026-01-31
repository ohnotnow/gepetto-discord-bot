# syntax=docker/dockerfile:1

FROM python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first (for better layer caching)
COPY pyproject.toml uv.lock .

# Sync dependencies
RUN uv sync --no-dev --no-install-project

# Copy the rest of the application
COPY . .

# Run using uv
CMD ["uv", "run", "python", "main.py"]
