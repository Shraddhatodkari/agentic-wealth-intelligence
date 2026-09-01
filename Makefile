.PHONY: install test demo yoy eval app api worker dev loadtest lint format security clean

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/ app.py

format:
	black src/ tests/ app.py

security:
	bandit -r src/

demo:
	python run_demo.py

yoy:
	python run_yoy_comparison.py

eval:
	python run_evaluation.py

app:
	streamlit run app.py

api:
	uvicorn src.api.main:app --reload --port 8000

worker:
	celery -A src.tasks worker --loglevel=info

dev:
	PORT=8000 honcho start -f Procfile

loadtest:
	locust -f loadtest/locustfile.py --host http://localhost:8000

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
