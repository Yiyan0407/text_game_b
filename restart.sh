#!/usr/bin/env bash
# 后台重启 Streamlit 跑团应用（适用于 Linux 服务器）
# 用法：./restart.sh
#       INSTALL=1 ./restart.sh   # 重启前 pip install -r requirements.txt

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PORT="${STREAMLIT_PORT:-8503}"
HOST="${STREAMLIT_HOST:-0.0.0.0}"
LOG_DIR="$ROOT_DIR/logs"
RUN_DIR="$ROOT_DIR/.run"
LOG_FILE="$LOG_DIR/streamlit.log"
PID_FILE="$RUN_DIR/streamlit.pid"

mkdir -p "$LOG_DIR" "$RUN_DIR"

if [[ -f "$ROOT_DIR/.venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "$ROOT_DIR/.venv/bin/activate"
elif [[ -f "$ROOT_DIR/venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "$ROOT_DIR/venv/bin/activate"
fi

stop_server() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "停止旧进程 PID=$pid ..."
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
  fi

  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" 2>/dev/null || true
  elif command -v lsof >/dev/null 2>&1; then
    lsof -ti ":${PORT}" | xargs -r kill -9 2>/dev/null || true
  fi
}

if [[ "${INSTALL:-0}" == "1" ]]; then
  echo "安装依赖..."
  python -m pip install -r requirements.txt
fi

stop_server

echo "启动 Streamlit（${HOST}:${PORT}）..."
nohup streamlit run app.py \
  --server.address="$HOST" \
  --server.port="$PORT" \
  --server.headless=true \
  >> "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"
sleep 1

if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "已启动 PID=$(cat "$PID_FILE")"
  echo "日志：$LOG_FILE"
  echo "访问：http://127.0.0.1:${PORT} （外网请用服务器 IP）"
else
  echo "启动失败，请查看日志：$LOG_FILE" >&2
  tail -n 30 "$LOG_FILE" >&2 || true
  exit 1
fi
