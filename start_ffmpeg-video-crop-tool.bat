@echo off
setlocal enabledelayedexpansion

set "REPO=patchamama/ffmpeg-video-crop-tool"
set "RAW_BASE=https://raw.githubusercontent.com/%REPO%/main"
set "SCRIPT_DIR=%~dp0"
set "VENV=%SCRIPT_DIR%.venv"
set "VENV_PY=%VENV%\Scripts\python.exe"

:: ---------------------------------------------------------------------------
:: Auto-bootstrap: download missing files from GitHub
:: ---------------------------------------------------------------------------
set "NEEDS_DOWNLOAD=0"
if not exist "%SCRIPT_DIR%crop_tool.py"     set "NEEDS_DOWNLOAD=1"
if not exist "%SCRIPT_DIR%launcher.py"      set "NEEDS_DOWNLOAD=1"
if not exist "%SCRIPT_DIR%requirements.txt" set "NEEDS_DOWNLOAD=1"
if not exist "%SCRIPT_DIR%version.txt"      set "NEEDS_DOWNLOAD=1"

if "%NEEDS_DOWNLOAD%"=="1" (
    echo Required files missing. Downloading from github.com/%REPO% ...
    if not exist "%SCRIPT_DIR%crop_tool.py"     call :dl crop_tool.py
    if not exist "%SCRIPT_DIR%launcher.py"      call :dl launcher.py
    if not exist "%SCRIPT_DIR%requirements.txt" call :dl requirements.txt
    if not exist "%SCRIPT_DIR%version.txt"      call :dl version.txt
    echo Download complete.
)

:: ---------------------------------------------------------------------------
:: Auto-update: compare local version.txt with GitHub (skipped in dev: .git)
:: ---------------------------------------------------------------------------
if not exist "%SCRIPT_DIR%.git" (
    set "LOCAL_VER=0.0.0"
    if exist "%SCRIPT_DIR%version.txt" set /p LOCAL_VER=<"%SCRIPT_DIR%version.txt"

    set "REMOTE_VER="
    set "TMP_VER=%TEMP%\ffmpeg_crop_ver.txt"

    where curl >nul 2>&1
    if !errorlevel!==0 (
        curl -fsSL --max-time 5 "%RAW_BASE%/version.txt" -o "!TMP_VER!" >nul 2>&1
    ) else (
        powershell -NoProfile -Command "try { (Invoke-WebRequest '%RAW_BASE%/version.txt' -UseBasicParsing -TimeoutSec 5).Content.Trim() | Out-File -FilePath '!TMP_VER!' -Encoding ASCII -NoNewline } catch {}" >nul 2>&1
    )

    if exist "!TMP_VER!" (
        set /p REMOTE_VER=<"!TMP_VER!"
        del "!TMP_VER!" >nul 2>&1
    )

    if defined REMOTE_VER (
        powershell -NoProfile -Command "if ([version]'!REMOTE_VER!' -gt [version]'!LOCAL_VER!') { exit 1 } else { exit 0 }" >nul 2>&1
        if !errorlevel! EQU 1 (
            echo Update available: v!LOCAL_VER! -^> v!REMOTE_VER!. Downloading...
            call :dl crop_tool.py
            call :dl launcher.py
            call :dl requirements.txt
            call :dl version.txt
            echo Updated to v!REMOTE_VER!.
        )
    )
)

:: ---------------------------------------------------------------------------
:: Create virtual environment if missing
:: ---------------------------------------------------------------------------
if not exist "%VENV_PY%" (
    echo Creating virtual environment...
    where py >nul 2>&1
    if !errorlevel!==0 (
        py -m venv "%VENV%"
    ) else (
        python -m venv "%VENV%"
    )
)

:: ---------------------------------------------------------------------------
:: Install / sync Python requirements inside venv
:: ---------------------------------------------------------------------------
if exist "%SCRIPT_DIR%requirements.txt" (
    echo Installing Python requirements...
    "%VENV_PY%" -m pip install -q -r "%SCRIPT_DIR%requirements.txt"
)

:: ---------------------------------------------------------------------------
:: Run via launcher using venv Python
:: ---------------------------------------------------------------------------
"%VENV_PY%" "%SCRIPT_DIR%launcher.py" %*
goto :eof

:: ---------------------------------------------------------------------------
:: Subroutine: download a single file from RAW_BASE to SCRIPT_DIR
:: Usage: call :dl filename
:: ---------------------------------------------------------------------------
:dl
echo   -^> %~1
where curl >nul 2>&1
if %errorlevel%==0 (
    curl -fsSL "%RAW_BASE%/%~1" -o "%SCRIPT_DIR%%~1" >nul 2>&1
) else (
    powershell -NoProfile -Command "Invoke-WebRequest '%RAW_BASE%/%~1' -OutFile '%SCRIPT_DIR%%~1' -UseBasicParsing" >nul 2>&1
)
goto :eof
