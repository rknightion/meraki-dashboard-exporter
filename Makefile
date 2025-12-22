# Makefile for Meraki Dashboard Exporter
# Provides common development workflows and Docker BuildKit support

# Variables
DOCKER_IMAGE_NAME := meraki-dashboard-exporter
DOCKER_REGISTRY := ghcr.io/rknightion
PYTHON_VERSION := 3.14
VERSION := $(shell sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml 2>/dev/null || echo "0.0.0")
GITHUB_REPO := $(shell git remote get-url origin 2>/dev/null | sed -E 's|.*github\.com[:/]([^/]+/[^/]+)\.git.*|\1|' || echo "owner/repo")

# Default target
.DEFAULT_GOAL := help

# Enable Docker BuildKit by default
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# Detect OS for platform-specific commands
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    OPEN_CMD := open
else
    OPEN_CMD := xdg-open
endif

# Terminal colors
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[0;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

.PHONY: help
help: ## Show this help message
	@echo "$(BLUE)Meraki Dashboard Exporter - Development Commands$(NC)"
	@echo "================================================"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)Docker BuildKit Tips:$(NC)"
	@echo "  - BuildKit is enabled by default in this Makefile"
	@echo "  - Use 'make docker-build-all' to build for all architectures"
	@echo "  - Use 'make docker-inspect' to see multi-arch manifest"

# Development Setup
.PHONY: install
install: ## Install dependencies using uv
	@echo "$(BLUE)Installing dependencies...$(NC)"
	uv sync

.PHONY: install-dev
install-dev: ## Install development dependencies
	@echo "$(BLUE)Installing development dependencies...$(NC)"
	uv sync --all-extras

# Code Quality
.PHONY: format
format: ## Format code with ruff
	@echo "$(BLUE)Formatting code...$(NC)"
	uv run ruff format .

.PHONY: lint
lint: ## Run linting with ruff
	@echo "$(BLUE)Running linter...$(NC)"
	uv run ruff check .

.PHONY: lint-fix
lint-fix: ## Run linting with fixes
	@echo "$(BLUE)Running linter with fixes...$(NC)"
	uv run ruff check --fix .

.PHONY: typecheck
typecheck: ## Run type checking with mypy
	@echo "$(BLUE)Running type checker...$(NC)"
	uv run mypy .

.PHONY: test
test: ## Run tests with pytest
	@echo "$(BLUE)Running tests...$(NC)"
	uv run pytest -v

.PHONY: test-cov
test-cov: ## Run tests with coverage
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	uv run pytest --cov=meraki_dashboard_exporter --cov-report=html --cov-report=term

.PHONY: coverage-report
coverage-report: test-cov ## Generate and open coverage report
	@echo "$(BLUE)Opening coverage report...$(NC)"
	$(OPEN_CMD) htmlcov/index.html

.PHONY: check
check: lint typecheck test ## Run all checks (lint, typecheck, test)
	@echo "$(GREEN)All checks passed!$(NC)"

# Docker BuildKit Commands
.PHONY: docker-build
docker-build: ## Build Docker image for current architecture
	@echo "$(BLUE)Building Docker image for current architecture...$(NC)"
	docker buildx build \
		--load \
		--tag $(DOCKER_IMAGE_NAME):latest \
		--tag $(DOCKER_IMAGE_NAME):$(VERSION) \
		--build-arg PY_VERSION=$(PYTHON_VERSION) \
		--cache-from type=local,src=/tmp/.buildx-cache \
		--cache-to type=local,dest=/tmp/.buildx-cache,mode=max \
		.

