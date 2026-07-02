#!/usr/bin/env bash
# Очистка старых контейнеров/образов проекта.
# Устраняет KeyError: ContainerConfig при docker-compose up.
#
# Использование:
#   ./scripts/docker-clean.sh
#   ./scripts/docker-clean.sh --build
#   ./scripts/docker-clean.sh --volumes --build

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

compose_files() {
  if [[ -f .env ]] && grep -q '^COMPOSE_FILE=' .env; then
    local raw
    raw="$(grep '^COMPOSE_FILE=' .env | cut -d= -f2- | tr -d '"')"
    local -a files
    IFS=':' read -ra files <<< "$raw"
    local -a args=()
    for f in "${files[@]}"; do
      args+=(-f "$f")
    done
    printf '%s\n' "${args[@]}"
  elif [[ -f docker-compose.host-network.yml ]]; then
    printf '%s\n' -f docker-compose.yml -f docker-compose.host-network.yml
  else
    printf '%s\n' -f docker-compose.yml
  fi
}

mapfile -t COMPOSE_ARGS < <(compose_files)

REMOVE_VOLUMES=false
REMOVE_ALL_IMAGES=false
START_AFTER=false

usage() {
  cat <<'EOF'
Usage: ./scripts/docker-clean.sh [options]

Options:
  --volumes       Удалить тома (postgres, фото) — данные будут потеряны
  --all-images    Удалить все образы сервисов (не только локальные)
  --build         После очистки: docker compose up -d --build
  -h, --help      Справка

Примеры:
  ./scripts/docker-clean.sh
  ./scripts/docker-clean.sh --build
  ./scripts/docker-clean.sh --volumes --build
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --volumes) REMOVE_VOLUMES=true; shift ;;
    --all-images) REMOVE_ALL_IMAGES=true; shift ;;
    --build) START_AFTER=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Неизвестный аргумент: $1" >&2; usage; exit 1 ;;
  esac
done

if ! docker compose version >/dev/null 2>&1; then
  if command -v docker-compose >/dev/null 2>&1; then
    echo "Ошибка: найден устаревший docker-compose (v1)." >&2
    echo "Установите Compose v2: sudo apt install docker-compose-v2" >&2
    echo "Используйте: docker compose (без дефиса)" >&2
  else
    echo "Ошибка: docker compose не найден." >&2
  fi
  exit 1
fi

PROJECT_NAME="$(basename "$ROOT")"

echo "==> Проект: ${PROJECT_NAME}"
echo "==> Остановка и удаление контейнеров..."

DOWN_ARGS=(down --remove-orphans)
if $REMOVE_ALL_IMAGES; then
  DOWN_ARGS+=(--rmi all)
else
  DOWN_ARGS+=(--rmi local)
fi
if $REMOVE_VOLUMES; then
  DOWN_ARGS+=(-v)
  echo "    (тома будут удалены)"
fi

docker compose "${COMPOSE_ARGS[@]}" "${DOWN_ARGS[@]}" || true

echo "==> Удаление зависших контейнеров..."

while IFS= read -r id; do
  [[ -z "$id" ]] && continue
  docker rm -f "$id" >/dev/null 2>&1 || true
done < <(docker ps -aq --filter "label=com.docker.compose.project=${PROJECT_NAME}" 2>/dev/null || true)

while IFS= read -r name; do
  [[ -z "$name" ]] && continue
  docker rm -f "$name" >/dev/null 2>&1 || true
done < <(docker ps -a --format '{{.Names}}' 2>/dev/null | grep -E "^${PROJECT_NAME}[-_]" || true)

echo "==> Очистка завершена."

if $START_AFTER; then
  echo "==> Запуск: docker compose up -d --build"
  docker compose "${COMPOSE_ARGS[@]}" up -d --build
  echo "==> Готово."
else
  echo "Дальше: docker compose up -d --build"
fi
