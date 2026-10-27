ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

.PHONY: run test ci lint db_run migrate seed shell clean-venv \
        check-coverage-floor-ratchet print-cov-min check-migrations

LOG_DIR  ?= /tmp/foosball_logs
LOG_FILE ?= $(LOG_DIR)/foosball.log
HOST     ?= $(shell python3 -c "import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2>/dev/null || echo 127.0.0.1)
PORT     ?= 8000

# Minimum total coverage, enforced by `make ci` locally and in GitHub Actions.
# The value itself lives in coverage-floor.txt (one tracked file, bare number,
# `#` comments allowed) so that it can be ratcheted: the floor may only ever go
# UP, which scripts/check_coverage_floor_ratchet.py enforces against the base
# commit.  Keep this parse in sync with parse_floor() in that script —
# `make print-cov-min` prints what the Makefile sees.
COVERAGE_FLOOR_FILE := $(ROOT_DIR)/coverage-floor.txt
COV_MIN := $(shell sed -e 's/#.*//' -e 's/[[:space:]]//g' -e '/^$$/d' $(COVERAGE_FLOOR_FILE) | head -n 1)

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

lint:
	ruff check .

# Fails if coverage-floor.txt is lower than on the base commit (PR merge-base /
# HEAD~1 on a push / origin/main locally).  Skips with a log message when no
# comparison point exists — see scripts/check_coverage_floor_ratchet.py.
check-coverage-floor-ratchet:
	python3 scripts/check_coverage_floor_ratchet.py

# What COV_MIN resolved to, for debugging the floor file parse.
print-cov-min:
	@echo $(COV_MIN)

# The single entry point used by both humans and GitHub Actions
# (.github/workflows/ci.yml calls exactly `make ci` — no duplicated logic).
# The playwright-based frontend smoke tests skip themselves when playwright
# is absent, so this needs no browser download.
ci: check-coverage-floor-ratchet
	ruff check .
	pytest league_app/tests -q \
		--cov=league_app \
		--cov-report=term-missing \
		--cov-fail-under=$(COV_MIN)

db_run:
	sqlite3 sql_app.db

seed:
	python3 scripts/seed.py

seed-reset:
	python3 scripts/seed.py --reset

migrate:
	alembic upgrade head

# Drift guard: `alembic upgrade head` on an empty DB must produce exactly the
# schema the models describe.  Part of `make ci` (it is a normal test); this
# target runs it alone, e.g. after adding a model field.
check-migrations:
	pytest league_app/tests/test_schema_source_of_truth.py -v


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
