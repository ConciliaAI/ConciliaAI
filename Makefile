.PHONY: up down logs test lint migrate
up:
	docker compose up --build
down:
	docker compose down
logs:
	docker compose logs -f
migrate:
	docker compose exec api alembic upgrade head
test:
	docker compose exec api pytest -q
lint:
	docker compose exec api ruff check .
