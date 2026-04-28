"""
Unit tests for MetaAnalysisEngine.

Tests all core statistical methods:
  - Dichotomous OR / RR calculation
  - Fixed effect and random effects models
  - Heterogeneity statistics (I², Q, τ²)
  - Egger's test, Begg's test, trim-and-fill
  - Cumulative analysis
  - Meta-regression
  - Dose-response analysis
  - Continuous data (SMD)
  - Subgroup analysis
  - Sensitivity analysis
"""

import math
import sys
import os
import pytest

# Ensure app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import MetaAnalysisEngine, StudyInput, StudyResult


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def engine():
    return MetaAnalysisEngine()


def _make_dichotomous_studies():
    """Return a list of 5 StudyInput objects with dichotomous data."""
    return [
        StudyInput(name="Study A", e_events=45, e_total=100, c_events=30, c_total=100, data_type="dichotomous"),
        StudyInput(name="Study B", e_events=60, e_total=120, c_events=40, c_total=110, data_type="dichotomous"),
        StudyInput(name="Study C", e_events=35, e_total=90,  c_events=25, c_total=95,  data_type="dichotomous"),
        StudyInput(name="Study D", e_events=80, e_total=200, c_events=55, c_total=190, data_type="dichotomous"),
        StudyInput(name="Study E", e_events=50, e_total=110, c_events=38, c_total=105, data_type="dichotomous"),
    ]


def _make_continuous_studies():
    """Return a list of 5 StudyInput objects with continuous data."""
    return [
        StudyInput(name="Cont A", e_total=50, c_total=50, e_mean=12.5, e_sd=3.2, c_mean=10.1, c_sd=2.8, data_type="continuous"),
        StudyInput(name="Cont B", e_total=60, c_total=58, e_mean=14.0, e_sd=4.0, c_mean=11.5, c_sd=3.5, data_type="continuous"),
        StudyInput(name="Cont C", e_total=40, c_total=42, e_mean=11.8, e_sd=2.9, c_mean=10.3, c_sd=3.0, data_type="continuous"),
        StudyInput(name="Cont D", e_total=80, c_total=78, e_mean=13.2, e_sd=3.5, c_mean=10.8, c_sd=3.1, data_type="continuous"),
        StudyInput(name="Cont E", e_total=55, c_total=53, e_mean=15.0, e_sd=4.5, c_mean=12.0, c_sd=3.8, data_type="continuous"),
    ]


def _make_subgroup_studies():
    """Return studies with subgroup labels for subgroup analysis."""
    return [
        StudyInput(name="S1", e_events=30, e_total=100, c_events=20, c_total=100, subgroup="A", data_type="dichotomous"),
        StudyInput(name="S2", e_events=45, e_total=120, c_events=25, c_total=110, subgroup="A", data_type="dichotomous"),
        StudyInput(name="S3", e_events=50, e_total=100, c_events=35, c_total=100, subgroup="B", data_type="dichotomous"),
        StudyInput(name="S4", e_events=60, e_total=130, c_events=40, c_total=120, subgroup="B", data_type="dichotomous"),
    ]


# ── Dichotomous OR calculation ───────────────────────────────

class TestDichotomousOR:
    def test_or_calculation_basic(self, engine):
        """Verify OR = (a*d)/(b*c) for a single study."""
        studies = _make_dichotomous_studies()
        sr = engine._calc_dichotomous(studies[0], "OR")
        # a=45, b=55, c=30, d=70 (with 0.5 continuity correction for zeros)
        expected_or = (45 * 70) / (55 * 30)
        assert abs(sr.effect - expected_or) < 1e-6

    def test_or_is_positive(self, engine):
        studies = _make_dichotomous_studies()
        for s in studies:
            sr = engine._calc_dichotomous(s, "OR")
            assert sr.effect > 0

    def test_or_ci_contains_point_estimate(self, engine):
        studies = _make_dichotomous_studies()
        for s in studies:
            sr = engine._calc_dichotomous(s, "OR")
            assert sr.ci_lower <= sr.effect <= sr.ci_upper

    def test_or_weight_positive(self, engine):
        studies = _make_dichotomous_studies()
        for s in studies:
            sr = engine._calc_dichotomous(s, "OR")
            assert sr.weight > 0