.PHONY: docker-build-all
docker-build-all: ## Build Docker image for all supported architectures
	@echo "$(BLUE)Building Docker image for all architectures...$(NC)"
	@echo "$(YELLOW)Note: This builds but doesn't load (can't load multi-arch locally)$(NC)"
	docker buildx build \
		--platform linux/386,linux/amd64,linux/arm/v5,linux/arm/v7,linux/arm64/v8,linux/ppc64le,linux/s390x \
		--tag $(DOCKER_IMAGE_NAME):latest \
		--tag $(DOCKER_IMAGE_NAME):$(VERSION) \
		--build-arg PY_VERSION=$(PYTHON_VERSION) \
		--cache-from type=local,src=/tmp/.buildx-cache \
		--cache-to type=local,dest=/tmp/.buildx-cache,mode=max \
		.

.PHONY: docker-build-push
docker-build-push: ## Build and push multi-arch image to registry (requires login)
	@echo "$(BLUE)Building and pushing multi-arch image...$(NC)"
	docker buildx build \
		--platform linux/386,linux/amd64,linux/arm/v5,linux/arm/v7,linux/arm64/v8,linux/ppc64le,linux/s390x \
		--push \
		--tag $(DOCKER_REGISTRY)/$(DOCKER_IMAGE_NAME):latest \
		--tag $(DOCKER_REGISTRY)/$(DOCKER_IMAGE_NAME):$(VERSION) \
		--build-arg PY_VERSION=$(PYTHON_VERSION) \
		--cache-from type=local,src=/tmp/.buildx-cache \
		--cache-to type=local,dest=/tmp/.buildx-cache,mode=max \
		.

.PHONY: docker-run
docker-run: docker-build ## Run Docker container locally
	@echo "$(BLUE)Running Docker container...$(NC)"
	docker run --rm -it \
		-p 9099:9099 \
		-e MERAKI_API_KEY=$${MERAKI_API_KEY} \
		-e MERAKI_EXPORTER_LOG_LEVEL=DEBUG \
		$(DOCKER_IMAGE_NAME):latest

.PHONY: docker-shell
docker-shell: docker-build ## Run shell in Docker container
	@echo "$(BLUE)Starting shell in Docker container...$(NC)"
	docker run --rm -it \
		--entrypoint /bin/sh \
		$(DOCKER_IMAGE_NAME):latest

.PHONY: docker-test
docker-test: docker-build ## Test Docker image build
	@echo "$(BLUE)Testing Docker image...$(NC)"
	docker run --rm $(DOCKER_IMAGE_NAME):latest --help
	@echo "$(GREEN)Docker image test passed!$(NC)"

.PHONY: docker-inspect
docker-inspect: ## Inspect Docker image manifest
	@echo "$(BLUE)Inspecting Docker image...$(NC)"
	docker buildx imagetools inspect $(DOCKER_IMAGE_NAME):latest || echo "$(YELLOW)Image not found. Build it first with 'make docker-build'$(NC)"

.PHONY: docker-compose-up
docker-compose-up: ## Start services with docker-compose
	@echo "$(BLUE)Starting services with docker-compose...$(NC)"
	docker-compose -f docker-compose.dev.yml up --build

.PHONY: docker-compose-down
docker-compose-down: ## Stop services
	@echo "$(BLUE)Stopping services...$(NC)"
	docker-compose -f docker-compose.dev.yml down

# BuildKit Setup
.PHONY: buildkit-setup
buildkit-setup: ## Setup Docker BuildKit builder for multi-arch builds
	@echo "$(BLUE)Setting up Docker BuildKit builder...$(NC)"
	docker buildx create --name multiarch-builder --driver docker-container --use || true
	docker buildx inspect --bootstrap
	@echo "$(GREEN)BuildKit builder ready!$(NC)"

.PHONY: buildkit-info
buildkit-info: ## Show BuildKit builder information
	@echo "$(BLUE)BuildKit Builder Information:$(NC)"
	docker buildx ls
	@echo ""
	@echo "$(BLUE)Current Builder:$(NC)"
	docker buildx inspect

# Version Management
.PHONY: version
version: ## Show current version
	@echo "$(BLUE)Current version: $(GREEN)$(VERSION)$(NC)"

