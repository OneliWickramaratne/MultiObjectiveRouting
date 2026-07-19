FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system hospital && useradd --system --gid hospital hospital

WORKDIR /app/backend

COPY backend/requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt

COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/docker-entrypoint.sh ./docker-entrypoint.sh
COPY data /app/data
COPY ml /app/ml

RUN chown -R hospital:hospital /app
USER hospital

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/ready', timeout=3)" || exit 1

ENTRYPOINT ["sh", "/app/backend/docker-entrypoint.sh"]
