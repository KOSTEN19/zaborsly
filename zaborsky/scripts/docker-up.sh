#!/usr/bin/env bash
# Очистка + сборка + запуск (без ContainerConfig).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${ROOT}/scripts/docker-clean.sh" --build "$@"
