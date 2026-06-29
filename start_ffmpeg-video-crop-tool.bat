@echo off
setlocal enabledelayedexpansion

set "REPO=patchamama/ffmpeg-video-crop-tool"
set "RAW_BASE=https://raw.githubusercontent.com/%REPO%/main"
set "SCRIPT_DIR=%~dp0"

:: ---------------------------------------------------------------------------
:: Auto-bootstrap: download missing files from GitHub
:: ---------------------------------------------------------------------------
set "NEEDS_DOWNLOAD=0"
if not exist "%SCRIPT_DIR%crop_tool.py"     set "NEEDS_DOWNLOAD=1"
if not exist "%SCRIPT_DIR%launcher.py"      set "NEEDS_DOWNLOAD=1"
if not exist "%SCRIPT_DIR%requirements.txt" set "NEEDS_DOWNLOAD=1"

if "%NEEDS_DOWNLOAD%"=="1" (
    echo Required files missing. Downloading from github.com/%REPO% ...

    where curl >nul 2>&1
    if !errorlevel!==0 (
        if not exist "%SCRIPT_DIR%crop_tool.py" (
            echo   -^> crop_tool.py
            curl -fsSL "%RAW_BASE%/crop_tool.py" -o "%SCRIPT_DIR%crop_tool.py"
        )
        if not exist "%SCRIPT_DIR%launcher.py" (
            echo   -^> launcher.py
            curl -fsSL "%RAW_BASE%/launcher.py" -o "%SCRIPT_DIR%launcher.py"
        )
        if not exist "%SCRIPT_DIR%requirements.txt" (
            echo   -^> requirements.txt
            curl -fsSL "%RAW_BASE%/requirements.txt" -o "%SCRIPT_DIR%requirements.txt"
        )
    ) else (
        echo   Using PowerShell to download...
        if not exist "%SCRIPT_DIR%crop_tool.py" (
            echo   -^> crop_tool.py
            powershell -NoProfile -Command "Invoke-WebRequest -Uri '%RAW_BASE%/crop_tool.py' -OutFile '%SCRIPT_DIR%crop_tool.py'"
        )
        if not exist "%SCRIPT_DIR%launcher.py" (
            echo   -^> launcher.py
            powershell -NoProfile -Command "Invoke-WebRequest -Uri '%RAW_BASE%/launcher.py' -OutFile '%SCRIPT_DIR%launcher.py'"
        )
        if not exist "%SCRIPT_DIR%requirements.txt" (
            echo   -^> requirements.txt
            powershell -NoProfile -Command "Invoke-WebRequest -Uri '%RAW_BASE%/requirements.txt' -OutFile '%SCRIPT_DIR%requirements.txt'"
        )
    )
    echo Download complete.
)

:: ---------------------------------------------------------------------------
:: Install Python requirements (Flask etc.)
:: ---------------------------------------------------------------------------
if exist "%SCRIPT_DIR%requirements.txt" (
    echo Installing Python requirements...
    where py >nul 2>&1
    if !errorlevel!==0 (
        py -m pip install -q -r "%SCRIPT_DIR%requirements.txt"
    ) else (
        python -m pip install -q -r "%SCRIPT_DIR%requirements.txt"
    )
)

:: ---------------------------------------------------------------------------
:: Run via launcher — handles kill-old-instance, dep check, and browser open
:: ---------------------------------------------------------------------------
where py >nul 2>&1
if %errorlevel%==0 (
    py "%SCRIPT_DIR%launcher.py" %*
) else (
    python "%SCRIPT_DIR%launcher.py" %*
)
