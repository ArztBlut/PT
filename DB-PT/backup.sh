#!/usr/bin/env bash
# Write a compressed dump to ./backups. Keeps the 30 most recent.
#   ./backup.sh [output-directory]
set -euo pipefail
cd "$(dirname "$0")"

KEEP=30
OUT_DIR="${1:-backups}"
[ -f .env ] || { echo "No .env found. Run ./install.sh first." >&2; exit 1; }
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

mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
FILE="$OUT_DIR/personnel-${DB_ENGINE}-${STAMP}.sql.gz"

case "$DB_ENGINE" in
  postgres)
    dc exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" --clean --if-exists ;;
  mariadb)
    dc exec -T db mariadb-dump -u "$DB_USER" -p"$DB_PASSWORD" \
      --single-transaction --default-character-set=utf8mb4 "$DB_NAME" ;;
  *) echo "DB_ENGINE must be postgres or mariadb." >&2; exit 1 ;;
esac | gzip > "$FILE"

# A dump that failed part-way leaves a small file behind; don't keep it.
if [ ! -s "$FILE" ] || [ "$(gzip -dc "$FILE" | head -c 64 | wc -c)" -lt 16 ]; then
  rm -f "$FILE"
  echo "The backup came back empty. Is the database container running?" >&2
  exit 1
fi

chmod 600 "$FILE"
echo "Saved $FILE ($(du -h "$FILE" | cut -f1))"

ls -1t "$OUT_DIR"/personnel-*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
  rm -f "$old"; echo "Removed old backup $old"
done
