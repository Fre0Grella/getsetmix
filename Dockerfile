FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/getsetmix
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV GSM_DATA_DIR=/data \
    GSM_LIBRARY_ROOT=/music \
    GSM_XML_PATH=/data/rekordbox/getsetmix.xml

VOLUME ["/data", "/music"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8765/healthz')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
