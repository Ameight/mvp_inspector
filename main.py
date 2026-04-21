from nicegui import ui
import importlib.util
import hashlib
import json
import os
import shutil
import yaml
import inspect
import subprocess
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv
from sdk.base_plugin import PluginInterface, app_log, _logs
import asyncio
from collections import defaultdict

VERSION_PATH = Path("VERSION")
GITHUB_REPO = "Ameight/mvp_inspector"
update_state: dict = {"latest_release": None, "checked": False, "error": None, "update_done": None, "banner_dismissed": False}

# === Конфигурация
# Порядок поиска config.yaml:
#   1. Переменная окружения TL_IDE_CONFIG
#   2. ~/.tl-ide/config.yaml (пользовательский уровень, вне проекта)
#   3. <папка main.py>/config.yaml (dev-режим / fallback)
# При первом запуске, если конфиг не найден нигде — копируем config.example.yaml
load_dotenv()

_APP_DIR = Path(__file__).parent
_EXAMPLE_CONFIG = _APP_DIR / "config.example.yaml"

def _resolve_config_path() -> Path:
    if env := os.environ.get("TL_IDE_CONFIG"):
        return Path(env).expanduser()
    home_cfg = Path.home() / ".tl-ide" / "config.yaml"
    if home_cfg.exists():
        return home_cfg
    return _APP_DIR / "config.yaml"

CONFIG_PATH = _resolve_config_path()

if not CONFIG_PATH.exists() and _EXAMPLE_CONFIG.exists():
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(_EXAMPLE_CONFIG, CONFIG_PATH)

if CONFIG_PATH.exists():
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}
else:
    config = {}

# Директория плагинов — читается из config.yaml: app.plugins_dir
_plugins_dir_raw = (config.get("app") or {}).get("plugins_dir", "plugins")
PLUGINS_DIR = Path(_plugins_dir_raw).expanduser()
if not PLUGINS_DIR.is_absolute():
    PLUGINS_DIR = Path(__file__).parent / PLUGINS_DIR
MANIFEST_PATH = PLUGINS_DIR / "manifest.json"


# === Manifest — источник и целостность плагинов
def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def compute_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_local_version() -> str:
    return VERSION_PATH.read_text(encoding="utf-8").strip() if VERSION_PATH.exists() else "0.0.0"


def parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except Exception:
        return (0, 0, 0)


def get_dirty_tracked_files() -> list[str]:
    try:
        r = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        # Пропускаем неотслеживаемые файлы (??) — они не мешают checkout
        return [line[3:].strip() for line in r.stdout.splitlines()
                if line.strip() and not line.startswith("??")]
    except Exception:
        return []


async def fetch_latest_release() -> dict | None:
    try:
        resp = await asyncio.to_thread(
            lambda: requests.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                timeout=8,
                headers={"Accept": "application/vnd.github+json"},
            )
        )
        if resp.status_code == 200:
            return resp.json()
        app_log(f"GitHub API вернул {resp.status_code}: {resp.text[:300]}", level="error", source="updater")
        return None
    except Exception as e:
        app_log(f"Ошибка соединения с GitHub: {e}", level="error", source="updater")
        return None


async def do_update(tag: str) -> None:
    dirty = get_dirty_tracked_files()
    if dirty:
        msg = f"Незафиксированные изменения: {', '.join(dirty[:3])}{'...' if len(dirty) > 3 else ''}. Сделай git stash или commit перед обновлением."
        app_log(msg, level="warning", source="updater")
        ui.notify(msg, type="warning", timeout=8000)
        return
    # Сохраняем и удаляем config.yaml до checkout:
    # - backup нужен чтобы не потерять настройки
    # - удаление нужно чтобы git не падал с "untracked file would be overwritten"
    #   (актуально при откате на тег, где config.yaml ещё был отслежен)
    config_backup = CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else None
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()
    spinner = ui.notification("Обновление...", spinner=True, timeout=None)
    try:
        app_log(f"Начинаем обновление до {tag}", source="updater")
        await asyncio.to_thread(lambda: subprocess.run(
            ["git", "fetch", "--tags"], check=True, capture_output=True
        ))
        app_log("git fetch --tags — OK", source="updater")
        await asyncio.to_thread(lambda: subprocess.run(
            ["git", "checkout", tag], check=True, capture_output=True
        ))
        app_log(f"git checkout {tag} — OK", source="updater")
        if config_backup is not None:
            CONFIG_PATH.write_text(config_backup, encoding="utf-8")
            app_log("config.yaml восстановлен", source="updater")
        await asyncio.to_thread(lambda: subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            check=True, capture_output=True,
        ))
        app_log("pip install — OK", source="updater")
        spinner.dismiss()
        update_state["update_done"] = tag
        plugin_panel.refresh()
    except subprocess.CalledProcessError as e:
        spinner.dismiss()
        if config_backup is not None:
            CONFIG_PATH.write_text(config_backup, encoding="utf-8")
        err = (e.stderr or b"").decode(errors="replace")
        full_err = err or str(e)
        app_log(f"Ошибка обновления: {full_err}", level="error", source="updater")
        ui.notify(f"❌ Ошибка обновления: {full_err[:200]}", type="negative", timeout=10000)


def check_integrity(plugin_id: str, manifest: dict) -> bool:
    """SHA256 проверка для marketplace-плагинов. Custom всегда OK."""
    entry = manifest.get(plugin_id, {})
    if entry.get("source") != "marketplace":
        return True
    stored = entry.get("sha256")
    if not stored:
        return True
    plugin_file = PLUGINS_DIR / plugin_id / "plugin.py"
    if not plugin_file.exists():
        return False
    return compute_sha256(plugin_file) == stored


