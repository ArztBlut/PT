#!/usr/bin/env bash
# Pull the latest code from GitHub, back up the database, and restart the stack.
# Database migrations run automatically when the app container starts.
set -euo pipefail
cd "$(dirname "$0")"

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


echo "Backing up the database first..."
./backup.sh

if [ -d .git ]; then
  echo "Fetching the latest code..."
  if [ -n "$(git status --porcelain -- . ':!.env' 2>/dev/null)" ]; then
    echo "You have local changes. Commit or stash them before updating." >&2
    git status --short -- . ':!.env' >&2
    exit 1
  fi
  git pull --ff-only
else
  echo "This isn't a git checkout. Pulling the latest published image."
fi

echo "Pulling the new image and restarting..."
dc pull
dc up -d
docker image prune -f >/dev/null 2>&1 || true

echo "Waiting for the registry..."
for i in $(seq 1 60); do
  if dc exec -T app python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=3)" >/dev/null 2>&1; then
    echo "Update complete."; exit 0
  fi
  sleep 2
done
echo "The registry hasn't answered yet. Check:  docker compose -f "$(compose_file)" logs -f app" >&2
exit 1
