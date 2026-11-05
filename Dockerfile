FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    VOGUE_HOST=0.0.0.0 \
    VOGUE_PORT=8765 \
    VOGUE_DB_PATH=/app/data/local/prototype.sqlite3 \
    VOGUE_HM_ANALYSIS_PATH=/app/data/processed/hm-personalized-fashion-recommendations/hm_analysis.json

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY web/ ./web/
COPY docs/ ./docs/
COPY examples/fixtures/ ./examples/fixtures/

RUN useradd --create-home --uid 10001 vogue \
    && mkdir -p /app/data/local /app/data/processed/hm-personalized-fashion-recommendations \
    && chown -R vogue:vogue /app

USER vogue

EXPOSE 8765

CMD ["python3", "-m", "vogue_npp.prototype_server"]
