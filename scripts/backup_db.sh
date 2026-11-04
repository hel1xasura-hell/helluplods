#!/usr/bin/env sh
set -eu
: "${DATABASE_URL:?DATABASE_URL is required}"
# pg_dump wants a plain postgresql:// URL
URL=$(printf '%s' "$DATABASE_URL" | sed 's#postgresql+psycopg://#postgresql://#')
OUT="backup-$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump --format=custom --file="$OUT" "$URL"
echo "Wrote $OUT"
