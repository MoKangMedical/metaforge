"""
Integration tests for MetaForge API endpoints.

Tests all major HTTP endpoints using FastAPI TestClient:
  - /api/health
  - /api/analyze
  - /api/demo
  - /api/bias
  - /api/cumulative
  - /api/forest
  - /api/funnel
  - /api/galbraith
  - /api/labbe
  - /api/nma/demo
  - /api/export/csv
  - /api/export/json
"""

import json
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# ── Shared payload ────────────────────────────────────────────

def _studies_payload():
    """A JSON-serialisable body for /api/analyze and other POST endpoints."""
    return {
        "studies": [
            {"name": "Study A", "e_events": 45, "e_total": 100, "c_events": 30, "c_total": 100},
            {"name": "Study B", "e_events": 60, "e_total": 120, "c_events": 40, "c_total": 110},
            {"name": "Study C", "e_events": 35, "e_total": 90,  "c_events": 25, "c_total": 95},
            {"name": "Study D", "e_events": 80, "e_total": 200, "c_events": 55, "c_total": 190},
            {"name": "Study E", "e_events": 50, "e_total": 110, "c_events": 38, "c_total": 105},
        ],
        "model": "random",
        "effect_measure": "OR",
    }


def _studies_for_bias():
    """Need at least 3 studies for bias tests."""
    return {
        "studies": [
            {"name": "Study A", "e_events": 45, "e_total": 100, "c_events": 30, "c_total": 100},
            {"name": "Study B", "e_events": 60, "e_total": 120, "c_events": 40, "c_total": 110},
            {"name": "Study C", "e_events": 35, "e_total": 90,  "c_events": 25, "c_total": 95},
            {"name": "Study D", "e_events": 80, "e_total": 200, "c_events": 55, "c_total": 190},
            {"name": "Study E", "e_events": 50, "e_total": 110, "c_events": 38, "c_total": 105},
        ],
        "effect_measure": "OR",
    }


# ── /api/health ───────────────────────────────────────────────

