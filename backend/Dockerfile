FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium (deps installed above, skip --with-deps to avoid broken font packages on Debian Trixie)
RUN playwright install chromium

# Copy application code
COPY . .

# Create uploads directory
RUN mkdir -p uploads

EXPOSE 8000

# WEB_CONCURRENCY controls worker count — set via env var on your hosting platform
# Recommended: 2 workers per CPU core (e.g. 4 for a 2-core server)
ENV WEB_CONCURRENCY=2

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY}"]
