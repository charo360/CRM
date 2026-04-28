FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (gcc for builds; Playwright will add Chromium deps)
RUN apt-get update && apt-get install -y --no-install-recommends gcc

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium + its OS-level dependencies
RUN playwright install --with-deps chromium

RUN rm -rf /var/lib/apt/lists/*

# Copy application code
COPY . .

# Create uploads directory
RUN mkdir -p uploads

EXPOSE 8000

# WEB_CONCURRENCY controls worker count — set via env var on your hosting platform
# Recommended: 2 workers per CPU core (e.g. 4 for a 2-core server)
ENV WEB_CONCURRENCY=2

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY}"]
