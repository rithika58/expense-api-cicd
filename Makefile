.PHONY: help install run test lint cov docker-build docker-run up down logs ps health clean

PY ?= python3
IMAGE ?= expense-api:local
PORT ?= 8000

help:  ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## create .venv and install dev dependencies
	$(PY) -m venv .venv
	./.venv/bin/pip install --upgrade pip
	./.venv/bin/pip install -r requirements-dev.txt

run:  ## run the app locally with gunicorn (reload-free)
	DATABASE_URL=sqlite:///$$PWD/local.db GIT_SHA=$$(git rev-parse --short HEAD 2>/dev/null || echo dev) \
		./.venv/bin/gunicorn -b 0.0.0.0:$(PORT) --reload --workers 2 wsgi:app

test:  ## run the test suite
	./.venv/bin/pytest -q

lint:  ## run flake8
	./.venv/bin/flake8 app tests wsgi.py

cov:  ## tests + coverage report
	./.venv/bin/pytest -q --cov=app --cov-report=term-missing

docker-build:  ## build the multi-stage image
	docker build --build-arg GIT_SHA=$$(git rev-parse --short HEAD 2>/dev/null || echo dev) \
		-t $(IMAGE) .

docker-run:  ## run the image standalone on $(PORT)
	docker run --rm -p $(PORT):8000 -e GIT_SHA=manual $(IMAGE)

up:  ## start app + nginx with docker compose -> http://localhost:8080
	mkdir -p logs logs/nginx
	docker compose up -d --build
	@echo "waiting for the app to report healthy..."
	@docker compose ps
	@echo "  -> http://localhost:8080/health"

down:  ## stop compose and remove volumes
	docker compose down -v

logs:  ## tail compose logs
	docker compose logs -f --tail=100

ps:  ## show container + health status
	docker compose ps

health:  ## hit the health endpoint through nginx
	curl -fsS http://localhost:8080/health | $(PY) -m json.tool

clean:  ## remove local artifacts
	rm -rf .pytest_cache .coverage htmlcov local.db logs __pycache__ \
		app/__pycache__ tests/__pycache__
