#!/usr/bin/env bash
# FFmpeg Crop Tool — macOS file association installer
# Creates a minimal .app bundle in ~/Applications and registers it with
# Launch Services so the tool appears in "Open With" for video files.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER="$(realpath "$SCRIPT_DIR/../start_ffmpeg-video-crop-tool.sh")"

if [[ ! -f "$LAUNCHER" ]]; then
    echo "Error: start_ffmpeg-video-crop-tool.sh not found at $LAUNCHER" >&2
    exit 1
fi
chmod +x "$LAUNCHER"

APP_NAME="FFmpegCropTool"
INSTALL_DIR="$HOME/Applications"
APP="$INSTALL_DIR/$APP_NAME.app"

echo "Creating $APP ..."
mkdir -p "$APP/Contents/MacOS"

# Executable wrapper that calls the .sh launcher
cat > "$APP/Contents/MacOS/$APP_NAME" << SHELL
#!/bin/bash
exec "$LAUNCHER" "\$@"
SHELL
chmod +x "$APP/Contents/MacOS/$APP_NAME"

# Info.plist — declares supported video types for "Open With"
cat > "$APP/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>FFmpeg Crop Tool</string>
  <key>CFBundleDisplayName</key>
  <string>FFmpeg Crop Tool</string>
  <key>CFBundleIdentifier</key>
  <string>com.patchamama.ffmpeg-crop-tool</string>
  <key>CFBundleVersion</key>
  <string>1.0</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleExecutable</key>
  <string>FFmpegCropTool</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSMinimumSystemVersion</key>
  <string>10.14</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>CFBundleDocumentTypes</key>
  <array>
    <dict>
      <key>CFBundleTypeName</key>
      <string>Video File</string>
      <key>CFBundleTypeRole</key>
      <string>Viewer</string>
      <key>LSHandlerRank</key>
      <string>Alternate</string>
      <key>CFBundleTypeExtensions</key>
      <array>
        <string>mp4</string>
        <string>mkv</string>
        <string>avi</string>
        <string>mov</string>
        <string>webm</string>
        <string>m4v</string>
      </array>
      <key>LSItemContentTypes</key>
      <array>
        <string>public.movie</string>
        <string>public.mpeg-4</string>
        <string>public.avi</string>
        <string>com.apple.quicktime-movie</string>
        <string>org.webmproject.webm</string>
      </array>
    </dict>
  </array>
</dict>
</plist>
PLIST

# Register with macOS Launch Services
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [[ -x "$LSREGISTER" ]]; then
    "$LSREGISTER" -f "$APP" && echo "Registered with Launch Services."
else
    echo "Warning: lsregister not found — you may need to log out and back in."
fi

echo ""
echo "Installed to: $APP"
echo "Right-click any video file → 'Open With' → 'FFmpeg Crop Tool'"
echo ""
echo "To uninstall:"
echo "  rm -rf \"$APP\""
echo "  $LSREGISTER -u \"$APP\""
