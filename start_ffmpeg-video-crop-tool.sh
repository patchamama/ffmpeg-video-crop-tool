#!/usr/bin/env bash
set -euo pipefail

REPO="patchamama/ffmpeg-video-crop-tool"
RAW_BASE="https://raw.githubusercontent.com/$REPO/main"
REQUIRED_FILES=("crop_tool.py" "requirements.txt")

PORT=5553
URL="http://127.0.0.1:$PORT"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$SCRIPT_DIR/crop_tool.py"

# ---------------------------------------------------------------------------
# Auto-bootstrap: download any missing required files from GitHub
# ---------------------------------------------------------------------------
needs_download=0
for f in "${REQUIRED_FILES[@]}"; do
    [[ -f "$SCRIPT_DIR/$f" ]] || needs_download=1
done

if [[ "$needs_download" -eq 1 ]]; then
    echo "Required files missing. Downloading from github.com/$REPO ..."

    if command -v curl >/dev/null 2>&1; then
        _dl() { curl -fsSL "$1" -o "$2"; }
    elif command -v wget >/dev/null 2>&1; then
        _dl() { wget -q -O "$2" "$1"; }
    else
        echo "Error: install curl or wget and try again." >&2
        exit 1
    fi

    for f in "${REQUIRED_FILES[@]}"; do
        if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
            echo "  -> $f"
            _dl "$RAW_BASE/$f" "$SCRIPT_DIR/$f"
        fi
    done
    echo "Download complete."
fi

# ---------------------------------------------------------------------------
# Install Python dependencies
# ---------------------------------------------------------------------------
if [[ -f "$SCRIPT_DIR/requirements.txt" ]]; then
    echo "Installing Python requirements..."
    python3 -m pip install -q -r "$SCRIPT_DIR/requirements.txt"
fi

# ---------------------------------------------------------------------------
# Kill any process already using the port
# ---------------------------------------------------------------------------
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
    echo "Port $port busy (PID $pids). Stopping..."
    kill $pids 2>/dev/null || true
    sleep 1
    for pid in $pids; do
      kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
    done
  fi

  # WSL fallback: Windows-side processes are invisible to lsof/fuser/ss.
  # Flask debug mode spawns reloader parent + server child — kill both.
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
      echo "Port $port in use by Windows PID(s): $win_pids. Stopping via taskkill..."
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
  if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null && command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /C start "" "$url" >/dev/null 2>&1 || true
    return
  fi
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 || true
  fi
}

# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------
kill_port "$PORT"
echo "Starting $SCRIPT at $URL"
(sleep 1; open_browser "$URL") &
exec python3 "$SCRIPT"
