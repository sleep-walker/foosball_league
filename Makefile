ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

.PHONY: run test db_run migrate seed shell clean-venv

LOG_DIR  ?= /tmp/foosball_logs
LOG_FILE ?= $(LOG_DIR)/foosball.log
HOST     ?= $(shell python3 -c "import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2>/dev/null || echo 127.0.0.1)
PORT     ?= 8000

run:
	@mkdir -p $(LOG_DIR)
	@echo "──── Listening on http://$(HOST):$(PORT) ────"
	BASE_URL=http://$(HOST):$(PORT) \
	uvicorn league_app.main:app --reload \
		--reload-dir league_app \
		--reload-dir frontend \
		--host 0.0.0.0 --port $(PORT) \
		2>&1 | tee -a $(LOG_FILE)

test:
	pytest -vv league_app/tests

db_run:
	sqlite3 sql_app.db

seed:
	python3 scripts/seed.py

seed-reset:
	python3 scripts/seed.py --reset

migrate:
	alembic upgrade head


shell:
	bash

requirements.txt: requirements.in
	uv pip compile --output-file=requirements.txt requirements.in

venv: requirements.txt
	uv venv -p python3.13 "$(ROOT_DIR)"/venv
	source venv/bin/activate && uv pip install -r requirements.txt

clean-venv:
	rm -rf "$(ROOT_DIR)"/venv


.PHONY: venv-%
venv-%: venv
	bash -c 'source "$(ROOT_DIR)"/venv/bin/activate; target='$@'; vtarget="$${target#venv-}"; echo "Running \"$$vtarget\" in virtual environment ($(ROOT_DIR)/venv)"; make -C "$(ROOT_DIR)" "$$vtarget"'
