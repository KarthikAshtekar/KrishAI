FROM python:3.13-slim AS base

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .

RUN apt-get update && \
    apt-get install -y --no-install-recommends libgomp1 && \
    rm -rf /var/lib/apt/lists/* && \
    python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt

FROM base AS test

COPY requirements-dev.txt .
RUN python -m pip install --no-cache-dir -r requirements-dev.txt
COPY . .
RUN ruff check . && python -m unittest discover -v

FROM base AS runtime

RUN useradd --create-home --uid 10001 appuser

COPY --chown=appuser:appuser app.py auth.py config.py database.py db_models.py decision_engine.py ml_services.py observability.py repositories.py schemas.py alembic.ini ./
COPY --chown=appuser:appuser migrations ./migrations
COPY --chown=appuser:appuser scripts ./scripts
COPY --chown=appuser:appuser static ./static
COPY --chown=appuser:appuser templates ./templates
COPY --chown=appuser:appuser models ./models
COPY --chown=appuser:appuser ["Jupyter files", "./Jupyter files"]

USER appuser

EXPOSE 8080

CMD exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}
