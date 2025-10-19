# docker/Dockerfile — Flask + MySQL Connector
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System deps (reportlab needs some fonts/ghostscript optional)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libjpeg62-turbo \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application (expect the Flask project to be in ./Projekt)
COPY Projekt /app

EXPOSE 5000
CMD ["python", "app.py"]
