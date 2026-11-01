#!/bin/sh
# Prove a backup restores: dump the live database, restore it into an empty scratch database, and compare every table.
#
#   DATABASE_URL=postgresql+psycopg://…/vitram SCRATCH_DATABASE_URL=postgresql+psycopg://…/vitram_verify scripts/verify_backup.sh
#
# The scratch database must exist and may be overwritten. Run it on a schedule (see .github/workflows/backup-verify.yml). Needs pg_dump and
# pg_restore on PATH and a Python with psycopg (PYTHON="uv run --extra postgres python"). Exits non-zero if the restore fails or any table differs.
set -eu
: "${DATABASE_URL:?set DATABASE_URL}"
: "${SCRATCH_DATABASE_URL:?set SCRATCH_DATABASE_URL (an empty database you do not mind overwriting)}"
here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
"$here/backup.sh" "$tmp" >/dev/null
dump="$(ls "$tmp"/*.dump)"
DATABASE_URL="$SCRATCH_DATABASE_URL" "$here/restore.sh" "$dump" --yes >/dev/null
${PYTHON:-python} "$here/compare_databases.py" "$DATABASE_URL" "$SCRATCH_DATABASE_URL"
