FROM python:3.11-slim

# System dependencies for pdfplumber, tesseract, spaCy
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libmagic1 \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    grep -v '^fastapi' requirements.txt > /tmp/requirements-no-fastapi.txt && \
    pip install --no-cache-dir -r /tmp/requirements-no-fastapi.txt && \
    pip install --no-cache-dir fastapi==0.111.0 --no-deps && \
    pip install --no-cache-dir \
        'starlette>=0.37.2,<0.38.0' \
        typing-extensions email-validator jinja2 orjson ujson \
        python-magic greenlet 'bcrypt==4.2.1'

# Download spaCy model
RUN pip install --no-cache-dir \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl

# Copy source
COPY --chown=appuser:appuser . .

# Create uploads dir
RUN mkdir -p /app/uploads && chown appuser:appuser /app/uploads

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
