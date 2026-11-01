# Freedom Pay gateway emulator.
#   docker build -t fpay-emulator ./fpay-emulator
#   docker run --rm -p 18080:8080 -e FPAY_MERCHANTS=12345:my_secret fpay-emulator

FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
# Pinned, reproducible install into a self-contained virtualenv (see requirements.txt).
COPY requirements.lock /tmp/requirements.lock
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-compile -r /tmp/requirements.lock

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    FPAY_DB_PATH=/data/fpay-emulator.sqlite3 \
    FPAY_PORT=8080
RUN groupadd --system --gid 10001 fpay \
    && useradd --system --uid 10001 --gid fpay --home-dir /app --shell /usr/sbin/nologin fpay \
    && mkdir -p /data && chown fpay:fpay /data
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY --chown=root:root fpay_emulator ./fpay_emulator
USER fpay
# Payments, the callback retry schedule and the virtual clock survive restarts here.
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import os, sys, urllib.request; r = urllib.request.urlopen('http://127.0.0.1:%s/status/healthcheck' % os.environ.get('FPAY_PORT', '8080'), timeout=2); sys.exit(0 if r.status == 200 else 1)"]
CMD ["python", "-m", "fpay_emulator"]
