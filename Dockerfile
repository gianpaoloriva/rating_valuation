# syntax=docker/dockerfile:1.7

# -----------------------------------------------------------------------------
# Rating & Valuation Suite — Streamlit container
# -----------------------------------------------------------------------------
# Build:
#     docker build -t rating-valuation .
#
# Run:
#     docker run --rm -p 8501:8501 rating-valuation
#
# Then open http://localhost:8501
#
# For development with live code reload, mount the repo as a volume:
#     docker run --rm -p 8501:8501 -v "$(pwd)":/app rating-valuation
# -----------------------------------------------------------------------------

FROM python:3.11-slim AS base

# System deps: build tools are only required if a wheel is missing for
# scipy/numpy on the host arch. Keep the image small by cleaning apt cache.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g ${APP_GID} appgroup \
    && useradd -u ${APP_UID} -g appgroup -m -s /bin/bash appuser

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# -----------------------------------------------------------------------------
# Dependencies layer — copy only the metadata first to maximize cache hits
# -----------------------------------------------------------------------------
COPY pyproject.toml README.md ./
RUN mkdir -p src/rating_valuation \
    && touch src/rating_valuation/__init__.py \
    && pip install -e ".[app]"

# -----------------------------------------------------------------------------
# Application layer
# -----------------------------------------------------------------------------
COPY src ./src
COPY app ./app
COPY data ./data
COPY examples ./examples
COPY overview.md ./overview.md

# Regenerate fake dataset if needed (idempotent — fixed seed)
RUN python3 data/generators/seed_companies.py

RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl --fail --silent http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app/streamlit_app.py"]
