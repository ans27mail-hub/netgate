FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN pip install --no-cache-dir "playwright==1.48.0" \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY server.py .
EXPOSE 3000
CMD ["python", "server.py"]
