.PHONY: up down logs rebuild ps
up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f web worker

rebuild:
	docker compose build --no-cache && docker compose up -d

ps:
	docker compose ps
