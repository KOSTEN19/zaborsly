#!/usr/bin/env bash
# Проверка HTTP-камеры Dahua с Linux-хоста и из worker.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILES=(-f docker-compose.yml)
if [[ -f .env ]] && grep -q '^COMPOSE_FILE=' .env; then
  IFS=':' read -ra files <<< "$(grep '^COMPOSE_FILE=' .env | cut -d= -f2- | tr -d '"')"
  COMPOSE_FILES=()
  for f in "${files[@]}"; do
    COMPOSE_FILES+=(-f "$f")
  done
elif [[ -f docker-compose.host-network.yml ]]; then
  COMPOSE_FILES+=(-f docker-compose.host-network.yml)
fi

HTTP_URL="$(grep '^CAMERA_1_HTTP=' .env | cut -d= -f2- | tr -d '"' || true)"
if [[ -z "$HTTP_URL" ]]; then
  echo "Задайте CAMERA_1_HTTP в .env" >&2
  exit 1
fi

read -r HOST PORT <<< "$(python3 - <<'PY' "$HTTP_URL"
import sys
from urllib.parse import urlparse
u = urlparse(sys.argv[1])
print(u.hostname or "", u.port or 80)
PY
)"

tcp_open() {
  timeout 3 bash -c "echo >/dev/tcp/${1}/${2}" 2>/dev/null
}

echo "==> HTTP: ${HTTP_URL/@*/@***}"
echo "==> Хост: ${HOST}:${PORT}"
echo ""

echo "==> 1) TCP порт ${PORT}"
if tcp_open "$HOST" "$PORT"; then
  echo "    OK"
else
  echo "    FAIL — сервер не видит камеру на порту ${PORT}"
  exit 1
fi

echo ""
echo "==> 2) HTTP из worker (Dahua reader)"
if ! docker compose "${COMPOSE_FILES[@]}" ps worker 2>/dev/null | grep -qE 'Up|running'; then
  echo "    Worker не запущен: docker compose up -d worker"
  exit 1
fi

docker compose "${COMPOSE_FILES[@]}" exec -T worker python - <<'PY' "$HTTP_URL"
import sys
from app.services.rtsp_reader import CameraReader, mask_stream_url

url = sys.argv[1]
print(f"    URL: {mask_stream_url(url)}")

reader = CameraReader(0, url)
ok = False
for i in range(5):
    frame = reader.read_raw()
    if frame is not None:
        print(f"    OK: кадр {frame.shape[1]}x{frame.shape[0]} (попытка {i + 1})")
        ok = True
        break
reader.close()
if not ok:
    print(f"    FAIL: {reader.last_error}")
    sys.exit(1)
PY

echo ""
echo "==> Камера доступна по HTTP."
