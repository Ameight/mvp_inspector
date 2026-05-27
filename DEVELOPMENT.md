# TL IDE — Документация для разработчика

---

## Содержание

- [Быстрый старт](#быстрый-старт)
- [Команды Make](#команды-make)
- [Структура проекта](#структура-проекта)
- [Архитектура](#архитектура)
- [Конфигурация в dev-режиме](#конфигурация-в-dev-режиме)
- [Добавление зависимости](#добавление-зависимости)
- [Отладка](#отладка)
- [Workflow выпуска релиза](#workflow-выпуска-релиза)
- [Настройка Homebrew tap](#настройка-homebrew-tap)

---

## Быстрый старт

```bash
git clone https://github.com/Ameight/mvp_inspector.git
cd mvp_inspector
make install   # создаёт .venv и устанавливает зависимости
make run       # запускает приложение
```

Приложение открывается в браузере: **http://localhost:8080**

При первом запуске — wizard выбора папок. Для разработки удобно выбрать `~/.tl-ide/` или задать путь через переменную окружения:

```bash
export TL_IDE_CONFIG=./config.yaml
make run
```

---

## Команды Make

| Команда | Описание |
|---|---|
| `make install` | Создать `.venv` и установить зависимости |
| `make run` | Запустить приложение |
| `make stop` | Остановить приложение (по PID-файлу или порту 8080) |
| `make update` | `git pull origin master` + `pip install -r requirements.txt` |
| `make plugin name=X [category=Y]` | Сгенерировать новый плагин по шаблону |
| `make install-service` | Установить как systemd user-сервис (Linux) |
| `make uninstall-service` | Удалить systemd сервис |
| `make service-start` | Запустить systemd сервис |
| `make service-stop` | Остановить systemd сервис |
| `make service-status` | Статус systemd сервиса |
| `make service-logs` | Логи в реальном времени (journalctl -f) |

---

## Структура проекта

```
mvp_inspector/
├── main.py                  # точка входа — весь UI и логика
├── create_plugin.py         # генератор плагинов по шаблону
├── marketplace_server.py    # сервер для приватного маркетплейса
├── install.sh               # curl-инсталлятор для Linux/macOS
├── Makefile
├── requirements.txt
├── tl-ide.service           # шаблон systemd user-сервиса
├── config.example.yaml      # шаблон конфига
├── config.yaml              # активный конфиг (не коммитить если содержит секреты)
├── .env                     # секреты (токены) — не коммитить
├── sdk/
│   └── base_plugin.py       # базовый класс PluginInterface
├── plugins/                 # папка плагинов (путь настраивается)
│   ├── manifest.json        # реестр установленных плагинов
│   └── <категория>/
│       └── <плагин>/
│           └── plugin.py
└── .github/
    └── workflows/
        └── release.yml      # CI/CD: сборка и публикация релиза
```

---

## Архитектура

Весь UI и логика живут в одном файле — `main.py`. NiceGUI рендерит интерфейс в браузере через WebSocket; сервер — uvicorn.

### Конфигурация

Порядок поиска `config.yaml`:
1. `$TL_IDE_CONFIG` — переменная окружения
2. `~/.tl-ide/config.yaml`
3. `./config.yaml` — dev fallback (рядом с `main.py`)

### Плагины

Загружаются динамически через `importlib` при старте. Каждый плагин — файл `plugin.py` в папке `<plugins_dir>/<категория>/<имя>/`. Базовый класс — `sdk/base_plugin.py`.

### UI-состояние и sentinel-объекты

Вместо роутинга используются константы-сентинели, которые хранятся в `state["plugin"]`:

```python
MARKETPLACE_SENTINEL   # → показывает панель маркетплейса
SETTINGS_SENTINEL      # → показывает панель настроек
LOGS_SENTINEL          # → показывает панель логов
NEW_PLUGIN_SENTINEL    # → показывает инструкцию создания плагина
```

### Перезапуск приложения

- **Под systemd** (определяется по `INVOCATION_ID` env): `nicegui_app.shutdown()` → systemd поднимает сам
- **Без systemd**: запускается независимый процесс-наблюдатель (`start_new_session=True`), который ждёт освобождения порта 8080 и только потом стартует новый процесс

### Manifest

`plugins/manifest.json` хранит метаданные marketplace-плагинов: источник (`marketplace`), версию, SHA-256. Позволяет показывать индикатор «⚠ изменён».

---

## Конфигурация в dev-режиме

```bash
# Изолированная разработка: config рядом с кодом
export TL_IDE_CONFIG=./config.yaml
cp config.example.yaml config.yaml
# Отредактируй config.yaml — добавь plugins_dir, marketplaces и т.д.

make run
```

Секреты (токены) — в `.env` в корне проекта. Файл в `.gitignore`.

---

## Добавление зависимости

```bash
.venv/bin/pip install some-package

# Зафиксировать:
.venv/bin/pip freeze | grep some-package >> requirements.txt
# или вручную добавить строку в requirements.txt
```

---

## Отладка

Логи приложения и плагинов — кнопка 🐛 в шапке сайдбара.

Из кода плагина:
```python
self.log("Сообщение для дебага", level="debug")
```

Если запущен через systemd:
```bash
make service-logs   # journalctl --user -u tl-ide -f
```

---

## Workflow выпуска релиза

### Семантическое версионирование

```
v1.0.1  — hotfix (баг в существующей функции)
v1.1.0  — новая функция (обратно совместима)
v2.0.0  — breaking change (несовместимые изменения)
```

### Создать релиз

```bash
# 1. Убедиться что всё работает на master
git log --oneline v1.2.0..HEAD   # посмотреть что войдёт в релиз

# 2. Создать тег
git tag v1.3.0

# 3. Запушить (через HTTPS если SSH недоступен)
git push https://github.com/Ameight/mvp_inspector.git v1.3.0
```

GitHub Actions автоматически:
- Собирает **source ZIP** (`tl-ide-vX.Y.Z-source.zip`)
- Собирает **бинарные файлы** через PyInstaller для Linux, Windows, macOS
- Создаёт **GitHub Release** со всеми артефактами

> Тег не двигать и не удалять после публикации.  
> Если Actions упал — исправь, удали тег локально и удалённо, пересоздай с тем же номером.

### CI/CD pipeline (`.github/workflows/release.yml`)

```
push tag v* 
  └─▶ source-zip   — копирует нужные файлы, создаёт Release
        └─▶ build-exe (matrix: Linux / Windows / macOS)
              └─▶ PyInstaller --onedir --collect-all nicegui
                    └─▶ zip архив → upload to Release
```

Важно: все `run:` шаги с обратным слешем используют `shell: bash` явно — иначе PowerShell на Windows их не поймёт.

---

## Настройка Homebrew tap

Homebrew tap — это отдельный GitHub-репозиторий с формулой. Для TL IDE его нужно создать один раз.

### 1. Создай репозиторий `homebrew-tl-ide`

Репозиторий **обязательно** должен называться `homebrew-<tap-name>`:
- Зайди на GitHub → New repository → `homebrew-tl-ide`
- Public, без README

### 2. Добавь формулу

Создай файл `Formula/tl-ide.rb`:

```ruby
class TlIde < Formula
  desc "Pluggable web utility for team lead tasks"
  homepage "https://github.com/Ameight/mvp_inspector"
  version "1.2.0"
  license "MIT"

  on_macos do
    url "https://github.com/Ameight/mvp_inspector/releases/download/v#{version}/tl-ide-v#{version}-macOS.zip"
    # sha256 обновляй при каждом релизе:
    # shasum -a 256 tl-ide-v1.2.0-macOS.zip
    sha256 "REPLACE_WITH_ACTUAL_SHA256"
  end

  on_linux do
    url "https://github.com/Ameight/mvp_inspector/releases/download/v#{version}/tl-ide-v#{version}-Linux.zip"
    sha256 "REPLACE_WITH_ACTUAL_SHA256"
  end

  def install
    # Внутри ZIP папка tl-ide/ с исполняемым файлом tl-ide
    libexec.install Dir["tl-ide/*"]
    bin.write_exec_script libexec/"tl-ide"
  end

  test do
    # Простая проверка что бинарник запускается
    assert_predicate bin/"tl-ide", :exist?
  end
end
```

### 3. Получи SHA256 артефактов

```bash
# Скачай ZIP из релиза и вычисли:
curl -LO https://github.com/Ameight/mvp_inspector/releases/download/v1.2.0/tl-ide-v1.2.0-macOS.zip
shasum -a 256 tl-ide-v1.2.0-macOS.zip

curl -LO https://github.com/Ameight/mvp_inspector/releases/download/v1.2.0/tl-ide-v1.2.0-Linux.zip
shasum -a 256 tl-ide-v1.2.0-Linux.zip
```

Подставь результаты в `sha256` полей формулы.

### 4. Обновление при каждом релизе

При выходе нового релиза нужно:
1. Обновить `version "X.Y.Z"` в формуле
2. Обновить оба `sha256`
3. Закоммитить в `homebrew-tl-ide`

Пример автоматизации через GitHub Actions (в репо `homebrew-tl-ide`):

```yaml
name: Update Formula
on:
  repository_dispatch:
    types: [new-release]
jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Update version and sha256
        run: |
          VERSION="${{ github.event.client_payload.version }}"
          MAC_SHA="${{ github.event.client_payload.mac_sha }}"
          LIN_SHA="${{ github.event.client_payload.linux_sha }}"
          sed -i "s/version \".*\"/version \"${VERSION}\"/" Formula/tl-ide.rb
          # обновить sha256 — sed по строкам
      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "Update to $VERSION"
```

### 5. Использование

После публикации формулы:

```bash
brew tap Ameight/tl-ide
brew install tl-ide
brew upgrade tl-ide   # обновить
```
