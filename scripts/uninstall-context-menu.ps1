# FFmpeg Crop Tool - Windows context menu uninstaller

$VideoExts = @(".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv")
foreach ($ext in $VideoExts) {
    $base = "HKCU:\Software\Classes\$ext\shell\FFmpegCropTool"
    Remove-Item -Path "$base\command" -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $base           -Force -ErrorAction SilentlyContinue
}

Write-Host "Context menu entries removed."
