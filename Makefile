.PHONY: run migrate lint lint-fix format format-check

PORT ?= 8000

run:
	python manage.py runserver $(PORT)

migrate:
	python manage.py migrate

lint-fix:
	ruff check --fix .
	ruff format .
