#!/usr/bin/env bash
# Restore a backup made by ./backup.sh. This REPLACES the current data.
#   ./restore.sh backups/personnel-postgres-20260101-120000.sql.gz
set -euo pipefail
cd "$(dirname "$0")"

FILE="${1:-}"
[ -n "$FILE" ] && [ -f "$FILE" ] || { echo "Usage: ./restore.sh <backup.sql.gz>" >&2; exit 1; }
[ -f .env ] || { echo "No .env found." >&2; exit 1; }
# shellcheck disable=SC1091
set -a; . ./.env; set +a

# Pick the compose file that matches the engine recorded in .env.
compose_file() {
  case "${DB_ENGINE:-postgres}" in
    mariadb) echo "compose.mariadb.yaml" ;;
    *) echo "compose.yaml" ;;
  esac
}
dc() { docker compose -f "$(compose_file)" "$@"; }

case "$FILE" in
  *"-$DB_ENGINE-"*) ;;
  *) echo "That backup wasn't taken from $DB_ENGINE. Dumps aren't interchangeable between engines." >&2; exit 1 ;;
esac

printf 'This replaces everything currently in the %s database. Type yes to continue: ' "$DB_NAME"
read -r reply
[ "$reply" = "yes" ] || { echo "Cancelled."; exit 1; }

dc stop app >/dev/null

case "$DB_ENGINE" in
  postgres) gzip -dc "$FILE" | dc exec -T db psql -q -U "$DB_USER" -d "$DB_NAME" ;;
  mariadb)  gzip -dc "$FILE" | dc exec -T db mariadb -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" ;;
esac

dc start app >/dev/null
echo "Restored. The app is starting again."
