#!/usr/bin/env bash
set -euo pipefail

PORT=5553
URL="http://127.0.0.1:$PORT"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$SCRIPT_DIR/crop_tool.py"

kill_port() {
  local port="$1"
  local pids=""

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti TCP:"$port" 2>/dev/null || true)"
  fi

  if [ -z "$pids" ] && command -v fuser >/dev/null 2>&1; then
    pids="$(fuser "$port"/tcp 2>/dev/null || true)"
  fi

  if [ -z "$pids" ] && command -v ss >/dev/null 2>&1; then
    pids="$(ss -ltnp "sport = :$port" 2>/dev/null | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | sort -u || true)"
  fi

  if [ -n "$pids" ]; then
    echo "Puerto $port ocupado por PID(s): $pids. Cerrando..."
    kill $pids 2>/dev/null || true
    sleep 1
    for pid in $pids; do
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
    done
  fi

  # WSL fallback: kill Windows-side processes via PowerShell (invisible to lsof/fuser/ss).
  # Flask debug mode runs a reloader parent + server child; kill child AND its parent.
  if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null && command -v powershell.exe >/dev/null 2>&1; then
    local attempts=0
    while [ $attempts -lt 5 ]; do
      local win_pids
      win_pids="$(powershell.exe -NoProfile -Command "
        \$child_pids = (Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue).OwningProcess |
          Where-Object { \$_ -ne 0 } | Sort-Object -Unique
        \$parent_pids = \$child_pids | ForEach-Object {
          (Get-WmiObject Win32_Process -Filter \"ProcessId = \$_\" -ErrorAction SilentlyContinue).ParentProcessId
        } | Where-Object { \$_ -and \$_ -ne 0 }
        (@(\$child_pids) + @(\$parent_pids)) | Where-Object { \$_ } | Sort-Object -Unique
      " 2>/dev/null | tr -d '\r' | grep -E '^[1-9][0-9]*$' || true)"
      [ -z "$win_pids" ] && break
      echo "Puerto $port ocupado por proceso(s) Windows PID(s): $win_pids. Cerrando via taskkill..."
      for wpid in $win_pids; do
        powershell.exe -NoProfile -Command "Stop-Process -Id $wpid -Force -ErrorAction SilentlyContinue" 2>/dev/null || true
      done
      sleep 1
      attempts=$((attempts + 1))
    done
  fi
}

open_browser() {
  local url="$1"

  # In WSL, open the Windows default browser.
  if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null && command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /C start "" "$url" >/dev/null 2>&1 || true
    return
  fi

  # Linux/macOS fallback.
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 || true
  fi
}

kill_port "$PORT"
echo "Iniciando $SCRIPT en $URL"
(sleep 1; open_browser "$URL") &
exec python3 "$SCRIPT"