# Build
.PHONY: build
build: ## Build Python package with uv
	@echo "$(BLUE)Building Python package...$(NC)"
	uv build

# Documentation
.PHONY: docgen
docgen: ## Generate all documentation (metrics and configuration)
	@echo "$(BLUE)Generating documentation...$(NC)"
	./scripts/generate-docs.sh

.PHONY: docs-metrics
docs-metrics: ## Generate metrics documentation only
	@echo "$(BLUE)Generating metrics documentation...$(NC)"
	uv run python scripts/generate_metrics_docs.py

.PHONY: docs-config
docs-config: ## Generate configuration documentation only
	@echo "$(BLUE)Generating configuration documentation...$(NC)"
	uv run python scripts/generate_config_docs.py

.PHONY: docs-collectors
docs-collectors: ## Generate collector documentation only
	@echo "$(BLUE)Generating collector documentation...$(NC)"
	uv run python scripts/generate_collector_docs.py

.PHONY: docs-endpoints
docs-endpoints: ## Generate HTTP endpoints documentation only
	@echo "$(BLUE)Generating endpoint documentation...$(NC)"
	uv run python scripts/generate_endpoints_docs.py

# Development Server
.PHONY: run
run: ## Run the exporter locally
	@echo "$(BLUE)Starting exporter...$(NC)"
	uv run python -m meraki_dashboard_exporter

.PHONY: run-dev
run-dev: ## Run with auto-reload for development
	@echo "$(BLUE)Starting exporter in development mode...$(NC)"
	uv run uvicorn meraki_dashboard_exporter.app:create_app --factory --reload --host 0.0.0.0 --port 9099

# Cleaning
.PHONY: clean
clean: ## Clean build artifacts
	@echo "$(BLUE)Cleaning build artifacts...$(NC)"
	rm -rf build/ dist/ *.egg-info .coverage htmlcov/ .pytest_cache/ .ruff_cache/ .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

.PHONY: clean-docker
clean-docker: ## Clean Docker build cache
	@echo "$(BLUE)Cleaning Docker build cache...$(NC)"
	docker buildx prune -f
	rm -rf /tmp/.buildx-cache

# Git Hooks
.PHONY: pre-commit
pre-commit: format lint typecheck ## Run pre-commit checks
	@echo "$(GREEN)Pre-commit checks passed!$(NC)"

.PHONY: install-hooks
install-hooks: ## Install git pre-commit hook
	@echo "$(BLUE)Installing git hooks...$(NC)"
	@echo '#!/bin/sh\nmake pre-commit' > .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "$(GREEN)Git hooks installed!$(NC)"

# Utilities
.PHONY: tree
tree: ## Show project structure
	@command -v tree >/dev/null 2>&1 && tree -I '__pycache__|*.egg-info|.git|.ruff_cache|.mypy_cache|htmlcov|.pytest_cache|dist|build' || echo "$(YELLOW)tree command not found$(NC)"

.PHONY: todo
todo: ## Show TODO items in code
	@echo "$(BLUE)TODO items in code:$(NC)"
	@grep -r "TODO\|FIXME\|XXX" --include="*.py" src/ || echo "$(GREEN)No TODO items found!$(NC)"

.PHONY: metrics
metrics: docker-run ## Run exporter and open metrics endpoint
	@echo "$(BLUE)Opening metrics endpoint...$(NC)"
	@sleep 3
	$(OPEN_CMD) http://localhost:9099/metrics

# Dependencies
.PHONY: deps-update
deps-update: ## Update dependencies
	@echo "$(BLUE)Updating dependencies...$(NC)"
	uv lock --upgrade

.PHONY: deps-show
deps-show: ## Show dependency tree
	@echo "$(BLUE)Dependency tree:$(NC)"
	uv tree

.PHONY: deps-outdated
deps-outdated: ## Show outdated dependencies
	@echo "$(BLUE)Checking for outdated dependencies...$(NC)"
	uv pip list --outdated
