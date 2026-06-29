@echo off
setlocal enabledelayedexpansion

set "REPO=patchamama/ffmpeg-video-crop-tool"
set "RAW_BASE=https://raw.githubusercontent.com/%REPO%/main"
set "PORT=5553"
set "URL=http://127.0.0.1:%PORT%"
set "SCRIPT_DIR=%~dp0"
set "SCRIPT=%SCRIPT_DIR%crop_tool.py"

:: ---------------------------------------------------------------------------
:: Auto-bootstrap: download missing files from GitHub
:: ---------------------------------------------------------------------------
set "NEEDS_DOWNLOAD=0"
if not exist "%SCRIPT_DIR%crop_tool.py"     set "NEEDS_DOWNLOAD=1"
if not exist "%SCRIPT_DIR%requirements.txt" set "NEEDS_DOWNLOAD=1"

if "%NEEDS_DOWNLOAD%"=="1" (
    echo Required files missing. Downloading from github.com/%REPO% ...

    where curl >nul 2>&1
    if !errorlevel!==0 (
        if not exist "%SCRIPT_DIR%crop_tool.py" (
            echo   -^> crop_tool.py
            curl -fsSL "%RAW_BASE%/crop_tool.py" -o "%SCRIPT_DIR%crop_tool.py"
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
        if not exist "%SCRIPT_DIR%requirements.txt" (
            echo   -^> requirements.txt
            powershell -NoProfile -Command "Invoke-WebRequest -Uri '%RAW_BASE%/requirements.txt' -OutFile '%SCRIPT_DIR%requirements.txt'"
        )
    )
    echo Download complete.
)

:: ---------------------------------------------------------------------------
:: Install Python requirements
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
:: Kill any process already using the port
:: ---------------------------------------------------------------------------
set "KILLED="
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr /R /C:":%PORT% .*LISTENING" /C:":%PORT% .*ABHÖREN"') do (
    echo Port %PORT% in use by PID %%a. Stopping...
    taskkill /PID %%a /F >nul 2>&1
    set "KILLED=1"
)
if defined KILLED timeout /t 1 /nobreak >nul

:: ---------------------------------------------------------------------------
:: Start
:: ---------------------------------------------------------------------------
echo Starting %SCRIPT% at %URL%
start "" "%URL%"

where py >nul 2>&1
if %errorlevel%==0 (
    py "%SCRIPT%"
) else (
    python "%SCRIPT%"
)
