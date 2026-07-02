#!/usr/bin/env bash
# Диагностика доступа к RTSP-камере с Linux-хоста.
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

if [[ ! -f .env ]]; then
  echo "Файл .env не найден" >&2
  exit 1
fi

RTSP_URL="$(grep '^CAMERA_1_HTTP=' .env | cut -d= -f2- | tr -d '"' || true)"
SOURCE_KIND="HTTP"
if [[ -z "$RTSP_URL" ]]; then
  RTSP_URL="$(grep '^CAMERA_1_RTSP=' .env | cut -d= -f2- | tr -d '"' || true)"
  SOURCE_KIND="RTSP"
fi
if [[ -z "$RTSP_URL" ]]; then
  echo "Задайте CAMERA_1_HTTP или CAMERA_1_RTSP в .env" >&2
  exit 1
fi

read -r HOST PORT <<< "$(python3 - <<'PY' "$RTSP_URL"
import sys
from urllib.parse import urlparse
u = urlparse(sys.argv[1])
host = u.hostname or ""
if u.port:
    port = u.port
elif u.scheme == "http":
    port = 80
else:
    port = 554
print(host, port)
PY
)"

tcp_open() {
  local host="$1" port="$2"
  timeout 3 bash -c "echo >/dev/tcp/${host}/${port}" 2>/dev/null
}

echo "==> Источник: ${SOURCE_KIND}"
echo "==> Камера: ${HOST}:${PORT}"
echo "==> RTSP: ${RTSP_URL/@*/@***}"
echo ""

echo "==> 0) Сеть Linux-хоста"
if command -v ip >/dev/null 2>&1; then
  ip -4 route get "$HOST" 2>/dev/null | sed 's/^/    /' || echo "    Нет маршрута до ${HOST}"
  echo "    IP хоста:"
  ip -4 addr show scope global 2>/dev/null | awk '/inet /{print "      "$2" "$NF}' || true
else
  echo "    (команда ip не найдена)"
fi

echo ""
echo "==> 1) Ping"
if ping -c 2 -W 2 "$HOST" >/dev/null 2>&1; then
  echo "    OK: ping проходит"
else
  echo "    WARN: ping не проходит (ICMP может быть отключён на камере)"
fi

echo ""
echo "==> 2) TCP-порты камеры"
declare -A PORT_NAMES=([80]="HTTP (веб-интерфейс)" [554]="RTSP" [37777]="Dahua SDK")
HOST_REACHABLE=false
RTSP_OPEN=false
for p in 80 554 37777; do
  label="${PORT_NAMES[$p]}"
  if tcp_open "$HOST" "$p"; then
    echo "    OK  :${p}  ${label}"
    HOST_REACHABLE=true
    [[ "$p" == "554" ]] && RTSP_OPEN=true
  else
    echo "    FAIL:${p}  ${label}"
  fi
done

if ! $HOST_REACHABLE; then
  echo ""
  echo "!!! Хост не видит камеру ни на одном порту."
  echo "    Docker тут не поможет — сначала нужна сеть до ${HOST}."
  echo ""
  echo "Проверьте:"
  echo "  • Linux и камера в одной подсети? (например 172.16.0.x/24)"
  echo "  • IP камеры верный? Посмотрите в приложении производителя или на роутере"
  echo "  • Кабель / PoE / питание камеры"
  echo "  • Маршрутизация между VLAN (если сервер в другой сети)"
  echo "  • firewall: sudo ufw status"
  exit 1
fi

if ! $RTSP_OPEN && [[ "$SOURCE_KIND" == "HTTP" ]] && tcp_open "$HOST" 80; then
  echo ""
  echo "Порт 554 закрыт, но HTTP (80) доступен — используйте CAMERA_1_HTTP (уже задан)."
  RTSP_OPEN=true
fi

if ! $RTSP_OPEN; then
  echo ""
  echo "!!! Порт 554 закрыт — VLC и worker не подключатся."
  echo ""
  if tcp_open "$HOST" 80; then
    echo "Веб-интерфейс доступен: http://${HOST}/"
    echo "В камере включите RTSP: Настройки → Сеть → RTSP (или Аналоговый канал → Кодирование)."
  fi
  echo ""
  echo "Попробуйте в VLC (Медиа → Открыть URL) с TCP:"
  echo "  ${RTSP_URL}"
  echo "  В VLC: Инструменты → Настройки → Ввод/кодеки → RTSP через TCP"
  echo ""
  echo "Альтернативные URL Dahua:"
  echo "  rtsp://USER:PASS@${HOST}:554/cam/realmonitor?channel=1&subtype=1"
  echo "  rtsp://USER:PASS@${HOST}:554/Streaming/Channels/101"
  echo "  rtsp://USER:PASS@${HOST}:554/Streaming/Channels/102"
  exit 1
fi

echo ""
echo "==> 3) HTTP веб-интерфейс"
if command -v curl >/dev/null 2>&1 && tcp_open "$HOST" 80; then
  code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 "http://${HOST}/" || echo "000")"
  echo "    HTTP код: ${code} (ожидается 200/401/302)"
else
  echo "    пропуск (curl или порт 80 недоступен)"
fi

echo ""
echo "==> 4) Поток через ffmpeg (если установлен)"
if command -v ffprobe >/dev/null 2>&1; then
  FFPROBE_ARGS=(-v error -show_entries stream=codec_name -of csv=p=0 -timeout 10000000 -i "$RTSP_URL")
  if [[ "$SOURCE_KIND" == "RTSP" ]]; then
    FFPROBE_ARGS=(-rtsp_transport tcp "${FFPROBE_ARGS[@]}")
  fi
  if ffprobe "${FFPROBE_ARGS[@]}" 2>/dev/null | head -1 | grep -q .; then
    echo "    OK: ffprobe открыл поток"
  else
    echo "    FAIL: ffprobe не открыл поток (проверьте логин/пароль и URL)"
    echo ""
    echo "VLC: включите RTSP через TCP."
    echo "Пароль со спецсимволами кодируйте в URL: ! → %21  @ → %40"
    exit 1
  fi
else
  echo "    пропуск (установите: sudo apt install ffmpeg)"
fi

echo ""
echo "==> 5) Поток из worker (OpenCV / HTTP)"
if docker compose "${COMPOSE_FILES[@]}" ps worker 2>/dev/null | grep -qE 'Up|running'; then
  docker compose "${COMPOSE_FILES[@]}" exec -T worker python - <<'PY' "$RTSP_URL" "$SOURCE_KIND"
import os
import sys
import cv2

url = sys.argv[1]
kind = sys.argv[2]
if kind == "RTSP":
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;15000000"
cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
if not cap.isOpened() and kind == "HTTP":
    from app.services.rtsp_reader import RTSPReader
    reader = RTSPReader(0, url)
    frame = reader.read_raw()
    reader.close()
    if frame is None:
        print("    FAIL: HTTP поток не открыт")
        sys.exit(1)
    print(f"    OK: HTTP кадр {frame.shape[1]}x{frame.shape[0]}")
    sys.exit(0)
if not cap.isOpened():
    print("    FAIL: поток не открыт")
    sys.exit(1)
ok, frame = cap.read()
cap.release()
if not ok or frame is None:
    print("    FAIL: кадр не получен")
    sys.exit(1)
print(f"    OK: кадр {frame.shape[1]}x{frame.shape[0]}")
PY
else
  echo "    пропуск (worker не запущен)"
fi

echo ""
echo "==> Камера доступна по сети."
