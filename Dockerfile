# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PORT=7860 \
    FAISS_INDEX_PATH=faiss_index.bin \
    CHUNKS_PATH=chunks.pkl \
    SQLITE_DB_PATH=chats_v2.db \
    HF_HOME=/app/.cache

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the vector DB builder and preloader
COPY build_vector_db.py .
COPY preload_model.py .

# ── Cache the embedding model weights inside the image layer ──────────────────
# This runs ONCE at build time so startup is instant.
RUN python preload_model.py

# ── Build the FAISS index inside the image ─────────────────────────────────────
# All data is embedded in build_vector_db.py – no external files needed.
RUN python build_vector_db.py

# ── Copy built frontend and backend ───────────────────────────────────────────
COPY frontend/dist ./frontend/dist
COPY main.py .

# Expose the HF Spaces default port
EXPOSE 7860

# Docker Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:7860/health || exit 1

# Run uvicorn server on port 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
