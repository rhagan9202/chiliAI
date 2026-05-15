# chiliAI — Development Makefile
# ============================================================

COMPOSE_DEV  = docker compose -f docker-compose.dev.yaml
COMPOSE_PROD = docker compose

.PHONY: dev down build logs clean prod prod-down api-shell migrate test help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ---------- Development ----------

dev: ## Start dev stack (hot-reload)
	$(COMPOSE_DEV) up --build

down: ## Stop dev stack
	$(COMPOSE_DEV) down

logs: ## Tail logs from dev stack
	$(COMPOSE_DEV) logs -f

build: ## Build all images (dev)
	$(COMPOSE_DEV) build

clean: ## Stop dev stack and remove volumes
	$(COMPOSE_DEV) down -v

api-shell: ## Open a shell in the API container
	$(COMPOSE_DEV) exec api /bin/bash

migrate: ## Run database migrations inside the API container
	$(COMPOSE_DEV) exec api alembic upgrade head

test: ## Run backend tests inside the API container
	$(COMPOSE_DEV) exec api pytest --cov

# ---------- Production ----------

prod: ## Start production stack
	$(COMPOSE_PROD) up --build -d

prod-down: ## Stop production stack
	$(COMPOSE_PROD) down
