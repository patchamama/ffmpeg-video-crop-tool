# FFmpeg Crop Tool - Windows context menu installer
# Run as the current user (no admin required).

$ExePath = Join-Path $PSScriptRoot "FFmpegCropTool.exe"
if (-not (Test-Path $ExePath)) {
    Write-Error "FFmpegCropTool.exe not found in $PSScriptRoot"
    exit 1
}

$VideoExts = @(".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv")
foreach ($ext in $VideoExts) {
    $base = "HKCU:\Software\Classes\$ext\shell\FFmpegCropTool"
    New-Item -Path "$base\command" -Force | Out-Null
    Set-ItemProperty -Path $base          -Name "(default)" -Value "Open with FFmpeg Crop Tool"
    Set-ItemProperty -Path $base          -Name "Icon"      -Value "`"$ExePath`""
    Set-ItemProperty -Path "$base\command" -Name "(default)" -Value "`"$ExePath`" `"%1`""
}

Write-Host "Done. Right-click any video file to see 'Open with FFmpeg Crop Tool'."
