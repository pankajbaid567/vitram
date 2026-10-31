#!/bin/sh
# Back up everything needed to restore VITRAM: the database AND the encrypted uploads.
#
#   DATABASE_URL=postgresql+psycopg://user:pass@host/vitram DATA_DIR=/data scripts/backup.sh [output-dir]
#
# Writes <dir>/vitram-<timestamp>.dump (pg_dump custom format) and, if DATA_DIR/objects exists,
# <dir>/vitram-<timestamp>-files.tgz. Needs `pg_dump` (postgresql-client) on PATH. SQLite users: `python -m app.migrate backup`.
#
# NOT included, on purpose: VITRAM_DATA_KEY. Uploaded files are unreadable without it, so keep it in your secret
# manager and back it up *separately* from this archive.
set -eu
: "${DATABASE_URL:?set DATABASE_URL}"
dir="${1:-.}"
stamp="$(date +%Y%m%d-%H%M%S)"
url="$(printf '%s' "$DATABASE_URL" | sed 's#^postgresql+[a-z0-9]*://#postgresql://#')"
mkdir -p "$dir"
pg_dump --format=custom --no-owner --file "$dir/vitram-$stamp.dump" "$url"
echo "database  -> $dir/vitram-$stamp.dump"
if [ -n "${DATA_DIR:-}" ] && [ -d "$DATA_DIR/objects" ]; then
  tar -czf "$dir/vitram-$stamp-files.tgz" -C "$DATA_DIR" objects
  echo "uploads   -> $dir/vitram-$stamp-files.tgz"
fi
