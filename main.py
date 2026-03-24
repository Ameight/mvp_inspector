from nicegui import ui
import importlib.util
import yaml
import inspect
from pathlib import Path
from dotenv import load_dotenv
from plugins.base_plugin import PluginInterface
import asyncio

PLUGINS_DIR = Path("plugins")
CONFIG_PATH = Path("config.yaml")

# === Загрузка конфигурации и .env
load_dotenv()
with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

# === Загрузка плагинов
loaded_plugins = []
for plugin_file in PLUGINS_DIR.rglob("plugin.py"):
    try:
        spec = importlib.util.spec_from_file_location(plugin_file.stem, plugin_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for obj in mod.__dict__.values():
            if isinstance(obj, type) and issubclass(obj, PluginInterface) and obj is not PluginInterface:
                loaded_plugins.append(obj())
    except Exception as e:
        print(f"⚠️ Ошибка загрузки {plugin_file}: {e}")

# === UI
ui.dark_mode().enable()
ui.label("TL IDE").classes("text-2xl font-bold my-4")

if not loaded_plugins:
    ui.label("❌ Не найдено ни одного плагина").classes("text-red-500 text-xl")
else:
    with ui.tabs().classes("w-full") as tabs:
        tab_names = [p.get_display_name() for p in loaded_plugins]
        for name in tab_names:
            ui.tab(name)

    with ui.tab_panels(tabs, value=tab_names[0]).classes("w-full"):
        for plugin in loaded_plugins:
            with ui.tab_panel(plugin.get_display_name()):
                schema = plugin.get_config_schema()
                inputs = {}

                for key, field in schema.items():
                    label = field.get("label", key)
                    default = field.get("default", "")
                    input_type = field.get("type", "string")

                    if input_type == "int":
                        inputs[key] = ui.number(label=label, value=default)

                    elif input_type == "bool":
                        inputs[key] = ui.checkbox(text=label, value=default)
                    elif input_type == "select_or_input":
                        options = field.get("options", [])
                        inputs[key] = ui.select(options, value=default, label=label, with_input=True)

                    else:
                        inputs[key] = ui.input(label=label, value=default)


                output_area = ui.markdown("⌛ Ожидание запуска…").classes("w-full text-left text-sm").style(
                    "min-height: 200px; max-height: 600px; overflow-y: auto;"
                )
                run_button = ui.button("▶ Запустить", color="primary")

                async def run_plugin(p=plugin, fields=inputs, out=output_area, button=run_button):
                    data = {k: v.value for k, v in fields.items()}

                    # Показываем, что плагин запускается
                    out.content = "⏳ **Выполнение...**"
                    button.set_enabled(False)
                    button.set_text("Выполнение..")
                    await asyncio.sleep(0.1)

                    try:
                        result = p.run(data)
                        if inspect.isawaitable(result):
                            result = await result

                        out.content = result if isinstance(result, str) else str(result)
                    except Exception as e:
                        out.content = f"❌ Ошибка:\n```\n{e}\n```"
                    finally:
                        button.set_text("▶ Запустить")
                        button.set_enabled(True)


                run_button.on("click", run_plugin)

ui.run(title="TL IDE")
