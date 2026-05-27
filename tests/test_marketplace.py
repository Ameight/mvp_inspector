"""Тесты для marketplace_server.py — HTTP API приватного маркетплейса."""
import json
import threading
from http.server import HTTPServer
from pathlib import Path

import pytest
import requests

import marketplace_server as ms


# ── Фикстуры ──────────────────────────────────────────────────────────────────

@pytest.fixture
def plugins_dir(tmp_path) -> Path:
    """Временная папка с registry.json и тестовыми плагинами."""
    d = tmp_path / "plugins"
    d.mkdir()

    # registry.json
    registry = [
        {
            "id": "devops/deploy",
            "name": "Deploy Checker",
            "category": "DevOps",
            "version": "1.0.0",
            "raw_url": "http://localhost/devops/deploy/plugin.py",
        }
    ]
    (d / "registry.json").write_text(json.dumps(registry), encoding="utf-8")

    # Файл плагина
    plugin_path = d / "devops" / "deploy"
    plugin_path.mkdir(parents=True)
    (plugin_path / "plugin.py").write_text("# deploy plugin", encoding="utf-8")

    return d


@pytest.fixture
def server(plugins_dir):
    """Поднимает тестовый сервер на случайном порту, останавливает после теста."""
    # Настраиваем глобальные переменные модуля напрямую
    ms._valid_keys = {"test-key-123": "Test Team", "other-key": "Other"}
    ms._plugins_dir = plugins_dir

    httpd = HTTPServer(("127.0.0.1", 0), ms.PrivateMarketplaceHandler)
    port = httpd.server_address[1]

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{port}"

    httpd.shutdown()


# ── Авторизация ───────────────────────────────────────────────────────────────

class TestAuth:
    def test_no_api_key_returns_401(self, server):
        r = requests.get(f"{server}/registry.json")
        assert r.status_code == 401

    def test_wrong_api_key_returns_401(self, server):
        r = requests.get(f"{server}/registry.json", headers={"X-API-Key": "wrong"})
        assert r.status_code == 401

    def test_valid_api_key_passes(self, server):
        r = requests.get(f"{server}/registry.json", headers={"X-API-Key": "test-key-123"})
        assert r.status_code == 200

    def test_second_valid_key_also_works(self, server):
        r = requests.get(f"{server}/registry.json", headers={"X-API-Key": "other-key"})
        assert r.status_code == 200

    def test_no_keys_configured_blocks_everything(self, plugins_dir):
        """Если ключи не настроены — все запросы отклоняются."""
        ms._valid_keys = {}
        ms._plugins_dir = plugins_dir

        httpd = HTTPServer(("127.0.0.1", 0), ms.PrivateMarketplaceHandler)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            r = requests.get(f"http://127.0.0.1:{port}/registry.json",
                             headers={"X-API-Key": "any-key"})
            assert r.status_code == 401
        finally:
            httpd.shutdown()
            ms._valid_keys = {"test-key-123": "Test Team"}


# ── registry.json ─────────────────────────────────────────────────────────────

class TestRegistry:
    HEADERS = {"X-API-Key": "test-key-123"}

    def test_returns_registry_content(self, server):
        r = requests.get(f"{server}/registry.json", headers=self.HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert data[0]["name"] == "Deploy Checker"

    def test_registry_not_found(self, server, plugins_dir):
        """Если registry.json удалён — 404."""
        (plugins_dir / "registry.json").unlink()
        r = requests.get(f"{server}/registry.json", headers=self.HEADERS)
        assert r.status_code == 404
        # Восстановим для других тестов
        (plugins_dir / "registry.json").write_text("[]", encoding="utf-8")


# ── Файлы плагинов ────────────────────────────────────────────────────────────

class TestPluginFiles:
    HEADERS = {"X-API-Key": "test-key-123"}

    def test_returns_plugin_file(self, server):
        r = requests.get(f"{server}/devops/deploy/plugin.py", headers=self.HEADERS)
        assert r.status_code == 200
        assert "deploy plugin" in r.text

    def test_missing_plugin_returns_404(self, server):
        r = requests.get(f"{server}/devops/missing/plugin.py", headers=self.HEADERS)
        assert r.status_code == 404

    def test_path_traversal_blocked(self, server):
        """Попытка выйти за пределы plugins_dir должна вернуть 404."""
        r = requests.get(f"{server}/../../../etc/passwd", headers=self.HEADERS)
        assert r.status_code == 404

    def test_arbitrary_path_blocked(self, server):
        """Любой путь не соответствующий паттерну <cat>/<name>/plugin.py — 404."""
        r = requests.get(f"{server}/some-file.txt", headers=self.HEADERS)
        assert r.status_code == 404

    def test_double_plugin_py_blocked(self, server):
        """Двойной plugin.py в пути — не подходит под regex."""
        r = requests.get(f"{server}/devops/deploy/plugin.py/plugin.py",
                         headers=self.HEADERS)
        assert r.status_code == 404


# ── _load_config ──────────────────────────────────────────────────────────────

class TestLoadConfig:
    def test_creates_default_config_if_missing(self, tmp_path):
        cfg_path = tmp_path / "server.yaml"
        cfg = ms._load_config(cfg_path)
        # Файл создан
        assert cfg_path.exists()
        # Дефолтные значения присутствуют
        assert cfg["host"] == "0.0.0.0"
        assert cfg["port"] == 9090
        assert "api_keys" in cfg

    def test_loads_existing_config(self, tmp_path):
        import yaml
        cfg_path = tmp_path / "server.yaml"
        cfg_path.write_text(yaml.dump({
            "host": "127.0.0.1",
            "port": 8888,
            "plugins_dir": "./my-plugins",
            "api_keys": [{"key": "abc", "name": "Test"}],
        }), encoding="utf-8")
        cfg = ms._load_config(cfg_path)
        assert cfg["host"] == "127.0.0.1"
        assert cfg["port"] == 8888
        assert cfg["api_keys"][0]["key"] == "abc"

    def test_missing_keys_get_defaults(self, tmp_path):
        """Частичный конфиг дополняется дефолтными значениями."""
        import yaml
        cfg_path = tmp_path / "server.yaml"
        cfg_path.write_text(yaml.dump({"port": 7777}), encoding="utf-8")
        cfg = ms._load_config(cfg_path)
        assert cfg["port"] == 7777
        assert cfg["host"] == "0.0.0.0"   # дефолт
