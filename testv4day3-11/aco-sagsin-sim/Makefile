.PHONY: seed up down rebuild fmt lint test

seed:
	docker compose run --rm controller python -m src.data.seed

up:
	docker compose up --build --scale node=$${NODES:-50}

down:
	docker compose down -v

rebuild:
	docker compose build --no-cache

fmt:
	docker compose run --rm controller bash -lc "ruff check --fix . && black ."

lint:
	docker compose run --rm controller bash -lc "ruff check . && mypy src"

test:
	docker compose run --rm controller pytest -q

stop-containers:
	./scripts/stop-containers.sh
