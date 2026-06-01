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
