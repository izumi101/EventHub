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

# Semantic search (sentence-transformers + PyTorch). Set
# INSTALL_SEMANTIC_SEARCH=0 in .env for a slim image — search then falls back
# to keyword matching. PyTorch comes from its CPU-only index: the PyPI build
# drags in ~3 GB of CUDA libraries a CPU server never uses, so those pins are
# dropped from the lock. The embedding model is downloaded at build time, so
# containers don't fetch it from Hugging Face at runtime.
ARG INSTALL_SEMANTIC_SEARCH=1
ENV HF_HOME=/opt/hf-cache
RUN if [ "$INSTALL_SEMANTIC_SEARCH" = "1" ]; then \
        TORCH_VERSION=$(sed -n 's/^torch==//p' requirements-search.lock) \
        && pip install --index-url https://download.pytorch.org/whl/cpu "torch==${TORCH_VERSION}" \
        && grep -vE '^(torch|triton|nvidia-[a-z0-9-]+)==' requirements-search.lock > /tmp/search-cpu.lock \
        && pip install -r /tmp/search-cpu.lock \
        && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"; \
    fi
# Never reach out to Hugging Face from a running container.
ENV HF_HUB_OFFLINE=1

COPY . .
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
# ASGI server: serves both the REST API and the seat-map WebSockets
# (gunicorn + WSGI would silently drop the WebSocket routes).
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "eventhub_backend.asgi:application"]
