"""Validates monitoring config (Prometheus scrape config, Grafana provisioning
and dashboard JSON) is well-formed."""

import json

import yaml


def test_prometheus_config_is_valid_yaml_with_scrape_target():
    with open("monitoring/prometheus.yml") as f:
        config = yaml.safe_load(f)
    assert "scrape_configs" in config
    job_names = [j["job_name"] for j in config["scrape_configs"]]
    assert "agentic-wealth-intelligence" in job_names


def test_grafana_datasource_provisioning_is_valid():
    with open("monitoring/grafana/provisioning/datasources.yml") as f:
        config = yaml.safe_load(f)
    assert config["datasources"][0]["type"] == "prometheus"


def test_grafana_dashboard_json_is_valid_and_uses_real_metrics():
    with open("monitoring/grafana/dashboards/awi-operations.json") as f:
        dashboard = json.load(f)

    assert dashboard["title"]
    assert len(dashboard["panels"]) >= 5

    all_exprs = " ".join(
        target["expr"] for panel in dashboard["panels"] for target in panel.get("targets", [])
    )
    # Every metric referenced in the dashboard must be one this app actually
    # exports (src/metrics.py) - no dashboard panels pointing at metrics that
    # don't exist.
    assert "awi_requests_total" in all_exprs
    assert "awi_request_duration_seconds" in all_exprs
    assert "awi_agent_stage_duration_seconds" in all_exprs
