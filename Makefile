SHELL := /bin/zsh

.PHONY: dev db-init

dev:
	FLASK_APP=app.py FLASK_ENV=development flask run --host 127.0.0.1 --port 5050

db-init:
	python init_db.py
