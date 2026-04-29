.PHONY: up down bootstrap run-ingestion

up:
	docker compose up -d

down:
	docker compose down

bootstrap:
	python scripts/bootstrap_topics.py

run-ingestion:
	PYTHONPATH=. python -m src.apps.run_ingestion
