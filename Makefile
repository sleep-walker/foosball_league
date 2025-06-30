ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

.PHONY: run test db_run migrate shell clean-venv

run:
	fastapi dev league_app/main.py

test:
	pytest -vv league_app/tests

db_run:
	sqlite3 sql_app.db

migrate:
	alembic upgrade head


shell:
	bash

requirements.txt:
	uv pip compile --output-file=requirements.txt requirements.in

venv: requirements.txt
	uv venv "$(ROOT_DIR)"/venv
	source venv/bin/activate && uv pip install -r requirements.txt

clean-venv:
	rm -rf "$(ROOT_DIR)"/venv


.PHONY: venv-%
venv-%:
	bash -c 'source "$(ROOT_DIR)"/venv/bin/activate; target='$@'; vtarget="$${target#venv-}"; echo "Running \"$$vtarget\" in virtual environment ($(ROOT_DIR)/venv)"; make -C "$(ROOT_DIR)" "$$vtarget"'
