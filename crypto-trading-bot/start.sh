#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "Первый запуск: создаю окружение и устанавливаю зависимости..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

echo "Запускаю бота... Сейчас откроется браузер."
python web/app.py
