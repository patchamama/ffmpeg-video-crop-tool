@echo off
setlocal

set "PORT=5553"
set "URL=http://127.0.0.1:%PORT%"
set "SCRIPT_DIR=%~dp0"
set "SCRIPT=%SCRIPT_DIR%crop_tool.py"

for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    echo Puerto %PORT% ocupado por PID %%a. Cerrando...
    taskkill /PID %%a /F >nul 2>&1
)

echo Iniciando %SCRIPT% en %URL%
start "" "%URL%"

where py >nul 2>&1
if %errorlevel%==0 (
    py "%SCRIPT%"
) else (
    python "%SCRIPT%"
)
