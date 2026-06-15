# syntax=docker/dockerfile:1

# Digest pinned 2026-06-15 (tag 3.11-slim). Update tag + digest together; re-resolve with:
#   docker buildx imagetools inspect python:3.11-slim --format '{{.Manifest.Digest}}'
FROM python:3.11-slim@sha256:ae52c5bef62a6bdd42cd1e8dffef86b9cd284bde9427da79839de7a4b983e7ca

WORKDIR /app

# Install uv. Digest pinned 2026-06-15 (tag 0.11.6); pinning also stops uv re-publishing
# the same tag from busting the build cache. Update tag + digest together; re-resolve with:
#   docker buildx imagetools inspect ghcr.io/astral-sh/uv:0.11.6 --format '{{.Manifest.Digest}}'
COPY --from=ghcr.io/astral-sh/uv:0.11.6@sha256:b1e699368d24c57cda93c338a57a8c5a119009ba809305cc8e86986d4a006754 /uv /uvx /bin/

# Copy dependency files first (for better layer caching)
COPY pyproject.toml uv.lock .

# Sync dependencies
RUN uv sync --no-dev --no-install-project

# Copy the rest of the application
COPY . .

# Run using uv
CMD ["uv", "run", "python", "main.py"]
