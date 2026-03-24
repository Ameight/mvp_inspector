.DEFAULT_GOAL := help

ifeq ($(OS),Windows_NT)
	VENV_PIP = .venv/Scripts/pip
	VENV_PYTHON = .venv/Scripts/python
else
	VENV_PIP = .venv/bin/pip
	VENV_PYTHON = .venv/bin/python
endif

.PHONY: help install run plugin

help:
	@echo "Использование:"
	@echo "  make install              Создать venv и установить зависимости"
	@echo "  make run                  Запустить приложение"
	@echo "  make plugin name=<name>   Создать плагин (категория опциональна: category=<cat>)"

install:
	python -m venv .venv
	$(VENV_PIP) install -r requirements.txt

run:
	$(VENV_PYTHON) main.py

plugin:
	@if [ -z "$(name)" ]; then echo "❌ Укажи имя: make plugin name=my_plugin [category=devops]"; exit 1; fi
	$(VENV_PYTHON) create_plugin.py $(name) $(category)
