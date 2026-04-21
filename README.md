# TL IDE

Плагинируемая утилита для team lead-задач: запускай инструменты для GitLab, GitHub, Jira и любых других сервисов через единый веб-интерфейс.

## Требования

- Python 3.10+
- Git

## Установка

```bash
git clone https://github.com/Ameight/mvp_inspector.git
cd mvp_inspector
make install
```

Или без Make:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Запуск

```bash
make run
# или
python main.py
```

Приложение откроется в браузере по адресу **http://localhost:8080**

## Интерфейс

- **Сайдбар** — список плагинов, сгруппированных по категориям. Иконка 🏪 — плагин из маркетплейса, иконка ⚠ — файл плагина изменён после установки.
- **🛒 Marketplace** — каталог плагинов из подключённых реестров. Установка в один клик.
- **⚙ Настройки** — управление env-переменными, маркетплейсами, редактор `config.yaml`, проверка обновлений.

## Создание плагина

```bash
make plugin name=my_plugin category=devops
# или
python create_plugin.py my_plugin devops
```

Создаётся файл `plugins/devops/my_plugin/plugin.py`. Открой его и реализуй метод `run`.

Структура папок:

```
plugins/
  devops/
    my_plugin/plugin.py
  jira/
    issue_info/plugin.py
    my_tasks/plugin.py
  general/
    ip_checker/plugin.py
```

## Интерфейс плагина

Все плагины наследуют `PluginInterface` из `plugins/base_plugin.py`.

| Метод | Обязателен | Описание |
|---|---|---|
| `run(inputs) -> str` | да | Основная логика. Возвращает строку (поддерживает Markdown) |
| `get_display_name()` | нет | Название в сайдбаре |
| `get_description()` | нет | Описание под заголовком |
| `get_category()` | нет | Категория для группировки (по умолчанию `General`) |
| `get_config_schema()` | нет | Схема полей формы |
| `get_required_env()` | нет | Объявление нужных env-переменных |
| `get_config_key()` | нет | Ключ в `config.yaml → plugins` (по умолчанию snake_case имени класса) |
| `is_enabled()` | нет | `False` — плагин не загружается |

### Типы полей формы

| Тип | Описание |
|---|---|
| `string` | Однострочный ввод |
| `textarea` | Многострочный ввод (код, промпты) |
| `int` | Числовой ввод |
| `bool` | Чекбокс |
| `select_or_input` | Выпадающий список + ручной ввод |

### Пример плагина

```python
import os
from plugins.base_plugin import PluginInterface

class MyPlugin(PluginInterface):

    def get_display_name(self) -> str:
        return "My Tool"

    def get_category(self) -> str:
        return "DevOps"

    def get_required_env(self) -> dict:
        return {
            "MY_TOKEN": {
                "label": "API Token",
                "description": "Токен для доступа к сервису",
                "secret": True,
            }
        }

    def get_config_schema(self) -> dict:
        return {
            "query": {"label": "Запрос", "type": "string", "default": ""},
        }

    def run(self, inputs: dict) -> str:
        token = os.getenv("MY_TOKEN")
        query = inputs.get("query", "")
        # ...
        return f"**Результат:** {query}"
```

Секреты (токены) — в `.env`, читай через `os.getenv("MY_TOKEN")`.  
Конфиг (URL, настройки) — в `config.yaml` → `plugins.<get_config_key()>`, читай через `self.config.get("base_url")`.

## Маркетплейс

Плагины устанавливаются из реестров (JSON-файлов). По умолчанию подключён официальный реестр.  
Дополнительные реестры добавляются в ⚙ Настройки → Маркетплейсы.

## Обновление

При старте приложение проверяет наличие новой версии в фоне. Если доступна — появится уведомление.

Ручное обновление: ⚙ Настройки → Обновления → «Проверить обновления».  
После обновления перезапусти приложение.

> Перед обновлением зафиксируй локальные изменения (`git stash` или `git commit`).

## Структура проекта

```
mvp_inspector/
├── main.py               # точка входа
├── create_plugin.py      # генератор плагинов
├── Makefile
├── requirements.txt
├── VERSION               # текущая версия
├── config.yaml           # конфиг сервисов и плагинов
├── .env                  # секреты (токены) — не коммитить
└── plugins/
    ├── base_plugin.py    # базовый класс
    ├── manifest.json     # реестр установленных плагинов
    └── <категория>/
        └── <плагин>/
            └── plugin.py
```
