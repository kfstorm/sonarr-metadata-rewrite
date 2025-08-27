# Multi-stage Docker build for sonarr-metadata-rewrite using uv

# Build stage
FROM ghcr.io/astral-sh/uv:python3.10-bookworm-slim AS builder

# Set environment variables for optimal uv behavior
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Create app directory
WORKDIR /app

# Copy uv configuration files
COPY pyproject.toml uv.lock ./

# Install dependencies into a virtual environment
RUN uv sync --frozen --no-install-project --no-dev

# Copy and install the pre-built wheel
COPY dist/*.whl /tmp/
RUN uv pip install /tmp/*.whl --no-deps

# Runtime stage
FROM python:3.13-slim-bookworm AS runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

# Create non-root user
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --shell /bin/bash --create-home app

# Copy virtual environment from builder stage
COPY --from=builder --chown=app:app /app/.venv /app/.venv

# Create directories for the application
RUN mkdir -p /app/data && chown -R app:app /app

# Switch to non-root user
USER app

# Set working directory
WORKDIR /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import sonarr_metadata_rewrite" || exit 1

# Expose any ports if needed (none for this application)
# EXPOSE 8080

# Set the entry point to the CLI command
ENTRYPOINT ["sonarr-metadata-rewrite"]
