"""Тесты для updater.py — проверка и применение обновлений приложения."""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from updater import (
    fetch_latest_release,
    get_dirty_tracked_files,
    get_local_version,
    perform_update,
)


# ── get_local_version ─────────────────────────────────────────────────────────

class TestGetLocalVersion:
    def _git_ok(self, tag: str):
        result = MagicMock()
        result.stdout = f"{tag}\n"
        return lambda *a, **kw: result

    def _git_fail(self):
        def _raise(*a, **kw):
            raise subprocess.CalledProcessError(128, "git")
        return _raise

    def test_reads_git_tag(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._git_ok("v1.3.0"))
        assert get_local_version() == "v1.3.0"

    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._git_ok("  v2.1.0  "))
        assert get_local_version() == "v2.1.0"

    def test_falls_back_to_version_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._git_fail())
        (tmp_path / "VERSION").write_text("v2.0.0", encoding="utf-8")
        assert get_local_version(tmp_path) == "v2.0.0"

    def test_version_file_strips_whitespace(self, tmp_path, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._git_fail())
        (tmp_path / "VERSION").write_text("  v0.5.0\n", encoding="utf-8")
        assert get_local_version(tmp_path) == "v0.5.0"

    def test_returns_zero_when_no_git_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._git_fail())
        assert get_local_version(tmp_path) == "0.0.0"

    def test_git_tag_takes_priority_over_version_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._git_ok("v3.0.0"))
        (tmp_path / "VERSION").write_text("v1.0.0", encoding="utf-8")
        assert get_local_version(tmp_path) == "v3.0.0"


# ── get_dirty_tracked_files ───────────────────────────────────────────────────

class TestGetDirtyTrackedFiles:
    def _mock_git(self, output: str):
        result = MagicMock()
        result.stdout = output
        return lambda *a, **kw: result

    def test_clean_repo(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._mock_git(""))
        assert get_dirty_tracked_files() == []

    def test_returns_modified_files(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._mock_git(" M main.py\n M utils.py\n"))
        assert get_dirty_tracked_files() == ["main.py", "utils.py"]

    def test_ignores_untracked_files(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._mock_git(" M main.py\n?? new_file.py\n"))
        assert get_dirty_tracked_files() == ["main.py"]

    def test_ignores_only_untracked(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._mock_git("?? foo.py\n?? bar.py\n"))
        assert get_dirty_tracked_files() == []

    def test_staged_and_modified(self, monkeypatch):
        output = "M  staged.py\n M unstaged.py\n?? new.py\n"
        monkeypatch.setattr(subprocess, "run", self._mock_git(output))
        result = get_dirty_tracked_files()
        assert "staged.py" in result
        assert "unstaged.py" in result
        assert "new.py" not in result

    def test_returns_empty_on_exception(self, monkeypatch):
        def _raise(*a, **kw):
            raise OSError("git not found")
        monkeypatch.setattr(subprocess, "run", _raise)
        assert get_dirty_tracked_files() == []


# ── fetch_latest_release ──────────────────────────────────────────────────────

