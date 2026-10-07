FROM python:3.12-slim

WORKDIR /app

# Install system deps needed by some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer caching)
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model at build time so cold starts are fast
ENV FASTEMBED_CACHE_PATH=/app/model-cache
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2', cache_dir='/app/model-cache')"

# Copy application code
COPY . .

# Render sets PORT dynamically
ENV PORT=8000
ENV DATA_DIR=/app/data
ENV MODEL_CACHE_DIR=/app/model-cache

EXPOSE ${PORT}

# Start the FastAPI server
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 1 --limit-concurrency 20 --timeout-keep-alive 5
