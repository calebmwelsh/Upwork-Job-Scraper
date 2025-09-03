# Use official Playwright image matching Playwright 1.52.0
FROM mcr.microsoft.com/playwright/python:v1.52.0-jammy

# Base image already includes system dependencies and browsers

# Set workdir
WORKDIR /app

# Copy requirements and install
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# add this line to pull in the geoip extra
RUN pip install --no-cache-dir "camoufox[geoip]"

# Ensure browsers are installed for the pinned Playwright version
RUN python -m playwright install

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