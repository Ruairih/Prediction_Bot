# Market Explorer Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir pip --upgrade && \
    pip install --no-cache-dir .

# Copy application code
COPY src/ ./src/
COPY sync_markets_v2.py ./

# Set Python path
ENV PYTHONPATH=/app/src

# Default command: run API server
CMD ["uvicorn", "explorer.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
