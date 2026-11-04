#!/usr/bin/env sh
# Restore a backup into a database. TEST IT ON A SCRATCH DATABASE FIRST.
#   DATABASE_URL=postgresql://user:pw@host/scratch ./scripts/restore_db.sh backup.dump
set -eu
: "${DATABASE_URL:?DATABASE_URL is required}"
FILE="${1:?usage: restore_db.sh backup.dump}"
URL=$(printf '%s' "$DATABASE_URL" | sed 's#postgresql+psycopg://#postgresql://#')
pg_restore --list "$FILE" >/dev/null   # refuses files that are not valid dumps
echo "This will REPLACE the contents of the target database. Type 'restore' to continue:"
read -r answer
[ "$answer" = "restore" ] || { echo "Cancelled."; exit 1; }
pg_restore --clean --if-exists --no-owner --dbname "$URL" "$FILE"
echo "Restored. Run 'alembic upgrade head' to apply any newer migrations."
