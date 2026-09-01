web: uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
worker: celery -A src.tasks worker --loglevel=info
dashboard: streamlit run app.py --server.port ${DASHBOARD_PORT:-8501} --server.address 0.0.0.0
