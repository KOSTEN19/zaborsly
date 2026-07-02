#!/usr/bin/env bash
# Запуск с host-network для доступа worker к камере в LAN.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

exec docker compose -f docker-compose.yml -f docker-compose.host-network.yml up -d --build "$@"
