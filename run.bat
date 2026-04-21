@echo off
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo Ошибка: python не найден. Установи Python 3.10+ с https://python.org
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Первый запуск: создаём окружение и устанавливаем зависимости...
    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt -q
    echo Готово.
)

call .venv\Scripts\activate.bat
python main.py