# === Загрузка плагинов
manifest = load_manifest()
loaded_plugins: list[PluginInterface] = []
# id(instance) -> {plugin_id, source, integrity_ok, plugin_file}
plugin_meta: dict[int, dict] = {}

for plugin_file in sorted(PLUGINS_DIR.rglob("plugin.py")):
    try:
        plugin_id = "/".join(plugin_file.parts[1:-1])
        module_name = f"plugin_{'_'.join(plugin_file.parts[1:-1])}"
        spec = importlib.util.spec_from_file_location(module_name, plugin_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for obj in mod.__dict__.values():
            if isinstance(obj, type) and issubclass(obj, PluginInterface) and obj is not PluginInterface:
                instance = obj()
                plugin_config = config.get("plugins", {}).get(instance.get_config_key(), {})
                instance.configure(plugin_config)
                if instance.is_enabled():
                    loaded_plugins.append(instance)
                    m_entry = manifest.get(plugin_id, {})
                    p_source = m_entry.get("source", "custom")
                    p_label = m_entry.get("marketplace", "local") if p_source == "marketplace" else "local"
                    plugin_meta[id(instance)] = {
                        "plugin_id": plugin_id,
                        "source": p_source,
                        "label": p_label,
                        "integrity_ok": check_integrity(plugin_id, manifest),
                        "plugin_file": plugin_file,
                    }
    except Exception as e:
        print(f"⚠️ Ошибка загрузки {plugin_file}: {e}")

plugins_by_category: dict[str, list[PluginInterface]] = defaultdict(list)
for p in loaded_plugins:
    plugins_by_category[p.get_category()].append(p)

NEW_PLUGIN_SENTINEL = "__new_plugin__"
MARKETPLACE_SENTINEL = "__marketplace__"
SETTINGS_SENTINEL = "__settings__"
LOGS_SENTINEL = "__logs__"
MARKETPLACES: list[dict] = config.get("marketplaces", [
    {"name": "Official", "url": "https://raw.githubusercontent.com/Ameight/tl-ide-plugins/master/registry.json"}
])


def save_marketplaces(new_list: list) -> None:
    """Обновляет MARKETPLACES в памяти и сохраняет в config.yaml."""
    MARKETPLACES.clear()
    MARKETPLACES.extend(new_list)
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
    cfg["marketplaces"] = new_list
    CONFIG_PATH.write_text(
        yaml.dump(cfg, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def save_env_vars(updates: dict) -> None:
    """Записывает переменные в .env и сразу применяет в os.environ."""
    env_path = Path(".env")
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    key_to_idx = {
        line.split("=", 1)[0].strip(): i
        for i, line in enumerate(lines)
        if "=" in line and not line.startswith("#")
    }
    for key, value in updates.items():
        os.environ[key] = value
        if key in key_to_idx:
            lines[key_to_idx[key]] = f"{key}={value}"
        else:
            lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def delete_plugin(plugin: PluginInterface) -> None:
    meta = plugin_meta.get(id(plugin), {})
    plugin_id = meta.get("plugin_id", "")
    pfile: Path | None = meta.get("plugin_file")

    if pfile and pfile.exists():
        pfile.unlink()
        parent = pfile.parent
        # Удаляем папку плагина если пустая (кроме __pycache__)
        leftover = [f for f in parent.iterdir() if f.name != "__pycache__"]
        if not leftover:
            shutil.rmtree(parent, ignore_errors=True)

    # Обновляем manifest
    if plugin_id:
        m = load_manifest()
        m.pop(plugin_id, None)
        save_manifest(m)

    # Убираем из памяти
    if plugin in loaded_plugins:
        loaded_plugins.remove(plugin)
    category = plugin.get_category()
    if category in plugins_by_category and plugin in plugins_by_category[category]:
        plugins_by_category[category].remove(plugin)
        if not plugins_by_category[category]:
            del plugins_by_category[category]

    state["plugin"] = loaded_plugins[0] if loaded_plugins else None
    sidebar_panel.refresh()
    plugin_panel.refresh()


# === Состояние
state: dict = {"plugin": loaded_plugins[0] if loaded_plugins else None}


PLUGIN_TEMPLATE = '''\
from sdk.base_plugin import PluginInterface


class MyPlugin(PluginInterface):

    def get_display_name(self) -> str:
        return "My Plugin"

    def get_description(self) -> str:
        return "Краткое описание плагина."

    def get_category(self) -> str:
        return "General"

    def get_config_schema(self) -> dict:
        return {
            "input": {
                "label": "Входные данные",
                "type": "string",   # string | textarea | int | bool | select_or_input
                "default": "",
            },
        }

    def run(self, inputs: dict) -> str:
        value = inputs.get("input", "")

        # TODO: реализовать логику плагина
        # Secrets: os.getenv("MY_TOKEN")
        # Config:  self.config.get("base_url")
        return f"**Результат:**\\n\\n{value}"
'''


def _env_dialog(plugin: PluginInterface, req: dict) -> None:
    """Открывает модальное окно для настройки env-переменных плагина."""
    field_inputs: dict = {}
    with ui.dialog() as dlg, ui.card().classes("min-w-96"):
        ui.label("Переменные окружения").classes("text-xl font-bold mb-1")
        ui.label(plugin.get_display_name()).classes("text-gray-400 text-sm mb-4")
        for var_name, meta in req.items():
            is_secret = meta.get("secret", True)
            field_inputs[var_name] = ui.input(
                label=f"{meta.get('label', var_name)}  ({var_name})",
                value=os.getenv(var_name, ""),
                password=is_secret,
                password_toggle_button=is_secret,
            ).classes("w-full")
            if meta.get("description"):
                ui.label(meta["description"]).classes("text-gray-500 text-xs -mt-2 mb-2")
        with ui.row().classes("gap-2 mt-4 justify-end w-full"):
            ui.button("Отмена", on_click=dlg.close).props("flat")
            def do_save(d=dlg, fi=field_inputs):
                upd = {k: v.value for k, v in fi.items() if v.value}
                if upd:
                    save_env_vars(upd)
                    ui.notify(f"Сохранено: {len(upd)} переменных", type="positive")
                d.close()
                plugin_panel.refresh()
            ui.button("Сохранить", on_click=do_save).props("unelevated color=primary")
    dlg.open()


@ui.refreshable
def sidebar_panel():
    if not loaded_plugins:
        ui.label("Нет плагинов").classes("text-red-400 text-sm px-4")
        return
    for category in sorted(plugins_by_category):
        with ui.expansion(category, value=True).classes("w-full").style(
            "border-radius: 0;"
        ).props("dense expand-icon-class='text-gray-500'"):
            for p in plugins_by_category[category]:
                def make_handler(plugin=p):
                    def handler():
                        state["plugin"] = plugin
                        plugin_panel.refresh()
                    return handler

                is_active = state["plugin"] is p
                pmeta = plugin_meta.get(id(p), {})
                plabel = pmeta.get("label", "local")
                pintact = pmeta.get("integrity_ok", True)

                btn = ui.button(on_click=make_handler()).classes(
                    "w-full text-sm" + (" bg-blue-900" if is_active else "")
                ).props("flat align=left").style("border-radius: 0; padding: 6px 16px;")
                with btn:
                    with ui.row().classes("items-center gap-2 w-full no-wrap"):
                        if not pintact:
                            ui.icon("warning", size="xs", color="red")
                        elif plabel != "local":
                            ui.icon("storefront", size="xs").classes("text-blue-400").tooltip(plabel)
                        else:
                            ui.icon("code", size="xs").classes("text-gray-600")
                        with ui.column().classes("gap-0 flex-1 min-w-0"):
                            ui.label(p.get_display_name()).classes("text-sm leading-tight")
                            lc = "text-blue-400" if plabel != "local" else "text-gray-500"
                            ui.label(plabel).classes(f"text-xs {lc}")


# === Панель плагина (перерисовывается при смене)
@ui.refreshable
def plugin_panel():
    p = state["plugin"]

    if p is None:
        with ui.column().classes("w-full items-center justify-center").style("min-height: 300px"):
            ui.label("Выберите плагин из списка слева").classes("text-gray-500 text-lg")
        return

    if p is NEW_PLUGIN_SENTINEL:
        ui.label("Добавить плагин").classes("text-2xl font-bold mb-1")
        ui.label("Создай файл по одному из способов ниже, перезапусти приложение — плагин появится в сайдбаре.").classes("text-gray-400 text-sm mb-6")

        ui.label("Способ 1 — генератор").classes("text-base font-semibold mt-2")
        ui.markdown(
            "```bash\n"
            "make plugin name=my_plugin category=jira\n"
            "# или\n"
            "python create_plugin.py my_plugin jira\n"
            "```"
        ).classes("w-full")

        ui.label("Способ 2 — вручную").classes("text-base font-semibold mt-4")
        ui.markdown(
            "Создай файл `plugins/<category>/<name>/plugin.py` со следующим содержимым:"
        ).classes("text-gray-400 text-sm")

        with ui.row().classes("w-full gap-2 mt-1"):
            ui.textarea(value=PLUGIN_TEMPLATE).classes("flex-1 font-mono text-sm").props("rows=30 outlined readonly")
            async def copy_template():
                await ui.run_javascript(f"navigator.clipboard.writeText({repr(PLUGIN_TEMPLATE)})")
                ui.notify("Скопировано!", type="positive")
            ui.button("📋 Копировать", on_click=copy_template).props("flat").classes("self-start")

        ui.label("Структура папок").classes("text-base font-semibold mt-6")
        ui.markdown(
            "```\n"
            "plugins/\n"
            "  jira/\n"
            "    issue_info/plugin.py    ← категория Jira\n"
            "    my_tasks/plugin.py\n"
            "  general/\n"
            "    ip_checker/plugin.py\n"
            "```"
        ).classes("w-full")

        ui.label("Secrets и конфиг").classes("text-base font-semibold mt-4")
        ui.markdown(
            "- Токены → `.env` → читай через `os.getenv('MY_TOKEN')`\n"
            "- URL, настройки → `config.yaml` → `plugins.my_plugin_key` → читай через `self.config.get('base_url')`"
        ).classes("w-full")
        return

    if p is MARKETPLACE_SENTINEL:
        ui.label("Marketplace").classes("text-2xl font-bold mb-1")
        ui.label("Плагины из подключённых реестров. После установки перезапусти приложение.").classes("text-gray-400 text-sm mb-4")

        with ui.row().classes("w-full gap-3 mb-4"):
            search_input = ui.input(placeholder="Поиск по названию или категории...").classes("flex-1")
            mp_options = ["Все"] + [m["name"] for m in MARKETPLACES]
            mp_select = ui.select(mp_options, value="Все", label="Маркетплейс").classes("w-48")
        status_label = ui.label("Загрузка...").classes("text-gray-400 text-sm")
        cards_column = ui.column().classes("w-full gap-3")

        def is_installed(plugin_id: str) -> bool:
            return (PLUGINS_DIR / plugin_id / "plugin.py").exists()

        def render_cards(registry: list, search: str = "", mp_filter: str = "Все"):
            cards_column.clear()
            search = search.lower()
            filtered = [
                e for e in registry
                if (not search
                    or search in e.get("name", "").lower()
                    or search in e.get("category", "").lower()
                    or search in e.get("description", "").lower())
                and (mp_filter == "Все" or e.get("_marketplace") == mp_filter)
            ]
            status_label.set_text(f"{len(filtered)} плагинов" if filtered else "Ничего не найдено")
            current_manifest = load_manifest()
            local_v = get_local_version()
            with cards_column:
                for entry in filtered:
                    plugin_id = entry.get("id", "")
                    installed = is_installed(plugin_id)
                    integrity_ok = check_integrity(plugin_id, current_manifest) if installed else True
                    mp_name = entry.get("_marketplace", "")
                    min_app_v = entry.get("min_app_version", "")
                    compat = not min_app_v or parse_version(local_v) >= parse_version(min_app_v)
                    with ui.card().classes("w-full"):
                        with ui.row().classes("items-start justify-between w-full"):
                            with ui.column().classes("gap-0"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.label(entry.get("name", "?")).classes("font-semibold")
                                    ui.badge(entry.get("category", ""), color="blue").props("outline")
                                    if len(MARKETPLACES) > 1:
                                        ui.badge(mp_name, color="teal").props("outline")
                                    if min_app_v:
                                        ui.badge(f"app ≥ {min_app_v}", color="grey").props("outline")
                                ui.label(entry.get("description", "")).classes("text-gray-400 text-sm")
                                requires = entry.get("requires", [])
                                if requires:
                                    ui.label("requires: " + ", ".join(requires)).classes("text-gray-600 text-xs mt-1")
                            with ui.column().classes("items-end gap-1 shrink-0"):
                                if installed:
                                    if not integrity_ok:
                                        ui.label("⚠ Изменён").classes("text-orange-400 text-sm")
                                    else:
                                        ui.label("✓ Установлен").classes("text-green-500 text-sm")
                                    installed_v = current_manifest.get(plugin_id, {}).get("version", "")
                                    registry_v = entry.get("version", "")
                                    versions_list = entry.get("versions", [])
                                    if versions_list:
                                        v_options = [v["version"] for v in versions_list]
                                        default_v = installed_v if installed_v in v_options else (v_options[-1] if v_options else installed_v)
                                        with ui.row().classes("items-center gap-1 mt-1"):
                                            ver_sel = ui.select(v_options, value=default_v).props("dense outlined").classes("text-xs").style("min-width:90px")
                                            async def install_ver(e=entry, vs=ver_sel, vl=versions_list):
                                                sel = vs.value
                                                v_data = next((v for v in vl if v["version"] == sel), None)
                                                if v_data:
                                                    await do_install({**e, "version": sel, "raw_url": v_data.get("raw_url", e.get("raw_url", ""))})
                                            ui.button("Установить", on_click=install_ver).props("dense unelevated").classes("text-xs")
                                    elif installed_v and registry_v and parse_version(registry_v) > parse_version(installed_v):
                                        ui.label(f"v{installed_v} → v{registry_v}").classes("text-orange-400 text-xs mt-1")
                                        async def update_p(e=entry):
                                            await do_install(e)
                                        ui.button(f"Обновить до v{registry_v}", on_click=update_p).props("dense unelevated color=positive").classes("text-xs mt-1")
                                    elif installed_v:
                                        ui.label(f"v{installed_v}").classes("text-gray-500 text-xs mt-1")
                                else:
                                    if compat:
                                        async def install(e=entry):
                                            await do_install(e)
                                        ui.button("Установить", on_click=install).props("dense unelevated").classes("text-sm")
                                    else:
                                        ui.label(f"Требуется приложение ≥ {min_app_v}").classes("text-orange-400 text-xs text-right")
                                ui.label(f"v{entry.get('version', '?')}  ·  {entry.get('author', '?')}").classes("text-gray-600 text-xs")

        async def do_install(entry: dict):
            plugin_id = entry.get("id", "")
            raw_url = entry.get("raw_url", "")
            requires = entry.get("requires", [])
            mp_name = entry.get("_marketplace", MARKETPLACES[0]["name"] if MARKETPLACES else "")
            min_app_v = entry.get("min_app_version", "")
            if min_app_v and parse_version(get_local_version()) < parse_version(min_app_v):
                ui.notify(
                    f"Плагин «{entry.get('name')}» требует приложение ≥ {min_app_v} (у тебя {get_local_version()}). Обнови приложение.",
                    type="warning", timeout=8000,
                )
                return
            dest = PLUGINS_DIR / plugin_id / "plugin.py"
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                code = await asyncio.to_thread(lambda: requests.get(raw_url, timeout=10).text)
                dest.write_text(code, encoding="utf-8")
                m = load_manifest()
                m[plugin_id] = {
                    "source": "marketplace",
                    "marketplace": mp_name,
                    "sha256": compute_sha256(dest),
                    "name": entry.get("name", ""),
                    "version": entry.get("version", ""),
                    "author": entry.get("author", ""),
                }
                save_manifest(m)
                if requires:
                    await asyncio.to_thread(
                        lambda: subprocess.run(
                            [sys.executable, "-m", "pip", "install", *requires],
                            check=True, capture_output=True,
                        )
                    )
                ui.notify(f"✅ {entry.get('name')} установлен. Перезапусти приложение.", type="positive", timeout=6000)
                plugin_panel.refresh()
            except Exception as e:
                ui.notify(f"❌ Ошибка установки: {e}", type="negative", timeout=8000)

        all_entries: list = []

        async def load_registry():
            nonlocal all_entries
            results = await asyncio.gather(
                *[
                    asyncio.to_thread(lambda url=m["url"], name=m["name"]: (name, requests.get(url, timeout=10)))
                    for m in MARKETPLACES
                ],
                return_exceptions=True,
            )
            all_entries = []
            errors = []
            for item in results:
                if isinstance(item, Exception):
                    errors.append(str(item))
                    continue
                mp_name, resp = item
                try:
                    if resp.status_code == 404:
                        errors.append(f"{mp_name}: registry.json не найден")
                        continue
                    resp.raise_for_status()
                    for entry in resp.json():
                        entry["_marketplace"] = mp_name
                        all_entries.append(entry)
                except Exception as e:
                    errors.append(f"{mp_name}: {e}")

            if errors and not all_entries:
                status_label.set_text("❌ " + "; ".join(errors))
                return
            render_cards(all_entries)
            if errors:
                ui.notify("Не удалось загрузить: " + "; ".join(errors), type="warning")

            search_input.on("update:model-value", lambda e: render_cards(all_entries, e.args, mp_select.value))
            mp_select.on("update:model-value", lambda _: render_cards(all_entries, search_input.value, mp_select.value))

        ui.timer(0.05, load_registry, once=True)
        return

    if p is LOGS_SENTINEL:
        _level_colors = {"info": "grey", "warning": "orange", "error": "red", "debug": "blue-grey"}
        with ui.row().classes("items-center justify-between w-full mb-4"):
            ui.label("Логи").classes("text-2xl font-bold")
            with ui.row().classes("gap-2"):
                ui.button("Обновить", on_click=plugin_panel.refresh).props("flat dense")
                def _clear_logs():
                    _logs.clear()
                    plugin_panel.refresh()
                ui.button("Очистить", on_click=_clear_logs).props("flat dense color=red-4")
        if not _logs:
            ui.label("Нет записей").classes("text-gray-500 text-sm")
            return
        with ui.column().classes("w-full gap-0"):
            for entry in reversed(_logs):
                level = entry["level"]
                color = _level_colors.get(level, "grey")
                ts = entry["ts"].strftime("%H:%M:%S")
                with ui.row().classes("items-start gap-2 w-full py-2 px-1").style("border-bottom: 1px solid #222;"):
                    ui.label(ts).classes("text-gray-500 shrink-0 text-xs font-mono pt-0.5 w-16")
                    ui.badge(level, color=color).props("outline").classes("shrink-0")
                    ui.label(entry["source"]).classes("text-blue-400 shrink-0 text-xs font-mono pt-0.5 w-24 truncate")
                    ui.label(entry["message"]).classes("text-gray-200 text-sm break-all")
        return

    if p is SETTINGS_SENTINEL:
        ui.label("Настройки").classes("text-2xl font-bold mb-1")
        ui.label("Переменные окружения и конфигурация плагинов.").classes("text-gray-400 text-sm mb-6")

        plugins_with_env = [pl for pl in loaded_plugins if pl.get_required_env()]
        if plugins_with_env:
            ui.label("Переменные окружения").classes("text-lg font-semibold mb-3")
            for pl in plugins_with_env:
                req = pl.get_required_env()
                missing = [k for k in req if not os.getenv(k)]
                with ui.card().classes("w-full mb-3"):
                    with ui.row().classes("items-center justify-between w-full"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("check_circle" if not missing else "warning",
                                    color="green" if not missing else "orange")
                            ui.label(pl.get_display_name()).classes("font-semibold")
                            ui.badge(pl.get_category(), color="blue").props("outline")
                        ui.button("Изменить", on_click=lambda plugin=pl, r=req: _env_dialog(plugin, r)).props("flat dense")
                    with ui.column().classes("w-full mt-2 gap-1"):
                        for var_name, meta in req.items():
                            val = os.getenv(var_name)
                            with ui.row().classes("items-center gap-2"):
                                ui.icon("circle", color="green" if val else "red").classes("text-xs")
                                ui.label(var_name).classes("font-mono text-sm")
                                ui.label(meta.get("label", "")).classes("text-gray-400 text-sm")
                                if val:
                                    ui.label("настроено").classes("text-green-500 text-xs ml-auto")
                                else:
                                    ui.label("не задано").classes("text-red-400 text-xs ml-auto")
        else:
            ui.label("Ни один загруженный плагин не требует env-переменных.").classes("text-gray-500 text-sm mb-4")

        ui.separator().classes("my-4")
        ui.label("Маркетплейсы").classes("text-lg font-semibold mb-3")
        ui.label("Изменения применяются сразу и сохраняются в config.yaml.").classes("text-gray-400 text-sm mb-3")

        mp_rows: list[dict] = []
        mp_list_col = ui.column().classes("w-full gap-2 mb-3")

        def render_mp_rows():
            mp_list_col.clear()
            mp_rows.clear()
            with mp_list_col:
                for idx, mp in enumerate(list(MARKETPLACES)):
                    row_inputs: dict = {}
                    with ui.card().classes("w-full"):
                        with ui.row().classes("items-center gap-2 w-full"):
                            row_inputs["name"] = ui.input(value=mp["name"], label="Название").classes("w-36")
                            row_inputs["url"] = ui.input(value=mp["url"], label="URL registry.json").classes("flex-1")
                            def do_save_row(i=idx, ri=row_inputs):
                                updated = list(MARKETPLACES)
                                updated[i] = {"name": ri["name"].value.strip(), "url": ri["url"].value.strip()}
                                if updated[i]["name"] and updated[i]["url"]:
                                    save_marketplaces(updated)
                                    ui.notify("Сохранено", type="positive")
                            def do_delete_row(i=idx):
                                save_marketplaces([m for j, m in enumerate(MARKETPLACES) if j != i])
                                render_mp_rows()
                            ui.button(icon="save", on_click=do_save_row).props("flat round dense color=primary").tooltip("Сохранить")
                            ui.button(icon="delete", on_click=do_delete_row).props("flat round dense color=red-4").tooltip("Удалить")
                    mp_rows.append(row_inputs)

        render_mp_rows()

        with ui.card().classes("w-full"):
            with ui.row().classes("items-center gap-2 w-full"):
                new_name = ui.input(label="Название").classes("w-36")
                new_url = ui.input(label="URL registry.json").classes("flex-1")
                def do_add_mp():
                    name_val = new_name.value.strip()
                    url_val = new_url.value.strip()
                    if not name_val or not url_val:
                        ui.notify("Заполни название и URL", type="warning")
                        return
                    save_marketplaces(list(MARKETPLACES) + [{"name": name_val, "url": url_val}])
                    new_name.set_value("")
                    new_url.set_value("")
                    render_mp_rows()
                    ui.notify(f"Добавлен маркетплейс «{name_val}»", type="positive")
                ui.button(icon="add", on_click=do_add_mp).props("flat round dense color=primary").tooltip("Добавить")

        ui.separator().classes("my-4")
        ui.label("Плагины").classes("text-lg font-semibold mb-2")

        plugins_dir_input = ui.input(value=str(PLUGINS_DIR)).classes("flex-1 font-mono text-sm").props("outlined dense")

        async def _pick_plugins_folder():
            # tkinter требует главный поток (macOS: NSWindow crash в asyncio.to_thread).
            # Запускаем диалог в отдельном subprocess — у него свой главный поток.
            initial = plugins_dir_input.value or str(PLUGINS_DIR)
            script = (
                "import tkinter as tk, sys\n"
                "from tkinter import filedialog\n"
                "root = tk.Tk(); root.withdraw(); root.wm_attributes('-topmost', True)\n"
                f"p = filedialog.askdirectory(title='Папка с плагинами', initialdir={repr(initial)})\n"
                "root.destroy(); print(p, end='')"
            )
            try:
                result = await asyncio.to_thread(
                    lambda: subprocess.run(
                        [sys.executable, "-c", script],
                        capture_output=True, text=True, timeout=120,
                    )
                )
                chosen = result.stdout.strip()
                if chosen:
                    plugins_dir_input.set_value(chosen)
            except Exception:
                ui.notify("Нативный диалог недоступен — введи путь вручную", type="info")

        def _save_plugins_dir():
            new_path = plugins_dir_input.value.strip()
            if not new_path:
                ui.notify("Путь не может быть пустым", type="warning")
                return
            p = Path(new_path).expanduser()
            if not p.exists():
                try:
                    p.mkdir(parents=True)
                except Exception as e:
                    ui.notify(f"Не удалось создать папку: {e}", type="negative")
                    return
            try:
                raw = CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else ""
                cfg = yaml.safe_load(raw) or {}
                if "app" not in cfg or cfg["app"] is None:
                    cfg["app"] = {}
                cfg["app"]["plugins_dir"] = new_path
                CONFIG_PATH.write_text(yaml.dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
                ui.notify("Сохранено. Перезапусти приложение для применения.", type="positive")
            except Exception as e:
                ui.notify(f"Ошибка сохранения: {e}", type="negative")

        with ui.row().classes("items-center gap-2 w-full mb-1"):
            plugins_dir_input
            ui.button(icon="folder_open", on_click=_pick_plugins_folder).props("flat round dense color=grey-5").tooltip("Выбрать папку")
            ui.button(icon="save", on_click=_save_plugins_dir).props("flat round dense color=primary").tooltip("Сохранить")
        ui.label("Абсолютный или относительный к main.py путь. Сохраняется в config.yaml.").classes("text-gray-600 text-xs mb-1")

        ui.separator().classes("my-4")
        ui.label("config.yaml").classes("text-lg font-semibold mb-2")
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("description", color="grey").classes("text-sm")
            ui.label(str(CONFIG_PATH)).classes("text-gray-400 text-sm font-mono")
        if os.environ.get("TL_IDE_CONFIG"):
            _cfg_source = "из TL_IDE_CONFIG"
        elif CONFIG_PATH == Path.home() / ".tl-ide" / "config.yaml":
            _cfg_source = "из ~/.tl-ide/"
        else:
            _cfg_source = "dev-режим (рядом с main.py)"
        ui.label(f"Источник: {_cfg_source}. Для prod вынеси в ~/.tl-ide/config.yaml или задай TL_IDE_CONFIG.").classes("text-gray-600 text-xs mb-3")
        yaml_content = CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else ""
        config_area = ui.textarea(value=yaml_content).classes("w-full font-mono text-sm").props("rows=20 outlined")

        def save_config():
            try:
                yaml.safe_load(config_area.value)
                CONFIG_PATH.write_text(config_area.value, encoding="utf-8")
                ui.notify("config.yaml сохранён. Перезапусти приложение для применения.", type="positive", timeout=5000)
            except yaml.YAMLError as e:
                ui.notify(f"Ошибка YAML: {e}", type="negative", timeout=8000)

        ui.button("Сохранить config.yaml", on_click=save_config).props("unelevated color=primary").classes("mt-2")

        ui.separator().classes("my-4")
        ui.label("Обновления").classes("text-lg font-semibold mb-2")
        local_v = get_local_version()
        ui.label(f"Текущая версия: {local_v}").classes("text-gray-400 text-sm mb-3")

        upd_err = update_state.get("error")
        if upd_err:
            ui.label(f"Ошибка: {upd_err}").classes("text-red-400 text-sm mb-2")

        is_git_repo = Path(".git").exists()

        upd_release = update_state.get("latest_release")

        if update_state.get("update_done"):
            done_tag = update_state["update_done"]
            with ui.card().classes("w-full mb-3").style("background: #0d2b0d; border: 1px solid #1a4a1a;"):
                with ui.row().classes("items-center gap-2 mb-3"):
                    ui.icon("check_circle", color="green")
                    ui.label(f"Обновлено до {done_tag}. Перезапусти для применения.").classes("text-green-400 font-semibold")
                def _restart():
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                ui.button("Перезапустить", icon="restart_alt", on_click=_restart).props("unelevated color=positive")

        elif update_state.get("checked") and upd_release:
            upd_tag = upd_release.get("tag_name", "")
            if parse_version(upd_tag) > parse_version(local_v) and not update_state.get("banner_dismissed"):
                with ui.card().classes("w-full mb-3").style("background: #0d2b0d; border: 1px solid #1a4a1a;"):
                    with ui.row().classes("items-center justify-between w-full mb-2"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("system_update_alt", color="green")
                            ui.label(f"Доступна {upd_tag}").classes("text-green-400 font-semibold")
                        def _dismiss_banner():
                            update_state["banner_dismissed"] = True
                            plugin_panel.refresh()
                        ui.button(icon="close", on_click=_dismiss_banner).props("flat round dense color=grey-5").tooltip("Скрыть")
                    upd_body = upd_release.get("body", "")
                    if upd_body:
                        ui.markdown(upd_body[:600]).classes("text-sm mb-3")
                    if is_git_repo:
                        async def _do_update_click(t=upd_tag):
                            await do_update(t)
                        ui.button(f"Обновить до {upd_tag}", on_click=_do_update_click).props("unelevated color=positive")
                    else:
                        download_url = upd_release.get("html_url", f"https://github.com/{GITHUB_REPO}/releases/latest")
                        ui.label("Скачай новую версию:").classes("text-gray-400 text-sm mb-1")
                        ui.link(download_url, download_url, new_tab=True).classes("text-blue-400 text-sm break-all")
            elif parse_version(upd_tag) <= parse_version(local_v):
                with ui.row().classes("items-center gap-2 mb-3"):
                    ui.icon("check_circle", color="green")
                    ui.label(f"Установлена последняя версия ({upd_tag})").classes("text-green-500 text-sm")

        async def _check_updates():
            update_state["error"] = None
            plugin_panel.refresh()
            rel = await fetch_latest_release()
            if rel is None:
                update_state["error"] = "Не удалось получить данные с GitHub"
            else:
                update_state["latest_release"] = rel
            update_state["checked"] = True
            plugin_panel.refresh()

        ui.button("Проверить обновления", on_click=_check_updates).props("outlined")
        return

    # === Обычный плагин
    p: PluginInterface
    meta = plugin_meta.get(id(p), {})
    label = meta.get("label", "local")
    integrity_ok = meta.get("integrity_ok", True)

    # Заголовок + бейдж источника + кнопка удаления
    with ui.row().classes("items-center justify-between w-full mb-1"):
        with ui.row().classes("items-center gap-2"):
            ui.label(p.get_display_name()).classes("text-2xl font-bold")
            if not integrity_ok:
                ui.badge("⚠ изменён", color="red").props("outline")
            elif label != "local":
                ui.badge(label, color="blue").props("outline")
            else:
                ui.badge("local", color="grey").props("outline")

        def confirm_delete(plugin=p):
            with ui.dialog() as dlg, ui.card():
                ui.label("Удалить плагин?").classes("text-lg font-bold mb-2")
                ui.label(f"Файл плагина «{plugin.get_display_name()}» будет удалён безвозвратно.").classes("text-gray-400 text-sm mb-4")
                with ui.row().classes("gap-2 justify-end w-full"):
                    ui.button("Отмена", on_click=dlg.close).props("flat")
                    def do_delete(d=dlg, pl=plugin):
                        d.close()
                        delete_plugin(pl)
                    ui.button("Удалить", on_click=do_delete).props("unelevated color=negative")
            dlg.open()

        ui.button(icon="delete", on_click=confirm_delete).props("flat round dense color=red-4").tooltip("Удалить плагин")

    desc = p.get_description()
    if desc:
        ui.label(desc).classes("text-gray-400 text-sm mb-4")

    # Предупреждение о нарушенной целостности
    if not integrity_ok:
        with ui.row().classes("items-center gap-2 mb-4 px-3 py-2 rounded w-full").style("background: #2d0a0a;"):
            ui.icon("warning", color="red")
            ui.label("Файл плагина был изменён после установки из marketplace.").classes("text-red-300 text-sm")

    # Env vars check
    required_env = p.get_required_env()
    if required_env:
        missing_env = [k for k in required_env if not os.getenv(k)]
        bg = "background: #2d1b00;" if missing_env else "background: #0d2b0d;"
        with ui.row().classes("items-center gap-2 mb-4 px-3 py-2 rounded w-full").style(bg):
            if missing_env:
                ui.icon("warning", color="orange")
                ui.label(f"Не настроено: {', '.join(missing_env)}").classes("text-orange-300 text-sm flex-1")
            else:
                ui.icon("check_circle", color="green")
                ui.label("Все переменные окружения настроены").classes("text-green-400 text-sm flex-1")
            lbl = "Настроить" if missing_env else "Изменить"
            ui.button(lbl, on_click=lambda plugin=p, req=required_env: _env_dialog(plugin, req)).props("flat dense size=sm")

    schema = p.get_config_schema()
    inputs: dict = {}

    with ui.column().classes("w-full gap-3"):
        for key, field in schema.items():
            label = field.get("label", key)
            default = field.get("default", "")
            input_type = field.get("type", "string")

            if input_type == "int":
                inputs[key] = ui.number(label=label, value=default).classes("w-full")
            elif input_type == "bool":
                inputs[key] = ui.checkbox(text=label, value=default)
            elif input_type == "select_or_input":
                options = field.get("options", [])
                inputs[key] = ui.select(options, value=default, label=label, with_input=True).classes("w-full")
            elif input_type == "textarea":
                inputs[key] = ui.textarea(label=label, value=default).classes("w-full").props("rows=5")
            else:
                inputs[key] = ui.input(label=label, value=default).classes("w-full")

    output_area = ui.markdown("*Ожидание запуска…*").classes("w-full text-left text-sm mt-4").style(
        "min-height: 180px; max-height: 600px; overflow-y: auto;"
        "border: 1px solid #333; padding: 16px; border-radius: 8px;"
    )
    result_store: dict = {"text": ""}

    with ui.row().classes("gap-2 mt-2"):
        run_button = ui.button("▶ Запустить", color="primary")
        copy_button = ui.button("📋 Копировать").props("flat")

    async def run_plugin():
        data = {k: v.value for k, v in inputs.items()}
        output_area.content = "⏳ **Выполнение...**"
        run_button.set_enabled(False)
        run_button.set_text("Выполнение...")
        await asyncio.sleep(0.05)
        try:
            result = p.run(data)
            if inspect.isawaitable(result):
                result = await result
            text = result if isinstance(result, str) else str(result)
            result_store["text"] = text
            output_area.content = text
        except Exception as e:
            app_log(str(e), level="error", source=p.get_display_name())
            output_area.content = f"❌ **Ошибка:**\n```\n{e}\n```"
        finally:
            run_button.set_text("▶ Запустить")
            run_button.set_enabled(True)

    async def copy_output():
        text = result_store["text"]
        if not text:
            ui.notify("Нечего копировать", type="warning")
            return
        await ui.run_javascript(f"navigator.clipboard.writeText({repr(text)})")
        ui.notify("Скопировано!", type="positive")

    run_button.on("click", run_plugin)
    copy_button.on("click", copy_output)


# === Layout
ui.dark_mode().enable()

with ui.row().classes("w-full gap-0").style("min-height: 100vh"):

    # Сайдбар
    with ui.column().classes("gap-0 p-0").style(
        "width: 220px; min-height: 100vh; background: #1a1a1a; border-right: 1px solid #2a2a2a; flex-shrink: 0;"
    ):
        with ui.row().classes("items-center justify-between px-4 py-4"):
            ui.label("TL IDE").classes("text-lg font-bold")
            with ui.row().classes("gap-1"):
                def open_marketplace():
                    state["plugin"] = MARKETPLACE_SENTINEL
                    plugin_panel.refresh()
                ui.button(icon="storefront", on_click=open_marketplace).props("flat round dense").tooltip("Marketplace")
                def open_new_plugin():
                    state["plugin"] = NEW_PLUGIN_SENTINEL
                    plugin_panel.refresh()
                ui.button(icon="add", on_click=open_new_plugin).props("flat round dense").classes("text-gray-400").tooltip("Добавить плагин")
                def open_settings():
                    state["plugin"] = SETTINGS_SENTINEL
                    plugin_panel.refresh()
                ui.button(icon="settings", on_click=open_settings).props("flat round dense").classes("text-gray-400").tooltip("Настройки")
                def open_logs():
                    state["plugin"] = LOGS_SENTINEL
                    plugin_panel.refresh()
                ui.button(icon="bug_report", on_click=open_logs).props("flat round dense").classes("text-gray-400").tooltip("Логи")

        sidebar_panel()

    # Основная область
    with ui.column().classes("flex-1 p-8 overflow-auto"):
        plugin_panel()

async def _startup_update_check():
    rel = await fetch_latest_release()
    if rel is None:
        return
    update_state["latest_release"] = rel
    update_state["checked"] = True
    tag = rel.get("tag_name", "")
    if parse_version(tag) > parse_version(get_local_version()):
        action = "Настройки → Обновления" if Path(".git").exists() else f"github.com/{GITHUB_REPO}/releases/latest"
        ui.notify(
            f"Доступна новая версия {tag}. {action}",
            type="info", timeout=0, close_button="✕",
        )

ui.timer(2.0, _startup_update_check, once=True)

ui.run(title="TL IDE", favicon="🛠️")
