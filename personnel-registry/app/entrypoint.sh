#!/bin/sh
# Apply database migrations, then start the web server.
set -e
python -m registry.bootstrap
exec uvicorn registry.main:app \
  --host 0.0.0.0 \
  --port 8080 \
  --proxy-headers \
  --no-server-header \
  --timeout-graceful-shutdown 10
