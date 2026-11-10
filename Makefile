.PHONY: up down test lint format migrate

up:
	docker compose up --build

down:
	docker compose down

test:
	docker compose run --rm tests

lint:
	ruff check . && ruff format --check .

format:
	ruff check --fix . && ruff format .

migrate:
	alembic upgrade head
