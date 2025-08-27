# LinuxServer.io-style Docker image for sonarr-metadata-rewrite
FROM ghcr.io/linuxserver/baseimage-ubuntu:jammy

# Add package information
LABEL build_version="sonarr-metadata-rewrite version:- Build-date:-"
LABEL maintainer="kfstorm"

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install Python and uv
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Add uv to PATH
ENV PATH="/root/.cargo/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy application files and install
COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# Install the application and make it available system-wide
RUN uv sync --frozen --no-dev \
    && chmod +x /app/.venv/bin/sonarr-metadata-rewrite

# Copy LinuxServer.io services and init scripts
COPY root/ /

# Expose volumes for configuration and media
VOLUME ["/config", "/tv"]

# LinuxServer.io uses s6-overlay for process management and PUID/PGID handling
