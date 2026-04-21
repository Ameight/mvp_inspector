import requests
from sdk.base_plugin import PluginInterface


class IpCheckerPlugin(PluginInterface):

    def get_display_name(self) -> str:
        return "IP Checker"

    def get_description(self) -> str:
        return "Определяет публичный IP-адрес машины через внешний API."

    def get_category(self) -> str:
        return "General"

    def get_config_schema(self) -> dict:
        return {}

    def run(self, inputs: dict) -> str:
        api_url = self.config.get("api_url", "https://api.ipify.org")

        try:
            response = requests.get(f"{api_url}?format=json", timeout=5)
            response.raise_for_status()
            data = response.json()
            ip = data.get("ip", "неизвестен")
        except requests.exceptions.Timeout:
            return "❌ **Ошибка:** превышено время ожидания (5 сек)"
        except requests.exceptions.ConnectionError:
            return "❌ **Ошибка:** нет подключения к интернету"
        except Exception as e:
            return f"❌ **Ошибка:** {e}"

        return (
            f"## Публичный IP\n\n"
            f"**`{ip}`**\n\n"
            f"---\n"
            f"*Источник: `{api_url}`*"
        )
