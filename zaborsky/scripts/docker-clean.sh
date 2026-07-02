#!/usr/bin/env bash
# Полная очистка контейнеров/образов проекта zaborsky.
# Устраняет KeyError: ContainerConfig (битые контейнеры + устаревший docker-compose v1).
#
# Использование:
#   ./scripts/docker-clean.sh --build
#   ./scripts/docker-clean.sh --volumes --build

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

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

Важно:
  Используйте только "docker compose" (v2), НЕ "docker-compose" (v1).
  Если ошибка ContainerConfig повторяется:
    sudo apt remove docker-compose
    ./scripts/docker-clean.sh --all-images --build

Примеры:
  ./scripts/docker-clean.sh --build
  ./scripts/docker-clean.sh --volumes --all-images --build
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

if command -v docker-compose >/dev/null 2>&1; then
  echo "==> ВНИМАНИЕ: найден устаревший docker-compose (v1) — из-за него бывает ContainerConfig." >&2
  echo "    Удалите: sudo apt remove docker-compose" >&2
  echo "    Используйте только: docker compose (без дефиса)" >&2
  echo "" >&2
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Ошибка: docker compose (v2) не найден." >&2
  echo "Установите: sudo apt install docker-compose-v2" >&2
  exit 1
fi

# Подхватить COMPOSE_FILE из .env (docker compose читает .env сам, но явно не помешает)
if [[ -f .env ]] && grep -q '^COMPOSE_FILE=' .env; then
  export COMPOSE_FILE="$(grep '^COMPOSE_FILE=' .env | cut -d= -f2- | tr -d '"')"
fi

compose_args() {
  if [[ -n "${COMPOSE_FILE:-}" ]]; then
    local -a files
    IFS=':' read -ra files <<< "$COMPOSE_FILE"
    for f in "${files[@]}"; do
      printf '%s\0' "-f" "$f"
    done
  elif [[ -f docker-compose.host-network.yml ]]; then
    printf '%s\0' "-f" "docker-compose.yml" "-f" "docker-compose.host-network.yml"
  else
    printf '%s\0' "-f" "docker-compose.yml"
  fi
}

mapfile -d '' -t COMPOSE_ARGS < <(compose_args)

