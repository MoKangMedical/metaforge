# ---- Stage 1: Build dependencies ----
FROM python:3.14-slim AS builder
# NOTE: Use python:3.12-bullseye if slim image unavailable locally

WORKDIR /build

# Install build deps needed for numpy/scipy compilation
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Stage 2: Production image ----
FROM python:3.14-slim AS production

LABEL maintainer="MetaForge Team"
LABEL description="MetaForge - AI Evidence-Based Medicine Meta-Analysis Platform"

# Create non-root user for security
RUN groupadd -r metaforge && useradd -r -g metaforge -d /app metaforge

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY app/ ./app/
COPY css/ ./css/
COPY js/ ./js/
COPY assets/ ./assets/
COPY index.html .

# Ensure correct ownership
RUN chown -R metaforge:metaforge /app

USER metaforge

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Run with uvicorn
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
