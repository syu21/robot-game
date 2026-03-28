SHELL := /bin/zsh

.PHONY: dev db-init install-hooks check-staged-secrets

dev:
	FLASK_APP=app.py FLASK_ENV=development flask run --host 127.0.0.1 --port 5050

db-init:
	python init_db.py

install-hooks:
	git config core.hooksPath .githooks
	chmod +x .githooks/pre-commit

check-staged-secrets:
	python3 check_staged_secrets.py