# ── Dichotomous RR calculation ───────────────────────────────

class TestDichotomousRR:
    def test_rr_calculation_basic(self, engine):
        """Verify RR = p1/p2."""
        studies = _make_dichotomous_studies()
        sr = engine._calc_dichotomous(studies[0], "RR")
        # p1 = 45/100, p2 = 30/100
        expected_rr = (45 / 100) / (30 / 100)
        assert abs(sr.effect - expected_rr) < 1e-6

    def test_rr_is_positive(self, engine):
        studies = _make_dichotomous_studies()
        for s in studies:
            sr = engine._calc_dichotomous(s, "RR")
            assert sr.effect > 0

    def test_rr_ci_contains_point_estimate(self, engine):
        studies = _make_dichotomous_studies()
        for s in studies:
            sr = engine._calc_dichotomous(s, "RR")
            assert sr.ci_lower <= sr.effect <= sr.ci_upper


# ── Fixed effect model ───────────────────────────────────────

class TestFixedEffect:
    def test_fixed_effect_returns_required_keys(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        pooled = engine._fixed_effect(srs, use_log_scale=True)
        for key in ("effect", "ci_lower", "ci_upper", "p_value"):
            assert key in pooled

    def test_fixed_effect_ci_contains_effect(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        pooled = engine._fixed_effect(srs, use_log_scale=True)
        assert pooled["ci_lower"] <= pooled["effect"] <= pooled["ci_upper"]

    def test_fixed_effect_p_value_range(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        pooled = engine._fixed_effect(srs)
        assert 0.0 <= pooled["p_value"] <= 1.0

    def test_fixed_effect_continuous(self, engine):
        studies = _make_continuous_studies()
        srs = [engine._calc_continuous(s, "SMD") for s in studies]
        pooled = engine._fixed_effect(srs, use_log_scale=False)
        assert "effect" in pooled
        assert pooled["ci_lower"] <= pooled["effect"] <= pooled["ci_upper"]


# ── Random effects model ─────────────────────────────────────

class TestRandomEffects:
    def test_random_effects_returns_required_keys(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        pooled = engine._random_effects(srs)
        for key in ("effect", "ci_lower", "ci_upper", "p_value"):
            assert key in pooled

    def test_random_effects_ci_contains_effect(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        pooled = engine._random_effects(srs)
        assert pooled["ci_lower"] <= pooled["effect"] <= pooled["ci_upper"]

    def test_random_effects_ci_wider_than_fixed(self, engine):
        """Random effects CI should generally be wider than fixed effect CI."""
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        fe = engine._fixed_effect(srs)
        re = engine._random_effects(srs)
        fe_width = fe["ci_upper"] - fe["ci_lower"]
        re_width = re["ci_upper"] - re["ci_lower"]
        # With DerSimonian-Laird, RE CI >= FE CI
        assert re_width >= fe_width - 1e-10

    def test_random_effects_p_value_range(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        pooled = engine._random_effects(srs)
        assert 0.0 <= pooled["p_value"] <= 1.0


# ── Heterogeneity (I², Q, τ²) ────────────────────────────────

class TestHeterogeneity:
    def test_heterogeneity_returns_required_keys(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        het = engine._heterogeneity(srs)
        for key in ("i_squared", "tau_squared", "q_statistic", "q_p_value", "level"):
            assert key in het

    def test_i_squared_range(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        het = engine._heterogeneity(srs)
        assert 0 <= het["i_squared"] <= 100

    def test_tau_squared_non_negative(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        het = engine._heterogeneity(srs)
        assert het["tau_squared"] >= 0

    def test_q_statistic_non_negative(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        het = engine._heterogeneity(srs)
        assert het["q_statistic"] >= 0

    def test_q_p_value_range(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        het = engine._heterogeneity(srs)
        assert 0 <= het["q_p_value"] <= 1

    def test_heterogeneity_level_valid(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        het = engine._heterogeneity(srs)
        assert het["level"] in ("low", "moderate", "high")

    def test_identical_studies_low_heterogeneity(self, engine):
        """Identical studies should yield I² ≈ 0."""
        studies = [
            StudyInput(name="X1", e_events=50, e_total=100, c_events=30, c_total=100, data_type="dichotomous"),
            StudyInput(name="X2", e_events=50, e_total=100, c_events=30, c_total=100, data_type="dichotomous"),
            StudyInput(name="X3", e_events=50, e_total=100, c_events=30, c_total=100, data_type="dichotomous"),
        ]
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        het = engine._heterogeneity(srs)
        assert het["i_squared"] < 1.0


# ── Egger's test ─────────────────────────────────────────────

class TestEggersTest:
    def test_egger_returns_required_keys(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        result = engine.egger_test(srs)
        for key in ("intercept", "slope", "t_statistic", "p_value", "conclusion"):
            assert key in result

    def test_egger_p_value_range(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        result = engine.egger_test(srs)
        assert 0 <= result["p_value"] <= 1

    def test_egger_conclusion_valid(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        result = engine.egger_test(srs)
        assert result["conclusion"] in ("significant", "not_significant")

    def test_egger_insufficient_studies(self, engine):
        """Egger's test should return a default result for < 3 studies."""
        studies = _make_dichotomous_studies()[:2]
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        result = engine.egger_test(srs)
        assert result["conclusion"] == "insufficient_studies"


# ── Begg's test ──────────────────────────────────────────────

class TestBeggsTest:
    def test_begg_returns_required_keys(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        result = engine.begg_test(srs)
        for key in ("tau", "p_value", "conclusion"):
            assert key in result

    def test_begg_tau_range(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        result = engine.begg_test(srs)
        assert -1 <= result["tau"] <= 1

    def test_begg_conclusion_valid(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        result = engine.begg_test(srs)
        assert result["conclusion"] in ("significant", "not_significant")

    def test_begg_insufficient_studies(self, engine):
        studies = _make_dichotomous_studies()[:2]
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        result = engine.begg_test(srs)
        assert result["conclusion"] == "insufficient_studies"


# ── Trim-and-fill ────────────────────────────────────────────

class TestTrimAndFill:
    def test_trim_and_fill_returns_required_keys(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        result = engine.trim_and_fill(srs)
        for key in ("estimated_missing", "original_effect", "adjusted_effect",
                     "adjusted_ci_lower", "adjusted_ci_upper", "imputed_studies"):
            assert key in result

    def test_trim_and_fill_non_negative_missing(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        result = engine.trim_and_fill(srs)
        assert result["estimated_missing"] >= 0

    def test_trim_and_fill_imputed_list(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        result = engine.trim_and_fill(srs)
        assert isinstance(result["imputed_studies"], list)
        assert len(result["imputed_studies"]) == result["estimated_missing"]

    def test_trim_and_fill_insufficient_studies(self, engine):
        studies = _make_dichotomous_studies()[:2]
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        result = engine.trim_and_fill(srs)
        assert result["estimated_missing"] == 0


# ── Cumulative analysis ──────────────────────────────────────

class TestCumulativeAnalysis:
    def test_cumulative_returns_list(self, engine):
        studies = _make_dichotomous_studies()
        results = engine.cumulative_analysis(studies, effect_measure="OR")
        assert isinstance(results, list)

    def test_cumulative_correct_length(self, engine):
        studies = _make_dichotomous_studies()
        results = engine.cumulative_analysis(studies, effect_measure="OR")
        # Cumulative starts at 2 studies
        assert len(results) == len(studies) - 1

    def test_cumulative_each_step_has_keys(self, engine):
        studies = _make_dichotomous_studies()
        results = engine.cumulative_analysis(studies, effect_measure="OR")
        for r in results:
            for key in ("step", "n_studies", "studies_included", "pooled_effect",
                        "ci_lower", "ci_upper", "p_value", "i_squared"):
                assert key in r

    def test_cumulative_step_increases(self, engine):
        studies = _make_dichotomous_studies()
        results = engine.cumulative_analysis(studies, effect_measure="OR")
        for r in results:
            assert r["n_studies"] == r["step"]

    def test_cumulative_sorted_by_effect(self, engine):
        studies = _make_dichotomous_studies()
        results = engine.cumulative_analysis(studies, sort_by="effect", effect_measure="OR")
        assert len(results) > 0

    def test_cumulative_random_model(self, engine):
        studies = _make_dichotomous_studies()
        results = engine.cumulative_analysis(studies, model="random", effect_measure="OR")
        assert len(results) > 0


# ── Meta-regression ──────────────────────────────────────────

class TestMetaRegression:
    def test_meta_regression_returns_required_keys(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        covariate = [100, 200, 300, 400, 500]
        result = engine.meta_regression(srs, covariate, covariate_name="sample_size")
        for key in ("coefficient", "coefficient_se", "p_value", "intercept",
                     "r_squared", "curve", "covariate_name"):
            assert key in result

    def test_meta_regression_coefficient_not_nan(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        covariate = [100, 200, 300, 400, 500]
        result = engine.meta_regression(srs, covariate)
        assert not math.isnan(result["coefficient"])

    def test_meta_regression_r_squared_range(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        covariate = [100, 200, 300, 400, 500]
        result = engine.meta_regression(srs, covariate)
        assert 0 <= result["r_squared"] <= 1

    def test_meta_regression_insufficient_studies(self, engine):
        studies = _make_dichotomous_studies()[:2]
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        result = engine.meta_regression(srs, [1, 2])
        assert "error" in result

    def test_meta_regression_mismatched_covariate(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        result = engine.meta_regression(srs, [1, 2])  # length mismatch
        assert "error" in result


# ── Dose-response ────────────────────────────────────────────

class TestDoseResponse:
    def test_dose_response_returns_required_keys(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        doses = [10, 20, 30, 40, 50]
        result = engine.dose_response(srs, doses)
        for key in ("n_studies", "dose_range", "knots", "linear", "spline", "study_points"):
            assert key in result

    def test_dose_response_linear_keys(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        doses = [10, 20, 30, 40, 50]
        result = engine.dose_response(srs, doses)
        for key in ("coefficient", "coefficient_se", "p_value", "r_squared", "curve"):
            assert key in result["linear"]

    def test_dose_response_spline_keys(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        doses = [10, 20, 30, 40, 50]
        result = engine.dose_response(srs, doses)
        for key in ("coefficients", "r_squared", "curve", "nonlinearity_test_p", "lr_test_p"):
            assert key in result["spline"]

    def test_dose_response_insufficient_studies(self, engine):
        studies = _make_dichotomous_studies()[:2]
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        result = engine.dose_response(srs, [10, 20])
        assert "error" in result

    def test_dose_response_mismatched_doses(self, engine):
        studies = _make_dichotomous_studies()
        srs = [engine._calc_dichotomous(s, "OR") for s in studies]
        result = engine.dose_response(srs, [10, 20])
        assert "error" in result


# ── Continuous data (SMD) ────────────────────────────────────

class TestContinuousSMD:
    def test_smd_calculation(self, engine):
        studies = _make_continuous_studies()
        sr = engine._calc_continuous(studies[0], "SMD")
        # Effect should be nonzero since means differ
        assert abs(sr.effect) > 0

    def test_smd_ci_contains_effect(self, engine):
        studies = _make_continuous_studies()
        for s in studies:
            sr = engine._calc_continuous(s, "SMD")
            assert sr.ci_lower <= sr.effect <= sr.ci_upper

    def test_smd_weight_positive(self, engine):
        studies = _make_continuous_studies()
        for s in studies:
            sr = engine._calc_continuous(s, "SMD")
            assert sr.weight > 0

    def test_full_analysis_continuous(self, engine):
        """Engine.analyze should work with continuous data."""
        studies = _make_continuous_studies()
        result = engine.analyze(studies, model="random", effect_measure="SMD")
        assert result.pooled_effect is not None
        assert result.i_squared >= 0

    def test_wmd_calculation(self, engine):
        studies = _make_continuous_studies()
        sr = engine._calc_continuous(studies[0], "WMD")
        # WMD should approximate the raw mean difference
        assert abs(sr.effect - (12.5 - 10.1)) < 0.5


# ── Subgroup analysis ────────────────────────────────────────

class TestSubgroupAnalysis:
    def test_subgroup_analysis_returns_dict(self, engine):
        studies = _make_subgroup_studies()
        result = engine._subgroup_analysis(studies, "OR")
        assert isinstance(result, dict)

    def test_subgroup_analysis_has_groups(self, engine):
        studies = _make_subgroup_studies()
        result = engine._subgroup_analysis(studies, "OR")
        assert "A" in result
        assert "B" in result

    def test_subgroup_each_group_has_keys(self, engine):
        studies = _make_subgroup_studies()
        result = engine._subgroup_analysis(studies, "OR")
        for g in result:
            for key in ("n_studies", "pooled_effect", "ci_lower", "ci_upper", "p_value", "i_squared"):
                assert key in result[g]

    def test_subgroup_n_studies_correct(self, engine):
        studies = _make_subgroup_studies()
        result = engine._subgroup_analysis(studies, "OR")
        assert result["A"]["n_studies"] == 2
        assert result["B"]["n_studies"] == 2


# ── Sensitivity analysis ─────────────────────────────────────

class TestSensitivityAnalysis:
    def test_sensitivity_returns_list(self, engine):
        studies = _make_dichotomous_studies()
        result = engine._sensitivity_analysis(studies, "OR")
        assert isinstance(result, list)

    def test_sensitivity_correct_length(self, engine):
        studies = _make_dichotomous_studies()
        result = engine._sensitivity_analysis(studies, "OR")
        assert len(result) == len(studies)

    def test_sensitivity_each_has_keys(self, engine):
        studies = _make_dichotomous_studies()
        result = engine._sensitivity_analysis(studies, "OR")
        for r in result:
            for key in ("excluded", "pooled_effect", "ci_lower", "ci_upper", "p_value"):
                assert key in r

    def test_sensitivity_excluded_names(self, engine):
        studies = _make_dichotomous_studies()
        result = engine._sensitivity_analysis(studies, "OR")
        excluded = [r["excluded"] for r in result]
        original_names = [s.name for s in studies]
        assert set(excluded) == set(original_names)


# ── Full analyze() integration ───────────────────────────────

class TestFullAnalyze:
    def test_analyze_returns_meta_result(self, engine):
        studies = _make_dichotomous_studies()
        result = engine.analyze(studies, model="random", effect_measure="OR")
        assert hasattr(result, "pooled_effect")
        assert hasattr(result, "i_squared")
        assert hasattr(result, "studies")

    def test_analyze_requires_two_studies(self, engine):
        studies = _make_dichotomous_studies()[:1]
        with pytest.raises(ValueError):
            engine.analyze(studies)

    def test_analyze_or_result(self, engine):
        studies = _make_dichotomous_studies()
        result = engine.analyze(studies, model="random", effect_measure="OR")
        assert result.effect_measure == "OR"
        assert result.pooled_effect > 0

    def test_analyze_rr_result(self, engine):
        studies = _make_dichotomous_studies()
        result = engine.analyze(studies, model="random", effect_measure="RR")
        assert result.effect_measure == "RR"
        assert result.pooled_effect > 0

    def test_analyze_fixed_model(self, engine):
        studies = _make_dichotomous_studies()
        result = engine.analyze(studies, model="fixed", effect_measure="OR")
        assert result.model == "fixed"

    def test_analyze_random_model(self, engine):
        studies = _make_dichotomous_studies()
        result = engine.analyze(studies, model="random", effect_measure="OR")
        assert result.model == "random"

    def test_analyze_generates_svg_plots(self, engine):
        studies = _make_dichotomous_studies()
        result = engine.analyze(studies, model="random", effect_measure="OR")
        assert "<svg" in result.forest_plot_svg
        assert "<svg" in result.funnel_plot_svg

    def test_analyze_subgroup_results_populated(self, engine):
        studies = _make_subgroup_studies()
        result = engine.analyze(studies, model="random", effect_measure="OR")
        assert len(result.subgroup_results) > 0

    def test_analyze_sensitivity_results_populated(self, engine):
        studies = _make_dichotomous_studies()
        result = engine.analyze(studies, model="random", effect_measure="OR")
        assert len(result.sensitivity_results) == len(studies)
