# Use official Python image
FROM python:3.10-slim

# Install system dependencies for Playwright
RUN apt-get update && \
    apt-get install -y wget gnupg2 curl unzip libglib2.0-0 libnss3 libgconf-2-4 libfontconfig1 libxss1 libasound2 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libpangocairo-1.0-0 libxshmfence1 xvfb && \
    rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy requirements and install
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# add this line to pull in the geoip extra
RUN pip install --no-cache-dir "camoufox[geoip]"

# Install Playwright browsers (Chromium, Firefox, WebKit)
RUN python -m playwright install --with-deps

# Copy project files
COPY . .
RUN python load_cfox.py

# Set environment variables for headless operation and Camoufox arch
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99
ENV TZ=UTC
ENV CAMOUFOX_ARCH=x64
ENV PROCESSOR_ARCHITECTURE=AMD64
ENV ARCH=x64

# Entrypoint
CMD ["python", "main.py"] 