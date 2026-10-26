FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Pinned, reproducible installs (see requirements*.txt for how to regenerate).
COPY requirements.lock requirements-search.lock ./
RUN pip install --upgrade pip && pip install -r requirements.lock

# Semantic search pulls in PyTorch (several GB). Build a slim image with
#   docker compose build --build-arg INSTALL_SEMANTIC_SEARCH=0 backend
# — search then falls back to keyword matching.
ARG INSTALL_SEMANTIC_SEARCH=1
RUN if [ "$INSTALL_SEMANTIC_SEARCH" = "1" ]; then pip install -r requirements-search.lock; fi

COPY . .
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
# ASGI server: serves both the REST API and the seat-map WebSockets
# (gunicorn + WSGI would silently drop the WebSocket routes).
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "eventhub_backend.asgi:application"]
