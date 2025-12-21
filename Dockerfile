# Polymarket Trading Bot - Production Dockerfile
#
# Build:
#   docker build -t polymarket-bot .
#
# Run:
#   docker run -e DATABASE_URL=... polymarket-bot

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash botuser

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/
COPY seed/ ./seed/
COPY scripts/ ./scripts/

# Install Python dependencies from pyproject.toml (with dashboard extras)
RUN pip install --no-cache-dir ".[dashboard]"

# Set ownership
RUN chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Set Python path
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["python", "-m", "polymarket_bot.main", "--mode", "all"]
