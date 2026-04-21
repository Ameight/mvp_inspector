#!/usr/bin/env python3
"""
Генератор шаблона плагина для TL IDE.

Использование:
    python create_plugin.py <name> [category]

Примеры:
    python create_plugin.py pr_checker
    python create_plugin.py deploy_status devops
    python create_plugin.py tech_debt_report code_review
"""

import sys
import re
from pathlib import Path

PLUGINS_DIR = Path("plugins")

TEMPLATE = '''\
from sdk.base_plugin import PluginInterface


class {class_name}(PluginInterface):

    def get_display_name(self) -> str:
        return "{display_name}"

    def get_description(self) -> str:
        return "{description}"

    def get_category(self) -> str:
        return "{category}"

    def get_config_schema(self) -> dict:
        return {{
            "input": {{
                "label": "Входные данные",
                "type": "string",
                "default": "",
            }},
        }}

    def run(self, inputs: dict) -> str:
        value = inputs.get("input", "")

        # TODO: реализовать логику плагина
        return f"**Результат:**\\n\\n{{value}}"
'''


def to_class_name(name: str) -> str:
    parts = re.split(r"[_\-\s]+", name)
    return "".join(p.capitalize() for p in parts) + "Plugin"


def to_snake(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).lower().strip("_")


def to_display(name: str) -> str:
    return re.sub(r"[_\-]+", " ", name).title()


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    raw_name = sys.argv[1]
    raw_category = sys.argv[2] if len(sys.argv) > 2 else "general"

    snake_name = to_snake(raw_name)
    snake_category = to_snake(raw_category)
    class_name = to_class_name(raw_name)
    display_name = to_display(raw_name)
    category_display = to_display(raw_category)

    plugin_dir = PLUGINS_DIR / snake_category / snake_name
    plugin_file = plugin_dir / "plugin.py"

    if plugin_file.exists():
        print(f"❌ Плагин уже существует: {plugin_file}")
        sys.exit(1)

    plugin_dir.mkdir(parents=True, exist_ok=True)

    content = TEMPLATE.format(
        class_name=class_name,
        display_name=display_name,
        description=f"Описание плагина {display_name}",
        category=category_display,
    )
    plugin_file.write_text(content, encoding="utf-8")

    print(f"✅ Плагин создан: {plugin_file}")
    print(f"   Класс:     {class_name}")
    print(f"   Категория: {category_display}")
    print(f"\n   Реализуй метод run() в файле:")
    print(f"   {plugin_file}")


if __name__ == "__main__":
    main()
