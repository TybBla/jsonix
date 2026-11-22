FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Zależności osobno, żeby zmiana kodu nie przebudowywała warstwy pip.
COPY requirements.txt requirements-lock.txt ./
RUN pip install -r requirements.txt -c requirements-lock.txt

COPY . .
RUN mkdir -p input output

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["python", "-m", "odw2json", "serve", "--host", "0.0.0.0", "--port", "8000"]
