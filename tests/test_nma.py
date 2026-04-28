"""
Unit tests for NMAEngine (Network Meta-Analysis).

Tests:
  - NMA with 3 treatments
  - NMA with 5 treatments
  - Consistency assessment
  - SUCRA ranking
  - Network diagram SVG generation
  - League table SVG generation
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import NMAEngine


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def engine():
    return NMAEngine()


def _comparisons_3():
    """3 treatments, 3 pairwise comparisons forming a triangle."""
    return [
        {"treatment_a": "DrugA", "treatment_b": "Placebo", "effect": 0.65, "ci_lower": 0.50, "ci_upper": 0.85},
        {"treatment_a": "DrugB", "treatment_b": "Placebo", "effect": 0.72, "ci_lower": 0.55, "ci_upper": 0.94},
        {"treatment_a": "DrugA", "treatment_b": "DrugB",   "effect": 0.90, "ci_lower": 0.70, "ci_upper": 1.16},
    ]


def _comparisons_5():
    """5 treatments, enough comparisons to form a connected network."""
    return [
        {"treatment_a": "A", "treatment_b": "B", "effect": 0.80, "ci_lower": 0.65, "ci_upper": 0.98},
        {"treatment_a": "A", "treatment_b": "C", "effect": 0.70, "ci_lower": 0.55, "ci_upper": 0.89},
        {"treatment_a": "B", "treatment_b": "D", "effect": 0.90, "ci_lower": 0.72, "ci_upper": 1.12},
        {"treatment_a": "C", "treatment_b": "E", "effect": 0.60, "ci_lower": 0.46, "ci_upper": 0.78},
        {"treatment_a": "B", "treatment_b": "C", "effect": 0.85, "ci_lower": 0.68, "ci_upper": 1.06},
        {"treatment_a": "D", "treatment_b": "E", "effect": 0.75, "ci_lower": 0.58, "ci_upper": 0.97},
    ]


# ── NMA with 3 treatments ────────────────────────────────────

class TestNMA3Treatments:
    def test_nma_3_treatments_runs(self, engine):
        result = engine.analyze(_comparisons_3())
        assert "error" not in result

    def test_nma_3_treatment_count(self, engine):
        result = engine.analyze(_comparisons_3())
        assert result["n_treatments"] == 3

    def test_nma_3_comparison_count(self, engine):
        result = engine.analyze(_comparisons_3())
        assert result["n_comparisons"] == 3

    def test_nma_3_treatments_sorted(self, engine):
        result = engine.analyze(_comparisons_3())
        assert result["treatments"] == sorted(result["treatments"])

    def test_nma_3_has_direct_estimates(self, engine):
        result = engine.analyze(_comparisons_3())
        assert len(result["direct_estimates"]) == 3

    def test_nma_3_has_network_estimates(self, engine):
        result = engine.analyze(_comparisons_3())
        assert len(result["network_estimates"]) > 0

    def test_nma_3_direct_effect_positive(self, engine):
        result = engine.analyze(_comparisons_3())
        for est in result["direct_estimates"]:
            assert est["effect"] > 0

    def test_nma_3_network_ci_contains_effect(self, engine):
        result = engine.analyze(_comparisons_3())
        for est in result["network_estimates"]:
            assert est["ci_lower"] <= est["effect"] <= est["ci_upper"]


# ── NMA with 5 treatments ────────────────────────────────────

class TestNMA5Treatments:
    def test_nma_5_treatments_runs(self, engine):
        result = engine.analyze(_comparisons_5())
        assert "error" not in result

    def test_nma_5_treatment_count(self, engine):
        result = engine.analyze(_comparisons_5())
        assert result["n_treatments"] == 5

    def test_nma_5_comparison_count(self, engine):
        result = engine.analyze(_comparisons_5())
        assert result["n_comparisons"] == 6

    def test_nma_5_has_ranking(self, engine):
        result = engine.analyze(_comparisons_5())
        assert len(result["ranking"]) == 5

    def test_nma_5_has_svg_outputs(self, engine):
        result = engine.analyze(_comparisons_5())
        assert "<svg" in result["network_svg"]
        assert "<svg" in result["league_svg"]


# ── NMA error handling ────────────────────────────────────────

class TestNMAErrors:
    def test_nma_too_few_treatments(self, engine):
        """NMA with only 2 treatments should return an error."""
        comps = [
            {"treatment_a": "A", "treatment_b": "B", "effect": 0.8, "ci_lower": 0.6, "ci_upper": 1.0},
        ]
        result = engine.analyze(comps)
        assert "error" in result


# ── Consistency assessment ────────────────────────────────────

class TestConsistency:
    def test_consistency_has_keys(self, engine):
        result = engine.analyze(_comparisons_3())
        consistency = result["consistency"]
        for key in ("loop_comparisons", "n_inconsistency_tests",
                     "overall_chi2", "overall_p_value", "conclusion"):
            assert key in consistency

    def test_consistency_conclusion_valid(self, engine):
        result = engine.analyze(_comparisons_3())
        assert result["consistency"]["conclusion"] in ("consistent", "inconsistent")

    def test_consistency_p_value_range(self, engine):
        result = engine.analyze(_comparisons_3())
        p = result["consistency"]["overall_p_value"]
        assert 0 <= p <= 1

    def test_consistency_5_treatments(self, engine):
        result = engine.analyze(_comparisons_5())
        assert "consistency" in result
        assert isinstance(result["consistency"]["loop_comparisons"], list)


# ── SUCRA ranking ─────────────────────────────────────────────

class TestSUCRA:
    def test_sucra_returns_per_treatment(self, engine):
        result = engine.analyze(_comparisons_3())
        ranking = result["ranking"]
        assert len(ranking) == 3

    def test_sucra_each_has_keys(self, engine):
        result = engine.analyze(_comparisons_3())
        for treatment, info in result["ranking"].items():
            assert "sucra" in info
            assert "rank" in info

    def test_sucra_range(self, engine):
        result = engine.analyze(_comparisons_3())
        for info in result["ranking"].values():
            assert 0 <= info["sucra"] <= 1

    def test_sucra_ranks_are_unique(self, engine):
        result = engine.analyze(_comparisons_5())
        ranks = [info["rank"] for info in result["ranking"].values()]
        assert len(set(ranks)) == len(ranks)

    def test_sucra_rank_range(self, engine):
        result = engine.analyze(_comparisons_5())
        ranks = [info["rank"] for info in result["ranking"].values()]
        assert set(ranks) == set(range(1, 6))


# ── Network diagram SVG generation ───────────────────────────

class TestNetworkDiagram:
    def test_network_svg_is_svg(self, engine):
        result = engine.analyze(_comparisons_3())
        svg = result["network_svg"]
        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_network_svg_contains_treatment_names(self, engine):
        result = engine.analyze(_comparisons_3())
        svg = result["network_svg"]
        for t in result["treatments"]:
            assert t in svg

    def test_network_svg_dimensions(self, engine):
        result = engine.analyze(_comparisons_5())
        svg = result["network_svg"]
        assert 'width="600"' in svg
        assert 'height="500"' in svg

    def test_network_svg_has_edges(self, engine):
        result = engine.analyze(_comparisons_3())
        svg = result["network_svg"]
        assert "<line" in svg


# ── League table SVG generation ──────────────────────────────

class TestLeagueTable:
    def test_league_svg_is_svg(self, engine):
        result = engine.analyze(_comparisons_3())
        svg = result["league_svg"]
        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_league_svg_contains_treatment_names(self, engine):
        result = engine.analyze(_comparisons_3())
        svg = result["league_svg"]
        for t in result["treatments"]:
            assert t in svg

    def test_league_svg_has_cells(self, engine):
        result = engine.analyze(_comparisons_3())
        svg = result["league_svg"]
        # Should have rect elements for cells
        assert "<rect" in svg

    def test_league_svg_has_title(self, engine):
        result = engine.analyze(_comparisons_3())
        svg = result["league_svg"]
        assert "League Table" in svg
