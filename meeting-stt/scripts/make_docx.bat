@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

if "%~1"=="" (
    echo Usage: %~nx0 ^<meeting_minutes.md^> [--template TEMPLATE_PATH] [--output OUTPUT_PATH]
    exit /b 1
)

python "%PROJECT_ROOT%\src\md_to_docx.py" %*
