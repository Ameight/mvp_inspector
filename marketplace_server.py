#!/usr/bin/env python3
"""
TL IDE — Private Marketplace Server

Сервер для приватного маркетплейса плагинов.
Отдаёт registry.json и файлы плагинов только при наличии валидного X-API-Key.

Использование:
    python marketplace_server.py
    python marketplace_server.py --config /path/to/marketplace_server.yaml

Конфиг (marketplace_server.yaml):
    host: 0.0.0.0
    port: 9090
    plugins_dir: ./plugins     # папка с registry.json и плагинами
    api_keys:
      - key: secret-key-123
        name: "Team Alpha"     # только для логов, не проверяется
      - key: another-key-456
        name: "Team Beta"

Структура plugins_dir:
    plugins/
    ├── registry.json              ← генерируется publish.py
    ├── devops/
    │   └── deploy_checker/
    │       └── plugin.py
    └── jira/
        └── sprint_report/
            └── plugin.py

Подключение в TL IDE:
    Настройки → Маркетплейсы → URL: http://<host>:<port>/registry.json
                                    API Key: <ключ из api_keys>
"""

import argparse
import json
import logging
import pathlib
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

try:
    import yaml
except ImportError:
    print("❌ PyYAML не установлен. Запусти: pip install pyyaml")
    sys.exit(1)

DEFAULT_CONFIG: dict = {
    "host": "0.0.0.0",
    "port": 9090,
    "plugins_dir": "./plugins",
    "api_keys": [],
}

_cfg: dict = {}
_valid_keys: dict[str, str] = {}  # key -> name
_plugins_dir: pathlib.Path = pathlib.Path(".")


# ── Handler ────────────────────────────────────────────────────────────────────

class PrivateMarketplaceHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):  # noqa: override
        logging.info("%s %s", self.client_address[0], fmt % args)

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _check_auth(self) -> tuple[bool, str]:
        if not _valid_keys:
            return False, "No API keys configured on server"
        key = self.headers.get("X-API-Key", "")
        if key not in _valid_keys:
            return False, "Invalid or missing X-API-Key"
        return True, _valid_keys[key]

    # ── Response helpers ──────────────────────────────────────────────────────

    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data: dict, status: int = 200) -> None:
        self._send(
            json.dumps(data, ensure_ascii=False, indent=2).encode(),
            "application/json; charset=utf-8",
            status,
        )

    def _send_text(self, text: str, status: int = 200) -> None:
        self._send(text.encode(), "text/plain; charset=utf-8", status)

    # ── GET ───────────────────────────────────────────────────────────────────

    def do_GET(self):  # noqa: N802
        ok, info = self._check_auth()
        if not ok:
            logging.warning("Auth failed from %s: %s", self.client_address[0], info)
            self._send_json({"error": "Unauthorized", "detail": info}, 401)
            return

        path = urlparse(self.path).path.strip("/")
        logging.info("✅ [%s] GET /%s", info, path)

        # registry.json
        if path == "registry.json":
            registry = _plugins_dir / "registry.json"
            if not registry.exists():
                self._send_json({"error": "registry.json not found. Run publish.py first."}, 404)
                return
            self._send_text(registry.read_text(encoding="utf-8"))
            return

        # plugin files: <category>/<name>/plugin.py
        if re.fullmatch(r"[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+/plugin\.py", path):
            plugin_file = _plugins_dir / path
            if not plugin_file.exists():
                self._send_json({"error": f"Not found: {path}"}, 404)
                return
            self._send_text(plugin_file.read_text(encoding="utf-8"))
            return

        self._send_json({"error": "Not found"}, 404)


# ── Main ───────────────────────────────────────────────────────────────────────

def _load_config(path: pathlib.Path) -> dict:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return {**DEFAULT_CONFIG, **(yaml.safe_load(f) or {})}

    # Первый запуск — создаём конфиг по умолчанию
    cfg = DEFAULT_CONFIG.copy()
    cfg["api_keys"] = [
        {"key": "change-me-key-1", "name": "Team Alpha"},
        {"key": "change-me-key-2", "name": "Team Beta"},
    ]
    path.write_text(yaml.dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"📄 Создан конфиг: {path.resolve()}")
    print("   Замени ключи в api_keys на свои и перезапусти сервер.\n")
    return cfg


def main() -> None:
    global _cfg, _valid_keys, _plugins_dir

    parser = argparse.ArgumentParser(description="TL IDE Private Marketplace Server")
    parser.add_argument("--config", default="marketplace_server.yaml", metavar="FILE")
    args = parser.parse_args()

    _cfg = _load_config(pathlib.Path(args.config))
    _valid_keys = {
        e["key"]: e.get("name", "unknown")
        for e in _cfg.get("api_keys", [])
        if e.get("key")
    }
    _plugins_dir = pathlib.Path(_cfg["plugins_dir"]).resolve()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    host = _cfg["host"]
    port = int(_cfg["port"])

    print(f"\n🔒 TL IDE Private Marketplace Server")
    print(f"   URL      : http://{host}:{port}/registry.json")
    print(f"   Plugins  : {_plugins_dir}")
    print(f"   API keys : {len(_valid_keys)}")
    for name in _valid_keys.values():
        print(f"             • {name}")
    print()

    if not _valid_keys:
        print("⚠️  API-ключи не заданы — все запросы будут отклонены.")
        print(f"   Добавь ключи в {args.config} → api_keys\n")

    if not (_plugins_dir / "registry.json").exists():
        print(f"⚠️  registry.json не найден в {_plugins_dir}")
        print("   Запусти publish.py чтобы сгенерировать его.\n")

    server = HTTPServer((host, port), PrivateMarketplaceHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹  Остановлен.")


if __name__ == "__main__":
    main()
