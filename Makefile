# chiliAI — Development Makefile
# ============================================================

COMPOSE_DEV  = docker compose -f docker-compose.dev.yaml
COMPOSE_PROD = docker compose

.PHONY: dev down build logs clean prod prod-down api-shell migrate test test-e2e help

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

test-e2e: ## Run Playwright e2e against the full dev stack (real API/worker/services)
	$(COMPOSE_DEV) down -v
	CHILI_DEV_ANONYMOUS_ROLE=analyst $(COMPOSE_DEV) up -d --build
	scripts/wait_for_stack.sh
	cd chili_app && npm run test:e2e
	$(COMPOSE_DEV) down

# ---------- Production ----------

prod: ## Start production stack
	$(COMPOSE_PROD) up --build -d

prod-down: ## Stop production stack
	$(COMPOSE_PROD) down

# ---------- Demo ----------

# Demo build samples claims by default so the ingest is quick. The full TN
# subset is ~4.7M carrier claims (2.4 GB) — a load test, not a demo. Override
# with DEMO_SAMPLE_RATE=1.0 for the complete subset, or use `make tn-subset-full`.
DEMO_SAMPLE_RATE ?= 0.01

.PHONY: demo-tn-subset tn-subset-full data-setup
demo-tn-subset: ## Build a sampled TN subset and upload to the running API (DEMO_SAMPLE_RATE=0.01)
	python3 -m tools.sample_data.build_tennessee_subset \
		--nppes-root sample_data \
		--desynpuf-root sample_data/CMS \
		--output-root sample_data/CMS/tn_subset \
		--sample-rate $(DEMO_SAMPLE_RATE)
	scripts/demo_ingest_tn_subset.sh

tn-subset-full: ## Build the COMPLETE TN subset (no sampling, ~2.4 GB carrier) — slow
	python3 -m tools.sample_data.build_tennessee_subset \
		--nppes-root sample_data \
		--desynpuf-root sample_data/CMS \
		--output-root sample_data/CMS/tn_subset \
		--sample-rate 1.0

data-setup: ## Stage local CMS/NPPES source data into sample_data/ (extracts downloaded zips)
	scripts/setup_local_data.sh
