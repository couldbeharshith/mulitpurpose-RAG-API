# Optimized Dockerfile for Hugging Face Spaces
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including Tesseract OCR for PPTX image text extraction
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    ca-certificates \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Optional: Test Tesseract installation (uncomment to run during build)
# RUN python test_tesseract_docker.py

# Set environment variables for Hugging Face Spaces
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONOPTIMIZE=0

# Tesseract OCR configuration
ENV TESSERACT_CMD=/usr/bin/tesseract

# CPU optimization for Hugging Face Spaces
ENV CUDA_VISIBLE_DEVICES=""
ENV OMP_NUM_THREADS=2
ENV MKL_NUM_THREADS=2
ENV NUMEXPR_NUM_THREADS=2
ENV OPENBLAS_NUM_THREADS=2
ENV TOKENIZERS_PARALLELISM=false

# Hugging Face Spaces specific settings
ENV PLATFORM=huggingface
ENV HOST=0.0.0.0
ENV PORT=7860

# Create logs directory
RUN mkdir -p ./logs

# Expose Hugging Face Spaces port
EXPOSE 7860

# Health check for Hugging Face Spaces
HEALTHCHECK --interval=60s --timeout=30s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

# Run the application optimized for Hugging Face Spaces
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1", "--limit-concurrency", "8"]