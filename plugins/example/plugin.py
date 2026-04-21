from sdk.base_plugin import PluginInterface


class ExamplePlugin(PluginInterface):

    def get_display_name(self) -> str:
        return "Example"

    def get_description(self) -> str:
        return "Демо-плагин, показывает введённый текст обратно."

    def get_category(self) -> str:
        return "General"

    def get_config_schema(self) -> dict:
        return {
            "text": {
                "label": "Текст",
                "type": "textarea",
                "default": "Hello, TL IDE!",
            },
            "env": {
                "label": "Окружение",
                "type": "select_or_input",
                "options": ["prod", "staging", "dev"],
                "default": "dev",
            },
        }

    def run(self, inputs: dict) -> str:
        text = inputs.get("text", "")
        env = inputs.get("env", "")
        return f"**Окружение:** `{env}`\n\n**Текст:**\n```\n{text}\n```"
