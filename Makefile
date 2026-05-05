PYTHON ?= python
DOCKER_COMPOSE ?= docker compose

.PHONY: db-up db-down db-init db-reset db-logs

db-up:
	$(DOCKER_COMPOSE) up -d postgres

db-down:
	$(DOCKER_COMPOSE) down

db-init:
	$(PYTHON) backend/init_db.py

db-reset:
	$(DOCKER_COMPOSE) down -v
	$(DOCKER_COMPOSE) up -d postgres
	$(PYTHON) backend/init_db.py

db-logs:
	$(DOCKER_COMPOSE) logs -f postgres
