.DEFAULT_GOAL := help

ifeq ($(OS),Windows_NT)
	VENV_PIP = .venv/Scripts/pip
	VENV_PYTHON = .venv/Scripts/python
else
	VENV_PIP = .venv/bin/pip
	VENV_PYTHON = .venv/bin/python
endif

SERVICE_NAME = tl-ide
USER_SYSTEMD_DIR = $(HOME)/.config/systemd/user

.PHONY: help install update run plugin \
        install-service uninstall-service \
        service-start service-stop service-status service-logs

help:
	@echo "Использование:"
	@echo ""
	@echo "  Разработка:"
	@echo "  make install              Создать venv и установить зависимости"
	@echo "  make update               Обновить код и зависимости (dev-режим, ветка master)"
	@echo "  make run                  Запустить приложение напрямую"
	@echo "  make plugin name=<name>   Создать плагин [category=<cat>]"
	@echo ""
	@echo "  systemd (Linux):"
	@echo "  make install-service      Установить и запустить как systemd user-сервис"
	@echo "  make uninstall-service    Остановить и удалить сервис"
	@echo "  make service-start        Запустить сервис"
	@echo "  make service-stop         Остановить сервис"
	@echo "  make service-status       Статус сервиса"
	@echo "  make service-logs         Следить за логами (journalctl -f)"

# --- Разработка ---

install:
	python -m venv .venv
	$(VENV_PIP) install -r requirements.txt

update:
	git pull origin master
	$(VENV_PIP) install -r requirements.txt

run:
	$(VENV_PYTHON) main.py

plugin:
	@if [ -z "$(name)" ]; then echo "❌ Укажи имя: make plugin name=my_plugin [category=devops]"; exit 1; fi
	$(VENV_PYTHON) create_plugin.py $(name) $(category)

# --- systemd ---

install-service:
	@APP_DIR=$$(pwd); \
	VENV_PY=$$APP_DIR/$(VENV_PYTHON); \
	MAIN=$$APP_DIR/main.py; \
	mkdir -p $(USER_SYSTEMD_DIR); \
	sed -e "s|VENV_PYTHON|$$VENV_PY|g" \
	    -e "s|MAIN_PY|$$MAIN|g" \
	    -e "s|APP_DIR|$$APP_DIR|g" \
	    tl-ide.service > $(USER_SYSTEMD_DIR)/$(SERVICE_NAME).service; \
	systemctl --user daemon-reload; \
	systemctl --user enable $(SERVICE_NAME); \
	systemctl --user start $(SERVICE_NAME); \
	echo ""; \
	echo "✅ Сервис установлен и запущен"; \
	echo "   Статус : systemctl --user status $(SERVICE_NAME)"; \
	echo "   Логи   : journalctl --user -u $(SERVICE_NAME) -f"; \
	echo "   Стоп   : make service-stop"

uninstall-service:
	-systemctl --user stop $(SERVICE_NAME)
	-systemctl --user disable $(SERVICE_NAME)
	rm -f $(USER_SYSTEMD_DIR)/$(SERVICE_NAME).service
	systemctl --user daemon-reload
	@echo "✅ Сервис удалён"

service-start:
	systemctl --user start $(SERVICE_NAME)

service-stop:
	systemctl --user stop $(SERVICE_NAME)

service-status:
	systemctl --user status $(SERVICE_NAME)

service-logs:
	journalctl --user -u $(SERVICE_NAME) -f
