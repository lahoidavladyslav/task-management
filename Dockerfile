FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --create-home --uid 1000 appuser


FROM base AS dev

COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt

COPY --chown=appuser:appuser . .
USER appuser

CMD ["pytest"]


FROM base AS runtime

COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser alembic ./alembic
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser docker ./docker
USER appuser

EXPOSE 8000

CMD ["sh", "docker/entrypoint.sh"]
