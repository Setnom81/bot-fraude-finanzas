#!/bin/bash
# Started by bot-fraude.service. Brings up MySQL, waits for it, then runs the
# listener. The listener itself catches up on emails that arrived while the PC
# was off, so no separate catch-up step is needed.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"

cd "$PROJECT_DIR" || exit 1

echo "[STARTUP] Starting Docker containers..."
docker compose --env-file src/.env up -d

echo "[STARTUP] Waiting for MySQL..."
for _ in $(seq 1 60); do
    if docker exec mysql_finance_db mysqladmin ping -h 127.0.0.1 --silent >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

echo "[STARTUP] Starting the email listener..."
exec "$PYTHON_BIN" -m src.services.outlook_listener
