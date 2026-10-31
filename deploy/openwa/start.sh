#!/bin/sh
# Restore /app/data from the bucket, run OpenWA, and keep the bucket copy fresh.
# Needs S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY. Without them it simply runs OpenWA.
DATA=/app/data
PREFIX="${OPENWA_SYNC_PREFIX:-openwa-data}"
INTERVAL="${OPENWA_SYNC_SECONDS:-30}"

if [ -n "$S3_ENDPOINT_URL" ] && [ -n "$S3_BUCKET" ]; then
  export RCLONE_CONFIG_REMOTE_TYPE=s3 RCLONE_CONFIG_REMOTE_PROVIDER=Cloudflare \
         RCLONE_CONFIG_REMOTE_ACCESS_KEY_ID="$S3_ACCESS_KEY_ID" RCLONE_CONFIG_REMOTE_SECRET_ACCESS_KEY="$S3_SECRET_ACCESS_KEY" \
         RCLONE_CONFIG_REMOTE_ENDPOINT="$S3_ENDPOINT_URL" RCLONE_CONFIG_REMOTE_NO_CHECK_BUCKET=true
  REMOTE="REMOTE:$S3_BUCKET/$PREFIX"
  mkdir -p "$DATA"
  echo "[sync] restoring $DATA from $PREFIX"
  rclone sync "$REMOTE" "$DATA" --quiet || echo "[sync] nothing to restore yet"
  push() { rclone sync "$DATA" "$REMOTE" --exclude "media/**" --exclude "**/Singleton*" --quiet || echo "[sync] push failed"; }
else
  echo "[sync] no bucket configured: data will not survive a restart"
  push() { :; }
fi

/usr/local/bin/docker-entrypoint.sh "$@" &
APP=$!

( while kill -0 "$APP" 2>/dev/null; do sleep "$INTERVAL"; push; done ) &
LOOP=$!

stop() { kill -TERM "$APP" 2>/dev/null; wait "$APP" 2>/dev/null; kill "$LOOP" 2>/dev/null; push; exit 0; }
trap stop TERM INT

wait "$APP"
CODE=$?
kill "$LOOP" 2>/dev/null
push
exit "$CODE"
