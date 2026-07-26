# chiliAI — Development Makefile
# ============================================================

COMPOSE_DEV  = docker compose -f docker-compose.dev.yaml
COMPOSE_PROD = docker compose

.PHONY: dev dev-domain down build logs clean prod prod-down api-shell migrate test test-e2e help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ---------- Development ----------

dev: ## Start dev stack (hot-reload)
	$(COMPOSE_DEV) up --build

# Domain packs live in backend/config/defaults/<name>.yaml. The compose files
# parameterize CHILI_CONFIG_PATH (defaulting to the medicare exemplar), so a
# single env var retargets both api and worker. See backend/config/README.md.
dev-domain: ## Start dev stack under a named domain pack (make dev-domain DOMAIN=food_supply_chain)
ifndef DOMAIN
	$(error DOMAIN is required, e.g. make dev-domain DOMAIN=food_supply_chain)
endif
	@test -f backend/config/defaults/$(DOMAIN).yaml || \
		{ echo "Unknown domain pack '$(DOMAIN)' — expected backend/config/defaults/$(DOMAIN).yaml"; exit 1; }
	CHILI_CONFIG_PATH=/app/config/defaults/$(DOMAIN).yaml $(COMPOSE_DEV) up --build

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

# BL-042 / database.04: replay all migrations on a scratch database
# (chili_migration_check) on the compose postgres service and diff the schema
# against backend/database/migrations/snapshots/head.sql. Never touches the
# dev 'chili' database. Regenerate the snapshot in every migration PR.
.PHONY: migrate-check migrate-snapshot
migrate-check: ## Replay migrations on a scratch TimescaleDB and diff schema vs committed snapshot
	scripts/ci_migration_check.sh

migrate-snapshot: ## Regenerate backend/database/migrations/snapshots/head.sql (run after adding a migration)
	scripts/ci_migration_check.sh --update-snapshot

# The dev image ships runtime deps only (no pytest) since the 2026-05-15 slim,
# so the suite runs via the host venv — explicitly against chili_test: the
# migration tests downgrade/upgrade DATABASE_URL's database, and the dev
# `chili` DB must never be that target.
test: ## Run backend tests via the host venv (against chili_test, never the dev DB)
	cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest --cov

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

.PHONY: demo-cms
demo-cms: ## Full CMS fraud demo bring-up: pack switch + TN 1% staging + ingest + readiness probes (stack must be running: make dev; analytics fire natively — analytics.34)
	scripts/demo_cms.sh

# Requires the stack running with the Air Force housing pack, e.g.
# `make dev-domain DOMAIN=department_air_force_housing`. Uploads the tracked
# housing feed fixtures through the real records API. Extra args pass through:
# `make seed-housing SEED_ARGS="--scorecards"`.
.PHONY: seed-housing
seed-housing: ## Seed the Air Force housing demo KB via the running API (SEED_ARGS="--scorecards")
	PYTHONPATH=backend backend/.venv/bin/python -m tools.seed_housing_demo $(SEED_ARGS)
