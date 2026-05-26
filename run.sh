#!/bin/bash
# TL IDE — launcher для Linux / macOS
set -e
cd "$(dirname "$0")"

# Проверка Python
if ! command -v python3 &>/dev/null; then
    echo "❌ python3 не найден. Установи Python 3.10+ с https://python.org"
    exit 1
fi

MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
if [ "$MINOR" -lt 10 ]; then
    echo "❌ Требуется Python 3.10+, найден 3.$MINOR"
    exit 1
fi

# Создать venv если нет
if [ ! -d ".venv" ]; then
    echo "🔧 Создаём виртуальное окружение..."
    python3 -m venv .venv
fi

# Всегда синхронизируем зависимости (быстро если ничего не изменилось)
.venv/bin/pip install -q -r requirements.txt

exec .venv/bin/python main.py
