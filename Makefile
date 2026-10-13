.PHONY: run migrate lint lint-fix format format-check test ci

PORT ?= 8000

run:
	python manage.py runserver $(PORT)

migrate:
	python manage.py migrate

lint:
	ruff check .
	ruff format --check .

lint-fix:
	ruff check --fix .
	ruff format .

format:
	ruff format .

format-check:
	ruff format --check .

test:
	DJANGO_SETTINGS_MODULE=config.settings.ci pytest

ci: lint test
