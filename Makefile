.PHONY: setup test run audit release-check dist verify-dist

setup:
	python3 -m venv .venv
	.venv/bin/pip install --require-hashes -r requirements.lock

test:
	PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
	node --check static/app.js

audit:
	PYTHONPATH=. .venv/bin/python scripts/release_audit.py

release-check: test audit
	.venv/bin/python -m pip check
	bash -n run.sh scripts/setup-python.sh start.sh start.command
	PYTHONPATH=. .venv/bin/python scripts/build_dist.py

run:
	./run.sh

dist:
	PYTHONPATH=. .venv/bin/python scripts/build_dist.py

verify-dist: dist
	PYTHONPATH=. .venv/bin/python scripts/verify_dist.py
