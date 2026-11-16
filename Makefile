# Thin wrappers over `uv run`. `make` is not installed on the dev machine; run the
# underlying commands directly if needed.
.PHONY: test lint fmt fetch-% build site all

test:
	uv run pytest

lint:
	uv run ruff check . && uv run ruff format --check .

fmt:
	uv run ruff format . && uv run ruff check --fix .

fetch-%:
	uv run courtdelay fetch $*

build:
	uv run courtdelay build

site:
	@echo "site build not yet implemented (M2)"

all: test build