class TestFetchLatestRelease:
    async def test_returns_release_data_on_200(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"tag_name": "v1.5.0", "body": "bug fixes"}

        with patch("updater.requests.get", return_value=mock_resp):
            result = await fetch_latest_release("user/repo")

        assert result == {"tag_name": "v1.5.0", "body": "bug fixes"}

    async def test_returns_none_on_404(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"

        with patch("updater.requests.get", return_value=mock_resp):
            result = await fetch_latest_release("user/repo")

        assert result is None

    async def test_returns_none_on_network_error(self):
        with patch("updater.requests.get", side_effect=ConnectionError("No internet")):
            result = await fetch_latest_release("user/repo")

        assert result is None

    async def test_returns_none_on_timeout(self):
        import requests as req_lib
        with patch("updater.requests.get", side_effect=req_lib.Timeout()):
            result = await fetch_latest_release("user/repo")

        assert result is None

    async def test_uses_correct_api_url(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}

        with patch("updater.requests.get", return_value=mock_resp) as mock_get:
            await fetch_latest_release("myorg/myrepo")

        url = mock_get.call_args[0][0]
        assert "myorg/myrepo" in url
        assert "releases/latest" in url
        assert "api.github.com" in url

    async def test_sends_accept_header(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}

        with patch("updater.requests.get", return_value=mock_resp) as mock_get:
            await fetch_latest_release("user/repo")

        headers = mock_get.call_args[1]["headers"]
        assert headers.get("Accept") == "application/vnd.github+json"


# ── perform_update ────────────────────────────────────────────────────────────

class TestPerformUpdate:
    """Тестирует git fetch → checkout → pip install без реального git/pip."""

    def _make_run(self, *steps):
        """Возвращает заглушку subprocess.run, возвращающую шаги по очереди."""
        iterator = iter(steps)

        def fake_run(*args, **kwargs):
            step = next(iterator)
            if isinstance(step, BaseException):
                raise step
            return step

        return fake_run

    def _ok(self):
        return MagicMock(returncode=0)

    def _err(self, stderr: bytes = b"fatal error"):
        return subprocess.CalledProcessError(1, "git", stderr=stderr)

    @pytest.fixture
    def repo(self, tmp_path) -> Path:
        (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")
        return tmp_path

    # ── happy path ────────────────────────────────────────────────────────────

    async def test_success_returns_true(self, repo, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._make_run(self._ok(), self._ok(), self._ok()))
        success, error = await perform_update("v2.0.0", repo, repo / "config.yaml")
        assert success is True
        assert error == ""

    async def test_config_preserved_on_success(self, repo, monkeypatch):
        config = repo / "config.yaml"
        config.write_text("key: value", encoding="utf-8")
        monkeypatch.setattr(subprocess, "run", self._make_run(self._ok(), self._ok(), self._ok()))

        await perform_update("v2.0.0", repo, config)

        assert config.exists()
        assert config.read_text() == "key: value"

    async def test_works_without_config_file(self, repo, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._make_run(self._ok(), self._ok(), self._ok()))
        success, _ = await perform_update("v2.0.0", repo, repo / "nonexistent.yaml")
        assert success is True

    # ── git fetch fails ───────────────────────────────────────────────────────

    async def test_git_fetch_failure_returns_false(self, repo, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._make_run(self._err(b"network error")))
        success, error = await perform_update("v2.0.0", repo, repo / "config.yaml")
        assert success is False
        assert "network error" in error

    async def test_config_restored_after_fetch_failure(self, repo, monkeypatch):
        config = repo / "config.yaml"
        config.write_text("saved: data", encoding="utf-8")
        monkeypatch.setattr(subprocess, "run", self._make_run(self._err()))

        await perform_update("v2.0.0", repo, config)

        assert config.read_text() == "saved: data"

    # ── git checkout fails ────────────────────────────────────────────────────

    async def test_checkout_failure_returns_false(self, repo, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._make_run(self._ok(), self._err(b"bad tag")))
        success, error = await perform_update("v2.0.0", repo, repo / "config.yaml")
        assert success is False
        assert "bad tag" in error

    async def test_config_restored_after_checkout_failure(self, repo, monkeypatch):
        config = repo / "config.yaml"
        config.write_text("key: val", encoding="utf-8")
        monkeypatch.setattr(subprocess, "run", self._make_run(self._ok(), self._err()))

        await perform_update("v2.0.0", repo, config)

        assert config.read_text() == "key: val"

    # ── pip install fails ─────────────────────────────────────────────────────

    async def test_pip_failure_returns_false(self, repo, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run",
            self._make_run(self._ok(), self._ok(), self._err(b"pip error")),
        )
        success, error = await perform_update("v2.0.0", repo, repo / "config.yaml")
        assert success is False
        assert "pip error" in error

    async def test_config_restored_after_pip_failure(self, repo, monkeypatch):
        config = repo / "config.yaml"
        config.write_text("data: here", encoding="utf-8")
        monkeypatch.setattr(
            subprocess, "run",
            self._make_run(self._ok(), self._ok(), self._err()),
        )

        await perform_update("v2.0.0", repo, config)

        assert config.read_text() == "data: here"

    # ── error message ─────────────────────────────────────────────────────────

    async def test_error_from_stderr(self, repo, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._make_run(self._err(b"fatal: tag not found")))
        _, error = await perform_update("v99.0.0", repo, repo / "config.yaml")
        assert "fatal: tag not found" in error

    async def test_error_fallback_when_stderr_empty(self, repo, monkeypatch):
        monkeypatch.setattr(subprocess, "run", self._make_run(self._err(b"")))
        _, error = await perform_update("v99.0.0", repo, repo / "config.yaml")
        assert error  # не пустая строка
