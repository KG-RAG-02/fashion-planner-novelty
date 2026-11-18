FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    VOGUE_HOST=0.0.0.0 \
    VOGUE_HTTP_MODE=service \
    VOGUE_PORT=8767 \
    VOGUE_TLS_CERT_FILE=/run/secrets/server_cert \
    VOGUE_TLS_KEY_FILE=/run/secrets/server_key

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY prompts/ ./prompts/
RUN useradd --create-home --uid 10001 vogue \
    && mkdir -p /app/data/local \
    && chown -R vogue:vogue /app

USER vogue

EXPOSE 8767

CMD ["python3", "-m", "fashion_planner_novelty.server"]
