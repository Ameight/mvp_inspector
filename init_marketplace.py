#!/usr/bin/env python3
"""
TL IDE Marketplace — Init Script

Настраивает конфигурацию маркетплейса в текущей папке.
Запустить один раз после клонирования репозитория:

    python init_marketplace.py
"""

import pathlib
import secrets
import string
import sys

ROOT = pathlib.Path(".")

_EXAMPLE_PLUGIN = '''\
from sdk.base_plugin import PluginInterface


class HelloWorldPlugin(PluginInterface):

    def get_display_name(self) -> str:
        return "Hello World"

    def get_description(self) -> str:
        return "Пример плагина."

    def get_category(self) -> str:
        return "General"

    def get_config_schema(self) -> dict:
        return {
            "name": {
                "label": "Имя",
                "type": "string",
                "default": "World",
            },
        }

    def run(self, inputs: dict) -> str:
        name = inputs.get("name", "World")
        return f"**Hello, {name}!**"
'''

_EXAMPLE_META = """\
version: "1.0.0"
author: ""
requires: []
# min_app_version: "0.3.0"
# requires: список pip-пакетов, нужных плагину. Пример: [requests, pyyaml]
"""

_GITIGNORE = "__pycache__/\n*.pyc\n.env\n"


def _prompt(question: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    val = input(f"  {question}{hint}: ").strip()
    return val or default


def _prompt_choice(question: str, choices: list[str], default: str) -> str:
    opts = " / ".join(choices)
    while True:
        val = input(f"  {question} ({opts}) [{default}]: ").strip().lower() or default
        if val in choices:
            return val
        print(f"    Введи одно из: {opts}")


def _rand_key(n: int = 32) -> str:
    alpha = string.ascii_letters + string.digits
    return "".join(secrets.choice(alpha) for _ in range(n))


def _write(path: pathlib.Path, content: str) -> None:
    if path.exists():
        print(f"    (уже есть, пропускаю) {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"    ✍️  {path}")


def main() -> None:
    print("╔══════════════════════════════════════════════╗")
    print("║   TL IDE Marketplace — Init                  ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    hosting = _prompt_choice("Тип хостинга", ["github", "server"], "github")
    print()

    if hosting == "github":
        github_url = _prompt(
            "URL репозитория на GitHub",
            "https://github.com/your-org/your-plugins",
        )
        branch = _prompt("Ветка", "master")
        gh_parts = github_url.rstrip("/").split("github.com/")
        owner_repo = gh_parts[-1] if len(gh_parts) > 1 else "your-org/your-plugins"
        base_url = f"https://raw.githubusercontent.com/{owner_repo}/{branch}/plugins"
        registry_url = f"https://raw.githubusercontent.com/{owner_repo}/{branch}/registry.json"
        publish_yaml = (
            f"base_url: {base_url}\n"
            "plugins_dir: ./plugins\n"
            "output: ./registry.json\n"
        )
        server_mode = False
    else:
        srv_host = _prompt("Публичный хост или IP", "0.0.0.0")
        srv_port = _prompt("Порт", "9090")
        base_url = f"http://{srv_host}:{srv_port}"
        registry_url = f"http://{srv_host}:{srv_port}/registry.json"
        publish_yaml = (
            f"base_url: {base_url}\n"
            "plugins_dir: ./plugins\n"
            "output: ./plugins/registry.json\n"
        )
        server_mode = True

    print()
    print("📁 Создаю файлы:\n")

    _write(ROOT / "publish.yaml", publish_yaml)
    _write(ROOT / ".gitignore", _GITIGNORE)
    _write(ROOT / "plugins" / "general" / "hello_world" / "plugin.py",        _EXAMPLE_PLUGIN)
    _write(ROOT / "plugins" / "general" / "hello_world" / "plugin.meta.yaml", _EXAMPLE_META)

    key1 = key2 = None
    if server_mode:
        key1, key2 = _rand_key(), _rand_key()
        server_yaml = (
            f"host: 0.0.0.0\n"
            f"port: {srv_port}\n"
            "plugins_dir: ./plugins\n"
            "\n"
            "api_keys:\n"
            f"  - key: {key1}\n"
            "    name: \"Team Alpha\"\n"
            f"  - key: {key2}\n"
            "    name: \"Team Beta\"\n"
        )
        _write(ROOT / "marketplace_server.yaml", server_yaml)

    print()
    print("✅  Готово!\n")

    if server_mode:
        print("🔑 API-ключи (сохранены в marketplace_server.yaml):")
        print(f"   Team Alpha : {key1}")
        print(f"   Team Beta  : {key2}")
        print()

    print("Следующие шаги:\n")
    if hosting == "github":
        print("  1. python publish.py    # сгенерировать registry.json")
        print("  2. git add . && git commit -m 'init' && git push")
        print()
        print("  Подключить в TL IDE → Настройки → Маркетплейсы:")
        print(f"    URL: {registry_url}")
    else:
        print("  1. python publish.py            # сгенерировать registry.json")
        print("  2. python marketplace_server.py # запустить сервер")
        print()
        print("  Подключить в TL IDE → Настройки → Маркетплейсы:")
        print(f"    URL    : {registry_url}")
        print(f"    API Key: <ключ из marketplace_server.yaml>")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nОтменено.")
        sys.exit(0)
