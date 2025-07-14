# Makefile for Meraki Dashboard Exporter
# Provides common development workflows and Docker BuildKit support

# Variables
DOCKER_IMAGE_NAME := meraki-dashboard-exporter
DOCKER_REGISTRY := ghcr.io/rknightion
PYTHON_VERSION := 3.13
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

.PHONY: version-bump-patch
version-bump-patch: ## Bump patch version (0.0.X)
	@echo "$(BLUE)Bumping patch version...$(NC)"
	@NEW_VERSION=$$(echo $(VERSION) | awk -F. '{$$NF = $$NF + 1;} 1' | sed 's/ /./g') && \
	sed -i.bak "s/^version = \".*\"/version = \"$$NEW_VERSION\"/" pyproject.toml && \
	rm pyproject.toml.bak && \
	echo "$(GREEN)Version bumped from $(VERSION) to $$NEW_VERSION$(NC)"

.PHONY: version-bump-minor
version-bump-minor: ## Bump minor version (0.X.0)
	@echo "$(BLUE)Bumping minor version...$(NC)"
	@NEW_VERSION=$$(echo $(VERSION) | awk -F. '{$$2 = $$2 + 1; $$3 = 0;} 1' | sed 's/ /./g') && \
	sed -i.bak "s/^version = \".*\"/version = \"$$NEW_VERSION\"/" pyproject.toml && \
	rm pyproject.toml.bak && \
	echo "$(GREEN)Version bumped from $(VERSION) to $$NEW_VERSION$(NC)"

.PHONY: version-bump-major
version-bump-major: ## Bump major version (X.0.0)
	@echo "$(BLUE)Bumping major version...$(NC)"
	@NEW_VERSION=$$(echo $(VERSION) | awk -F. '{$$1 = $$1 + 1; $$2 = 0; $$3 = 0;} 1' | sed 's/ /./g') && \
	sed -i.bak "s/^version = \".*\"/version = \"$$NEW_VERSION\"/" pyproject.toml && \
	rm pyproject.toml.bak && \
	echo "$(GREEN)Version bumped from $(VERSION) to $$NEW_VERSION$(NC)"

.PHONY: version-set
version-set: ## Set version explicitly (use VERSION=x.y.z)
	@if [ -z "$(NEW_VERSION)" ]; then \
		echo "$(RED)ERROR: Please specify NEW_VERSION=x.y.z$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Setting version to $(NEW_VERSION)...$(NC)"
	@sed -i.bak "s/^version = \".*\"/version = \"$(NEW_VERSION)\"/" pyproject.toml && \
	rm pyproject.toml.bak && \
	echo "$(GREEN)Version set to $(NEW_VERSION)$(NC)"

# Release Management
.PHONY: release-prepare
release-prepare: ## Prepare release (run checks)
	@echo "$(BLUE)Preparing release...$(NC)"
	@make check
	@echo "$(GREEN)All checks passed!$(NC)"

.PHONY: release-patch
release-patch: release-prepare ## Create patch release (0.0.X)
	@make version-bump-patch
	@make _release-finalize

.PHONY: release-minor
release-minor: release-prepare ## Create minor release (0.X.0)
	@make version-bump-minor
	@make _release-finalize

.PHONY: release-major
release-major: release-prepare ## Create major release (X.0.0)
	@make version-bump-major
	@make _release-finalize

.PHONY: _release-finalize
_release-finalize: ## Internal: Finalize release after version bump
	@echo "$(BLUE)Updating lock file with new version...$(NC)"
	@uv lock
	@make _release-create

.PHONY: _release-create
_release-create: ## Internal: Create release after version bump
	@NEW_VERSION=$$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml) && \
	echo "$(BLUE)Creating release for version $$NEW_VERSION...$(NC)" && \
	echo "$(BLUE)Staging all changes...$(NC)" && \
	git add pyproject.toml uv.lock && \
	if [ -z "$$(git diff --cached --name-only)" ]; then \
		echo "$(RED)No changes to commit. Did the version bump fail?$(NC)"; \
		exit 1; \
	fi && \
	echo "$(BLUE)Files to be committed:$(NC)" && \
	git diff --cached --name-only && \
	echo "$(BLUE)Committing version bump...$(NC)" && \
	git commit -m "chore: bump version to $$NEW_VERSION" && \
	echo "$(BLUE)Creating git tag v$$NEW_VERSION...$(NC)" && \
	git tag -a "v$$NEW_VERSION" -m "Release version $$NEW_VERSION" && \
	echo "$(YELLOW)Ready to push. Review the changes:$(NC)" && \
	git log --oneline -n 5 && \
	echo "" && \
	echo "$(YELLOW)Push to GitHub and create release? [y/N]$(NC)" && \
	read -r REPLY; \
	if [ "$$REPLY" = "y" ] || [ "$$REPLY" = "Y" ]; then \
		echo "$(BLUE)Pushing to GitHub...$(NC)" && \
		git push origin main && \
		git push origin "v$$NEW_VERSION" && \
		echo "$(BLUE)Creating GitHub release...$(NC)" && \
		if command -v gh >/dev/null 2>&1; then \
			gh release create "v$$NEW_VERSION" \
				--title "Release v$$NEW_VERSION" \
				--generate-notes \
				--latest && \
			echo "$(GREEN)Release v$$NEW_VERSION created successfully!$(NC)" && \
			echo "$(BLUE)GitHub Actions will now:$(NC)" && \
			echo "  - Build and publish to PyPI" && \
			echo "  - Build and push Docker images" && \
			echo "" && \
			echo "$(BLUE)View release at: https://github.com/$(GITHUB_REPO)/releases/tag/v$$NEW_VERSION$(NC)"; \
		else \
			echo "$(YELLOW)GitHub CLI not found. Please create the release manually at:$(NC)" && \
			echo "https://github.com/$(GITHUB_REPO)/releases/new?tag=v$$NEW_VERSION"; \
		fi \
	else \
		echo "$(RED)Push cancelled. Changes are committed locally.$(NC)" && \
		echo "$(YELLOW)To push later, run:$(NC)" && \
		echo "  git push origin main" && \
		echo "  git push origin v$$NEW_VERSION"; \
	fi

# Release
.PHONY: build
build: ## Build Python package with uv
	@echo "$(BLUE)Building Python package...$(NC)"
	uv build

.PHONY: release-test
release-test: build ## Test release to TestPyPI (requires auth)
	@echo "$(BLUE)Testing release to TestPyPI...$(NC)"
	uv publish --publish-url https://test.pypi.org/legacy/

.PHONY: release-manual
release-manual: check build ## Manual release to PyPI (requires auth)
	@echo "$(YELLOW)Are you sure you want to release version $(VERSION) to PyPI? [y/N]$(NC)"
	@read -r REPLY; \
	if [ "$$REPLY" = "y" ] || [ "$$REPLY" = "Y" ]; then \
		echo "$(BLUE)Releasing to PyPI...$(NC)"; \
		uv publish; \
	else \
		echo "$(RED)Release cancelled.$(NC)"; \
	fi

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
