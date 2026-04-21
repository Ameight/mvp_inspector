#!/bin/bash
set -e
cd "$(dirname "$0")"

if ! command -v python3 &>/dev/null; then
    echo "Ошибка: python3 не найден. Установи Python 3.10+ с https://python.org"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(sys.version_info.minor)")
if [ "$PYTHON_VERSION" -lt 10 ]; then
    echo "Ошибка: требуется Python 3.10+, найден 3.$PYTHON_VERSION"
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Первый запуск: создаём окружение и устанавливаем зависимости..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt -q
    echo "Готово."
fi

source .venv/bin/activate
python main.py
