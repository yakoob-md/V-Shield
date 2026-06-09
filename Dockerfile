# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
# HF_HOME configures huggingface cache directory inside the container,
# which ensures baked-in weights are loaded instantly.
ENV PYTHONUNBUFFERED=1 \
    PORT=7860 \
    FAISS_INDEX_PATH=faiss_index.bin \
    CHUNKS_PATH=chunks.pkl \
    SQLITE_DB_PATH=chats_v2.db \
    HF_HOME=/app/.cache

# Set working directory
WORKDIR /app

# Install system dependencies (build-essential for compiling, curl for Docker health check)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy model preloader script and cache embedding model weights inside Docker layer
COPY preload_model.py .
RUN python preload_model.py

# Copy built frontend assets
COPY frontend/dist ./frontend/dist

# Copy backend application code
COPY main.py .
COPY build_vector_db.py .
COPY faiss_index.bin .
COPY chunks.pkl .
COPY chats_v2.db .
COPY datasets.json .

# Expose the port (Hugging Face Space default port is 7860)
EXPOSE 7860

# Docker Healthcheck to detect hung containers
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:7860/health || exit 1

# Run uvicorn server on port 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
