FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# YouTube only serves media to clients that solve its JavaScript challenges;
# yt-dlp does that through an external runtime (Deno is its default). Pinned on
# purpose: bump it deliberately, not as a side effect of a rebuild.
COPY --from=denoland/deno:bin-2.9.3 /deno /usr/local/bin/deno

WORKDIR /srv/getsetmix
COPY requirements.txt .
# YTDLP_VERSION is resolved by CI to the newest release on every build. As a
# build arg it is part of this layer's cache key, so a new yt-dlp release
# busts the cache instead of silently reusing a stale install.
ARG YTDLP_VERSION=
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ -n "$YTDLP_VERSION" ]; then pip install --no-cache-dir "yt-dlp[default]==$YTDLP_VERSION"; fi \
 && deno --version \
 && python -c "import yt_dlp_ejs, yt_dlp.version as v; print('yt-dlp', v.__version__)"

COPY app ./app

ENV GSM_DATA_DIR=/data \
    GSM_LIBRARY_ROOT=/music \
    GSM_XML_PATH=/data/rekordbox/getsetmix.xml

VOLUME ["/data", "/music"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8765/healthz')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
