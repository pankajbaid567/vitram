#!/bin/sh
# Restore a backup made by backup.sh. DESTRUCTIVE: replaces the contents of the target database.
#
#   DATABASE_URL=postgresql+psycopg://…/vitram DATA_DIR=/data scripts/restore.sh vitram-<stamp>.dump [vitram-<stamp>-files.tgz] --yes
#
# Stop the API and worker first. Afterwards start the API: it checks the schema revision and refuses to serve
# if the dump is from a *newer* code version.
set -eu
: "${DATABASE_URL:?set DATABASE_URL}"
dump="${1:?usage: restore.sh <dump> [files.tgz] --yes}"
files=""
for a in "$@"; do
  case "$a" in *-files.tgz) files="$a" ;; esac
done
case " $* " in *" --yes "*) ;; *) echo "refusing: this replaces the target database. Re-run with --yes."; exit 2 ;; esac
url="$(printf '%s' "$DATABASE_URL" | sed 's#^postgresql+[a-z0-9]*://#postgresql://#')"
pg_restore --clean --if-exists --no-owner --dbname "$url" "$dump"
echo "database restored from $dump"
if [ -n "$files" ] && [ -n "${DATA_DIR:-}" ]; then
  mkdir -p "$DATA_DIR" && tar -xzf "$files" -C "$DATA_DIR"
  echo "uploads restored into $DATA_DIR/objects"
fi