PROJECT_NAME="$(basename "$ROOT")"
if [[ ${#COMPOSE_ARGS[@]} -gt 0 ]]; then
  cfg_name="$(docker compose "${COMPOSE_ARGS[@]}" config --format '{{.name}}' 2>/dev/null || true)"
  [[ -n "$cfg_name" ]] && PROJECT_NAME="$cfg_name"
fi

echo "==> Проект: ${PROJECT_NAME}"
if [[ -n "${COMPOSE_FILE:-}" ]]; then
  echo "==> COMPOSE_FILE: ${COMPOSE_FILE}"
fi

container_name_matches() {
  local name="$1"
  [[ "$name" =~ ^${PROJECT_NAME}[-_] ]] || [[ "$name" =~ _${PROJECT_NAME}[-_] ]]
}

force_remove_containers() {
  local id name removed=0

  echo "==> Принудительная остановка контейнеров проекта..."

  set +e
  while IFS= read -r id; do
    [[ -z "$id" ]] && continue
    docker kill "$id" >/dev/null 2>&1
    docker rm -f "$id" >/dev/null 2>&1 && removed=$((removed + 1))
  done < <(docker ps -aq --filter "label=com.docker.compose.project=${PROJECT_NAME}" 2>/dev/null)

  while IFS= read -r name; do
    [[ -z "$name" ]] && continue
    if container_name_matches "$name"; then
      docker rm -f "$name" >/dev/null 2>&1 && removed=$((removed + 1))
    fi
  done < <(docker ps -a --format '{{.Names}}' 2>/dev/null)

  # Старые контейнеры compose v1 с hash-префиксом: abc123_zaborsky_frontend_1
  while IFS= read -r name; do
    [[ -z "$name" ]] && continue
    if [[ "$name" == *"${PROJECT_NAME}"* ]]; then
      docker rm -f "$name" >/dev/null 2>&1 && removed=$((removed + 1))
    fi
  done < <(docker ps -a --format '{{.Names}}' 2>/dev/null | grep -F "${PROJECT_NAME}" || true)

  set -e
  echo "    удалено контейнеров: ${removed}"
}

remove_images() {
  local id repo removed=0
  echo "==> Удаление образов проекта..."

  set +e
  while IFS= read -r id; do
    [[ -z "$id" ]] && continue
    docker rmi -f "$id" >/dev/null 2>&1 && removed=$((removed + 1))
  done < <(docker images -q --filter "label=com.docker.compose.project=${PROJECT_NAME}" 2>/dev/null)

  while IFS= read -r line; do
    id="${line%% *}"
    repo="${line#* }"
    [[ -z "$id" || -z "$repo" ]] && continue
    if [[ "$repo" == "${PROJECT_NAME}-"* ]] || [[ "$repo" == "${PROJECT_NAME}_"* ]]; then
      docker rmi -f "$id" >/dev/null 2>&1 && removed=$((removed + 1))
    fi
  done < <(docker images --format '{{.ID}} {{.Repository}}' 2>/dev/null)

  if $REMOVE_ALL_IMAGES; then
    for svc in api worker frontend postgres nginx; do
      while IFS= read -r id; do
        [[ -z "$id" ]] && continue
        docker rmi -f "$id" >/dev/null 2>&1 && removed=$((removed + 1))
      done < <(docker images -q "${PROJECT_NAME}-${svc}" 2>/dev/null)
    done
  fi

  set -e
  echo "    удалено образов: ${removed}"
}

remove_networks() {
  echo "==> Удаление сетей проекта..."
  set +e
  docker network ls --format '{{.Name}}' 2>/dev/null | while IFS= read -r net; do
    [[ "$net" == "${PROJECT_NAME}_default" || "$net" == "${PROJECT_NAME}-default" ]] || continue
    docker network rm "$net" >/dev/null 2>&1 || true
  done
  set -e
}

remove_volumes() {
  echo "==> Удаление томов проекта..."
  set +e
  docker volume ls --format '{{.Name}}' 2>/dev/null | while IFS= read -r vol; do
    [[ "$vol" == "${PROJECT_NAME}_"* ]] || continue
    docker volume rm -f "$vol" >/dev/null 2>&1 || true
    echo "    том удалён: ${vol}"
  done
  set -e
}

# 1) Сначала принудительно убить контейнеры (compose down падает с ContainerConfig на битых)
force_remove_containers

# 2) compose down — best effort
echo "==> docker compose down..."
set +e
DOWN_ARGS=(down --remove-orphans)
if $REMOVE_ALL_IMAGES; then
  DOWN_ARGS+=(--rmi all)
else
  DOWN_ARGS+=(--rmi local)
fi
if $REMOVE_VOLUMES; then
  DOWN_ARGS+=(-v)
fi
docker compose "${COMPOSE_ARGS[@]}" "${DOWN_ARGS[@]}"
down_rc=$?
set -e
if [[ $down_rc -ne 0 ]]; then
  echo "    compose down завершился с кодом ${down_rc} (продолжаем принудительную очистку)"
fi

# 3) Повторно — на случай если down что-то оставил
force_remove_containers
remove_images
remove_networks
$REMOVE_VOLUMES && remove_volumes

# 4) Dangling мусор compose
set +e
docker container prune -f >/dev/null 2>&1
$REMOVE_ALL_IMAGES && docker image prune -f >/dev/null 2>&1
set -e

echo "==> Очистка завершена."

if $START_AFTER; then
  echo "==> Запуск: docker compose up -d --build --remove-orphans"
  # Без --force-recreate: контейнеры уже удалены, создаём с нуля
  docker compose "${COMPOSE_ARGS[@]}" up -d --build --remove-orphans
  echo "==> Готово."
  docker compose "${COMPOSE_ARGS[@]}" ps
else
  echo ""
  echo "Дальше:"
  echo "  docker compose up -d --build --remove-orphans"
  echo "или:"
  echo "  ./scripts/docker-clean.sh --build"
fi
