FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    NOVELTY_HOST=0.0.0.0 \
    NOVELTY_HTTP_MODE=service \
    NOVELTY_PORT=8767 \
    NOVELTY_TLS_CERT_FILE=/run/secrets/server_cert \
    NOVELTY_TLS_KEY_FILE=/run/secrets/server_key

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY prompts/ ./prompts/
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data/local \
    && chown -R app:app /app

USER app

EXPOSE 8767

CMD ["python3", "-m", "fashion_planner_novelty.server"]
