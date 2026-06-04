"""Логика проверки и применения обновлений приложения.

Не содержит UI-зависимостей — тестируется напрямую.
"""
import asyncio
import subprocess
import sys
from pathlib import Path

import requests


def get_local_version(repo_dir: Path | None = None) -> str:
    """Текущая версия: git describe --tags --abbrev=0, иначе файл VERSION."""
    try:
        r = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True, text=True, check=True,
            cwd=repo_dir,
        )
        return r.stdout.strip()
    except Exception:
        pass
    base = repo_dir if repo_dir is not None else Path(__file__).parent
    version_file = base / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return "0.0.0"


def get_dirty_tracked_files(repo_dir: Path | None = None) -> list[str]:
    """Список изменённых отслеживаемых файлов (не untracked)."""
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True,
            cwd=repo_dir,
        )
        return [
            line[3:].strip()
            for line in r.stdout.splitlines()
            if line.strip() and not line.startswith("??")
        ]
    except Exception:
        return []


async def fetch_latest_release(github_repo: str) -> dict | None:
    """Запрашивает последний релиз через GitHub API. None при ошибке."""
    try:
        resp = await asyncio.to_thread(
            lambda: requests.get(
                f"https://api.github.com/repos/{github_repo}/releases/latest",
                timeout=8,
                headers={"Accept": "application/vnd.github+json"},
            )
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


async def perform_update(
    tag: str,
    repo_dir: Path,
    config_path: Path,
) -> tuple[bool, str]:
    """Применяет обновление: git fetch --tags → git checkout → pip install.

    Бэкапит и восстанавливает config.yaml вокруг checkout, чтобы
    пользовательские настройки не терялись при переключении тега.

    Returns:
        (True, "")            — успех
        (False, error_str)    — ошибка с описанием
    """
    config_backup = config_path.read_text(encoding="utf-8") if config_path.exists() else None
    if config_path.exists():
        config_path.unlink()

    def _run(*cmd: str) -> None:
        subprocess.run(list(cmd), check=True, capture_output=True, cwd=repo_dir)

    try:
        await asyncio.to_thread(_run, "git", "fetch", "--tags")
        await asyncio.to_thread(_run, "git", "checkout", tag)
        if config_backup is not None:
            config_path.write_text(config_backup, encoding="utf-8")
        await asyncio.to_thread(
            _run, sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        )
        return True, ""
    except subprocess.CalledProcessError as e:
        if config_backup is not None:
            config_path.write_text(config_backup, encoding="utf-8")
        error = (e.stderr or b"").decode(errors="replace") or str(e)
        return False, error
