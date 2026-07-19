# Build from repository root (default when Railway "Root Directory" is unset).
# Railpack only inspects the service root; Python lives under backend/, so we
# use an explicit Docker build instead of language auto-detection.
FROM python:3.13-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY backend/ /app/

# Non-root runtime (SEC-006). Cache/logs dirs must be writable by this user.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin nova \
    && mkdir -p /app/.cache /app/logs \
    && chown -R nova:nova /app

USER nova

# Railway sets PORT at runtime. Public bind requires NOVA_API_KEY (see auth.py).
CMD sh -c "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"
