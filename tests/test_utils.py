"""Тесты для utils.py — чистые утилиты без UI и сетевых зависимостей."""
import hashlib
import os
from pathlib import Path

import pytest

from utils import check_integrity, compute_sha256, is_systemd, parse_version


# ── parse_version ─────────────────────────────────────────────────────────────

class TestParseVersion:
    def test_standard(self):
        assert parse_version("1.2.3") == (1, 2, 3)

    def test_with_v_prefix(self):
        assert parse_version("v1.2.3") == (1, 2, 3)

    def test_large_minor(self):
        assert parse_version("1.10.0") == (1, 10, 0)

    def test_zero_patch(self):
        assert parse_version("2.0.0") == (2, 0, 0)

    def test_broken_string(self):
        assert parse_version("broken") == (0, 0, 0)

    def test_empty_string(self):
        assert parse_version("") == (0, 0, 0)

    def test_partial_version(self):
        # Если передать "1.2" — должно не упасть
        result = parse_version("1.2")
        assert result == (1, 2)

    def test_version_comparison(self):
        """Гарантируем что кортежи сравниваются правильно."""
        assert parse_version("1.10.0") > parse_version("1.9.0")
        assert parse_version("2.0.0") > parse_version("1.99.99")
        assert parse_version("v1.2.3") == parse_version("1.2.3")


# ── compute_sha256 ────────────────────────────────────────────────────────────

class TestComputeSha256:
    def test_known_hash(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello")
        expected = hashlib.sha256(b"hello").hexdigest()
        assert compute_sha256(f) == expected

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert compute_sha256(f) == expected

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")
        assert compute_sha256(f1) != compute_sha256(f2)

    def test_returns_hex_string(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_bytes(b"data")
        result = compute_sha256(f)
        assert isinstance(result, str)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


# ── check_integrity ───────────────────────────────────────────────────────────

class TestCheckIntegrity:
    @pytest.fixture
    def plugins_dir(self, tmp_path):
        """Временная папка с плагинами."""
        return tmp_path / "plugins"

    def _make_plugin(self, plugins_dir: Path, plugin_id: str, content: bytes = b"# plugin") -> Path:
        f = plugins_dir / plugin_id / "plugin.py"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(content)
        return f

    def test_custom_plugin_always_ok(self, plugins_dir):
        """Кастомные плагины (не marketplace) всегда проходят проверку."""
        manifest = {"devops/my_tool": {"source": "custom"}}
        assert check_integrity("devops/my_tool", manifest, plugins_dir) is True

    def test_missing_from_manifest_is_ok(self, plugins_dir):
        """Плагина нет в manifest вообще — значит кастомный, OK."""
        assert check_integrity("devops/unknown", {}, plugins_dir) is True

    def test_marketplace_no_sha_in_manifest(self, plugins_dir):
        """Marketplace-плагин без sha256 в manifest — доверяем."""
        manifest = {"jira/checker": {"source": "marketplace"}}
        assert check_integrity("jira/checker", manifest, plugins_dir) is True

    def test_marketplace_correct_sha(self, plugins_dir):
        """Файл не изменён — sha совпадает."""
        content = b"print('hello from plugin')"
        plugin_file = self._make_plugin(plugins_dir, "devops/deploy", content)
        sha = hashlib.sha256(content).hexdigest()
        manifest = {
            "devops/deploy": {"source": "marketplace", "sha256": sha}
        }
        assert check_integrity("devops/deploy", manifest, plugins_dir) is True

    def test_marketplace_wrong_sha(self, plugins_dir):
        """Файл изменён — sha не совпадает."""
        content = b"print('original')"
        self._make_plugin(plugins_dir, "devops/deploy", content)
        manifest = {
            "devops/deploy": {
                "source": "marketplace",
                "sha256": "0" * 64,  # заведомо неверный
            }
        }
        assert check_integrity("devops/deploy", manifest, plugins_dir) is False

    def test_marketplace_file_missing(self, plugins_dir):
        """Файл плагина удалён — False."""
        manifest = {
            "devops/missing": {
                "source": "marketplace",
                "sha256": "abc123",
            }
        }
        assert check_integrity("devops/missing", manifest, plugins_dir) is False


# ── is_systemd ────────────────────────────────────────────────────────────────

class TestIsSystemd:
    def test_without_env(self, monkeypatch):
        monkeypatch.delenv("INVOCATION_ID", raising=False)
        assert is_systemd() is False

    def test_with_env(self, monkeypatch):
        monkeypatch.setenv("INVOCATION_ID", "abc123")
        assert is_systemd() is True

    def test_empty_string_is_false(self, monkeypatch):
        monkeypatch.setenv("INVOCATION_ID", "")
        assert is_systemd() is False
