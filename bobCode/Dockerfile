FROM python:3.14-slim

WORKDIR /app

# Install build dependencies and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definitions
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and seed data
COPY . .

# Ingest RAG synthetic knowledge base into local ChromaDB
RUN python data/ingest.py || true

# Set environment variables
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
