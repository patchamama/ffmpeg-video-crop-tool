#!/usr/bin/env bash
# FFmpeg Crop Tool — Linux file association installer
# Supports both the compiled exe and the .sh script launcher.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXE_PATH="$SCRIPT_DIR/../FFmpegCropTool"
SH_PATH="$SCRIPT_DIR/../start_ffmpeg-video-crop-tool.sh"

if [[ -f "$EXE_PATH" ]]; then
    EXE="$(realpath "$EXE_PATH")"
    chmod +x "$EXE"
    EXEC_LINE="Exec=\"$EXE\" %f"
    TERMINAL="false"
elif [[ -f "$SH_PATH" ]]; then
    SH="$(realpath "$SH_PATH")"
    chmod +x "$SH"
    EXEC_LINE="Exec=bash \"$SH\" %f"
    TERMINAL="true"
else
    echo "Error: neither FFmpegCropTool nor start_ffmpeg-video-crop-tool.sh found in $(realpath "$SCRIPT_DIR/..")" >&2
    exit 1
fi

APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"

cat > "$APPS_DIR/ffmpeg-crop-tool.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=FFmpeg Crop Tool
Comment=Crop videos with a visual overlay using FFmpeg
$EXEC_LINE
Terminal=$TERMINAL
MimeType=video/mp4;video/x-matroska;video/x-msvideo;video/quicktime;video/webm;video/x-ms-wmv;video/x-flv;
Categories=AudioVideo;Video;;
EOF

chmod +x "$APPS_DIR/ffmpeg-crop-tool.desktop"
update-desktop-database "$APPS_DIR" 2>/dev/null || true

echo "Installed to $APPS_DIR/ffmpeg-crop-tool.desktop"
echo "Right-click a video file → 'Open With' → 'FFmpeg Crop Tool'"
echo ""
echo "To uninstall:"
echo "  rm \"$APPS_DIR/ffmpeg-crop-tool.desktop\""
echo "  update-desktop-database \"$APPS_DIR\""
