# MedConnect — Medical Platform Backend
# ─────────────────────────────────────────────────────────────

FROM python:3.11-slim

LABEL maintainer="MedConnect Team"
LABEL description="Medical platform backend — Gemini AI + MongoDB + Redis"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# Install Python deps first (layer caching)
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Copy application code
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

# Expose the API port
EXPOSE 8000

# Health check for Code Engine
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run with uvicorn (hot reload disabled for production)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
