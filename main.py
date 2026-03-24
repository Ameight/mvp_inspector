from nicegui import ui
import importlib.util
import yaml
import inspect
from pathlib import Path
from dotenv import load_dotenv
from plugins.base_plugin import PluginInterface
import asyncio
from collections import defaultdict

PLUGINS_DIR = Path("plugins")
CONFIG_PATH = Path("config.yaml")

# === Конфигурация
load_dotenv()
if CONFIG_PATH.exists():
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}
else:
    config = {}

# === Загрузка плагинов
loaded_plugins: list[PluginInterface] = []
for plugin_file in sorted(PLUGINS_DIR.rglob("plugin.py")):
    try:
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
    except Exception as e:
        print(f"⚠️ Ошибка загрузки {plugin_file}: {e}")

plugins_by_category: dict[str, list[PluginInterface]] = defaultdict(list)
for p in loaded_plugins:
    plugins_by_category[p.get_category()].append(p)

NEW_PLUGIN_SENTINEL = "__new_plugin__"

# === Состояние
state: dict = {"plugin": loaded_plugins[0] if loaded_plugins else None}


PLUGIN_TEMPLATE = '''\
from plugins.base_plugin import PluginInterface


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
            code_area = ui.textarea(value=PLUGIN_TEMPLATE).classes("flex-1 font-mono text-sm").props("rows=30 outlined readonly")
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

    p: PluginInterface
    ui.label(p.get_display_name()).classes("text-2xl font-bold mb-1")
    desc = p.get_description()
    if desc:
        ui.label(desc).classes("text-gray-400 text-sm mb-4")

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
            def open_new_plugin():
                state["plugin"] = NEW_PLUGIN_SENTINEL
                plugin_panel.refresh()
            ui.button("+", on_click=open_new_plugin).props("flat round dense").classes("text-gray-400")

        if not loaded_plugins:
            ui.label("Нет плагинов").classes("text-red-400 text-sm px-4")
        else:
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
                        ui.button(p.get_display_name(), on_click=make_handler()).classes(
                            "w-full text-sm"
                            + (" bg-blue-900" if is_active else "")
                        ).props("flat align=left").style("border-radius: 0; padding: 6px 16px;")

    # Основная область
    with ui.column().classes("flex-1 p-8 overflow-auto"):
        plugin_panel()

ui.run(title="TL IDE", favicon="🛠️")
