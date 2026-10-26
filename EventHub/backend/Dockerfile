FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update     && apt-get install -y --no-install-recommends build-essential libpq-dev     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip     && pip install -r requirements.txt

COPY . .
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
# ASGI server: serves both the REST API and the seat-map WebSockets
# (gunicorn + WSGI would silently drop the WebSocket routes).
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "eventhub_backend.asgi:application"]
