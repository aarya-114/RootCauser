# =============================================================================
# RootCauser — Makefile
# =============================================================================

COMPOSE = docker compose

.PHONY: up down logs status ps

## Start the SigNoz stack in detached mode
up:
	$(COMPOSE) up -d

## Stop and remove all containers (volumes are preserved)
down:
	$(COMPOSE) down

## Tail logs from all services (Ctrl-C to exit)
logs:
	$(COMPOSE) logs -f

## Show health status of every container
status:
	$(COMPOSE) ps

## Alias for status
ps: status
