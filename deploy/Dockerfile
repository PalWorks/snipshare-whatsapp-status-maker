# SnipShare: the hosted page and the renderer, the same engine as the local tool.
# Built and run by deploy/docker-compose.yml. See DEPLOYMENT.md.
FROM python:3.13-slim-trixie

# What deploy.sh prunes by. The host may be shared, so a prune that is not limited
# to this project's own images could remove another project's.
LABEL project.name="snipshare"

# ffmpeg from the distribution: trixie ships 7.1, which has everything the engine
# asks of it (trim, -fps_mode, libx264, libopus, libvpx, libdav1d for AV1 input).
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# Never root. /data is created here, owned by this user, so a fresh named volume
# takes that ownership when Docker first fills it.
# /data/backups is a volume of its own, mounted inside /data, and takes the same
# ownership the same way.
RUN useradd --system --uid 10001 --home-dir /data --shell /usr/sbin/nologin wastatus \
 && mkdir -p /data/backups /app \
 && chown -R wastatus:wastatus /data

WORKDIR /app
# The hosted image's own list, a subset of requirements.txt: nothing the site never
# runs (yt-dlp, the token plugin, the WhatsApp driver's websocket client).
COPY deploy/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY wastatus/ wastatus/
COPY assets/ assets/
# The extension people install, built by deploy.sh for this site. In the image, so
# it is root's and read-only to the app: nothing inside the running container can
# replace it (DECISIONS.md D-101).
COPY extension/ extension/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1 \
    WASTATUS_HOSTED_DATA=/data \
    WASTATUS_LOG_DIR=/data/logs \
    WASTATUS_STICKER_DIR=/data/stickers \
    TMPDIR=/data/tmp

USER wastatus
EXPOSE 8790
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8790/api/v1/health', timeout=4).status != 200)"
# umask 027: the people database, its journal and everybody's clips are readable
# by this user alone.
CMD ["sh", "-c", "umask 027 && mkdir -p /data/tmp /data/logs && exec python -m wastatus hosted serve --host 0.0.0.0 --port 8790"]
