# FFmpeg Crop Tool — Windows context menu installer
# Supports both the compiled exe and the .bat script launcher.
# Run as the current user (no admin required).

$ExePath = Join-Path $PSScriptRoot "..\FFmpegCropTool.exe"
$BatPath = Join-Path $PSScriptRoot "..\start_ffmpeg-video-crop-tool.bat"

if (Test-Path $ExePath) {
    $Exe      = (Resolve-Path $ExePath).Path
    $CmdValue = "`"$Exe`" `"%1`""
    $IconPath = $Exe
} elseif (Test-Path $BatPath) {
    $Bat      = (Resolve-Path $BatPath).Path
    $CmdValue = "cmd.exe /C `"$Bat`" `"%1`""
    $IconPath = "C:\Windows\System32\cmd.exe"
} else {
    Write-Error "Neither FFmpegCropTool.exe nor start_ffmpeg-video-crop-tool.bat found in $(Resolve-Path "$PSScriptRoot\..")"
    exit 1
}

$VideoExts = @(".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv")
foreach ($ext in $VideoExts) {
    $base = "HKCU:\Software\Classes\$ext\shell\FFmpegCropTool"
    New-Item -Path "$base\command" -Force | Out-Null
    Set-ItemProperty -Path $base           -Name "(default)" -Value "Open with FFmpeg Crop Tool"
    Set-ItemProperty -Path $base           -Name "Icon"      -Value $IconPath
    Set-ItemProperty -Path "$base\command" -Name "(default)" -Value $CmdValue
}

Write-Host "Done. Right-click any video file to see 'Open with FFmpeg Crop Tool'."
