@echo off
:: TL IDE — launcher для Windows
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo [x] python не найден. Установи Python 3.10+ с https://python.org
    pause
    exit /b 1
)

:: Создать venv если нет
if not exist ".venv" (
    echo [*] Создаём виртуальное окружение...
    python -m venv .venv
)

:: Всегда синхронизируем зависимости
.venv\Scripts\pip install -q -r requirements.txt

.venv\Scripts\python main.py
