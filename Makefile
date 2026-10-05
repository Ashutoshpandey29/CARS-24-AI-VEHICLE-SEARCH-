PY ?= .venv/bin/python
PORT ?= 8000

.PHONY: install seed run test bench docker

install:
	python3 -m venv .venv
	$(PY) -m pip install -r requirements-dev.txt

seed:
	$(PY) scripts/seed.py $(or $(N),600)

run:
	$(PY) -m uvicorn app.main:app --reload --port $(PORT) $(if $(wildcard .env),--env-file .env)

test:
	$(PY) -m pytest -q

bench:
	$(PY) scripts/benchmark.py --count $(or $(N),1000000)

docker:
	docker build -t cars24-vehicle-search .
	docker run --rm -p $(PORT):8000 --env-file $(if $(wildcard .env),.env,.env.example) cars24-vehicle-search
