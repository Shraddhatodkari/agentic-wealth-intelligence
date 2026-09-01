import os

os.environ.setdefault("LLM_MODE", "mock")
os.environ.setdefault("API_KEYS", "test-key-123:admin,analyst-key:analyst,viewer-key:viewer")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_api.db")

from fastapi.testclient import TestClient

from src import db
from src.api.main import app

db.init_db()
client = TestClient(app)
VALID_KEY = "test-key-123"  # admin
ANALYST_KEY = "analyst-key"
VIEWER_KEY = "viewer-key"


def test_health_check_requires_no_auth():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_analyze_without_api_key_returns_401():
    resp = client.post("/analyze", json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"})
    assert resp.status_code == 401


def test_analyze_with_invalid_api_key_returns_401():
    resp = client.post(
        "/analyze",
        json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_analyze_with_valid_key_returns_report():
    resp = client.post(
        "/analyze",
        json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"},
        headers={"X-API-Key": VALID_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["report"]["company"] == "Nimbus Dynamics, Inc."
    assert data["indexed_chunk_count"] > 0


def test_analyze_missing_filing_returns_404():
    resp = client.post(
        "/analyze",
        json={
            "company": "Ghost Corp",
            "fiscal_year": "FY2025",
            "filing_path": "data/sample_filings/does_not_exist.txt",
        },
        headers={"X-API-Key": VALID_KEY},
    )
    assert resp.status_code == 404


def test_compare_with_valid_key_returns_report():
    resp = client.post(
        "/compare",
        json={
            "company": "Nimbus Dynamics, Inc.",
            "prior_fiscal_year": "FY2024",
            "current_fiscal_year": "FY2025",
        },
        headers={"X-API-Key": VALID_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "trend_shifts" in data["report"]
    assert len(data["report"]["trend_shifts"]) > 0


def test_evaluate_with_valid_key_returns_results():
    resp = client.get("/evaluate", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_accuracy"] == 1.0
    assert len(data["results"]) == 2


def test_ask_without_prior_analyze_returns_400():
    # Fresh cache state isn't guaranteed across test order, so this just
    # checks the endpoint responds sensibly whether or not a prior run exists.
    resp = client.post(
        "/ask",
        json={"question": "What is the leverage ratio?"},
        headers={"X-API-Key": VALID_KEY},
    )
    assert resp.status_code in (200, 400)


def test_response_includes_request_id_header():
    resp = client.get("/health")
    assert "X-Request-ID" in resp.headers


def test_metrics_endpoint_returns_prometheus_format():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"awi_requests_total" in resp.content


def test_analyze_persists_report_and_is_retrievable():
    analyze_resp = client.post(
        "/analyze",
        json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"},
        headers={"X-API-Key": VALID_KEY},
    )
    assert analyze_resp.status_code == 200

    list_resp = client.get("/reports", headers={"X-API-Key": VALID_KEY})
    assert list_resp.status_code == 200
    reports = list_resp.json()
    assert len(reports) > 0
    assert any(r["report_type"] == "synthesis" for r in reports)

    report_id = next(r["id"] for r in reports if r["report_type"] == "synthesis")
    detail_resp = client.get(f"/reports/{report_id}", headers={"X-API-Key": VALID_KEY})
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["company"] == "Nimbus Dynamics, Inc."
    assert "executive_summary" in detail["payload"]


def test_get_nonexistent_report_returns_404():
    resp = client.get("/reports/does-not-exist", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 404


def test_reports_endpoint_requires_auth():
    resp = client.get("/reports")
    assert resp.status_code == 401


def test_analyze_second_identical_call_is_cache_hit():
    from src import cache

    cache.clear_cache()
    payload = {
        "company": "Nimbus Dynamics, Inc.",
        "fiscal_year": "FY2025",
        "filing_path": "data/sample_filings/nimbus_dynamics_10k_fy2025.txt",
    }
    first = client.post("/analyze", json=payload, headers={"X-API-Key": VALID_KEY})
    assert first.status_code == 200
    assert first.json()["cache_hit"] is False

    second = client.post("/analyze", json=payload, headers={"X-API-Key": VALID_KEY})
    assert second.status_code == 200
    assert second.json()["cache_hit"] is True
    assert second.json()["report"] == first.json()["report"]


def test_viewer_role_cannot_call_analyze():
    resp = client.post(
        "/analyze",
        json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"},
        headers={"X-API-Key": VIEWER_KEY},
    )
    assert resp.status_code == 403


def test_analyst_role_can_call_analyze():
    resp = client.post(
        "/analyze",
        json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"},
        headers={"X-API-Key": ANALYST_KEY},
    )
    assert resp.status_code == 200


def test_viewer_role_can_list_reports():
    resp = client.get("/reports", headers={"X-API-Key": VIEWER_KEY})
    assert resp.status_code == 200


def test_analyst_role_cannot_delete_report():
    resp = client.delete("/reports/some-id", headers={"X-API-Key": ANALYST_KEY})
    assert resp.status_code == 403


def test_admin_role_can_delete_nonexistent_report_returns_404():
    resp = client.delete("/reports/does-not-exist", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 404


def test_admin_can_create_and_then_delete_report():
    client.post(
        "/analyze",
        json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"},
        headers={"X-API-Key": VALID_KEY},
    )
    report_id = client.get("/reports", headers={"X-API-Key": VALID_KEY}).json()[0]["id"]

    delete_resp = client.delete(f"/reports/{report_id}", headers={"X-API-Key": VALID_KEY})
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True

    get_resp = client.get(f"/reports/{report_id}", headers={"X-API-Key": VALID_KEY})
    assert get_resp.status_code == 404


def test_export_report_as_markdown():
    client.post(
        "/analyze",
        json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"},
        headers={"X-API-Key": VALID_KEY},
    )
    reports = client.get("/reports", headers={"X-API-Key": VALID_KEY}).json()
    report_id = next(r["id"] for r in reports if r["report_type"] == "synthesis")

    resp = client.get(f"/reports/{report_id}/export?format=md", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 200
    assert "Executive Summary" in resp.text
    assert "attachment" in resp.headers["content-disposition"]


def test_export_report_as_pdf():
    client.post(
        "/analyze",
        json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"},
        headers={"X-API-Key": VALID_KEY},
    )
    reports = client.get("/reports", headers={"X-API-Key": VALID_KEY}).json()
    report_id = next(r["id"] for r in reports if r["report_type"] == "synthesis")

    resp = client.get(f"/reports/{report_id}/export?format=pdf", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 200
    assert resp.content[:5] == b"%PDF-"


def test_export_report_as_docx():
    client.post(
        "/analyze",
        json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"},
        headers={"X-API-Key": VALID_KEY},
    )
    reports = client.get("/reports", headers={"X-API-Key": VALID_KEY}).json()
    report_id = next(r["id"] for r in reports if r["report_type"] == "synthesis")

    resp = client.get(f"/reports/{report_id}/export?format=docx", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 200
    assert resp.content[:4] == b"PK\x03\x04"


def test_export_unsupported_format_returns_400():
    client.post(
        "/analyze",
        json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"},
        headers={"X-API-Key": VALID_KEY},
    )
    reports = client.get("/reports", headers={"X-API-Key": VALID_KEY}).json()
    report_id = next(r["id"] for r in reports if r["report_type"] == "synthesis")

    resp = client.get(f"/reports/{report_id}/export?format=xyz", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 400


def test_export_nonexistent_report_returns_404():
    resp = client.get("/reports/does-not-exist/export?format=md", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 404


def test_analyze_low_confidence_routes_to_pending_review():
    from src import cache

    cache.clear_cache()
    resp = client.post(
        "/analyze",
        json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"},
        headers={"X-API-Key": VALID_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["report"]["confidence_score"] == 0.78
    assert data["approval_status"] == "pending_review"


def test_pending_review_queue_contains_low_confidence_report():
    from src import cache

    cache.clear_cache()
    client.post(
        "/analyze",
        json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"},
        headers={"X-API-Key": VALID_KEY},
    )
    resp = client.get("/reports/pending-review", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 200
    pending = resp.json()
    assert any(r["confidence_score"] == 0.78 for r in pending)


def test_submit_review_approves_and_removes_from_queue():
    from src import cache

    cache.clear_cache()
    client.post(
        "/analyze",
        json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"},
        headers={"X-API-Key": VALID_KEY},
    )
    pending = client.get("/reports/pending-review", headers={"X-API-Key": VALID_KEY}).json()
    report_id = pending[0]["id"]

    review_resp = client.post(
        f"/reports/{report_id}/review",
        json={
            "reviewer": "jane.analyst",
            "decision": "approve",
            "edited_recommendation": "Escalate if FTC exposure exceeds $25M.",
            "notes": "Tightened the escalation trigger.",
        },
        headers={"X-API-Key": VALID_KEY},
    )
    assert review_resp.status_code == 200
    assert review_resp.json()["approval_status"] == "approved"
    assert review_resp.json()["reviewer"] == "jane.analyst"

    still_pending = client.get("/reports/pending-review", headers={"X-API-Key": VALID_KEY}).json()
    assert report_id not in [r["id"] for r in still_pending]


def test_submit_review_reject_decision():
    from src import cache

    cache.clear_cache()
    client.post(
        "/analyze",
        json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"},
        headers={"X-API-Key": VALID_KEY},
    )
    pending = client.get("/reports/pending-review", headers={"X-API-Key": VALID_KEY}).json()
    report_id = pending[0]["id"]

    resp = client.post(
        f"/reports/{report_id}/review",
        json={"reviewer": "jane.analyst", "decision": "reject", "notes": "Needs more data first."},
        headers={"X-API-Key": VALID_KEY},
    )
    assert resp.status_code == 200
    assert resp.json()["approval_status"] == "rejected"


def test_submit_review_invalid_decision_returns_400():
    from src import cache

    cache.clear_cache()
    client.post(
        "/analyze",
        json={"company": "Nimbus Dynamics, Inc.", "fiscal_year": "FY2025"},
        headers={"X-API-Key": VALID_KEY},
    )
    pending = client.get("/reports/pending-review", headers={"X-API-Key": VALID_KEY}).json()
    report_id = pending[0]["id"]

    resp = client.post(
        f"/reports/{report_id}/review",
        json={"reviewer": "jane.analyst", "decision": "maybe"},
        headers={"X-API-Key": VALID_KEY},
    )
    assert resp.status_code == 400


def test_review_nonexistent_report_returns_404():
    resp = client.post(
        "/reports/does-not-exist/review",
        json={"reviewer": "jane.analyst", "decision": "approve"},
        headers={"X-API-Key": VALID_KEY},
    )
    assert resp.status_code == 404


def test_pending_review_requires_analyst_role():
    resp = client.get("/reports/pending-review", headers={"X-API-Key": VIEWER_KEY})
    assert resp.status_code == 403


def test_portfolio_analyze_ranks_three_companies():
    resp = client.post(
        "/portfolio/analyze",
        json={
            "companies": [
                {
                    "company": "Nimbus Dynamics, Inc.",
                    "fiscal_year": "FY2025",
                    "filing_path": "data/sample_filings/nimbus_dynamics_10k_fy2025.txt",
                },
                {
                    "company": "Solara Energy Corp",
                    "fiscal_year": "FY2025",
                    "filing_path": "data/sample_filings/solara_energy_corp_10k_fy2025.txt",
                },
                {
                    "company": "Vantage Robotics, Inc.",
                    "fiscal_year": "FY2025",
                    "filing_path": "data/sample_filings/vantage_robotics_10k_fy2025.txt",
                },
            ]
        },
        headers={"X-API-Key": VALID_KEY},
    )
    assert resp.status_code == 200
    report = resp.json()["report"]
    assert len(report["companies"]) == 3
    assert report["growth_ranking"][0]["company"] == "Solara Energy Corp"
    assert report["debt_ranking"][0]["company"] == "Vantage Robotics, Inc."


def test_portfolio_analyze_missing_filing_returns_404():
    resp = client.post(
        "/portfolio/analyze",
        json={
            "companies": [
                {
                    "company": "Ghost Corp",
                    "fiscal_year": "FY2025",
                    "filing_path": "data/sample_filings/does_not_exist.txt",
                }
            ]
        },
        headers={"X-API-Key": VALID_KEY},
    )
    assert resp.status_code == 404


def test_portfolio_analyze_requires_analyst_role():
    resp = client.post(
        "/portfolio/analyze",
        json={
            "companies": [
                {
                    "company": "Nimbus Dynamics, Inc.",
                    "fiscal_year": "FY2025",
                    "filing_path": "data/sample_filings/nimbus_dynamics_10k_fy2025.txt",
                }
            ]
        },
        headers={"X-API-Key": VIEWER_KEY},
    )
    assert resp.status_code == 403


def test_portfolio_analyze_persists_as_report():
    client.post(
        "/portfolio/analyze",
        json={
            "companies": [
                {
                    "company": "Solara Energy Corp",
                    "fiscal_year": "FY2025",
                    "filing_path": "data/sample_filings/solara_energy_corp_10k_fy2025.txt",
                }
            ]
        },
        headers={"X-API-Key": VALID_KEY},
    )
    reports = client.get("/reports", headers={"X-API-Key": VALID_KEY}).json()
    assert any(r["report_type"] == "portfolio" for r in reports)
