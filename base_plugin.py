from abc import ABC, abstractmethod

class PluginInterface(ABC):
    """
    Интерфейс для всех плагинов.
    """

    @abstractmethod
    def run(self, inputs: dict) -> str:
        """
        Основной метод выполнения плагина.

        :param inputs: словарь входных параметров
        :return: словарь с результатом
        """
        pass

    def get_config_schema(self) -> dict:
        """
        Описание полей для ввода — используется для генерации формы в UI.
        """
        return {}

    def get_display_name(self) -> str:
        """
        Название плагина, отображаемое в интерфейсе.
        """
        return self.__class__.__name__

    def is_enabled(self) -> bool:
        """
        Можно отключать плагины логически.
        """
        return True
