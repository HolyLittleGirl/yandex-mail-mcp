FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt \
    && useradd --create-home --uid 10001 mcp

COPY --chown=mcp:mcp server.py ./

USER mcp
EXPOSE 8000

CMD ["python", "server.py"]
