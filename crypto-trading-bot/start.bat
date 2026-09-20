@echo off
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Install it from https://www.python.org/downloads/ and check "Add python.exe to PATH" during setup.
    pause
    exit /b 1
)

if not exist .venv (
    echo First run: creating environment and installing dependencies, this takes a minute...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: failed to create the virtual environment.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
if errorlevel 1 (
    echo ERROR: failed to install dependencies. Check your internet connection.
    pause
    exit /b 1
)

echo Starting the bot... your browser will open shortly.
python web\app.py

pause
