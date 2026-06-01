#!/usr/bin/env python3
"""
publish.py — генерирует registry.json из папки с плагинами.

Использование:
    python publish.py
    python publish.py --config publish.yaml
    python publish.py --base-url https://raw.githubusercontent.com/org/repo/master/plugins
"""

import argparse
import importlib.util
import json
import pathlib
import sys
import types

try:
    import yaml
except ImportError:
    print("❌ PyYAML не установлен. Запусти: pip install pyyaml")
    sys.exit(1)

DEFAULT_CONFIG = {
    "base_url": "",
    "plugins_dir": "./plugins",
    "output": "./registry.json",
}


def _load_config(config_path: pathlib.Path, base_url_override: str | None) -> dict:
    cfg = DEFAULT_CONFIG.copy()
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        cfg.update({k: v for k, v in loaded.items() if v is not None})
    if base_url_override:
        cfg["base_url"] = base_url_override
    return cfg


def _stub_sdk() -> None:
    """Заглушка sdk.base_plugin — позволяет импортировать плагины вне TL IDE."""
    if "sdk.base_plugin" in sys.modules:
        return

    class PluginInterface:
        config: dict = {}
        def configure(self, c: dict) -> None: self.config = c
        def get_config_key(self) -> str: return ""
        def get_display_name(self) -> str: return type(self).__name__
        def get_description(self) -> str: return ""
        def get_category(self) -> str: return "General"
        def get_config_schema(self) -> dict: return {}
        def is_enabled(self) -> bool: return True
        def get_required_env(self) -> dict: return {}
        def run(self, inputs: dict) -> str: return ""

    sdk_pkg = types.ModuleType("sdk")
    sdk_mod = types.ModuleType("sdk.base_plugin")
    sdk_mod.PluginInterface = PluginInterface
    sdk_mod.app_log = lambda *a, **kw: None
    sdk_mod._logs = []
    sdk_pkg.base_plugin = sdk_mod
    sys.modules["sdk"] = sdk_pkg
    sys.modules["sdk.base_plugin"] = sdk_mod


def _load_plugin_instance(plugin_file: pathlib.Path):
    _stub_sdk()
    spec = importlib.util.spec_from_file_location("_probe", plugin_file)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        return None, str(e)
    for obj in mod.__dict__.values():
        if (
            isinstance(obj, type)
            and obj.__name__ != "PluginInterface"
            and hasattr(obj, "get_display_name")
            and hasattr(obj, "run")
        ):
            try:
                return obj(), None
            except Exception as e:
                return None, str(e)
    return None, "класс PluginInterface не найден"


def _load_meta(plugin_dir: pathlib.Path) -> dict:
    meta_file = plugin_dir / "plugin.meta.yaml"
    if meta_file.exists():
        return yaml.safe_load(meta_file.read_text(encoding="utf-8")) or {}
    return {}


def build_registry(plugins_dir: pathlib.Path, base_url: str) -> list[dict]:
    registry: list[dict] = []
    base_url = base_url.rstrip("/")

    for plugin_file in sorted(plugins_dir.rglob("plugin.py")):
        rel = plugin_file.relative_to(plugins_dir)
        parts = rel.parts  # (category, name, "plugin.py")
        if len(parts) != 3:
            continue

        category, name = parts[0], parts[1]
        plugin_id = f"{category}/{name}"

        instance, err = _load_plugin_instance(plugin_file)
        if instance is None:
            print(f"  ⚠️  {plugin_id}: {err}")
            continue

        meta = _load_meta(plugin_file.parent)
        version = str(meta.get("version", "1.0.0"))
        author = str(meta.get("author", "") or "")
        requires = meta.get("requires") or []
        min_app_ver = str(meta.get("min_app_version", "") or "")

        entry: dict = {
            "id": plugin_id,
            "name": instance.get_display_name(),
            "description": instance.get_description(),
            "category": instance.get_category(),
            "version": version,
            "author": author,
            "raw_url": f"{base_url}/{plugin_id}/plugin.py",
        }
        if requires:
            entry["requires"] = requires
        if min_app_ver:
            entry["min_app_version"] = min_app_ver

        registry.append(entry)
        print(f"  ✅  {plugin_id}  ({entry['name']}  v{version})")

    return registry


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate registry.json for TL IDE Marketplace")
    parser.add_argument("--config", default="publish.yaml", metavar="FILE")
    parser.add_argument("--base-url", default=None, metavar="URL")
    args = parser.parse_args()

    cfg = _load_config(pathlib.Path(args.config), args.base_url)

    if not cfg["base_url"]:
        print("❌ base_url не задан. Укажи в publish.yaml или через --base-url.")
        sys.exit(1)

    plugins_dir = pathlib.Path(cfg["plugins_dir"]).resolve()
    output = pathlib.Path(cfg["output"])

    if not plugins_dir.exists():
        print(f"❌ Папка с плагинами не найдена: {plugins_dir}")
        sys.exit(1)

    print(f"🔍 Сканирую плагины в {plugins_dir} ...")
    registry = build_registry(plugins_dir, cfg["base_url"])

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\n📦 registry.json: {len(registry)} плагин(ов) → {output.resolve()}")


if __name__ == "__main__":
    main()
