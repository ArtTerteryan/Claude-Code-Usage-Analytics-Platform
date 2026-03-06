FROM python:3.13-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir ".[test]"

# Copy source code, tests, and config
COPY src/ src/
COPY tests/ tests/
COPY .streamlit/ .streamlit/
COPY claude_code_telemetry/generate_fake_data.py generate_fake_data.py

# Create data directories
RUN mkdir -p data output

ENV PYTHONPATH=/app

# Copy entrypoint
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["./entrypoint.sh"]
