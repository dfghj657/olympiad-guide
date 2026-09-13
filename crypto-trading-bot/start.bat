@echo off
cd /d "%~dp0"

if not exist .venv (
    echo Первый запуск: создаю окружение и устанавливаю зависимости...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -q -r requirements.txt

echo Запускаю бота... Сейчас откроется браузер.
python web\app.py

pause
