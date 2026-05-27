"""
Чистые утилиты TL IDE — без зависимостей от UI и конфига.
Импортируются как из main.py, так и из тестов.
"""
import hashlib
import os
from pathlib import Path


def parse_version(v: str) -> tuple[int, ...]:
    """Разбирает строку версии в кортеж чисел.

    >>> parse_version("v1.2.3")
    (1, 2, 3)
    >>> parse_version("1.10.0")
    (1, 10, 0)
    >>> parse_version("broken")
    (0, 0, 0)
    """
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except Exception:
        return (0, 0, 0)


def compute_sha256(path: Path) -> str:
    """SHA-256 хеш файла в hex-строке."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_integrity(plugin_id: str, manifest: dict, plugins_dir: Path) -> bool:
    """SHA-256 проверка для marketplace-плагинов.

    Возвращает True если:
    - плагин не из маркетплейса (кастомный)
    - в manifest нет sha256 для этого плагина
    - sha256 файла совпадает с manifest

    Возвращает False если:
    - файл плагина не существует
    - sha256 не совпадает
    """
    entry = manifest.get(plugin_id, {})
    if entry.get("source") != "marketplace":
        return True
    stored = entry.get("sha256")
    if not stored:
        return True
    plugin_file = plugins_dir / plugin_id / "plugin.py"
    if not plugin_file.exists():
        return False
    return compute_sha256(plugin_file) == stored


def is_systemd() -> bool:
    """True если процесс запущен под systemd (есть INVOCATION_ID)."""
    return bool(os.environ.get("INVOCATION_ID"))
