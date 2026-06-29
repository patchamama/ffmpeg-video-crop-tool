#!/usr/bin/env bash
# FFmpeg Crop Tool launcher — macOS / Linux
# Usage: ./start_ffmpeg-video-crop-tool.sh [video_file]

REPO="patchamama/ffmpeg-video-crop-tool"
RAW_BASE="https://raw.githubusercontent.com/$REPO/main"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
VENV_PY="$VENV/bin/python3"

# ---------------------------------------------------------------------------
# Download helper (curl preferred, wget fallback)
# ---------------------------------------------------------------------------
if command -v curl >/dev/null 2>&1; then
    _dl() { curl -fsSL --max-time 30 "$1" -o "$2"; }
elif command -v wget >/dev/null 2>&1; then
    _dl() { wget -q -T 30 -O "$2" "$1"; }
else
    echo "Error: install curl or wget and try again." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Auto-bootstrap: download missing required files from GitHub
# ---------------------------------------------------------------------------
REQUIRED_FILES=(crop_tool.py launcher.py requirements.txt version.txt)
needs_download=0
for f in "${REQUIRED_FILES[@]}"; do
    [[ -f "$SCRIPT_DIR/$f" ]] || needs_download=1
done

if [[ "$needs_download" -eq 1 ]]; then
    echo "Required files missing. Downloading from github.com/$REPO ..."
    for f in "${REQUIRED_FILES[@]}"; do
        if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
            echo "  -> $f"
            _dl "$RAW_BASE/$f" "$SCRIPT_DIR/$f" || echo "  Warning: could not download $f"
        fi
    done
    echo "Download complete."
fi

# ---------------------------------------------------------------------------
# Auto-update (skipped when running from a git clone)
# ---------------------------------------------------------------------------
if [[ ! -d "$SCRIPT_DIR/.git" ]] && [[ -f "$SCRIPT_DIR/version.txt" ]]; then
    LOCAL_VER="$(tr -d '[:space:]' < "$SCRIPT_DIR/version.txt")"
    TMP_VER="$(mktemp)"
    _dl "$RAW_BASE/version.txt" "$TMP_VER" 2>/dev/null || true
    if [[ -s "$TMP_VER" ]]; then
        REMOTE_VER="$(tr -d '[:space:]' < "$TMP_VER")"
        UPDATE_NEEDED="$(python3 -c "
import sys
def v(s): return tuple(int(x) for x in s.strip().split('.'))
sys.stdout.write('1' if v('$REMOTE_VER') > v('$LOCAL_VER') else '0')
" 2>/dev/null || echo 0)"
        if [[ "$UPDATE_NEEDED" == "1" ]]; then
            echo "Update available: v$LOCAL_VER -> v$REMOTE_VER. Downloading..."
            for f in crop_tool.py launcher.py requirements.txt version.txt; do
                echo "  -> $f"
                _dl "$RAW_BASE/$f" "$SCRIPT_DIR/$f" || echo "  Warning: could not update $f"
            done
            echo "Updated to v$REMOTE_VER."
        fi
    fi
    rm -f "$TMP_VER"
fi

# ---------------------------------------------------------------------------
# Create virtual environment if missing
# ---------------------------------------------------------------------------
if [[ ! -f "$VENV_PY" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV" || {
        echo "Error: python3-venv is required." >&2
        echo "  Ubuntu/Debian: sudo apt install python3-venv" >&2
        echo "  Fedora:        sudo dnf install python3" >&2
        exit 1
    }
fi

# ---------------------------------------------------------------------------
# Install / sync Python requirements
# ---------------------------------------------------------------------------
if [[ -f "$SCRIPT_DIR/requirements.txt" ]]; then
    echo "Installing Python requirements..."
    "$VENV_PY" -m pip install -q -r "$SCRIPT_DIR/requirements.txt"
fi

# ---------------------------------------------------------------------------
# Launch — pass any file arguments through to the launcher
# ---------------------------------------------------------------------------
exec "$VENV_PY" "$SCRIPT_DIR/launcher.py" "$@"
