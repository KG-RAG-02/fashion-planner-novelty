FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    VOGUE_HOST=0.0.0.0 \
    VOGUE_PORT=8765 \
    VOGUE_DB_PATH=/app/data/local/prototype.sqlite3

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
RUN useradd --create-home --uid 10001 vogue \
    && mkdir -p /app/data/local \
    && chown -R vogue:vogue /app

USER vogue

EXPOSE 8765

CMD ["python3", "-m", "vogue_npp.prototype.server"]
