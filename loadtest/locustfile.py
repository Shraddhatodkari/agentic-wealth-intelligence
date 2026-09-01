"""
Load test for the Agentic Wealth Intelligence API, using Locust.

No Docker required - Locust is a plain pip package. Run against a local
uvicorn instance (`make api` in one terminal) or a deployed URL.

Usage:
    locust -f loadtest/locustfile.py --host http://localhost:8000

Then open http://localhost:8089 to configure users/spawn-rate and start
the test, or run headless:

    locust -f loadtest/locustfile.py --host http://localhost:8000 \
        --users 20 --spawn-rate 5 --run-time 30s --headless \
        --html loadtest/report.html
"""

import os

from locust import HttpUser, between, task

API_KEY = os.getenv("LOAD_TEST_API_KEY", "dev-local-key")
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


class AnalystUser(HttpUser):
    """Simulates an analyst repeatedly hitting the core read/write endpoints."""

    wait_time = between(0.5, 2)

    @task(3)
    def health_check(self):
        self.client.get("/health")

    @task(5)
    def analyze_filing(self):
        self.client.post(
            "/analyze",
            json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"},
            headers=HEADERS,
            name="/analyze",
        )

    @task(2)
    def compare_years(self):
        self.client.post(
            "/compare",
            json={
                "company": "Nimbus Dynamics, Inc.",
                "prior_fiscal_year": "FY2024",
                "current_fiscal_year": "FY2025",
            },
            headers=HEADERS,
            name="/compare",
        )

    @task(2)
    def list_reports(self):
        self.client.get("/reports", headers=HEADERS, name="/reports")

    @task(1)
    def evaluate(self):
        self.client.get("/evaluate", headers=HEADERS, name="/evaluate")

    @task(1)
    def metrics(self):
        self.client.get("/metrics", name="/metrics")
