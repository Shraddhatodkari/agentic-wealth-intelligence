"""Validates the Locust load test file is well-formed and its tasks
target real API endpoints - doesn't run an actual load test (that needs
a live server; see loadtest/RESULTS.md for real recorded runs)."""

import ast


def test_locustfile_is_valid_python():
    with open("loadtest/locustfile.py") as f:
        source = f.read()
    ast.parse(source)  # raises SyntaxError if malformed


def test_locustfile_defines_a_user_class():
    with open("loadtest/locustfile.py") as f:
        source = f.read()
    assert "HttpUser" in source
    assert "class AnalystUser" in source


def test_locustfile_tasks_target_real_endpoints():
    # Cross-check against the actual API routes so this can't silently
    # drift to testing endpoints that no longer exist.
    from src.api.main import app

    real_paths = {route.path for route in app.routes if hasattr(route, "path")}

    with open("loadtest/locustfile.py") as f:
        source = f.read()

    for endpoint in ["/health", "/analyze", "/compare", "/reports", "/evaluate", "/metrics"]:
        assert endpoint in source, f"{endpoint} not referenced in locustfile"
        assert endpoint in real_paths, f"{endpoint} is not a real API route"
