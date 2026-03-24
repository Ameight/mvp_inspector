from abc import ABC, abstractmethod
import re


class PluginInterface(ABC):
    """
    Базовый интерфейс для всех плагинов TL IDE.

    Жизненный цикл:
        1. __init__()         — создание экземпляра
        2. configure(config)  — передача секции из config.yaml
        3. run(inputs)        — вызов из UI

    Secrets (токены и т.п.) брать через os.getenv(), они уже загружены из .env.
    Не-секретный конфиг (URL, настройки) — через self.config.
    """

    # Заполняется через configure() до первого вызова run()
    config: dict = {}

    def configure(self, config: dict) -> None:
        """
        Вызывается при загрузке приложения.
        Передаёт секцию config.yaml -> plugins -> <get_config_key()>.
        """
        self.config = config

    def get_config_key(self) -> str:
        """
        Ключ в config.yaml -> plugins -> <key>.
        По умолчанию — snake_case имени класса без суффикса Plugin.

        Пример: GitlabCheckerPlugin -> gitlab_checker
        """
        name = type(self).__name__
        if name.endswith("Plugin"):
            name = name[:-6]
        return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()

    @abstractmethod
    def run(self, inputs: dict) -> str:
        """
        Основной метод выполнения плагина.

        :param inputs: значения полей формы
        :return: строка результата (поддерживает markdown)
        """
        pass

    def get_config_schema(self) -> dict:
        """
        Схема полей формы.

        Поддерживаемые типы:
          string         — однострочный ввод
          textarea       — многострочный (для кода/промптов)
          int            — числовой ввод
          bool           — чекбокс
          select_or_input — выпадающий список + ручной ввод

        Пример:
            return {
                "query": {
                    "label": "Запрос",
                    "type": "string",
                    "default": "",
                },
                "env": {
                    "label": "Окружение",
                    "type": "select_or_input",
                    "options": ["prod", "staging", "dev"],
                    "default": "prod",
                },
            }
        """
        return {}

    def get_display_name(self) -> str:
        """Название в сайдбаре."""
        return type(self).__name__

    def get_description(self) -> str:
        """Краткое описание под заголовком плагина."""
        return ""

    def get_category(self) -> str:
        """Категория для группировки в сайдбаре."""
        return "General"

    def is_enabled(self) -> bool:
        """False — плагин не загружается."""
        return True