class TestHealth:
    def test_health_status_code(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_body(self):
        resp = client.get("/api/health")
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data


# ── /api/analyze ──────────────────────────────────────────────

class TestAnalyze:
    def test_analyze_status_code(self):
        resp = client.post("/api/analyze", json=_studies_payload())
        assert resp.status_code == 200

    def test_analyze_returns_pooled_effect(self):
        resp = client.post("/api/analyze", json=_studies_payload())
        data = resp.json()
        assert "pooled_effect" in data
        assert data["pooled_effect"] > 0

    def test_analyze_returns_heterogeneity(self):
        resp = client.post("/api/analyze", json=_studies_payload())
        data = resp.json()
        assert "i_squared" in data
        assert "tau_squared" in data
        assert "q_statistic" in data

    def test_analyze_returns_studies(self):
        resp = client.post("/api/analyze", json=_studies_payload())
        data = resp.json()
        assert "studies" in data
        assert len(data["studies"]) == 5

    def test_analyze_returns_plots(self):
        resp = client.post("/api/analyze", json=_studies_payload())
        data = resp.json()
        assert "forest_plot_svg" in data
        assert "funnel_plot_svg" in data
        assert "<svg" in data["forest_plot_svg"]

    def test_analyze_fixed_model(self):
        payload = _studies_payload()
        payload["model"] = "fixed"
        resp = client.post("/api/analyze", json=payload)
        assert resp.status_code == 200
        assert resp.json()["model"] == "fixed"

    def test_analyze_rr_measure(self):
        payload = _studies_payload()
        payload["effect_measure"] = "RR"
        resp = client.post("/api/analyze", json=payload)
        assert resp.status_code == 200
        assert resp.json()["effect_measure"] == "RR"

    def test_analyze_too_few_studies(self):
        payload = {"studies": [{"name": "Only", "e_events": 10, "e_total": 50, "c_events": 5, "c_total": 50}]}
        resp = client.post("/api/analyze", json=payload)
        assert resp.status_code == 400


# ── /api/demo ─────────────────────────────────────────────────

class TestDemo:
    def test_demo_status_code(self):
        resp = client.post("/api/demo")
        assert resp.status_code == 200

    def test_demo_returns_analysis(self):
        resp = client.post("/api/demo")
        data = resp.json()
        assert "pooled_effect" in data
        assert data["pooled_effect"] > 0

    def test_demo_has_prisma_svg(self):
        resp = client.post("/api/demo")
        data = resp.json()
        assert "prisma_svg" in data
        assert "<svg" in data["prisma_svg"]

    def test_demo_has_subgroup_results(self):
        resp = client.post("/api/demo")
        data = resp.json()
        assert "subgroup_results" in data

    def test_demo_has_sensitivity_results(self):
        resp = client.post("/api/demo")
        data = resp.json()
        assert "sensitivity_results" in data


# ── /api/bias ─────────────────────────────────────────────────

class TestBias:
    def test_bias_status_code(self):
        resp = client.post("/api/bias", json=_studies_for_bias())
        assert resp.status_code == 200

    def test_bias_returns_egger(self):
        resp = client.post("/api/bias", json=_studies_for_bias())
        data = resp.json()
        assert "egger_test" in data
        assert "intercept" in data["egger_test"]
        assert "p_value" in data["egger_test"]

    def test_bias_returns_begg(self):
        resp = client.post("/api/bias", json=_studies_for_bias())
        data = resp.json()
        assert "begg_test" in data
        assert "tau" in data["begg_test"]

    def test_bias_returns_trim_and_fill(self):
        resp = client.post("/api/bias", json=_studies_for_bias())
        data = resp.json()
        assert "trim_and_fill" in data
        assert "estimated_missing" in data["trim_and_fill"]
        assert "adjusted_effect" in data["trim_and_fill"]

    def test_bias_too_few_studies(self):
        payload = {"studies": [
            {"name": "A", "e_events": 10, "e_total": 50, "c_events": 5, "c_total": 50},
            {"name": "B", "e_events": 15, "e_total": 60, "c_events": 8, "c_total": 55},
        ]}
        resp = client.post("/api/bias", json=payload)
        assert resp.status_code == 400


# ── /api/cumulative ──────────────────────────────────────────

class TestCumulative:
    def test_cumulative_status_code(self):
        resp = client.post("/api/cumulative", json=_studies_payload())
        assert resp.status_code == 200

    def test_cumulative_returns_results(self):
        resp = client.post("/api/cumulative", json=_studies_payload())
        data = resp.json()
        assert "cumulative_results" in data
        assert isinstance(data["cumulative_results"], list)
        assert len(data["cumulative_results"]) > 0

    def test_cumulative_each_step_has_keys(self):
        resp = client.post("/api/cumulative", json=_studies_payload())
        data = resp.json()
        for r in data["cumulative_results"]:
            assert "pooled_effect" in r
            assert "ci_lower" in r
            assert "ci_upper" in r

    def test_cumulative_sort_by_effect(self):
        payload = _studies_payload()
        payload["sort_by"] = "effect"
        resp = client.post("/api/cumulative", json=payload)
        assert resp.status_code == 200


# ── /api/forest ──────────────────────────────────────────────

class TestForest:
    def test_forest_status_code(self):
        resp = client.post("/api/forest", json=_studies_payload())
        assert resp.status_code == 200

    def test_forest_returns_svg(self):
        resp = client.post("/api/forest", json=_studies_payload())
        data = resp.json()
        assert "svg" in data
        assert "<svg" in data["svg"]
        assert "Forest Plot" in data["svg"]

    def test_forest_returns_pooled(self):
        resp = client.post("/api/forest", json=_studies_payload())
        data = resp.json()
        assert "pooled" in data
        assert "effect" in data["pooled"]


# ── /api/funnel ──────────────────────────────────────────────

class TestFunnel:
    def test_funnel_status_code(self):
        resp = client.post("/api/funnel", json=_studies_payload())
        assert resp.status_code == 200

    def test_funnel_returns_svg(self):
        resp = client.post("/api/funnel", json=_studies_payload())
        data = resp.json()
        assert "svg" in data
        assert "<svg" in data["svg"]
        assert "Funnel Plot" in data["svg"]


# ── /api/galbraith ───────────────────────────────────────────

class TestGalbraith:
    def test_galbraith_status_code(self):
        resp = client.post("/api/galbraith", json=_studies_payload())
        assert resp.status_code == 200

    def test_galbraith_returns_svg(self):
        resp = client.post("/api/galbraith", json=_studies_payload())
        data = resp.json()
        assert "svg" in data
        assert "<svg" in data["svg"]
        assert "Galbraith" in data["svg"]

    def test_galbraith_too_few_studies(self):
        payload = {"studies": [
            {"name": "A", "e_events": 10, "e_total": 50, "c_events": 5, "c_total": 50},
        ]}
        resp = client.post("/api/galbraith", json=payload)
        assert resp.status_code == 400


# ── /api/labbe ───────────────────────────────────────────────

class TestLabbe:
    def test_labbe_status_code(self):
        resp = client.post("/api/labbe", json=_studies_payload())
        assert resp.status_code == 200

    def test_labbe_returns_svg(self):
        resp = client.post("/api/labbe", json=_studies_payload())
        data = resp.json()
        assert "svg" in data
        assert "<svg" in data["svg"]

    def test_labbe_too_few_studies(self):
        payload = {"studies": [
            {"name": "A", "e_events": 10, "e_total": 50, "c_events": 5, "c_total": 50},
        ]}
        resp = client.post("/api/labbe", json=payload)
        assert resp.status_code == 400


# ── /api/nma/demo ────────────────────────────────────────────

class TestNMADemo:
    def test_nma_demo_status_code(self):
        resp = client.get("/api/nma/demo")
        assert resp.status_code == 200

    def test_nma_demo_returns_treatments(self):
        resp = client.get("/api/nma/demo")
        data = resp.json()
        assert "treatments" in data
        assert len(data["treatments"]) >= 3

    def test_nma_demo_returns_ranking(self):
        resp = client.get("/api/nma/demo")
        data = resp.json()
        assert "ranking" in data
        assert len(data["ranking"]) >= 3

    def test_nma_demo_returns_svg(self):
        resp = client.get("/api/nma/demo")
        data = resp.json()
        assert "network_svg" in data
        assert "<svg" in data["network_svg"]
        assert "league_svg" in data
        assert "<svg" in data["league_svg"]

    def test_nma_demo_returns_consistency(self):
        resp = client.get("/api/nma/demo")
        data = resp.json()
        assert "consistency" in data
        assert "conclusion" in data["consistency"]


# ── /api/export/csv ──────────────────────────────────────────

class TestExportCSV:
    def test_export_csv_status_code(self):
        resp = client.post("/api/export/csv", json=_studies_payload())
        assert resp.status_code == 200

    def test_export_csv_content_type(self):
        resp = client.post("/api/export/csv", json=_studies_payload())
        assert "text/csv" in resp.headers["content-type"]

    def test_export_csv_has_header(self):
        resp = client.post("/api/export/csv", json=_studies_payload())
        text = resp.text
        assert "Study" in text
        assert "Effect" in text
        assert "CI_Lower" in text

    def test_export_csv_has_pooled_row(self):
        resp = client.post("/api/export/csv", json=_studies_payload())
        text = resp.text
        assert "Pooled" in text

    def test_export_csv_has_heterogeneity(self):
        resp = client.post("/api/export/csv", json=_studies_payload())
        text = resp.text
        assert "I_squared" in text
        assert "Tau_squared" in text

    def test_export_csv_too_few_studies(self):
        payload = {"studies": [{"name": "A", "e_events": 10, "e_total": 50, "c_events": 5, "c_total": 50}]}
        resp = client.post("/api/export/csv", json=payload)
        assert resp.status_code == 400


# ── /api/export/json ─────────────────────────────────────────

class TestExportJSON:
    def test_export_json_status_code(self):
        resp = client.post("/api/export/json", json=_studies_payload())
        assert resp.status_code == 200

    def test_export_json_is_json(self):
        resp = client.post("/api/export/json", json=_studies_payload())
        data = resp.json()
        assert isinstance(data, dict)

    def test_export_json_has_version(self):
        resp = client.post("/api/export/json", json=_studies_payload())
        data = resp.json()
        assert "metaforge_version" in data

    def test_export_json_has_results(self):
        resp = client.post("/api/export/json", json=_studies_payload())
        data = resp.json()
        assert "pooled_effect" in data
        assert "i_squared" in data
        assert "studies" in data

    def test_export_json_has_metadata(self):
        resp = client.post("/api/export/json", json=_studies_payload())
        data = resp.json()
        assert "model" in data
        assert "effect_measure" in data
        assert "exported_at" in data

    def test_export_json_too_few_studies(self):
        payload = {"studies": [{"name": "A", "e_events": 10, "e_total": 50, "c_events": 5, "c_total": 50}]}
        resp = client.post("/api/export/json", json=payload)
        assert resp.status_code == 400
