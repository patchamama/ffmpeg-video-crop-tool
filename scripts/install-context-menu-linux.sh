#!/usr/bin/env bash
# FFmpeg Crop Tool - Linux context menu / file association installer
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXE="$SCRIPT_DIR/FFmpegCropTool"

if [ ! -f "$EXE" ]; then
    echo "Error: FFmpegCropTool not found in $SCRIPT_DIR" >&2
    exit 1
fi

chmod +x "$EXE"

APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"

cat > "$APPS_DIR/ffmpeg-crop-tool.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=FFmpeg Crop Tool
Comment=Crop videos with a visual overlay using FFmpeg
Exec=$EXE %f
Terminal=true
MimeType=video/mp4;video/x-matroska;video/x-msvideo;video/quicktime;video/webm;video/x-ms-wmv;video/x-flv;
Categories=AudioVideo;Video;;
EOF

chmod +x "$APPS_DIR/ffmpeg-crop-tool.desktop"
update-desktop-database "$APPS_DIR" 2>/dev/null || true

echo "Installed. Right-click a video file and choose 'Open With > FFmpeg Crop Tool'."
