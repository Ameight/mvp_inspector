# TL IDE Marketplace

Шаблон для создания собственного маркетплейса плагинов [TL IDE](https://github.com/Ameight/mvp_inspector).

## Быстрый старт

```bash
git clone https://github.com/your-org/your-marketplace
cd your-marketplace
python init_marketplace.py
```

Скрипт спросит тип хостинга, определит платформу по URL репозитория и создаст конфиги. Затем:

```bash
python publish.py   # сгенерировать registry.json
# закоммить registry.json и запушить в репозиторий
```

## Типы хостинга

### Git-репозиторий (GitHub, GitLab, Bitbucket, Gitea…)

Плагины хранятся прямо в репозитории. `publish.py` генерирует `registry.json`, который коммитится вместе с плагинами. `init_marketplace.py` автоматически определяет платформу по URL и генерирует правильный raw-URL.

```
your-repo/
├── registry.json          ← генерируется publish.py, коммитить
├── plugins/
│   └── general/
│       └── my_plugin/
│           ├── plugin.py
│           └── plugin.meta.yaml
├── publish.py
├── publish.yaml
└── ...
```

#### URL для TL IDE по платформам

| Платформа | Формат URL registry.json |
|---|---|
| GitHub | `https://raw.githubusercontent.com/<owner>/<repo>/<branch>/registry.json` |
| GitLab | `https://gitlab.com/<owner>/<repo>/-/raw/<branch>/registry.json` |
| Self-hosted GitLab | `https://gitlab.company.com/<owner>/<repo>/-/raw/<branch>/registry.json` |
| Gitea / Forgejo | `https://gitea.company.com/<owner>/<repo>/raw/branch/<branch>/registry.json` |
| Bitbucket | `https://bitbucket.org/<owner>/<repo>/raw/<branch>/registry.json` |

#### publish.yaml по платформам

**GitHub:**
```yaml
base_url: https://raw.githubusercontent.com/<owner>/<repo>/<branch>/plugins
plugins_dir: ./plugins
output: ./registry.json
```

**GitLab (cloud или self-hosted):**
```yaml
base_url: https://gitlab.com/<owner>/<repo>/-/raw/<branch>/plugins
plugins_dir: ./plugins
output: ./registry.json
```

**Gitea / Forgejo:**
```yaml
base_url: https://gitea.company.com/<owner>/<repo>/raw/branch/<branch>/plugins
plugins_dir: ./plugins
output: ./registry.json
```

### Приватный сервер

Плагины отдаются через `marketplace_server.py` с проверкой API-ключа.

```bash
python marketplace_server.py
```

URL для TL IDE: `http://<host>:<port>/registry.json`, API Key из `marketplace_server.yaml`.

## Добавить плагин

1. Создай файл `plugins/<category>/<name>/plugin.py`:

```python
from sdk.base_plugin import PluginInterface

class MyPlugin(PluginInterface):

    def get_display_name(self) -> str:
        return "My Plugin"

    def get_description(self) -> str:
        return "Краткое описание."

    def get_category(self) -> str:
        return "General"

    def get_config_schema(self) -> dict:
        return {
            "query": {"label": "Запрос", "type": "string", "default": ""},
        }

    def run(self, inputs: dict) -> str:
        return f"Результат: {inputs.get('query')}"
```

2. Рядом создай `plugin.meta.yaml`:

```yaml
version: "1.0.0"
author: "Имя Автора"
requires: []              # pip-пакеты: [requests, pyyaml]
# min_app_version: "0.3.0"
```

3. Обнови реестр:

```bash
python publish.py
```

## Структура `get_config_schema`

| `type`           | Виджет в UI              |
|------------------|--------------------------|
| `string`         | Однострочный ввод        |
| `textarea`       | Многострочный ввод       |
| `int`            | Числовой ввод            |
| `bool`           | Чекбокс                  |
| `select_or_input`| Выпадающий список + ввод |

## Переменные окружения (секреты)

Если плагин требует токен — объяви это через `get_required_env()`:

```python
def get_required_env(self) -> dict:
    return {
        "MY_TOKEN": {
            "label": "API Token",
            "description": "Токен из настроек сервиса",
            "secret": True,
        }
    }
```

TL IDE покажет предупреждение и предложит ввести значение прямо в UI. В плагине читай через `os.getenv("MY_TOKEN")`.

## publish.yaml

```yaml
base_url: <raw-URL папки plugins в репозитории>
plugins_dir: ./plugins
output: ./registry.json
```

Переопределить `base_url` из командной строки:

```bash
python publish.py --base-url https://gitlab.com/org/repo/-/raw/master/plugins
```

## Подключить в TL IDE

**Настройки → Маркетплейсы → добавить:**
- **Название** — любое
- **URL** — ссылка на `registry.json`
- **API Key** — только для приватного сервера
