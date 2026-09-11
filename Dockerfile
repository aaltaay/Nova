# Optional local container image. Not a cloud host -- Nova API is local /
# Desktop sidecar only. Public bind requires NOVA_API_KEY (see auth.py).
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

CMD sh -c 'if [ -z "$$NOVA_API_KEY" ]; then echo "NOVA_API_KEY required when using this image" >&2; exit 1; fi; exec uvicorn main:app --host 0.0.0.0 --port $${PORT:-8000}'
