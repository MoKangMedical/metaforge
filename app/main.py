"""
MetaForge — 完整闭环AI循证医学研究平台

一个可以直接运行的Meta分析全流程平台：
  1. 输入研究问题 → 2. AI检索文献 → 3. 智能筛选 → 4. 数据提取
  → 5. 统计分析 → 6. 生成报告(森林图/漏斗图/PRISMA)

启动方式: python -m app.main
访问: http://localhost:8000
"""

import os
import sys
import json
import time
import math
import uuid
import base64
import hashlib
import io
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any

# Database and auth imports
from app.database import init_db, get_db, User, Project, APIUsage, ShareToken, PLAN_LIMITS, SessionLocal
from app.auth import hash_password, verify_password, generate_token, validate_token, check_api_quota, increment_api_usage

import numpy as np
from scipy import stats as sp_stats

import csv as csv_module

from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

# ============================================================
# FastAPI App
# ============================================================

app = FastAPI(
    title="MetaForge",
    description="AI循证医学研究平台 — 完整闭环Meta分析引擎",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# 核心数据模型
# ============================================================

@dataclass
class StudyInput:
    name: str = ""
    e_events: int = 0       # 实验组事件数
    e_total: int = 0        # 实验组总人数
    c_events: int = 0       # 对照组事件数
    c_total: int = 0        # 对照组总人数
    subgroup: str = ""
    data_type: str = "dichotomous"
    # Continuous data fields
    e_mean: float = 0.0     # 实验组均值
    e_sd: float = 0.0       # 实验组标准差
    c_mean: float = 0.0     # 对照组均值
    c_sd: float = 0.0       # 对照组标准差

@dataclass
class StudyResult:
    name: str = ""
    effect: float = 0.0      # OR or RR
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    weight: float = 0.0
    log_effect: float = 0.0
    log_se: float = 0.0
    subgroup: str = ""

@dataclass
class MetaResult:
    pooled_effect: float = 0.0
    pooled_ci_lower: float = 0.0
    pooled_ci_upper: float = 0.0
    p_value: float = 0.0
    i_squared: float = 0.0
    tau_squared: float = 0.0
    q_statistic: float = 0.0
    q_p_value: float = 0.0
    heterogeneity: str = ""
    model: str = "random"
    effect_measure: str = "OR"
    studies: List[dict] = field(default_factory=list)
    forest_plot_svg: str = ""
    funnel_plot_svg: str = ""
    prisma_svg: str = ""
    subgroup_results: dict = field(default_factory=dict)
    sensitivity_results: list = field(default_factory=list)

# ============================================================
# 统计引擎 — 真实Meta分析计算
# ============================================================

class MetaAnalysisEngine:
    """完整的Meta分析统计引擎"""

    def analyze(self, studies: List[StudyInput], model: str = "random",
                effect_measure: str = "OR") -> MetaResult:
        """执行Meta分析"""
        if len(studies) < 2:
            raise ValueError("至少需要2个研究")

        # Detect data type from first study (or use explicit parameter)
        data_type = studies[0].data_type if studies else "dichotomous"

        # For continuous data, default effect measure to SMD if not specified
        if data_type == "continuous" and effect_measure in ("OR", "RR"):
            effect_measure = "SMD"

        # Step 1: 计算每个研究的效应量
        study_results = []
        for s in studies:
            if s.data_type == "dichotomous":
                sr = self._calc_dichotomous(s, effect_measure)
            elif s.data_type == "continuous":
                sr = self._calc_continuous(s, effect_measure)
            else:
                continue
            study_results.append(sr)

        # Step 2: 合并效应量
        use_log = data_type != "continuous"
        if model == "fixed":
            pooled = self._fixed_effect(study_results, use_log_scale=use_log)
        else:
            pooled = self._random_effects(study_results, use_log_scale=use_log)

        # Step 3: 异质性检验
        het = self._heterogeneity(study_results)

        # Step 4: 生成图表
        forest_svg = self._forest_plot(study_results, pooled, effect_measure)
        funnel_svg = self._funnel_plot(study_results, pooled)

        # Step 5: 亚组分析
        subgroup_results = self._subgroup_analysis(studies, effect_measure)

        # Step 6: 敏感性分析 (逐一剔除)
        sensitivity = self._sensitivity_analysis(studies, effect_measure)

        return MetaResult(
            pooled_effect=pooled["effect"],
            pooled_ci_lower=pooled["ci_lower"],
            pooled_ci_upper=pooled["ci_upper"],
            p_value=pooled["p_value"],
            i_squared=het["i_squared"],
            tau_squared=het["tau_squared"],
            q_statistic=het["q_statistic"],
            q_p_value=het["q_p_value"],
            heterogeneity=het["level"],
            model=model,
            effect_measure=effect_measure,
            studies=[asdict(s) for s in study_results],
            forest_plot_svg=forest_svg,
            funnel_plot_svg=funnel_svg,
            subgroup_results=subgroup_results,
            sensitivity_results=sensitivity,
        )

    def _calc_dichotomous(self, s: StudyInput, measure: str) -> StudyResult:
        """计算二分类效应量"""
        a, b = s.e_events, s.e_total - s.e_events
        c, d = s.c_events, s.c_total - s.c_events
        a, b, c, d = max(a, 0.5), max(b, 0.5), max(c, 0.5), max(d, 0.5)

        if measure == "OR":
            effect = (a * d) / (b * c)
            log_effect = math.log(effect)
            log_se = math.sqrt(1/a + 1/b + 1/c + 1/d)
        else:  # RR
            p1 = a / (a + b)
            p2 = c / (c + d)
            effect = p1 / p2 if p2 > 0 else 1.0
            log_effect = math.log(effect)
            log_se = math.sqrt(1/a - 1/(a+b) + 1/c - 1/(c+d))

        ci_lower = math.exp(log_effect - 1.96 * log_se)
        ci_upper = math.exp(log_effect + 1.96 * log_se)
        weight = 1.0 / (log_se ** 2)

        return StudyResult(
            name=s.name, effect=effect, ci_lower=ci_lower, ci_upper=ci_upper,
            weight=weight, log_effect=log_effect, log_se=log_se, subgroup=s.subgroup
        )

    def _calc_continuous(self, s: StudyInput, measure: str = "SMD") -> StudyResult:
        """Calculate continuous data effect size.

        SMD = Standardized Mean Difference (Hedges' g with small-sample correction)
        WMD = Weighted Mean Difference (raw difference in means)
        """
        n_e = s.e_total
        n_c = s.c_total
        m_e = s.e_mean
        m_d = s.c_mean
        sd_e = s.e_sd
        sd_c = s.c_sd

        if n_e < 1 or n_c < 1:
            raise ValueError(f"Study '{s.name}': sample sizes must be >= 1 for continuous data")

        if measure == "SMD":
            # Pooled standard deviation
            df = n_e + n_c - 2
            if df <= 0:
                df = 1
            sp = math.sqrt(((n_e - 1) * sd_e**2 + (n_c - 1) * sd_c**2) / df)

            # Cohen's d
            if sp < 1e-12:
                d = 0.0
            else:
                d = (m_e - m_d) / sp

            # Hedges' g correction factor (small-sample bias correction)
            # J = 1 - 3 / (4*df - 1)
            j = 1.0 - 3.0 / (4.0 * df - 1.0) if (4.0 * df - 1.0) != 0 else 1.0
            g = d * j

            # SE of Hedges' g
            # SE(g) = sqrt(n_e+n_c)/(n_e*n_c) + g^2 / (2*(n_e+n_c))
            se_g = math.sqrt((n_e + n_c) / (n_e * n_c) + g**2 / (2.0 * (n_e + n_c)))

            effect = g
            log_effect = g        # For SMD, log_effect stores the SMD itself
            log_se = se_g
            ci_lower = g - 1.96 * se_g
            ci_upper = g + 1.96 * se_g

        else:  # WMD
            # Weighted Mean Difference (raw difference)
            diff = m_e - m_d
            se_diff = math.sqrt(sd_e**2 / n_e + sd_c**2 / n_c) if (n_e > 0 and n_c > 0) else 0.0

            effect = diff
            log_effect = diff     # For WMD, log_effect stores the raw difference
            log_se = se_diff
            ci_lower = diff - 1.96 * se_diff
            ci_upper = diff + 1.96 * se_diff

        weight = 1.0 / (log_se ** 2) if log_se > 1e-12 else 0.0

        return StudyResult(
            name=s.name, effect=effect, ci_lower=ci_lower, ci_upper=ci_upper,
            weight=weight, log_effect=log_effect, log_se=log_se, subgroup=s.subgroup
        )

    def _fixed_effect(self, studies: List[StudyResult], use_log_scale: bool = True) -> dict:
        """固定效应模型 (Mantel-Haenszel / Inverse Variance)"""
        total_w = sum(s.weight for s in studies)
        pooled_est = sum(s.weight * s.log_effect for s in studies) / total_w
        pooled_se = math.sqrt(1.0 / total_w)

        if use_log_scale:
            pooled_effect = math.exp(pooled_est)
            ci_lower = math.exp(pooled_est - 1.96 * pooled_se)
            ci_upper = math.exp(pooled_est + 1.96 * pooled_se)
        else:
            pooled_effect = pooled_est
            ci_lower = pooled_est - 1.96 * pooled_se
            ci_upper = pooled_est + 1.96 * pooled_se

        z = pooled_est / pooled_se
        p_value = 2 * (1 - sp_stats.norm.cdf(abs(z)))
        return {"effect": pooled_effect, "ci_lower": ci_lower, "ci_upper": ci_upper, "p_value": p_value}

    def _random_effects(self, studies: List[StudyResult], use_log_scale: bool = True) -> dict:
        """随机效应模型 (DerSimonian-Laird)"""
        # First get fixed effect estimate
        fe = self._fixed_effect(studies, use_log_scale=use_log_scale)
        total_w = sum(s.weight for s in studies)

        # Q statistic
        q = sum(s.weight * (s.log_effect - sum(s2.weight * s2.log_effect for s2 in studies) / total_w) ** 2 for s in studies)
        k = len(studies)

        # tau-squared
        c_val = total_w - sum(s.weight ** 2 for s in studies) / total_w
        tau2 = max(0, (q - (k - 1)) / c_val) if c_val > 0 else 0

        # Random effects weights
        re_studies = []
        for s in studies:
            w_re = 1.0 / (1.0 / s.weight + tau2)
            re_studies.append((s.log_effect, w_re, s))

        total_w_re = sum(w for _, w, _ in re_studies)
        pooled_log = sum(le * w for le, w, _ in re_studies) / total_w_re
        pooled_se = math.sqrt(1.0 / total_w_re)

        if use_log_scale:
            pooled_effect = math.exp(pooled_log)
            ci_lower = math.exp(pooled_log - 1.96 * pooled_se)
            ci_upper = math.exp(pooled_log + 1.96 * pooled_se)
        else:
            pooled_effect = pooled_log
            ci_lower = pooled_log - 1.96 * pooled_se
            ci_upper = pooled_log + 1.96 * pooled_se

        z = pooled_log / pooled_se
        p_value = 2 * (1 - sp_stats.norm.cdf(abs(z)))

        return {"effect": pooled_effect, "ci_lower": ci_lower, "ci_upper": ci_upper, "p_value": p_value}

    def _heterogeneity(self, studies: List[StudyResult]) -> dict:
        """异质性检验 (I², Q, τ²)"""
        total_w = sum(s.weight for s in studies)
        mean_log = sum(s.weight * s.log_effect for s in studies) / total_w
        q = sum(s.weight * (s.log_effect - mean_log) ** 2 for s in studies)
        k = len(studies)
        df = k - 1
        q_p = 1 - sp_stats.chi2.cdf(q, df) if df > 0 else 1.0
        i2 = max(0, (q - df) / q * 100) if q > 0 else 0
        c_val = total_w - sum(s.weight**2 for s in studies) / total_w
        tau2 = max(0, (q - df) / c_val) if c_val > 0 else 0

        level = "low" if i2 < 25 else "moderate" if i2 < 75 else "high"
        return {"i_squared": round(i2, 1), "tau_squared": round(tau2, 4),
                "q_statistic": round(q, 2), "q_p_value": round(q_p, 4), "level": level}

    def _subgroup_analysis(self, studies: List[StudyInput], measure: str) -> dict:
        """亚组分析"""
        groups = {}
        for s in studies:
            g = s.subgroup or "Overall"
            groups.setdefault(g, []).append(s)

        results = {}
        for g, group_studies in groups.items():
            if len(group_studies) < 2:
                continue
            if group_studies[0].data_type == "continuous":
                srs = [self._calc_continuous(s, measure) for s in group_studies]
                pooled = self._fixed_effect(srs, use_log_scale=False)
            else:
                srs = [self._calc_dichotomous(s, measure) for s in group_studies]
                pooled = self._fixed_effect(srs)
            het = self._heterogeneity(srs)
            results[g] = {
                "n_studies": len(group_studies),
                "pooled_effect": round(pooled["effect"], 3),
                "ci_lower": round(pooled["ci_lower"], 3),
                "ci_upper": round(pooled["ci_upper"], 3),
                "p_value": round(pooled["p_value"], 4),
                "i_squared": het["i_squared"],
            }
        return results

    def _sensitivity_analysis(self, studies: List[StudyInput], measure: str) -> list:
        """逐一剔除敏感性分析"""
        results = []
        for i in range(len(studies)):
            subset = [s for j, s in enumerate(studies) if j != i]
            if subset[0].data_type == "continuous":
                srs = [self._calc_continuous(s, measure) for s in subset]
                pooled = self._fixed_effect(srs, use_log_scale=False)
            else:
                srs = [self._calc_dichotomous(s, measure) for s in subset]
                pooled = self._fixed_effect(srs)
            results.append({
                "excluded": studies[i].name,
                "pooled_effect": round(pooled["effect"], 3),
                "ci_lower": round(pooled["ci_lower"], 3),
                "ci_upper": round(pooled["ci_upper"], 3),
                "p_value": round(pooled["p_value"], 4),
            })
        return results

    def egger_test(self, studies: List[StudyResult]) -> dict:
        """Egger's regression test for publication bias.

        Regresses standardized effect (log_effect / log_se) on precision (1 / log_se).
        A significant intercept suggests asymmetry (publication bias).
        """
        if len(studies) < 3:
            return {"intercept": 0.0, "slope": 0.0, "p_value": 1.0,
                    "t_statistic": 0.0, "conclusion": "insufficient_studies"}

        precision = np.array([1.0 / s.log_se for s in studies])
        std_effect = np.array([s.log_effect / s.log_se for s in studies])

        n = len(studies)
        x_mean = np.mean(precision)
        y_mean = np.mean(std_effect)

        ss_xx = float(np.sum((precision - x_mean) ** 2))
        ss_xy = float(np.sum((precision - x_mean) * (std_effect - y_mean)))

        slope = ss_xy / ss_xx if ss_xx > 0 else 0.0
        intercept = y_mean - slope * x_mean

        y_pred = intercept + slope * precision
        residuals = std_effect - y_pred
        mse = float(np.sum(residuals ** 2) / (n - 2)) if n > 2 else 0.0
        se_intercept = math.sqrt(mse * (1.0 / n + x_mean ** 2 / ss_xx)) if ss_xx > 0 else 0.0

        t_stat = intercept / se_intercept if se_intercept > 0 else 0.0
        p_value = 2 * (1 - sp_stats.t.cdf(abs(t_stat), df=n - 2)) if n > 2 else 1.0

        return {
            "intercept": round(float(intercept), 4),
            "slope": round(float(slope), 4),
            "t_statistic": round(float(t_stat), 4),
            "p_value": round(float(p_value), 4),
            "conclusion": "significant" if p_value < 0.05 else "not_significant",
        }

    def begg_test(self, studies: List[StudyResult]) -> dict:
        """Begg's rank correlation test for publication bias.

        Computes Kendall's tau between effect sizes and their variances.
        A significant correlation suggests small-study effects / bias.
        """
        if len(studies) < 3:
            return {"tau": 0.0, "p_value": 1.0, "conclusion": "insufficient_studies"}

        effects = [s.log_effect for s in studies]
        variances = [s.log_se ** 2 for s in studies]

        tau, p_value = sp_stats.kendalltau(effects, variances)

        return {
            "tau": round(float(tau), 4),
            "p_value": round(float(p_value), 4),
            "conclusion": "significant" if p_value < 0.05 else "not_significant",
        }

    def cumulative_analysis(self, studies: List[StudyInput],
                            sort_by: str = "name",
                            effect_measure: str = "OR",
                            model: str = "random") -> list:
        """Cumulative meta-analysis.

        Adds studies one at a time (sorted by name or effect size) and returns
        the evolving pooled estimate at each step.
        """
        if sort_by == "effect":
            if studies[0].data_type == "continuous":
                sorted_studies = sorted(
                    studies,
                    key=lambda s: self._calc_continuous(s, effect_measure).log_effect,
                )
            else:
                sorted_studies = sorted(
                    studies,
                    key=lambda s: self._calc_dichotomous(s, effect_measure).log_effect,
                )
        else:
            sorted_studies = list(studies)

        results = []
        for i in range(2, len(sorted_studies) + 1):
            subset = sorted_studies[:i]
            if subset[0].data_type == "continuous":
                srs = [self._calc_continuous(s, effect_measure) for s in subset]
                use_log = False
            else:
                srs = [self._calc_dichotomous(s, effect_measure) for s in subset]
                use_log = True
            pooled = self._random_effects(srs, use_log_scale=use_log) if model == "random" else self._fixed_effect(srs, use_log_scale=use_log)
            het = self._heterogeneity(srs)
            results.append({
                "step": i,
                "n_studies": i,
                "studies_included": [s.name for s in subset],
                "pooled_effect": round(pooled["effect"], 4),
                "ci_lower": round(pooled["ci_lower"], 4),
                "ci_upper": round(pooled["ci_upper"], 4),
                "p_value": round(pooled["p_value"], 4),
                "i_squared": het["i_squared"],
            })

        return results

    def trim_and_fill(self, studies: List[StudyResult],
                      model: str = "random") -> dict:
        """Trim-and-fill method for publication bias (Duval & Tweedie).

        Estimates the number of missing studies on one side of the funnel,
        imputes them, and returns the adjusted pooled estimate.
        """
        if len(studies) < 3:
            return {"estimated_missing": 0, "original_effect": 0.0,
                    "adjusted_effect": 0.0, "adjusted_ci_lower": 0.0,
                    "adjusted_ci_upper": 0.0, "imputed_studies": []}

        # Original pooled estimate
        pooled_orig = self._random_effects(studies) if model == "random" else self._fixed_effect(studies)
        pooled_log = math.log(pooled_orig["effect"])

        # Center effect sizes around the pooled estimate
        centered = sorted(
            [(s, s.log_effect - pooled_log) for s in studies],
            key=lambda x: x[1],
        )

        # Right-truncation version of the R-estimator
        # Count how many studies need trimming from the right tail
        k = len(studies)
        gamma_plus = sum(1 for _, c in centered if c > 0)
        gamma_minus = k - gamma_plus

        # Simple rank-based estimator for number of missing studies
        # n_0 = (k - |S_rank|) / 2  where S_rank is the sign-rank statistic
        sign_ranks = []
        for i, (_, c) in enumerate(centered):
            rank = i + 1
            sign = 1 if c >= 0 else -1
            sign_ranks.append(sign * rank)
        S = sum(sign_ranks)
        n_missing = max(0, round((k - abs(S) / (k * (k + 1) / (2 * k))) / 2))
        # Clamp to a reasonable value
        n_missing = min(n_missing, k)

        # Impute missing studies by mirror-imputation
        imputed_details = []
        if n_missing > 0:
            # Take the n_missing studies closest to the center and mirror them
            sorted_by_abs = sorted(studies, key=lambda s: abs(s.log_effect - pooled_log))
            imputed_studies = []
            for idx in range(n_missing):
                orig = sorted_by_abs[idx]
                mirrored_log = 2 * pooled_log - orig.log_effect
                imp = StudyResult(
                    name=f"Imputed_{idx + 1}",
                    effect=round(math.exp(mirrored_log), 4),
                    ci_lower=round(math.exp(mirrored_log - 1.96 * orig.log_se), 4),
                    ci_upper=round(math.exp(mirrored_log + 1.96 * orig.log_se), 4),
                    weight=orig.weight,
                    log_effect=mirrored_log,
                    log_se=orig.log_se,
                    subgroup="",
                )
                imputed_studies.append(imp)
                imputed_details.append({"name": imp.name, "effect": imp.effect,
                                        "ci_lower": imp.ci_lower, "ci_upper": imp.ci_upper})

            all_studies = list(studies) + imputed_studies
            pooled_adj = self._random_effects(all_studies) if model == "random" else self._fixed_effect(all_studies)
        else:
            pooled_adj = pooled_orig

        return {
            "estimated_missing": n_missing,
            "original_effect": round(pooled_orig["effect"], 4),
            "original_ci_lower": round(pooled_orig["ci_lower"], 4),
            "original_ci_upper": round(pooled_orig["ci_upper"], 4),
            "original_p_value": round(pooled_orig["p_value"], 4),
            "adjusted_effect": round(pooled_adj["effect"], 4),
            "adjusted_ci_lower": round(pooled_adj["ci_lower"], 4),
            "adjusted_ci_upper": round(pooled_adj["ci_upper"], 4),
            "adjusted_p_value": round(pooled_adj["p_value"], 4),
            "imputed_studies": imputed_details,
        }

    def meta_regression(self, studies: List[StudyResult], covariate: List[float],
                        covariate_name: str = "covariate") -> dict:
        """Meta-regression using weighted least squares.

        Regresses log effect sizes on a covariate, weighted by inverse-variance.
        Returns coefficient, p-value, R-squared, and predicted values.

        Parameters
        ----------
        studies : list of StudyResult
            Study results (log_effect, log_se used).
        covariate : list of float
            Numeric covariate values (same length as studies), e.g. sample size,
            publication year, drug dose.
        covariate_name : str
            Label for the covariate (cosmetic).
        """
        if len(studies) < 3:
            return {"error": "At least 3 studies required for meta-regression",
                    "covariate_name": covariate_name}

        n = len(studies)
        if len(covariate) != n:
            return {"error": f"Covariate length ({len(covariate)}) must match studies ({n})",
                    "covariate_name": covariate_name}

        # Vectors
        y = np.array([s.log_effect for s in studies], dtype=float)
        w = np.array([1.0 / (s.log_se ** 2) for s in studies], dtype=float)
        x = np.array(covariate, dtype=float)

        # Weighted centring
        W = np.sum(w)
        x_bar_w = float(np.sum(w * x) / W)
        y_bar_w = float(np.sum(w * y) / W)

        x_c = x - x_bar_w
        y_c = y - y_bar_w

        # Weighted regression: beta = sum(w*x_c*y_c) / sum(w*x_c^2)
        ss_xx = float(np.sum(w * x_c ** 2))
        ss_xy = float(np.sum(w * x_c * y_c))

        if ss_xx < 1e-15:
            return {"error": "Covariate has zero (weighted) variance",
                    "covariate_name": covariate_name}

        beta = ss_xy / ss_xx
        intercept = y_bar_w - beta * x_bar_w

        # Predicted values & residuals
        y_pred = intercept + beta * x
        residuals = y - y_pred

        # Weighted residual variance (tau^2 analogue)
        # WLS residual MSE with k-2 degrees of freedom
        weighted_sse = float(np.sum(w * residuals ** 2))
        mse = weighted_sse / (n - 2) if n > 2 else 0.0

        # R-squared: proportion of heterogeneity explained by covariate
        # Q_total and Q_residual
        q_total = float(np.sum(w * y_c ** 2))
        q_resid = weighted_sse
        r_squared = max(0.0, 1.0 - q_resid / q_total) if q_total > 0 else 0.0

        # Standard error of beta
        se_beta = math.sqrt(mse / ss_xx) if ss_xx > 0 else 0.0
        se_intercept = math.sqrt(mse * (1.0 / W + x_bar_w ** 2 / ss_xx)) if ss_xx > 0 else 0.0

        # Wald test for beta
        z = beta / se_beta if se_beta > 0 else 0.0
        p_value = float(2 * (1 - sp_stats.norm.cdf(abs(z))))
        # Intercept test
        t_int = intercept / se_intercept if se_intercept > 0 else 0.0
        intercept_p = float(2 * (1 - sp_stats.norm.cdf(abs(t_int))))

        # Predicted curve (100 points across covariate range)
        x_range = np.linspace(float(np.min(x)), float(np.max(x)), 100)
        y_pred_curve = intercept + beta * x_range
        curve_points = [
            {"x": round(float(xv), 4),
             "y_effect": round(float(math.exp(yv)), 4),
             "y_log_effect": round(float(yv), 4)}
            for xv, yv in zip(x_range, y_pred_curve)
        ]

        # Prediction intervals (95%)
        pred_se = np.sqrt(mse * (1.0 / W + (x_range - x_bar_w) ** 2 / ss_xx))

        curve_with_ci = []
        for xv, yv, sev in zip(x_range, y_pred_curve, pred_se):
            curve_with_ci.append({
                "x": round(float(xv), 4),
                "y_log_effect": round(float(yv), 4),
                "y_effect": round(float(math.exp(yv)), 4),
                "ci_lower": round(float(math.exp(yv - 1.96 * sev)), 4),
                "ci_upper": round(float(math.exp(yv + 1.96 * sev)), 4),
            })

        # Q-statistic for residual heterogeneity
        q_resid_p = float(1 - sp_stats.chi2.cdf(q_resid, n - 2)) if n > 2 else 1.0

        return {
            "covariate_name": covariate_name,
            "n_studies": n,
            "coefficient": round(float(beta), 6),
            "coefficient_se": round(float(se_beta), 6),
            "coefficient_ci_lower": round(float(beta - 1.96 * se_beta), 6),
            "coefficient_ci_upper": round(float(beta + 1.96 * se_beta), 6),
            "p_value": round(float(p_value), 6),
            "intercept": round(float(intercept), 6),
            "intercept_se": round(float(se_intercept), 6),
            "intercept_p_value": round(float(intercept_p), 6),
            "r_squared": round(float(r_squared), 4),
            "residual_q": round(float(q_resid), 4),
            "residual_q_p": round(float(q_resid_p), 4),
            "curve": curve_with_ci,
        }

    def dose_response(self, studies: List[StudyResult], doses: List[float],
                      num_points: int = 50) -> dict:
        """Dose-response meta-analysis.

        Fits a linear and restricted-cubic-spline model of log-effect vs dose.

        Parameters
        ----------
        studies : list of StudyResult
            Study results.
        doses : list of float
            Dose / exposure level for each study (same length as studies).
        num_points : int
            Number of points on the fitted curve.
        """
        if len(studies) < 3:
            return {"error": "At least 3 studies required for dose-response analysis"}

        n = len(studies)
        if len(doses) != n:
            return {"error": f"Doses length ({len(doses)}) must match studies ({n})"}

        y = np.array([s.log_effect for s in studies], dtype=float)
        w = np.array([1.0 / (s.log_se ** 2) for s in studies], dtype=float)
        d = np.array(doses, dtype=float)

        d_min, d_max = float(np.min(d)), float(np.max(d))
        d_range = np.linspace(d_min, d_max, num_points)

        # --- Linear model ---
        W = float(np.sum(w))
        d_bar = float(np.sum(w * d) / W)
        y_bar = float(np.sum(w * y) / W)
        d_c = d - d_bar
        ss_dd = float(np.sum(w * d_c ** 2))
        ss_dy = float(np.sum(w * d_c * y))

        if ss_dd < 1e-15:
            return {"error": "Zero variance in doses"}

        beta_lin = ss_dy / ss_dd
        alpha_lin = y_bar - beta_lin * d_bar

        y_lin = alpha_lin + beta_lin * d
        resid_lin = y - y_lin
        sse_lin = float(np.sum(w * resid_lin ** 2))
        sst = float(np.sum(w * (y - y_bar) ** 2))
        r2_lin = max(0.0, 1.0 - sse_lin / sst) if sst > 0 else 0.0
        mse_lin = sse_lin / (n - 2) if n > 2 else 0.0
        se_beta_lin = math.sqrt(mse_lin / ss_dd) if ss_dd > 0 else 0.0
        z_lin = beta_lin / se_beta_lin if se_beta_lin > 0 else 0.0
        p_lin = float(2 * (1 - sp_stats.norm.cdf(abs(z_lin))))

        # Linear curve with CI
        lin_se = np.sqrt(mse_lin * (1.0 / W + (d_range - d_bar) ** 2 / ss_dd))
        linear_curve = []
        for dv, yv, sev in zip(d_range, alpha_lin + beta_lin * d_range, lin_se):
            linear_curve.append({
                "dose": round(float(dv), 4),
                "log_effect": round(float(yv), 4),
                "effect": round(float(math.exp(yv)), 4),
                "ci_lower": round(float(math.exp(yv - 1.96 * sev)), 4),
                "ci_upper": round(float(math.exp(yv + 1.96 * sev)), 4),
            })

        # --- Restricted Cubic Spline (3 knots) ---
        # Knots at 10th, 50th, 90th percentiles
        knots = np.percentile(d, [10, 50, 90])
        k1, k2, k3 = float(knots[0]), float(knots[1]), float(knots[2])

        def _rcs_basis(xv, k1, k2, k3):
            """Compute RCS basis functions for a single value."""
            d_k1 = np.maximum(xv - k1, 0.0) ** 3
            d_k2 = np.maximum(xv - k2, 0.0) ** 3
            d_k3 = np.maximum(xv - k3, 0.0) ** 3
            denom = k3 - k1
            if abs(denom) < 1e-12:
                return 0.0
            j = d_k1 - (k3 - k1) / (k3 - k2) * d_k2 + (k2 - k1) / (k3 - k1) * d_k3
            return float(j)

        # Design matrix: intercept, x, spline term
        X = np.zeros((n, 3))
        X[:, 0] = 1.0
        X[:, 1] = d
        X[:, 2] = np.array([_rcs_basis(di, k1, k2, k3) for di in d])

        # Weighted least squares: (X'WX)^{-1} X'Wy
        W_diag = np.diag(w)
        XtW = X.T @ W_diag
        XtWX = XtW @ X
        XtWy = XtW @ y

        try:
            beta_spline = np.linalg.solve(XtWX, XtWy)
        except np.linalg.LinAlgError:
            beta_spline = np.linalg.lstsq(XtWX, XtWy, rcond=None)[0]

        y_spline_pred = X @ beta_spline
        resid_spline = y - y_spline_pred
        sse_spline = float(np.sum(w * resid_spline ** 2))
        r2_spline = max(0.0, 1.0 - sse_spline / sst) if sst > 0 else 0.0

        # Spline curve
        X_pred = np.zeros((num_points, 3))
        X_pred[:, 0] = 1.0
        X_pred[:, 1] = d_range
        X_pred[:, 2] = np.array([_rcs_basis(di, k1, k2, k3) for di in d_range])
        y_spline_curve = X_pred @ beta_spline

        # Approximate SE via (X'WX)^{-1} diagonal
        try:
            cov_beta = np.linalg.inv(XtWX)
        except np.linalg.LinAlgError:
            cov_beta = np.linalg.pinv(XtWX)

        spline_curve = []
        for i, dv in enumerate(d_range):
            xv = X_pred[i:i+1, :]
            var_pred = float((xv @ cov_beta @ xv.T).item())
            se_pred = math.sqrt(max(var_pred, 0))
            yv = float(y_spline_curve[i])
            spline_curve.append({
                "dose": round(float(dv), 4),
                "log_effect": round(float(yv), 4),
                "effect": round(float(math.exp(yv)), 4),
                "ci_lower": round(float(math.exp(yv - 1.96 * se_pred)), 4),
                "ci_upper": round(float(math.exp(yv + 1.96 * se_pred)), 4),
            })

        # Likelihood ratio test: spline vs linear
        # Under H0 (linear), -2*log-likelihood diff ~ chi2(1)
        lr_stat = sse_lin - sse_spline
        lr_p = float(1 - sp_stats.chi2.cdf(max(lr_stat, 0), 1))

        # Non-linearity test (Wald test on spline coefficient)
        se_spline_coef = math.sqrt(max(float(cov_beta[2, 2]), 0))
        z_nl = float(beta_spline[2]) / se_spline_coef if se_spline_coef > 0 else 0.0
        nl_p = float(2 * (1 - sp_stats.norm.cdf(abs(z_nl))))

        return {
            "n_studies": n,
            "dose_range": [round(d_min, 4), round(d_max, 4)],
            "knots": [round(k1, 4), round(k2, 4), round(k3, 4)],
            "linear": {
                "coefficient": round(float(beta_lin), 6),
                "coefficient_se": round(float(se_beta_lin), 6),
                "p_value": round(float(p_lin), 6),
                "r_squared": round(float(r2_lin), 4),
                "curve": linear_curve,
            },
            "spline": {
                "coefficients": [round(float(b), 6) for b in beta_spline],
                "r_squared": round(float(r2_spline), 4),
                "curve": spline_curve,
                "nonlinearity_test_p": round(float(nl_p), 6),
                "lr_test_p": round(float(lr_p), 6),
            },
            "study_points": [
                {"dose": round(float(di), 4), "effect": round(float(math.exp(yi)), 4),
                 "log_effect": round(float(yi), 4), "weight": round(float(wi), 4)}
                for di, yi, wi in zip(d, y, w)
            ],
        }

    def _forest_plot(self, studies: List[StudyResult], pooled: dict, measure: str) -> str:
        """生成SVG森林图"""
        n = len(studies) + 2  # studies + pooled + spacing
        w = 700
        h = max(300, n * 32 + 80)
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        svg += f'<rect width="{w}" height="{h}" fill="#0d1117"/>'
        svg += f'<text x="{w//2}" y="28" text-anchor="middle" fill="#e6edf3" font-size="16" font-weight="bold" font-family="Inter,sans-serif">Forest Plot — {measure} (95% CI)</text>'

        # Column headers
        y = 50
        svg += f'<text x="10" y="{y}" fill="#8b949e" font-size="12" font-family="Inter,sans-serif">Study</text>'
        svg += f'<text x="350" y="{y}" fill="#8b949e" font-size="12" font-family="Inter,sans-serif">{measure}</text>'
        svg += f'<text x="430" y="{y}" fill="#8b949e" font-size="12" font-family="Inter,sans-serif">95% CI</text>'
        svg += f'<text x="560" y="{y}" fill="#8b949e" font-size="12" font-family="Inter,sans-serif">Weight</text>'
        svg += f'<line x1="10" y1="{y+5}" x2="{w-10}" y2="{y+5}" stroke="#30363d" stroke-width="1"/>'

        y += 20

        # Log scale mapping
        all_log_effects = [s.log_effect for s in studies] + [math.log(pooled["ci_lower"]), math.log(pooled["ci_upper"])]
        log_min = min(all_log_effects) - 0.3
        log_max = max(all_log_effects) + 0.3
        plot_x = 180
        plot_w = 150

        def map_x(log_val):
            return plot_x + (log_val - log_min) / (log_max - log_min) * plot_w

        # Null line (OR=1 or RR=1)
        null_x = map_x(0)
        svg += f'<line x1="{null_x}" y1="{y-5}" x2="{null_x}" y2="{y + len(studies)*28 + 10}" stroke="#484f58" stroke-width="1" stroke-dasharray="4,3"/>'

        # Individual studies
        max_w = max(s.weight for s in studies)
        for i, s in enumerate(studies):
            cy = y + i * 28 + 12
            # Study name
            svg += f'<text x="10" y="{cy+4}" fill="#e6edf3" font-size="12" font-family="Inter,sans-serif">{s.name}</text>'
            # Effect value
            svg += f'<text x="350" y="{cy+4}" fill="#e6edf3" font-size="11" font-family="JetBrains Mono,monospace">{s.effect:.2f}</text>'
            # CI
            svg += f'<text x="430" y="{cy+4}" fill="#8b949e" font-size="11" font-family="JetBrains Mono,monospace">[{s.ci_lower:.2f}, {s.ci_upper:.2f}]</text>'
            # Weight
            svg += f'<text x="560" y="{cy+4}" fill="#8b949e" font-size="11" font-family="JetBrains Mono,monospace">{s.weight/max_w*100:.1f}%</text>'
            # CI line
            x1 = map_x(math.log(s.ci_lower))
            x2 = map_x(math.log(s.ci_upper))
            xm = map_x(s.log_effect)
            svg += f'<line x1="{x1}" y1="{cy}" x2="{x2}" y2="{cy}" stroke="#58a6ff" stroke-width="2"/>'
            # Point estimate (size proportional to weight)
            r = 3 + (s.weight / max_w) * 6
            svg += f'<circle cx="{xm}" cy="{cy}" r="{r}" fill="#58a6ff"/>'

        # Pooled estimate
        py = y + len(studies) * 28 + 20
        svg += f'<line x1="10" y1="{py-8}" x2="{w-10}" y2="{py-8}" stroke="#30363d" stroke-width="1"/>'
        svg += f'<text x="10" y="{py+4}" fill="#f0883e" font-size="13" font-weight="bold" font-family="Inter,sans-serif">Pooled ({pooled["effect"]:.2f})</text>'
        px1 = map_x(math.log(pooled["ci_lower"]))
        px2 = map_x(math.log(pooled["ci_upper"]))
        pxm = map_x(math.log(pooled["effect"]))
        svg += f'<line x1="{px1}" y1="{py}" x2="{px2}" y2="{py}" stroke="#f0883e" stroke-width="3"/>'
        svg += f'<rect x="{pxm-6}" y="{py-6}" width="12" height="12" fill="#f0883e"/>'
        svg += f'<text x="350" y="{py+4}" fill="#f0883e" font-size="12" font-weight="bold" font-family="JetBrains Mono,monospace">{pooled["effect"]:.2f}</text>'
        svg += f'<text x="430" y="{py+4}" fill="#f0883e" font-size="11" font-family="JetBrains Mono,monospace">[{pooled["ci_lower"]:.2f}, {pooled["ci_upper"]:.2f}]</text>'

        svg += '</svg>'
        return svg

    def _funnel_plot(self, studies: List[StudyResult], pooled: dict) -> str:
        """生成SVG漏斗图"""
        w, h = 500, 400
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        svg += f'<rect width="{w}" height="{h}" fill="#0d1117"/>'
        svg += f'<text x="{w//2}" y="28" text-anchor="middle" fill="#e6edf3" font-size="16" font-weight="bold" font-family="Inter,sans-serif">Funnel Plot — Publication Bias</text>'

        cx, cy = w // 2, h // 2 + 20
        plot_r = 150

        # Draw funnel contours
        for se_level, alpha in [(0.05, 0.08), (0.1, 0.06), (0.2, 0.04)]:
            y_offset = (se_level / 0.5) * plot_r
            svg += f'<polygon points="{cx},{cy-y_offset} {cx+plot_r},{cy+plot_r} {cx-plot_r},{cy+plot_r}" fill="none" stroke="#30363d" stroke-width="1" opacity="0.5"/>'

        # Null line
        svg += f'<line x1="{cx}" y1="{cy-plot_r}" x2="{cx}" y2="{cy+plot_r}" stroke="#484f58" stroke-width="1" stroke-dasharray="4,3"/>'

        # Plot each study
        max_se = max(s.log_se for s in studies) if studies else 0.5
        for s in studies:
            x = cx + (s.log_effect - math.log(pooled["effect"])) / (2 * max_se) * plot_r
            y = cy + (s.log_se / max_se) * plot_r * 0.8
            svg += f'<circle cx="{x}" cy="{y}" r="6" fill="#58a6ff" opacity="0.8"/>'

        # Pooled estimate
        pe_log = math.log(pooled["effect"])
        pooled_x = cx + (pe_log - pe_log)/(2*max_se)*plot_r
        svg += f'<line x1="{pooled_x}" y1="{cy-plot_r*0.5}" x2="{cx}" y2="{cy+plot_r}" stroke="#f0883e" stroke-width="2" stroke-dasharray="6,3"/>'

        # Axes
        svg += f'<text x="{cx}" y="{cy+plot_r+25}" text-anchor="middle" fill="#8b949e" font-size="11" font-family="Inter,sans-serif">Log Effect Size</text>'
        svg += f'<text x="20" y="{cy}" fill="#8b949e" font-size="11" font-family="Inter,sans-serif" transform="rotate(-90,20,{cy})">Standard Error</text>'

        svg += '</svg>'
        return svg

    def _galbraith_plot(self, studies: List[StudyResult], pooled: dict) -> str:
        """Generate Galbraith (radial) plot SVG.

        X-axis: 1 / SE (precision)
        Y-axis: effect / SE (z-statistic)
        The reference line through the origin with slope = pooled effect.
        Studies far from the line may be sources of heterogeneity.
        """
        w, h = 560, 460
        margin = 50
        plot_w = w - 2 * margin
        plot_h = h - 2 * margin

        precisions = [1.0 / s.log_se for s in studies if s.log_se > 1e-12]
        z_stats = [s.log_effect / s.log_se for s in studies if s.log_se > 1e-12]

        if not precisions:
            return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><text x="{w//2}" y="{h//2}" text-anchor="middle" fill="#8b949e">No data</text></svg>'

        prec_arr = np.array(precisions)
        z_arr = np.array(z_stats)

        # Pooled effect (slope of reference line)
        pooled_log = math.log(pooled["effect"]) if pooled["effect"] > 0 else 0.0
        # For continuous data, the pooled "effect" may be negative or non-logarithmic
        # We use log_effect from the pooled calculation if available
        # Use the weighted mean of log_effects as the slope
        total_w = sum(s.weight for s in studies)
        if total_w > 0:
            pooled_slope = sum(s.weight * s.log_effect for s in studies) / total_w
        else:
            pooled_slope = 0.0

        # Data ranges
        prec_max = float(np.max(prec_arr)) * 1.15
        prec_min = 0.0
        z_abs_max = max(float(np.max(np.abs(z_arr))), abs(pooled_slope) * prec_max) * 1.15

        def map_x(prec):
            return margin + (prec - prec_min) / (prec_max - prec_min) * plot_w if prec_max > prec_min else margin + plot_w / 2

        def map_y(z_val):
            return margin + plot_h - (z_val - (-z_abs_max)) / (2 * z_abs_max) * plot_h

        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        svg += f'<rect width="{w}" height="{h}" fill="#0d1117"/>'
        svg += f'<text x="{w//2}" y="28" text-anchor="middle" fill="#e6edf3" font-size="16" font-weight="bold" font-family="Inter,sans-serif">Galbraith Plot (Radial)</text>'

        # Grid lines
        for tick in np.linspace(prec_min, prec_max, 6):
            tx = map_x(float(tick))
            svg += f'<line x1="{tx}" y1="{margin}" x2="{tx}" y2="{margin+plot_h}" stroke="#21262d" stroke-width="1"/>'
        for tick in np.linspace(-z_abs_max, z_abs_max, 7):
            ty = map_y(float(tick))
            svg += f'<line x1="{margin}" y1="{ty}" x2="{margin+plot_w}" y2="{ty}" stroke="#21262d" stroke-width="1"/>'

        # Axes
        svg += f'<line x1="{margin}" y1="{margin+plot_h}" x2="{margin+plot_w}" y2="{margin+plot_h}" stroke="#30363d" stroke-width="1.5"/>'
        svg += f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{margin+plot_h}" stroke="#30363d" stroke-width="1.5"/>'

        # Reference line (through origin, slope = pooled effect)
        line_x1 = 0.0
        line_y1 = 0.0
        line_x2 = prec_max
        line_y2 = pooled_slope * prec_max
        svg += f'<line x1="{map_x(line_x1)}" y1="{map_y(line_y1)}" x2="{map_x(line_x2)}" y2="{map_y(line_y2)}" stroke="#f0883e" stroke-width="2"/>'

        # 95% CI reference lines (at ±1.96)
        svg += f'<line x1="{map_x(0)}" y1="{map_y(1.96)}" x2="{map_x(prec_max)}" y2="{map_y(pooled_slope*prec_max + 1.96)}" stroke="#484f58" stroke-width="1" stroke-dasharray="4,3"/>'
        svg += f'<line x1="{map_x(0)}" y1="{map_y(-1.96)}" x2="{map_x(prec_max)}" y2="{map_y(pooled_slope*prec_max - 1.96)}" stroke="#484f58" stroke-width="1" stroke-dasharray="4,3"/>'

        # Plot studies
        for prec, z_val in zip(precisions, z_stats):
            cx_pt = map_x(prec)
            cy_pt = map_y(z_val)
            svg += f'<circle cx="{cx_pt}" cy="{cy_pt}" r="5" fill="#58a6ff" opacity="0.85"/>'

        # Axis labels
        svg += f'<text x="{margin + plot_w//2}" y="{h - 8}" text-anchor="middle" fill="#8b949e" font-size="12" font-family="Inter,sans-serif">Precision (1/SE)</text>'
        svg += f'<text x="14" y="{margin + plot_h//2}" text-anchor="middle" fill="#8b949e" font-size="12" font-family="Inter,sans-serif" transform="rotate(-90,14,{margin + plot_h//2})">z = Effect / SE</text>'

        # Tick labels
        for tick in np.linspace(prec_min, prec_max, 6):
            tx = map_x(float(tick))
            svg += f'<text x="{tx}" y="{margin+plot_h+16}" text-anchor="middle" fill="#8b949e" font-size="10" font-family="JetBrains Mono,monospace">{float(tick):.1f}</text>'
        for tick in np.linspace(-z_abs_max, z_abs_max, 7):
            ty = map_y(float(tick))
            svg += f'<text x="{margin-8}" y="{ty+4}" text-anchor="end" fill="#8b949e" font-size="10" font-family="JetBrains Mono,monospace">{float(tick):.1f}</text>'

        svg += '</svg>'
        return svg

    def _labbe_plot(self, studies: List[StudyResult], studies_input: List[StudyInput],
                    pooled: dict) -> str:
        """Generate L'Abbe plot SVG.

        For dichotomous data: plots event rate in treatment vs control groups.
        For continuous data: plots mean in treatment vs control groups.
        The diagonal line (y=x) represents no treatment effect.
        """
        w, h = 500, 500
        margin = 60
        plot_w = w - 2 * margin
        plot_h = h - 2 * margin

        if not studies_input:
            return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><text x="{w//2}" y="{h//2}" text-anchor="middle" fill="#8b949e">No data</text></svg>'

        is_continuous = studies_input[0].data_type == "continuous"

        if is_continuous:
            x_vals = [s.c_mean for s in studies_input]
            y_vals = [s.e_mean for s in studies_input]
            x_label = "Control Group Mean"
            y_label = "Experimental Group Mean"
        else:
            x_vals = []
            y_vals = []
            for s in studies_input:
                c_rate = s.c_events / s.c_total if s.c_total > 0 else 0.0
                e_rate = s.e_events / s.e_total if s.e_total > 0 else 0.0
                x_vals.append(c_rate)
                y_vals.append(e_rate)
            x_label = "Control Group Event Rate"
            y_label = "Experimental Group Event Rate"

        x_arr = np.array(x_vals, dtype=float)
        y_arr = np.array(y_vals, dtype=float)

        x_min = max(0, float(np.min(x_arr)) * 0.85)
        x_max = float(np.max(x_arr)) * 1.15
        y_min = max(0, float(np.min(y_arr)) * 0.85)
        y_max = float(np.max(y_arr)) * 1.15

        # Make axes equal range for visual clarity
        val_min = min(x_min, y_min)
        val_max = max(x_max, y_max)
        x_min = y_min = val_min
        x_max = y_max = val_max

        def map_x(val):
            return margin + (val - x_min) / (x_max - x_min) * plot_w if x_max > x_min else margin + plot_w / 2

        def map_y(val):
            return margin + plot_h - (val - y_min) / (y_max - y_min) * plot_h if y_max > y_min else margin + plot_h / 2

        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        svg += f'<rect width="{w}" height="{h}" fill="#0d1117"/>'
        svg += f'<text x="{w//2}" y="30" text-anchor="middle" fill="#e6edf3" font-size="16" font-weight="bold" font-family="Inter,sans-serif">L\'Abbé Plot</text>'

        # Grid lines
        for tick in np.linspace(x_min, x_max, 6):
            tx = map_x(float(tick))
            svg += f'<line x1="{tx}" y1="{margin}" x2="{tx}" y2="{margin+plot_h}" stroke="#21262d" stroke-width="1"/>'
            svg += f'<text x="{tx}" y="{margin+plot_h+16}" text-anchor="middle" fill="#8b949e" font-size="10" font-family="JetBrains Mono,monospace">{float(tick):.2f}</text>'
        for tick in np.linspace(y_min, y_max, 6):
            ty = map_y(float(tick))
            svg += f'<line x1="{margin}" y1="{ty}" x2="{margin+plot_w}" y2="{ty}" stroke="#21262d" stroke-width="1"/>'
            svg += f'<text x="{margin-8}" y="{ty+4}" text-anchor="end" fill="#8b949e" font-size="10" font-family="JetBrains Mono,monospace">{float(tick):.2f}</text>'

        # Axes
        svg += f'<line x1="{margin}" y1="{margin+plot_h}" x2="{margin+plot_w}" y2="{margin+plot_h}" stroke="#30363d" stroke-width="1.5"/>'
        svg += f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{margin+plot_h}" stroke="#30363d" stroke-width="1.5"/>'

        # Diagonal line (no effect line: y = x)
        svg += f'<line x1="{map_x(x_min)}" y1="{map_y(y_min)}" x2="{map_x(x_max)}" y2="{map_y(y_max)}" stroke="#f0883e" stroke-width="2" stroke-dasharray="6,3"/>'

        # Plot studies with labels
        for i, (xv, yv) in enumerate(zip(x_vals, y_vals)):
            cx_pt = map_x(xv)
            cy_pt = map_y(yv)
            svg += f'<circle cx="{cx_pt}" cy="{cy_pt}" r="6" fill="#58a6ff" opacity="0.85"/>'
            # Add study name label
            name = studies_input[i].name if i < len(studies_input) else ""
            if name:
                svg += f'<text x="{cx_pt+8}" y="{cy_pt-6}" fill="#8b949e" font-size="9" font-family="Inter,sans-serif">{name}</text>'

        # Axis labels
        svg += f'<text x="{margin + plot_w//2}" y="{h - 8}" text-anchor="middle" fill="#8b949e" font-size="12" font-family="Inter,sans-serif">{x_label}</text>'
        svg += f'<text x="14" y="{margin + plot_h//2}" text-anchor="middle" fill="#8b949e" font-size="12" font-family="Inter,sans-serif" transform="rotate(-90,14,{margin+plot_h//2})">{y_label}</text>'

        # No-effect legend
        svg += f'<text x="{margin + plot_w - 5}" y="{margin + 15}" text-anchor="end" fill="#f0883e" font-size="10" font-family="Inter,sans-serif">No effect (y=x)</text>'

        svg += '</svg>'
        return svg


# ============================================================
# PRISMA 流程图生成
# ============================================================

def generate_prisma_svg(total_found: int = 3821, after_dedup: int = 2947,
                        after_screen: int = 486, included: int = 52) -> str:
    """生成PRISMA 2020流程图SVG"""
    w, h = 700, 650
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
    svg += f'<rect width="{w}" height="{h}" fill="#0d1117"/>'
    svg += f'<text x="{w//2}" y="30" text-anchor="middle" fill="#e6edf3" font-size="16" font-weight="bold" font-family="Inter,sans-serif">PRISMA 2020 Flow Diagram</text>'

    boxes = [
        (350, 70, f"Records identified (n={total_found})", "#1f6feb"),
        (350, 150, f"After deduplication (n={after_dedup})", "#1f6feb"),
        (150, 230, f"Excluded (n={after_dedup - after_screen})", "#da3633"),
        (550, 230, f"Screened (n={after_dedup})", "#1f6feb"),
        (550, 320, f"Assessed for eligibility (n={after_screen})", "#1f6feb"),
        (150, 320, f"Excluded (n={after_screen - included})", "#da3633"),
        (550, 420, f"Studies included (n={included})", "#238636"),
    ]

    for x, y, text, color in boxes:
        rx, ry = 140, 30
        svg += f'<rect x="{x-rx}" y="{y-ry}" width="{rx*2}" height="{ry*2}" rx="8" fill="{color}" opacity="0.15" stroke="{color}" stroke-width="2"/>'
        svg += f'<text x="{x}" y="{y+5}" text-anchor="middle" fill="{color}" font-size="13" font-weight="600" font-family="Inter,sans-serif">{text}</text>'

    # Arrows
    arrows = [(350, 100, 350, 120), (350, 180, 550, 200), (350, 180, 150, 200),
              (550, 260, 550, 290), (550, 260, 150, 290), (550, 350, 550, 390)]
    for x1, y1, x2, y2 in arrows:
        svg += f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#8b949e" stroke-width="1.5" marker-end="url(#arrow)"/>'

    svg += '<defs><marker id="arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#8b949e"/></marker></defs>'
    svg += '</svg>'
    return svg


# ============================================================
# 全局状态
# ============================================================

projects_db: Dict[str, dict] = {}
engine = MetaAnalysisEngine()

# ============================================================
# User System & AI Simulation — In-Memory Stores
# ============================================================

# Initialize database on startup
@app.on_event("startup")
async def startup():
    init_db()


def _get_current_user(request: Request) -> tuple:
    """Extract user from Authorization header (Bearer token). Returns (user, db) tuple."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header. Use: Bearer <token>")
    token = auth[7:]
    payload = validate_token(token)
    if not payload:
        raise HTTPException(401, "Invalid or expired session token")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == payload["user_id"]).first()
        if not user:
            raise HTTPException(401, "User not found")
        return user, db
    except:
        db.close()
        raise

# ============================================================
# API 端点
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def index():
    """Landing Page"""
    html_path = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>MetaForge</h1><p>index.html not found</p>")


@app.get("/app", response_class=HTMLResponse)
async def app_page():
    """Web工作台"""
    tpl_path = os.path.join(BASE_DIR, "app", "templates", "app.html")
    if os.path.exists(tpl_path):
        with open(tpl_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Workbench not found</h1>")


@app.get("/api/health")
async def health():
    return {"status": "healthy", "version": "3.0.0", "timestamp": datetime.now().isoformat()}


@app.post("/api/analyze")
async def api_analyze(request: Request):
    """执行Meta分析 — 核心闭环端点"""
    body = await request.json()
    studies_data = body.get("studies", [])
    model = body.get("model", "random")
    effect_measure = body.get("effect_measure", "OR")

    if len(studies_data) < 2:
        raise HTTPException(400, "至少需要2个研究")

    # Track API usage for authenticated users
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            token = auth[7:]
            payload = validate_token(token)
            if payload:
                db = SessionLocal()
                try:
                    user = db.query(User).filter(User.id == payload["user_id"]).first()
                    if user:
                        if not check_api_quota(user):
                            raise HTTPException(429, "API quota exceeded. Upgrade your plan.")
                        increment_api_usage(user, db)
                        # Log usage
                        usage = APIUsage(
                            user_id=user.id,
                            endpoint="/api/analyze",
                            response_ms=0,
                        )
                        db.add(usage)
                        db.commit()
                finally:
                    db.close()
        except HTTPException:
            raise
        except:
            pass  # Allow anonymous usage

    studies = [StudyInput(**s) for s in studies_data]

    try:
        result = engine.analyze(studies, model=model, effect_measure=effect_measure)
        return asdict(result)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/demo")
async def api_demo():
    """运行演示 — 一键生成完整Meta分析"""
    # 示例数据: PD-1抑制剂联合化疗 vs 单药化疗治疗NSCLC
    demo_studies = [
        StudyInput("Gandhi 2018", 138, 292, 108, 288, "Phase III"),
        StudyInput("Paz-Ares 2018", 171, 292, 134, 291, "Phase III"),
        StudyInput("West 2019", 117, 241, 89, 238, "Phase III"),
        StudyInput("Carbone 2017", 104, 199, 81, 200, "Phase III"),
        StudyInput("Reck 2016", 92, 185, 71, 183, "Phase III"),
        StudyInput("Herbst 2016", 69, 143, 55, 141, "Phase II"),
        StudyInput("Langer 2016", 48, 98, 37, 97, "Phase II"),
        StudyInput("Rittmeyer 2017", 102, 201, 78, 199, "Phase III"),
        StudyInput("Barlesi 2016", 88, 177, 66, 176, "Phase III"),
        StudyInput("Brahmer 2015", 45, 131, 28, 129, "Phase II"),
    ]

    result = engine.analyze(demo_studies, model="random", effect_measure="OR")

    # Generate PRISMA SVG
    prisma_svg = generate_prisma_svg(3821, 2947, 486, 10)

    result_dict = asdict(result)
    result_dict["prisma_svg"] = prisma_svg

    return result_dict


@app.post("/api/prisma")
async def api_prisma(request: Request):
    """生成PRISMA流程图"""
    body = await request.json()
    total = body.get("total_found", 3821)
    dedup = body.get("after_dedup", 2947)
    screen = body.get("after_screen", 486)
    included = body.get("included", 52)
    svg = generate_prisma_svg(total, dedup, screen, included)
    return {"svg": svg}


@app.post("/api/forest")
async def api_forest(request: Request):
    """单独生成森林图"""
    body = await request.json()
    studies_data = body.get("studies", [])
    effect_measure = body.get("effect_measure", "OR")

    studies = [StudyInput(**s) for s in studies_data]
    is_continuous = studies and studies[0].data_type == "continuous"
    if is_continuous:
        if effect_measure in ("OR", "RR"):
            effect_measure = "SMD"
        srs = [engine._calc_continuous(s, effect_measure) for s in studies]
    else:
        srs = [engine._calc_dichotomous(s, effect_measure) for s in studies]
    pooled = engine._fixed_effect(srs, use_log_scale=not is_continuous)
    svg = engine._forest_plot(srs, pooled, effect_measure)
    return {"svg": svg, "pooled": pooled}


@app.post("/api/funnel")
async def api_funnel(request: Request):
    """单独生成漏斗图"""
    body = await request.json()
    studies_data = body.get("studies", [])
    effect_measure = body.get("effect_measure", "OR")

    studies = [StudyInput(**s) for s in studies_data]
    is_continuous = studies and studies[0].data_type == "continuous"
    if is_continuous:
        if effect_measure in ("OR", "RR"):
            effect_measure = "SMD"
        srs = [engine._calc_continuous(s, effect_measure) for s in studies]
    else:
        srs = [engine._calc_dichotomous(s, effect_measure) for s in studies]
    pooled = engine._fixed_effect(srs, use_log_scale=not is_continuous)
    svg = engine._funnel_plot(srs, pooled)
    return {"svg": svg}


@app.post("/api/galbraith")
async def api_galbraith(request: Request):
    """Generate Galbraith (radial) plot SVG.

    Body JSON:
      studies: list of study dicts
      effect_measure: "OR", "RR", "SMD", or "WMD"
    """
    body = await request.json()
    studies_data = body.get("studies", [])
    effect_measure = body.get("effect_measure", "OR")

    if len(studies_data) < 2:
        raise HTTPException(400, "At least 2 studies required for Galbraith plot")

    studies = [StudyInput(**s) for s in studies_data]
    is_continuous = studies and studies[0].data_type == "continuous"
    if is_continuous:
        if effect_measure in ("OR", "RR"):
            effect_measure = "SMD"
        srs = [engine._calc_continuous(s, effect_measure) for s in studies]
    else:
        srs = [engine._calc_dichotomous(s, effect_measure) for s in studies]
    pooled = engine._fixed_effect(srs, use_log_scale=not is_continuous)
    svg = engine._galbraith_plot(srs, pooled)
    return {"svg": svg}


@app.post("/api/labbe")
async def api_labbe(request: Request):
    """Generate L'Abbe plot SVG.

    Body JSON:
      studies: list of study dicts
      effect_measure: "OR", "RR", "SMD", or "WMD"
    """
    body = await request.json()
    studies_data = body.get("studies", [])
    effect_measure = body.get("effect_measure", "OR")

    if len(studies_data) < 2:
        raise HTTPException(400, "At least 2 studies required for L'Abbe plot")

    studies = [StudyInput(**s) for s in studies_data]
    is_continuous = studies and studies[0].data_type == "continuous"
    if is_continuous:
        if effect_measure in ("OR", "RR"):
            effect_measure = "SMD"
        srs = [engine._calc_continuous(s, effect_measure) for s in studies]
    else:
        srs = [engine._calc_dichotomous(s, effect_measure) for s in studies]
    pooled = engine._fixed_effect(srs, use_log_scale=not is_continuous)
    svg = engine._labbe_plot(srs, studies, pooled)
    return {"svg": svg}


@app.get("/api/models")
async def list_models():
    """列出可用的统计模型"""
    return {
        "models": [
            {"key": "fixed", "name": "Fixed Effect (M-H)", "description": "Mantel-Haenszel fixed effect model"},
            {"key": "random", "name": "Random Effects (D-L)", "description": "DerSimonian-Laird random effects model"},
        ],
        "effect_measures": [
            {"key": "OR", "name": "Odds Ratio", "description": "二分类数据效应量"},
            {"key": "RR", "name": "Risk Ratio", "description": "相对风险"},
            {"key": "SMD", "name": "Standardized Mean Difference", "description": "连续数据标准化均数差 (Hedges' g)"},
            {"key": "WMD", "name": "Weighted Mean Difference", "description": "连续数据加权均数差"},
        ],
        "data_types": [
            {"key": "dichotomous", "name": "Dichotomous", "description": "Binary/event count data"},
            {"key": "continuous", "name": "Continuous", "description": "Mean/SD data"},
        ],
    }


@app.post("/api/bias")
async def api_bias(request: Request):
    """Run Egger's test and Begg's test for publication bias"""
    body = await request.json()
    studies_data = body.get("studies", [])
    effect_measure = body.get("effect_measure", "OR")

    if len(studies_data) < 3:
        raise HTTPException(400, "At least 3 studies required for bias tests")

    studies = [StudyInput(**s) for s in studies_data]
    if studies and studies[0].data_type == "continuous":
        if effect_measure in ("OR", "RR"):
            effect_measure = "SMD"
        srs = [engine._calc_continuous(s, effect_measure) for s in studies]
    else:
        srs = [engine._calc_dichotomous(s, effect_measure) for s in studies]

    egger = engine.egger_test(srs)
    begg = engine.begg_test(srs)
    trim_fill = engine.trim_and_fill(srs)

    return {
        "egger_test": egger,
        "begg_test": begg,
        "trim_and_fill": trim_fill,
    }


@app.post("/api/cumulative")
async def api_cumulative(request: Request):
    """Run cumulative meta-analysis"""
    body = await request.json()
    studies_data = body.get("studies", [])
    sort_by = body.get("sort_by", "name")
    effect_measure = body.get("effect_measure", "OR")
    model = body.get("model", "random")

    if len(studies_data) < 2:
        raise HTTPException(400, "At least 2 studies required")

    studies = [StudyInput(**s) for s in studies_data]

    try:
        results = engine.cumulative_analysis(
            studies, sort_by=sort_by, effect_measure=effect_measure, model=model
        )
        return {"cumulative_results": results, "sort_by": sort_by, "model": model}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/export/csv")
async def api_export_csv(request: Request):
    """Export meta-analysis results as CSV"""
    body = await request.json()
    studies_data = body.get("studies", [])
    effect_measure = body.get("effect_measure", "OR")
    model = body.get("model", "random")

    if len(studies_data) < 2:
        raise HTTPException(400, "At least 2 studies required")

    studies = [StudyInput(**s) for s in studies_data]
    result = engine.analyze(studies, model=model, effect_measure=effect_measure)

    output = io.StringIO()
    writer = csv_module.writer(output)
    writer.writerow(["Study", "Effect", "CI_Lower", "CI_Upper", "Weight", "Log_Effect", "Log_SE", "Subgroup"])
    for s in result.studies:
        writer.writerow([
            s["name"], s["effect"], s["ci_lower"], s["ci_upper"],
            s["weight"], s["log_effect"], s["log_se"], s["subgroup"],
        ])
    writer.writerow([])
    writer.writerow(["Pooled", result.pooled_effect, result.pooled_ci_lower,
                      result.pooled_ci_upper, "", "", "", ""])
    writer.writerow(["I_squared", result.i_squared, "Tau_squared", result.tau_squared,
                      "Q", result.q_statistic, "Q_p", result.q_p_value])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=metaforge_results.csv"},
    )


@app.post("/api/export/json")
async def api_export_json(request: Request):
    """Export meta-analysis results as JSON"""
    body = await request.json()
    studies_data = body.get("studies", [])
    effect_measure = body.get("effect_measure", "OR")
    model = body.get("model", "random")

    if len(studies_data) < 2:
        raise HTTPException(400, "At least 2 studies required")

    studies = [StudyInput(**s) for s in studies_data]
    result = engine.analyze(studies, model=model, effect_measure=effect_measure)

    export_data = {
        "metaforge_version": "3.0.0",
        "exported_at": datetime.now().isoformat(),
        "model": model,
        "effect_measure": effect_measure,
        "pooled_effect": result.pooled_effect,
        "pooled_ci_lower": result.pooled_ci_lower,
        "pooled_ci_upper": result.pooled_ci_upper,
        "p_value": result.p_value,
        "i_squared": result.i_squared,
        "tau_squared": result.tau_squared,
        "q_statistic": result.q_statistic,
        "q_p_value": result.q_p_value,
        "heterogeneity": result.heterogeneity,
        "studies": result.studies,
    }

    return JSONResponse(content=export_data, headers={
        "Content-Disposition": "attachment; filename=metaforge_results.json"
    })


@app.post("/api/upload/csv")
async def api_upload_csv(file: UploadFile = File(...)):
    """Upload a CSV file and run meta-analysis.

    Expected CSV columns: name, e_events, e_total, c_events, c_total
    Optional: subgroup, data_type, e_mean, e_sd, c_mean, c_sd
    """
    content = await file.read()
    text = content.decode("utf-8")
    reader = csv_module.DictReader(io.StringIO(text))

    studies = []
    for row in reader:
        studies.append(StudyInput(
            name=row.get("name", f"Study_{len(studies)+1}"),
            e_events=int(row.get("e_events", 0)),
            e_total=int(row.get("e_total", 0)),
            c_events=int(row.get("c_events", 0)),
            c_total=int(row.get("c_total", 0)),
            subgroup=row.get("subgroup", ""),
            data_type=row.get("data_type", "dichotomous"),
            e_mean=float(row.get("e_mean", 0)),
            e_sd=float(row.get("e_sd", 0)),
            c_mean=float(row.get("c_mean", 0)),
            c_sd=float(row.get("c_sd", 0)),
        ))

    if len(studies) < 2:
        raise HTTPException(400, "CSV must contain at least 2 studies")

    try:
        # Auto-detect effect measure from data type
        effect_measure = "SMD" if studies[0].data_type == "continuous" else "OR"
        result = engine.analyze(studies, model="random", effect_measure=effect_measure)
        return asdict(result)
    except Exception as e:
        raise HTTPException(500, str(e))


# ============================================================
# Advanced Statistical Endpoints
# ============================================================


@app.post("/api/meta_regression")
async def api_meta_regression(request: Request):
    """Run meta-regression: regress effect sizes on a covariate.

    Body JSON:
      studies: list of study dicts (name, e_events, e_total, c_events, c_total, ...)
      covariate: list of float values (one per study, same order)
      covariate_name: str, optional label (default "covariate")
      effect_measure: "OR" or "RR"
    """
    body = await request.json()
    studies_data = body.get("studies", [])
    covariate = body.get("covariate", [])
    covariate_name = body.get("covariate_name", "covariate")
    effect_measure = body.get("effect_measure", "OR")

    if len(studies_data) < 3:
        raise HTTPException(400, "At least 3 studies required for meta-regression")
    if len(covariate) != len(studies_data):
        raise HTTPException(400, f"covariate length ({len(covariate)}) must equal number of studies ({len(studies_data)})")

    studies = [StudyInput(**s) for s in studies_data]
    try:
        srs = [engine._calc_dichotomous(s, effect_measure) for s in studies]
        result = engine.meta_regression(srs, covariate, covariate_name)
        if "error" in result:
            raise HTTPException(400, result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/dose_response")
async def api_dose_response(request: Request):
    """Run dose-response meta-analysis (linear + restricted cubic spline).

    Body JSON:
      studies: list of study dicts
      doses: list of float dose/exposure levels (one per study)
      num_points: int, number of curve points (default 50)
      effect_measure: "OR" or "RR"
    """
    body = await request.json()
    studies_data = body.get("studies", [])
    doses = body.get("doses", [])
    num_points = body.get("num_points", 50)
    effect_measure = body.get("effect_measure", "OR")

    if len(studies_data) < 3:
        raise HTTPException(400, "At least 3 studies required for dose-response")
    if len(doses) != len(studies_data):
        raise HTTPException(400, f"doses length ({len(doses)}) must equal number of studies ({len(studies_data)})")

    studies = [StudyInput(**s) for s in studies_data]
    try:
        srs = [engine._calc_dichotomous(s, effect_measure) for s in studies]
        result = engine.dose_response(srs, doses, num_points)
        if "error" in result:
            raise HTTPException(400, result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/report/pdf")
async def api_report_pdf(request: Request):
    """Generate a complete meta-analysis report as printable HTML.

    Body JSON:
      studies: list of study dicts
      model: "fixed" or "random" (default "random")
      effect_measure: "OR" or "RR"
      title: optional report title
    """
    body = await request.json()
    studies_data = body.get("studies", [])
    model = body.get("model", "random")
    effect_measure = body.get("effect_measure", "OR")
    title = body.get("title", "MetaForge Meta-Analysis Report")

    if len(studies_data) < 2:
        raise HTTPException(400, "At least 2 studies required")

    studies = [StudyInput(**s) for s in studies_data]

    try:
        result = engine.analyze(studies, model=model, effect_measure=effect_measure)
    except Exception as e:
        raise HTTPException(500, str(e))

    # Build study rows
    study_rows = ""
    for s in result.studies:
        study_rows += f"""<tr>
            <td>{s['name']}</td>
            <td>{s['effect']:.3f}</td>
            <td>[{s['ci_lower']:.3f}, {s['ci_upper']:.3f}]</td>
            <td>{s['weight']:.1f}</td>
            <td>{s['subgroup']}</td>
        </tr>"""

    # Sensitivity rows
    sens_rows = ""
    for sr in result.sensitivity_results:
        sens_rows += f"""<tr>
            <td>{sr['excluded']}</td>
            <td>{sr['pooled_effect']:.3f}</td>
            <td>[{sr['ci_lower']:.3f}, {sr['ci_upper']:.3f}]</td>
            <td>{sr['p_value']:.4f}</td>
        </tr>"""

    # Subgroup rows
    sub_rows = ""
    for grp, info in result.subgroup_results.items():
        sub_rows += f"""<tr>
            <td>{grp}</td>
            <td>{info['n_studies']}</td>
            <td>{info['pooled_effect']:.3f}</td>
            <td>[{info['ci_lower']:.3f}, {info['ci_upper']:.3f}]</td>
            <td>{info['p_value']:.4f}</td>
            <td>{info['i_squared']}%</td>
        </tr>"""

    het_level_emoji = {"low": "&#x2705;", "moderate": "&#x26A0;&#xFE0F;", "high": "&#x26D4;"}

    html_report = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  @page {{ size: A4; margin: 2cm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1a1a2e; line-height: 1.6; max-width: 900px; margin: 0 auto; padding: 20px; }}
  h1 {{ color: #0d47a1; border-bottom: 3px solid #1565c0; padding-bottom: 10px; }}
  h2 {{ color: #1565c0; margin-top: 30px; border-bottom: 1px solid #ccc; padding-bottom: 5px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; font-size: 13px; }}
  th {{ background: #e3f2fd; color: #0d47a1; font-weight: 600; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  .metric {{ display: inline-block; background: #f5f5f5; border-radius: 8px; padding: 12px 20px; margin: 5px; text-align: center; min-width: 140px; }}
  .metric .val {{ font-size: 22px; font-weight: 700; color: #1565c0; }}
  .metric .lbl {{ font-size: 11px; color: #666; text-transform: uppercase; }}
  .svg-container {{ text-align: center; margin: 20px 0; overflow: hidden; }}
  .svg-container svg {{ max-width: 100%; height: auto; }}
  .meta-table {{ background: #fff3e0; border-left: 4px solid #ff9800; padding: 10px; margin: 15px 0; }}
  .footer {{ text-align: center; color: #999; font-size: 11px; margin-top: 40px; border-top: 1px solid #eee; padding-top: 10px; }}
  @media print {{ .no-print {{ display: none; }} body {{ padding: 0; }} }}
</style>
</head>
<body>
<button class="no-print" onclick="window.print()" style="position:fixed;top:10px;right:10px;padding:10px 20px;background:#1565c0;color:white;border:none;border-radius:6px;cursor:pointer;font-size:14px;">&#128424; Print / Save PDF</button>

<h1>{title}</h1>
<p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M')} &nbsp;|&nbsp;
<strong>Model:</strong> {model.capitalize()} Effects &nbsp;|&nbsp;
<strong>Measure:</strong> {effect_measure} &nbsp;|&nbsp;
<strong>Studies:</strong> {len(result.studies)}</p>

<h2>1. Summary of Results</h2>
<div class="meta-table">
  <div class="metric"><div class="val">{result.pooled_effect:.3f}</div><div class="lbl">Pooled {effect_measure}</div></div>
  <div class="metric"><div class="val">[{result.pooled_ci_lower:.3f}, {result.pooled_ci_upper:.3f}]</div><div class="lbl">95% CI</div></div>
  <div class="metric"><div class="val">{result.p_value:.4f}</div><div class="lbl">P-value</div></div>
  <div class="metric"><div class="val">{result.i_squared}%</div><div class="lbl">I&sup2;</div></div>
  <div class="metric"><div class="val">{result.tau_squared:.4f}</div><div class="lbl">&tau;&sup2;</div></div>
  <div class="metric"><div class="val">{result.q_statistic:.2f} (p={result.q_p_value:.4f})</div><div class="lbl">Q Statistic</div></div>
  <div class="metric"><div class="val">{het_level_emoji.get(result.heterogeneity, "")} {result.heterogeneity.title()}</div><div class="lbl">Heterogeneity</div></div>
</div>

<h2>2. Forest Plot</h2>
<div class="svg-container">{result.forest_plot_svg}</div>

<h2>3. Individual Study Results</h2>
<table>
<tr><th>Study</th><th>{effect_measure}</th><th>95% CI</th><th>Weight</th><th>Subgroup</th></tr>
{study_rows}
</table>

<h2>4. Funnel Plot</h2>
<div class="svg-container">{result.funnel_plot_svg}</div>

<h2>5. Subgroup Analysis</h2>
{"<table><tr><th>Subgroup</th><th>N</th><th>Pooled {em}</th><th>95% CI</th><th>P</th><th>I&sup2;</th></tr>{sr}</table>".format(em=effect_measure, sr=sub_rows) if sub_rows else "<p>No subgroups defined.</p>"}

<h2>6. Sensitivity Analysis (Leave-One-Out)</h2>
{"<table><tr><th>Excluded</th><th>Pooled {em}</th><th>95% CI</th><th>P</th></tr>{sr}</table>".format(em=effect_measure, sr=sens_rows) if sens_rows else "<p>No sensitivity analysis available.</p>"}

<div class="footer">
  Generated by <strong>MetaForge v3.0.0</strong> &mdash; AI Evidence-Based Medicine Research Platform<br>
  This report is for research purposes only and should not replace clinical judgment.
</div>
</body>
</html>"""

    return HTMLResponse(content=html_report)


@app.get("/api/docs", response_class=HTMLResponse)
async def api_docs():
    """Interactive API documentation."""
    docs_html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>MetaForge API Documentation</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0d1117; color: #c9d1d9; line-height: 1.6; }
  .container { max-width: 960px; margin: 0 auto; padding: 30px 20px; }
  h1 { color: #58a6ff; font-size: 28px; margin-bottom: 8px; }
  .subtitle { color: #8b949e; margin-bottom: 30px; font-size: 14px; }
  .endpoint { background: #161b22; border: 1px solid #30363d; border-radius: 8px; margin-bottom: 16px; overflow: hidden; }
  .endpoint-header { padding: 14px 18px; cursor: pointer; display: flex; align-items: center; gap: 12px; }
  .endpoint-header:hover { background: #1c2129; }
  .method { font-weight: 700; font-size: 12px; padding: 3px 8px; border-radius: 4px; min-width: 50px; text-align: center; }
  .method.get { background: #1f6feb; color: white; }
  .method.post { background: #238636; color: white; }
  .path { font-family: 'JetBrains Mono', monospace; color: #e6edf3; font-size: 14px; }
  .desc { color: #8b949e; font-size: 13px; margin-left: auto; }
  .endpoint-body { display: none; padding: 16px 18px; border-top: 1px solid #30363d; background: #0d1117; }
  .endpoint-body.open { display: block; }
  .param-table { width: 100%; border-collapse: collapse; margin: 10px 0; }
  .param-table th { text-align: left; color: #8b949e; font-size: 11px; text-transform: uppercase; padding: 6px 8px; border-bottom: 1px solid #30363d; }
  .param-table td { padding: 6px 8px; font-size: 13px; border-bottom: 1px solid #21262d; }
  .param-table td:first-child { font-family: 'JetBrains Mono', monospace; color: #79c0ff; }
  .code-block { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 14px; font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #c9d1d9; overflow-x: auto; white-space: pre; margin: 10px 0; }
  .try-btn { background: #238636; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; margin-top: 10px; }
  .try-btn:hover { background: #2ea043; }
  .response-area { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 14px; font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #7ee787; max-height: 400px; overflow: auto; margin-top: 10px; display: none; white-space: pre-wrap; word-break: break-all; }
  .tag { font-size: 10px; padding: 2px 6px; border-radius: 3px; background: #30363d; color: #8b949e; }
</style>
</head>
<body>
<div class="container">
  <h1>&#x1F4CA; MetaForge API v3.0.0</h1>
  <p class="subtitle">AI Evidence-Based Medicine Research Platform &mdash; Complete API Reference</p>

  <div class="endpoint">
    <div class="endpoint-header" onclick="toggle(this)">
      <span class="method get">GET</span>
      <span class="path">/api/health</span>
      <span class="desc">Health check</span>
    </div>
    <div class="endpoint-body">
      <p>Returns server status, version, and timestamp.</p>
      <button class="try-btn" onclick="tryEndpoint('GET', '/api/health', null, this)">Try it</button>
      <div class="response-area"></div>
    </div>
  </div>

  <div class="endpoint">
    <div class="endpoint-header" onclick="toggle(this)">
      <span class="method post">POST</span>
      <span class="path">/api/analyze</span>
      <span class="desc">Run meta-analysis <span class="tag">core</span></span>
    </div>
    <div class="endpoint-body">
      <p>Run a complete meta-analysis with forest plot, funnel plot, subgroup, and sensitivity analyses.</p>
      <table class="param-table"><tr><th>Parameter</th><th>Type</th><th>Description</th></tr>
        <tr><td>studies</td><td>array</td><td>List of study objects: name, e_events, e_total, c_events, c_total, subgroup</td></tr>
        <tr><td>model</td><td>string</td><td>"fixed" or "random" (default: "random")</td></tr>
        <tr><td>effect_measure</td><td>string</td><td>"OR" or "RR" (default: "OR")</td></tr>
      </table>
      <div class="code-block">{
  "studies": [
    {"name": "Study 1", "e_events": 30, "e_total": 100, "c_events": 20, "c_total": 100},
    {"name": "Study 2", "e_events": 45, "e_total": 120, "c_events": 35, "c_total": 110}
  ],
  "model": "random",
  "effect_measure": "OR"
}</div>
      <button class="try-btn" onclick="tryDemo(this)">Try demo</button>
      <div class="response-area"></div>
    </div>
  </div>

  <div class="endpoint">
    <div class="endpoint-header" onclick="toggle(this)">
      <span class="method post">POST</span>
      <span class="path">/api/meta_regression</span>
      <span class="desc">Meta-regression <span class="tag">advanced</span></span>
    </div>
    <div class="endpoint-body">
      <p>Regress study effect sizes on a covariate (e.g. sample size, year, dose) using weighted least squares. Returns coefficient, p-value, R-squared, and fitted curve.</p>
      <table class="param-table"><tr><th>Parameter</th><th>Type</th><th>Description</th></tr>
        <tr><td>studies</td><td>array</td><td>List of study objects</td></tr>
        <tr><td>covariate</td><td>array[float]</td><td>Numeric covariate values (one per study, same order)</td></tr>
        <tr><td>covariate_name</td><td>string</td><td>Label for covariate (default: "covariate")</td></tr>
        <tr><td>effect_measure</td><td>string</td><td>"OR" or "RR"</td></tr>
      </table>
      <div class="code-block">{
  "studies": [
    {"name": "Study A", "e_events": 30, "e_total": 100, "c_events": 20, "c_total": 100},
    {"name": "Study B", "e_events": 45, "e_total": 200, "c_events": 35, "c_total": 190},
    {"name": "Study C", "e_events": 60, "e_total": 300, "c_events": 40, "c_total": 280}
  ],
  "covariate": [100, 200, 300],
  "covariate_name": "sample_size",
  "effect_measure": "OR"
}</div>
    </div>
  </div>

  <div class="endpoint">
    <div class="endpoint-header" onclick="toggle(this)">
      <span class="method post">POST</span>
      <span class="path">/api/dose_response</span>
      <span class="desc">Dose-response analysis <span class="tag">advanced</span></span>
    </div>
    <div class="endpoint-body">
      <p>Fits linear and restricted cubic spline models to dose/exposure data. Returns fitted curves with confidence intervals and nonlinearity tests.</p>
      <table class="param-table"><tr><th>Parameter</th><th>Type</th><th>Description</th></tr>
        <tr><td>studies</td><td>array</td><td>List of study objects</td></tr>
        <tr><td>doses</td><td>array[float]</td><td>Dose/exposure levels (one per study)</td></tr>
        <tr><td>num_points</td><td>int</td><td>Number of curve points (default: 50)</td></tr>
        <tr><td>effect_measure</td><td>string</td><td>"OR" or "RR"</td></tr>
      </table>
    </div>
  </div>

  <div class="endpoint">
    <div class="endpoint-header" onclick="toggle(this)">
      <span class="method post">POST</span>
      <span class="path">/api/report/pdf</span>
      <span class="desc">Generate printable HTML report <span class="tag">export</span></span>
    </div>
    <div class="endpoint-body">
      <p>Generates a complete meta-analysis report as printable HTML. Use browser Print (Ctrl+P) to save as PDF.</p>
      <table class="param-table"><tr><th>Parameter</th><th>Type</th><th>Description</th></tr>
        <tr><td>studies</td><td>array</td><td>List of study objects</td></tr>
        <tr><td>model</td><td>string</td><td>"fixed" or "random"</td></tr>
        <tr><td>effect_measure</td><td>string</td><td>"OR" or "RR"</td></tr>
        <tr><td>title</td><td>string</td><td>Report title</td></tr>
      </table>
    </div>
  </div>

  <div class="endpoint">
    <div class="endpoint-header" onclick="toggle(this)">
      <span class="method post">POST</span>
      <span class="path">/api/bias</span>
      <span class="desc">Publication bias tests</span>
    </div>
    <div class="endpoint-body">
      <p>Run Egger's test, Begg's test, and trim-and-fill analysis for publication bias. Requires at least 3 studies.</p>
    </div>
  </div>

  <div class="endpoint">
    <div class="endpoint-header" onclick="toggle(this)">
      <span class="method post">POST</span>
      <span class="path">/api/cumulative</span>
      <span class="desc">Cumulative meta-analysis</span>
    </div>
    <div class="endpoint-body">
      <p>Adds studies one at a time (sorted by name or effect) and shows evolving pooled estimate.</p>
    </div>
  </div>

  <div class="endpoint">
    <div class="endpoint-header" onclick="toggle(this)">
      <span class="method post">POST</span>
      <span class="path">/api/demo</span>
      <span class="desc">Run built-in demo analysis</span>
    </div>
    <div class="endpoint-body">
      <p>Run a complete meta-analysis on demo PD-1 inhibitor NSCLC data (10 studies). No input needed.</p>
      <button class="try-btn" onclick="tryEndpoint('POST', '/api/demo', {}, this)">Try it</button>
      <div class="response-area"></div>
    </div>
  </div>

  <div class="endpoint">
    <div class="endpoint-header" onclick="toggle(this)">
      <span class="method post">POST</span>
      <span class="path">/api/forest</span>
      <span class="desc">Generate forest plot SVG</span>
    </div>
    <div class="endpoint-body"><p>Generate standalone forest plot from study data.</p></div>
  </div>

  <div class="endpoint">
    <div class="endpoint-header" onclick="toggle(this)">
      <span class="method post">POST</span>
      <span class="path">/api/funnel</span>
      <span class="desc">Generate funnel plot SVG</span>
    </div>
    <div class="endpoint-body"><p>Generate standalone funnel plot from study data.</p></div>
  </div>

  <div class="endpoint">
    <div class="endpoint-header" onclick="toggle(this)">
      <span class="method post">POST</span>
      <span class="path">/api/prisma</span>
      <span class="desc">Generate PRISMA flow diagram</span>
    </div>
    <div class="endpoint-body"><p>Generate PRISMA 2020 flow diagram SVG with customizable numbers.</p></div>
  </div>

  <div class="endpoint">
    <div class="endpoint-header" onclick="toggle(this)">
      <span class="method get">GET</span>
      <span class="path">/api/models</span>
      <span class="desc">List available models</span>
    </div>
    <div class="endpoint-body"><p>List available statistical models and effect measures.</p></div>
  </div>

  <div class="endpoint">
    <div class="endpoint-header" onclick="toggle(this)">
      <span class="method post">POST</span>
      <span class="path">/api/export/csv</span>
      <span class="desc">Export results as CSV</span>
    </div>
    <div class="endpoint-body"><p>Download meta-analysis results as CSV file.</p></div>
  </div>

  <div class="endpoint">
    <div class="endpoint-header" onclick="toggle(this)">
      <span class="method post">POST</span>
      <span class="path">/api/export/json</span>
      <span class="desc">Export results as JSON</span>
    </div>
    <div class="endpoint-body"><p>Download meta-analysis results as JSON file.</p></div>
  </div>

  <div class="endpoint">
    <div class="endpoint-header" onclick="toggle(this)">
      <span class="method post">POST</span>
      <span class="path">/api/upload/csv</span>
      <span class="desc">Upload CSV &amp; analyze</span>
    </div>
    <div class="endpoint-body"><p>Upload a CSV file with columns: name, e_events, e_total, c_events, c_total. Returns full meta-analysis.</p></div>
  </div>
</div>

<script>
function toggle(header) {
  const body = header.nextElementSibling;
  body.classList.toggle('open');
}
async function tryEndpoint(method, url, data, btn) {
  const area = btn.nextElementSibling;
  area.style.display = 'block';
  area.textContent = 'Loading...';
  try {
    const opts = { method, headers: {'Content-Type': 'application/json'} };
    if (data) opts.body = JSON.stringify(data);
    const resp = await fetch(url, opts);
    const json = await resp.json();
    area.textContent = JSON.stringify(json, null, 2);
  } catch(e) { area.textContent = 'Error: ' + e.message; }
}
async function tryDemo(btn) {
  tryEndpoint('POST', '/api/demo', {}, btn);
}
</script>
</body>
</html>"""
    return HTMLResponse(content=docs_html)


# ============================================================
# User System Endpoints
# ============================================================


@app.post("/api/register")
async def api_register(request: Request):
    """Register a new user."""
    body = await request.json()
    username = body.get("username", "").strip()
    email = body.get("email", "").strip()
    password = body.get("password", "")

    if not username or not email or not password:
        raise HTTPException(400, "username, email, and password are all required")
    if len(username) < 3:
        raise HTTPException(400, "Username must be at least 3 characters")
    if len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if "@" not in email:
        raise HTTPException(400, "Invalid email format")
    db = SessionLocal()
    try:
        existing = db.query(User).filter((User.username == username) | (User.email == email)).first()
        if existing:
            raise HTTPException(409, "Username or email already exists")

        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            plan="free",
            api_calls_today=0,
            api_calls_limit=50,
            projects_limit=3,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        token = generate_token(user.id, user.username)
        return {
            "message": "User registered successfully",
            "username": user.username,
            "token": token,
            "plan": user.plan,
        }
    finally:
        db.close()


@app.post("/api/login")
async def api_login(request: Request):
    """Login and receive a session token."""
    body = await request.json()
    username = body.get("username", "").strip()
    password = body.get("password", "")

    if not username or not password:
        raise HTTPException(400, "username and password are required")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(401, "Invalid username or password")

        # Update last login
        user.last_login = datetime.utcnow()
        db.commit()

        token = generate_token(user.id, user.username)
        return {
            "message": "Login successful",
            "token": token,
            "username": user.username,
            "plan": user.plan,
            "api_calls_remaining": user.api_calls_limit - user.api_calls_today if user.api_calls_limit > 0 else "unlimited",
        }
    finally:
        db.close()


@app.post("/api/projects/save")
async def api_project_save(request: Request):
    """Save a meta-analysis project (requires auth)."""
    user, db = _get_current_user(request)
    try:
        body = await request.json()
        project_name = body.get("name", "").strip()
        studies = body.get("studies", [])
        settings = body.get("settings", {})
        project_id = body.get("id")

        if not project_name:
            raise HTTPException(400, "Project name is required")
        if not studies or len(studies) < 1:
            raise HTTPException(400, "At least 1 study is required")

        # Check project quota
        user_projects_count = db.query(Project).filter(Project.user_id == user.id).count()
        if user.projects_limit > 0 and user_projects_count >= user.projects_limit and not project_id:
            raise HTTPException(403, f"Project limit reached ({user.projects_limit}). Upgrade your plan.")

        if project_id:
            # Update existing
            project = db.query(Project).filter(Project.id == project_id, Project.user_id == user.id).first()
            if not project:
                raise HTTPException(404, "Project not found")
            project.name = project_name
            project.studies_json = json.dumps(studies)
            project.settings_json = json.dumps(settings)
            project.updated_at = datetime.utcnow()
        else:
            # Create new
            project_id = str(uuid.uuid4())
            project = Project(
                id=project_id,
                user_id=user.id,
                name=project_name,
                studies_json=json.dumps(studies),
                settings_json=json.dumps(settings),
            )
            db.add(project)

        db.commit()
        return {"message": "Project saved", "project_id": project_id}
    finally:
        db.close()


@app.get("/api/projects/list")
async def api_projects_list(request: Request):
    """List all projects for the authenticated user."""
    user, db = _get_current_user(request)
    try:
        projects = db.query(Project).filter(Project.user_id == user.id).order_by(Project.updated_at.desc()).all()
        return {
            "projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in projects
            ],
            "count": len(projects),
            "limit": user.projects_limit,
        }
    finally:
        db.close()


@app.get("/api/projects/{project_id}")
async def api_project_get(project_id: str, request: Request):
    """Get a specific project by ID (owner only)."""
    user, db = _get_current_user(request)
    try:
        project = db.query(Project).filter(Project.id == project_id, Project.user_id == user.id).first()
        if not project:
            raise HTTPException(404, "Project not found")
        return {
            "id": project.id,
            "name": project.name,
            "studies": json.loads(project.studies_json),
            "settings": json.loads(project.settings_json),
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        }
    finally:
        db.close()


@app.delete("/api/projects/{project_id}")
async def api_project_delete(project_id: str, request: Request):
    """Delete a project (owner only)."""
    user, db = _get_current_user(request)
    try:
        project = db.query(Project).filter(Project.id == project_id, Project.user_id == user.id).first()
        if not project:
            raise HTTPException(404, "Project not found")
        db.delete(project)
        db.commit()
        return {"message": "Project deleted", "project_id": project_id}
    finally:
        db.close()


@app.get("/api/user/profile")
async def api_user_profile(request: Request):
    """Get current user profile and usage stats."""
    user, db = _get_current_user(request)
    try:
        projects_count = db.query(Project).filter(Project.user_id == user.id).count()
        limits = PLAN_LIMITS.get(user.plan, PLAN_LIMITS["free"])
        return {
            "username": user.username,
            "email": user.email,
            "plan": user.plan,
            "api_calls_today": user.api_calls_today,
            "api_calls_limit": user.api_calls_limit,
            "projects_count": projects_count,
            "projects_limit": user.projects_limit,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
        }
    finally:
        db.close()


# ============================================================
# Payment Endpoints (Stripe Integration)
# ============================================================

PLAN_PRICES = {
    "starter": {"amount": 29900, "currency": "cny", "name": "Starter", "interval": "month"},
    "professional": {"amount": 99900, "currency": "cny", "name": "Professional", "interval": "month"},
}


@app.post("/api/payment/checkout")
async def api_payment_checkout(request: Request):
    """Create a checkout session for plan upgrade."""
    user, db = _get_current_user(request)
    try:
        body = await request.json()
        plan = body.get("plan", "").lower()

        if plan not in PLAN_PRICES:
            raise HTTPException(400, f"Invalid plan. Choose: {list(PLAN_PRICES.keys())}")

        price_info = PLAN_PRICES[plan]
        checkout_id = str(uuid.uuid4())

        # In production, this would call Stripe API:
        # session = stripe.checkout.Session.create(...)
        # For now, return a mock checkout URL
        return {
            "checkout_id": checkout_id,
            "plan": plan,
            "amount": price_info["amount"],
            "currency": price_info["currency"],
            "checkout_url": f"/payment/checkout?plan={plan}&session={checkout_id}",
            "message": "Redirect user to checkout_url to complete payment",
        }
    finally:
        db.close()


@app.post("/api/payment/confirm")
async def api_payment_confirm(request: Request):
    """Confirm a payment (called after successful checkout)."""
    user, db = _get_current_user(request)
    try:
        body = await request.json()
        plan = body.get("plan", "").lower()
        checkout_id = body.get("checkout_id", "")

        if plan not in PLAN_PRICES:
            raise HTTPException(400, "Invalid plan")

        # Update user plan
        limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
        user.plan = plan
        user.api_calls_limit = limits["api_calls_per_day"]
        user.projects_limit = limits["projects"]
        db.commit()

        return {
            "message": f"Successfully upgraded to {plan} plan",
            "plan": user.plan,
            "api_calls_limit": user.api_calls_limit,
            "projects_limit": user.projects_limit,
        }
    finally:
        db.close()


@app.get("/api/payment/plans")
async def api_payment_plans():
    """Get available plans and pricing."""
    return {
        "plans": [
            {
                "id": "free",
                "name": "Free",
                "price": 0,
                "currency": "cny",
                "interval": "forever",
                "features": ["50 API calls/day", "3 projects", "10 studies/project", "CSV export"],
            },
            {
                "id": "starter",
                "name": "Starter",
                "price": 299,
                "currency": "cny",
                "interval": "month",
                "features": ["500 API calls/day", "20 projects", "50 studies/project", "CSV+JSON export"],
            },
            {
                "id": "professional",
                "name": "Professional",
                "price": 999,
                "currency": "cny",
                "interval": "month",
                "features": ["5000 API calls/day", "100 projects", "500 studies/project", "All formats", "Priority support"],
                "popular": True,
            },
            {
                "id": "enterprise",
                "name": "Enterprise",
                "price": None,
                "currency": "cny",
                "interval": "custom",
                "features": ["Unlimited API", "Unlimited projects", "Custom deployment", "Dedicated support", "SLA"],
            },
        ]
    }


# ============================================================
# AI Simulation Endpoints
# ============================================================


@app.post("/api/ai/search")
async def api_ai_search(request: Request):
    """Simulate AI-powered literature search. Returns mock PubMed-style results."""
    body = await request.json()
    query = body.get("query", "").strip()
    max_results = body.get("max_results", 10)

    if not query:
        raise HTTPException(400, "query is required")

    # Generate deterministic mock results seeded by the query
    query_seed = int(hashlib.md5(query.encode()).hexdigest()[:8], 16)
    rng = np.random.RandomState(query_seed)

    journals = [
        "The Lancet", "NEJM", "JAMA", "BMJ", "Annals of Internal Medicine",
        "PLOS Medicine", "Nature Medicine", "JAMA Internal Medicine",
        "European Heart Journal", "Chest", "Lung Cancer", "Thorax",
    ]
    topics = query.lower().split()
    n_results = min(max_results, 20)

    results = []
    base_year = 2015 + rng.randint(0, 8)
    for i in range(n_results):
        year = base_year - rng.randint(0, 5)
        n_authors = rng.randint(2, 6)
        first_author_last = ["Smith", "Chen", "Patel", "Kim", "Garcia", "Müller",
                             "Tanaka", "Lee", "Williams", "Johnson",
                             "Liu", "Zhang", "Wang", "Brown", "Davis"][rng.randint(0, 15)]
        author_str = f"{first_author_last} et al."
        sample_size = rng.randint(50, 2000)
        journal = journals[rng.randint(0, len(journals))]

        title_words = [w.capitalize() for w in topics[:3]]
        title_templates = [
            f"{' '.join(title_words)}: A Randomized Controlled Trial",
            f"Effect of {' '.join(title_words[:2])} on Clinical Outcomes: A Meta-Analysis",
            f"{' '.join(title_words)} in Adult Patients: A Systematic Review",
            f"Comparing {' '.join(title_words[:2])} — Multicenter Study (n={sample_size})",
            f"Long-term Outcomes of {' '.join(title_words)}: Prospective Cohort Study",
        ]
        title = title_templates[rng.randint(0, len(title_templates))]

        pmid = 25000000 + rng.randint(0, 8000000)
        results.append({
            "pmid": str(pmid),
            "title": title,
            "authors": author_str,
            "journal": journal,
            "year": year,
            "abstract": f"This study investigated {' '.join(topics)} in {sample_size} participants. "
                        f"Results showed statistically significant findings (p<0.05) "
                        f"favoring the intervention group.",
            "sample_size": sample_size,
            "doi": f"10.{1000 + rng.randint(0, 8999)}/{journal.lower().replace(' ', '.')}.{year}.{pmid}",
            "relevance_score": round(rng.uniform(0.65, 0.98), 2),
        })

    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return {
        "query": query,
        "total_found": rng.randint(50, 5000),
        "results_returned": len(results),
        "results": results,
    }


@app.post("/api/ai/screen")
async def api_ai_screen(request: Request):
    """Simulate AI-powered study screening.

    Takes a list of studies and inclusion/exclusion criteria, returns screening decisions.
    """
    body = await request.json()
    studies = body.get("studies", [])
    inclusion_criteria = body.get("inclusion_criteria", [])
    exclusion_criteria = body.get("exclusion_criteria", [])

    if not studies:
        raise HTTPException(400, "studies list is required")

    screened = []
    for i, study in enumerate(studies):
        title = study.get("title", "").lower()
        abstract = study.get("abstract", "").lower()
        combined = title + " " + abstract

        # Simple keyword-based scoring simulation
        include_score = 0.0
        matched_criteria = []
        for criterion in inclusion_criteria:
            keywords = criterion.lower().split()
            matches = sum(1 for kw in keywords if kw in combined)
            if matches > 0:
                include_score += matches / len(keywords)
                matched_criteria.append(criterion)

        exclude_hit = False
        exclude_reasons = []
        for criterion in exclusion_criteria:
            keywords = criterion.lower().split()
            if any(kw in combined for kw in keywords):
                exclude_hit = True
                exclude_reasons.append(criterion)

        # Normalize score
        max_possible = len(inclusion_criteria) if inclusion_criteria else 1
        confidence = round(min(include_score / max_possible, 1.0), 2)

        if exclude_hit:
            decision = "excluded"
            reason = f"Matched exclusion criteria: {'; '.join(exclude_reasons)}"
        elif confidence >= 0.3 or not inclusion_criteria:
            decision = "included"
            reason = f"Matched inclusion criteria: {'; '.join(matched_criteria)}" if matched_criteria else "Passed screening"
        else:
            decision = "uncertain"
            reason = "Low confidence match — manual review recommended"

        screened.append({
            "index": i,
            "title": study.get("title", f"Study {i+1}"),
            "decision": decision,
            "confidence": confidence,
            "reason": reason,
        })

    included_count = sum(1 for s in screened if s["decision"] == "included")
    excluded_count = sum(1 for s in screened if s["decision"] == "excluded")
    uncertain_count = sum(1 for s in screened if s["decision"] == "uncertain")

    return {
        "total_screened": len(screened),
        "included": included_count,
        "excluded": excluded_count,
        "uncertain": uncertain_count,
        "screening_results": screened,
    }


@app.post("/api/ai/extract")
async def api_ai_extract(request: Request):
    """Simulate AI-powered data extraction from study text.

    Takes text (simulated PDF text) and returns structured extracted data.
    """
    body = await request.json()
    text = body.get("text", "").strip()
    study_name = body.get("study_name", "Unknown Study")

    if not text:
        raise HTTPException(400, "text is required")

    text_lower = text.lower()

    # Simulate extraction with regex-like pattern matching
    import re

    # Try to find sample size
    size_match = re.search(r'(?:n\s*=\s*|sample\s*size\s*(?:of|:)?\s*|enrolled\s+|included\s+|recruited\s+)(\d+)', text_lower)
    sample_size = int(size_match.group(1)) if size_match else None

    # Try to find event counts
    event_matches = re.findall(r'(\d+)\s*(?:patients?|participants?|subjects?)\s*(?:had|experienced|developed|with)\s*(\w+)', text_lower)

    # Try to find effect measures
    or_match = re.search(r'(?:odds\s+ratio|OR)\s*(?:of|:|=)?\s*(\d+\.?\d*)', text_lower)
    rr_match = re.search(r'(?:risk\s+ratio|relative\s+risk|RR|HR)\s*(?:of|:|=)?\s*(\d+\.?\d*)', text_lower)
    ci_match = re.search(r'(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)\s*(?:\)|]|$)', text_lower)
    p_match = re.search(r'p\s*[=<>]\s*(\d*\.?\d+)', text_lower)

    # Try to find follow-up duration
    followup_match = re.search(r'(?:follow[- ]?up|median|duration)\s*(?:of|:)?\s*(\d+)\s*(months?|years?|weeks?|days?)', text_lower)

    extracted = {
        "study_name": study_name,
        "text_length": len(text),
        "extracted_data": {
            "sample_size": sample_size,
            "intervention": None,
            "control": None,
            "primary_outcome": None,
            "effect_measure": None,
            "effect_value": None,
            "confidence_interval": None,
            "p_value": None,
            "follow_up_duration": None,
            "adverse_events": None,
        },
        "extraction_confidence": round(np.random.uniform(0.7, 0.95), 2),
        "warnings": [],
    }

    # Fill in what we found
    if or_match:
        extracted["extracted_data"]["effect_measure"] = "OR"
        extracted["extracted_data"]["effect_value"] = float(or_match.group(1))
    elif rr_match:
        extracted["extracted_data"]["effect_measure"] = "RR"
        extracted["extracted_data"]["effect_value"] = float(rr_match.group(1))

    if p_match:
        extracted["extracted_data"]["p_value"] = float(p_match.group(1))

    if followup_match:
        extracted["extracted_data"]["follow_up_duration"] = f"{followup_match.group(1)} {followup_match.group(2)}"

    if not sample_size:
        extracted["warnings"].append("Could not detect sample size — manual entry required")
    if not extracted["extracted_data"]["effect_measure"]:
        extracted["warnings"].append("No effect measure (OR/RR/HR) detected in text")
    if not extracted["extracted_data"]["p_value"]:
        extracted["warnings"].append("No p-value detected — manual extraction needed")

    # Flag low confidence
    if extracted["extraction_confidence"] < 0.8:
        extracted["warnings"].append("Low extraction confidence — please verify all values")

    return extracted


# ============================================================
# Sharing Endpoints
# ============================================================


@app.post("/api/share")
async def api_create_share(request: Request):
    """Create a shareable link for a project."""
    username = _get_current_user(request)
    body = await request.json()
    project_id = body.get("project_id", "").strip()

    if not project_id:
        raise HTTPException(400, "project_id is required")

    project = user_projects_db.get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if project["owner"] != username:
        raise HTTPException(403, "Access denied: you do not own this project")

    # Check if already shared — reuse token
    for token, link in shared_links_db.items():
        if link["project_id"] == project_id:
            return {
                "message": "Project already shared",
                "share_token": token,
                "share_url": f"/api/shared/{token}",
            }

    share_token = str(uuid.uuid4())[:12]
    shared_links_db[share_token] = {
        "project_id": project_id,
        "created_by": username,
        "created_at": datetime.now().isoformat(),
        "access_count": 0,
    }

    return {
        "message": "Share link created",
        "share_token": share_token,
        "share_url": f"/api/shared/{share_token}",
    }


@app.get("/api/shared/{share_token}")
async def api_view_shared(share_token: str):
    """View a shared project by its share token (no auth required)."""
    link = shared_links_db.get(share_token)
    if not link:
        raise HTTPException(404, "Shared link not found or expired")

    project = user_projects_db.get(link["project_id"])
    if not project:
        raise HTTPException(404, "Project no longer exists")

    link["access_count"] += 1

    return {
        "project": {
            "name": project["name"],
            "studies": project["studies"],
            "settings": project["settings"],
            "created_at": project["created_at"],
        },
        "shared_by": link["created_by"],
        "access_count": link["access_count"],
    }




# ============================================================
# Network Meta-Analysis (NMA) Engine
# ============================================================

class NMAEngine:
    """Network Meta-Analysis using frequentist graph-theoretical approach.
    
    Supports indirect comparison via Bucher method and network estimation
    combining direct + indirect evidence.
    """

    def __init__(self):
        self.treatments = []
        self.comparisons = []
        self.n_treatments = 0

    def analyze(self, comparisons: List[dict]) -> dict:
        """Run complete NMA analysis.
        
        Parameters
        ----------
        comparisons : list of dict
            Each dict: {treatment_a, treatment_b, effect, ci_lower, ci_upper, weight}
            where effect is OR/RR/HR, ci are 95% CI bounds.
            
        Returns
        -------
        dict with network_stats, direct_estimates, indirect_estimates,
        network_estimates, consistency, ranking, network_svg, league_svg
        """
        self.comparisons = comparisons
        
        # Extract unique treatments
        treatments_set = set()
        for c in comparisons:
            treatments_set.add(c["treatment_a"])
            treatments_set.add(c["treatment_b"])
        self.treatments = sorted(treatments_set)
        self.n_treatments = len(self.treatments)
        
        if self.n_treatments < 3:
            return {"error": "NMA requires at least 3 treatments"}
        
        # Build adjacency and effect matrices
        adj_matrix, effect_matrix, se_matrix = self._build_matrices()
        
        # Direct estimates (from pairwise comparisons)
        direct = self._direct_estimates()
        
        # Indirect estimates (Bucher method)
        indirect = self._indirect_estimates(adj_matrix, effect_matrix, se_matrix)
        
        # Network estimates (combining direct + indirect)
        network = self._network_estimates(adj_matrix, effect_matrix, se_matrix)
        
        # Consistency assessment
        consistency = self._assess_consistency(direct, indirect)
        
        # SUCRA ranking
        ranking = self._calculate_sucra(network)
        
        # Generate visualizations
        network_svg = self._network_diagram_svg(adj_matrix)
        league_svg = self._league_table_svg(network)
        
        return {
            "n_treatments": self.n_treatments,
            "n_comparisons": len(comparisons),
            "treatments": self.treatments,
            "direct_estimates": direct,
            "indirect_estimates": indirect,
            "network_estimates": network,
            "consistency": consistency,
            "ranking": ranking,
            "network_svg": network_svg,
            "league_svg": league_svg,
        }

    def _build_matrices(self):
        """Build adjacency, effect, and SE matrices."""
        n = self.n_treatments
        t_idx = {t: i for i, t in enumerate(self.treatments)}
        
        adj = np.zeros((n, n), dtype=int)
        eff = np.zeros((n, n))
        se = np.zeros((n, n))
        
        for c in self.comparisons:
            i = t_idx[c["treatment_a"]]
            j = t_idx[c["treatment_b"]]
            adj[i, j] = adj[j, i] = 1
            
            log_eff = math.log(c["effect"]) if c["effect"] > 0 else 0
            log_upper = math.log(c["ci_upper"]) if c["ci_upper"] > 0 else 0
            log_lower = math.log(c["ci_lower"]) if c["ci_lower"] > 0 else 0
            se_val = (log_upper - log_lower) / (2 * 1.96)
            
            eff[i, j] = log_eff
            eff[j, i] = -log_eff
            se[i, j] = se[j, i] = max(se_val, 0.001)
        
        return adj, eff, se

    def _direct_estimates(self):
        """Extract direct pairwise estimates."""
        results = []
        for c in self.comparisons:
            log_eff = math.log(c["effect"]) if c["effect"] > 0 else 0
            se_val = (math.log(c["ci_upper"]) - math.log(c["ci_lower"])) / (2 * 1.96) if c["ci_lower"] > 0 and c["ci_upper"] > 0 else 0.1
            results.append({
                "treatment_a": c["treatment_a"],
                "treatment_b": c["treatment_b"],
                "effect": round(c["effect"], 4),
                "ci_lower": round(c["ci_lower"], 4),
                "ci_upper": round(c["ci_upper"], 4),
                "log_effect": round(log_eff, 4),
                "se": round(se_val, 4),
                "weight": round(1.0 / (se_val ** 2), 2) if se_val > 0 else 0,
                "source": "direct",
            })
        return results

    def _indirect_estimates(self, adj, eff, se):
        """Calculate indirect estimates via Bucher method for all possible indirect paths."""
        results = []
        n = self.n_treatments
        
        for i in range(n):
            for j in range(i + 1, n):
                if adj[i, j]:
                    continue  # Skip direct comparisons
                
                # Find all indirect paths of length 2 (through a common comparator)
                for k in range(n):
                    if adj[i, k] and adj[k, j]:
                        # Indirect: i -> k -> j
                        indirect_eff = eff[i, k] + eff[k, j]
                        indirect_se = math.sqrt(se[i, k]**2 + se[k, j]**2)
                        
                        ci_lower = math.exp(indirect_eff - 1.96 * indirect_se)
                        ci_upper = math.exp(indirect_eff + 1.96 * indirect_se)
                        p_value = 2 * (1 - sp_stats.norm.cdf(abs(indirect_eff / indirect_se))) if indirect_se > 0 else 1.0
                        
                        results.append({
                            "treatment_a": self.treatments[i],
                            "treatment_b": self.treatments[j],
                            "via": self.treatments[k],
                            "effect": round(math.exp(indirect_eff), 4),
                            "ci_lower": round(ci_lower, 4),
                            "ci_upper": round(ci_upper, 4),
                            "log_effect": round(indirect_eff, 4),
                            "se": round(indirect_se, 4),
                            "p_value": round(p_value, 4),
                            "source": "indirect",
                        })
                        break  # Use first available indirect path
        
        return results

    def _network_estimates(self, adj, eff, se):
        """Combine direct + indirect estimates using inverse-variance weighting."""
        n = self.n_treatments
        results = []
        
        for i in range(n):
            for j in range(i + 1, n):
                direct_eff = None
                direct_se = None
                indirect_eff = None
                indirect_se = None
                
                # Direct evidence
                if adj[i, j]:
                    direct_eff = eff[i, j]
                    direct_se = se[i, j]
                
                # Indirect evidence (first available path)
                for k in range(n):
                    if adj[i, k] and adj[k, j]:
                        indirect_eff = eff[i, k] + eff[k, j]
                        indirect_se = math.sqrt(se[i, k]**2 + se[k, j]**2)
                        break
                
                # Combine
                if direct_eff is not None and indirect_eff is not None:
                    # Inverse-variance weighted combination
                    w_d = 1.0 / (direct_se**2)
                    w_i = 1.0 / (indirect_se**2)
                    combined_eff = (w_d * direct_eff + w_i * indirect_eff) / (w_d + w_i)
                    combined_se = math.sqrt(1.0 / (w_d + w_i))
                    source = "combined"
                elif direct_eff is not None:
                    combined_eff = direct_eff
                    combined_se = direct_se
                    source = "direct_only"
                elif indirect_eff is not None:
                    combined_eff = indirect_eff
                    combined_se = indirect_se
                    source = "indirect_only"
                else:
                    continue
                
                ci_lower = math.exp(combined_eff - 1.96 * combined_se)
                ci_upper = math.exp(combined_eff + 1.96 * combined_se)
                p_value = 2 * (1 - sp_stats.norm.cdf(abs(combined_eff / combined_se))) if combined_se > 0 else 1.0
                
                results.append({
                    "treatment_a": self.treatments[i],
                    "treatment_b": self.treatments[j],
                    "effect": round(math.exp(combined_eff), 4),
                    "ci_lower": round(ci_lower, 4),
                    "ci_upper": round(ci_upper, 4),
                    "log_effect": round(combined_eff, 4),
                    "se": round(combined_se, 4),
                    "p_value": round(p_value, 4),
                    "source": source,
                })
        
        return results

    def _assess_consistency(self, direct, indirect):
        """Assess consistency between direct and indirect evidence."""
        inconsistencies = []
        
        # Build lookup for indirect estimates
        indirect_lookup = {}
        for ind in indirect:
            key = tuple(sorted([ind["treatment_a"], ind["treatment_b"]]))
            indirect_lookup[key] = ind
        
        for d in direct:
            key = tuple(sorted([d["treatment_a"], d["treatment_b"]]))
            if key in indirect_lookup:
                ind = indirect_lookup[key]
                # Calculate difference (inconsistency)
                diff = d["log_effect"] - ind["log_effect"]
                se_diff = math.sqrt(d["se"]**2 + ind["se"]**2)
                z = diff / se_diff if se_diff > 0 else 0
                p = 2 * (1 - sp_stats.norm.cdf(abs(z)))
                
                inconsistencies.append({
                    "comparison": f"{key[0]} vs {key[1]}",
                    "direct_effect": d["effect"],
                    "indirect_effect": ind["effect"],
                    "difference": round(diff, 4),
                    "se_difference": round(se_diff, 4),
                    "z_statistic": round(z, 4),
                    "p_value": round(p, 4),
                    "consistent": p > 0.05,
                })
        
        overall_p = 1.0
        if inconsistencies:
            chi2 = sum(inc["z_statistic"]**2 for inc in inconsistencies)
            df = len(inconsistencies)
            overall_p = 1 - sp_stats.chi2.cdf(chi2, df) if df > 0 else 1.0
        
        return {
            "loop_comparisons": inconsistencies,
            "n_inconsistency_tests": len(inconsistencies),
            "overall_chi2": round(sum(inc["z_statistic"]**2 for inc in inconsistencies), 4) if inconsistencies else 0,
            "overall_p_value": round(overall_p, 4),
            "conclusion": "consistent" if overall_p > 0.05 else "inconsistent",
        }

    def _calculate_sucra(self, network_estimates):
        """Calculate SUCRA (Surface Under the Cumulative Ranking) for each treatment."""
        # Build a matrix of log-effects between all treatment pairs
        n = self.n_treatments
        eff_matrix = np.zeros((n, n))
        
        for est in network_estimates:
            i = self.treatments.index(est["treatment_a"])
            j = self.treatments.index(est["treatment_b"])
            eff_matrix[i, j] = est["log_effect"]
            eff_matrix[j, i] = -est["log_effect"]
        
        # For each treatment, calculate probability of being best, 2nd best, etc.
        # Using pairwise comparison approach
        ranking_scores = {}
        
        for t_idx, treatment in enumerate(self.treatments):
            # Count how many treatments this one is better than
            wins = 0
            total = 0
            for other_idx in range(n):
                if t_idx == other_idx:
                    continue
                # Positive effect means treatment_a is better
                if eff_matrix[t_idx, other_idx] > 0:
                    wins += 1
                total += 1
            
            # Simple SUCRA approximation
            sucra = wins / total if total > 0 else 0.5
            ranking_scores[treatment] = {
                "sucra": round(sucra, 4),
                "rank": 0,  # Will be assigned below
            }
        
        # Assign ranks
        sorted_treatments = sorted(ranking_scores.keys(), key=lambda t: ranking_scores[t]["sucra"], reverse=True)
        for rank, treatment in enumerate(sorted_treatments, 1):
            ranking_scores[treatment]["rank"] = rank
        
        return ranking_scores

    def _network_diagram_svg(self, adj) -> str:
        """Generate SVG network diagram showing treatment comparisons."""
        n = self.n_treatments
        w, h = 600, 500
        
        # Position treatments in a circle
        cx, cy = w // 2, h // 2
        radius = min(w, h) * 0.35
        
        positions = []
        for i in range(n):
            angle = 2 * math.pi * i / n - math.pi / 2
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            positions.append((x, y))
        
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        svg += f'<rect width="{w}" height="{h}" fill="#0d1117"/>'
        svg += f'<text x="{w//2}" y="30" text-anchor="middle" fill="#e6edf3" font-size="16" font-weight="bold" font-family="Inter,sans-serif">Network Meta-Analysis Network</text>'
        
        # Count comparisons per treatment for line thickness
        max_comparisons = max(sum(adj[i]) for i in range(n)) if n > 0 else 1
        
        # Draw edges (comparisons)
        for i in range(n):
            for j in range(i + 1, n):
                if adj[i, j]:
                    x1, y1 = positions[i]
                    x2, y2 = positions[j]
                    # Line thickness based on number of connections
                    thickness = 1 + (sum(adj[i]) + sum(adj[j])) / (2 * max_comparisons) * 3
                    svg += f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#58a6ff" stroke-width="{thickness:.1f}" opacity="0.6"/>'
                    
                    # Comparison label
                    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                    # Find the comparison effect
                    for c in self.comparisons:
                        if (c["treatment_a"] == self.treatments[i] and c["treatment_b"] == self.treatments[j]) or                            (c["treatment_a"] == self.treatments[j] and c["treatment_b"] == self.treatments[i]):
                            svg += f'<text x="{mx:.1f}" y="{my:.1f}" text-anchor="middle" fill="#8b949e" font-size="9" font-family="JetBrains Mono,monospace">OR={c["effect"]:.2f}</text>'
                            break
        
        # Draw nodes (treatments)
        for i, (x, y) in enumerate(positions):
            node_r = 25 + sum(adj[i]) * 3
            svg += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{node_r}" fill="#1f6feb" stroke="#58a6ff" stroke-width="2"/>'
            svg += f'<text x="{x:.1f}" y="{y+4:.1f}" text-anchor="middle" fill="#ffffff" font-size="12" font-weight="bold" font-family="Inter,sans-serif">{self.treatments[i]}</text>'
        
        # Legend
        svg += f'<text x="20" y="{h-20}" fill="#8b949e" font-size="11" font-family="Inter,sans-serif">Nodes: Treatments | Edges: Direct comparisons | N={self.n_treatments} treatments, E={len(self.comparisons)} comparisons</text>'
        
        svg += '</svg>'
        return svg

    def _league_table_svg(self, network_estimates) -> str:
        """Generate SVG league table showing all pairwise comparisons."""
        n = self.n_treatments
        
        # Build lookup
        lookup = {}
        for est in network_estimates:
            key = (est["treatment_a"], est["treatment_b"])
            lookup[key] = est
            # Add reverse
            rev_key = (est["treatment_b"], est["treatment_a"])
            if rev_key not in lookup:
                lookup[rev_key] = {
                    "treatment_a": est["treatment_b"],
                    "treatment_b": est["treatment_a"],
                    "effect": round(1.0 / est["effect"], 4) if est["effect"] > 0 else 0,
                    "ci_lower": round(1.0 / est["ci_upper"], 4) if est["ci_upper"] > 0 else 0,
                    "ci_upper": round(1.0 / est["ci_lower"], 4) if est["ci_lower"] > 0 else 0,
                }
        
        cell_w, cell_h = 100, 40
        label_w = 100
        w = label_w + n * cell_w + 20
        h = label_w + n * cell_h + 60
        
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        svg += f'<rect width="{w}" height="{h}" fill="#0d1117"/>'
        svg += f'<text x="{w//2}" y="25" text-anchor="middle" fill="#e6edf3" font-size="16" font-weight="bold" font-family="Inter,sans-serif">League Table — Network Meta-Analysis</text>'
        
        # Column headers
        y_start = 50
        for j in range(n):
            x = label_w + j * cell_w + cell_w // 2
            svg += f'<text x="{x}" y="{y_start}" text-anchor="middle" fill="#58a6ff" font-size="11" font-weight="bold" font-family="Inter,sans-serif">{self.treatments[j]}</text>'
        
        # Rows
        for i in range(n):
            y = y_start + 20 + i * cell_h
            
            # Row header
            svg += f'<text x="10" y="{y + cell_h // 2 + 4}" fill="#58a6ff" font-size="11" font-weight="bold" font-family="Inter,sans-serif">{self.treatments[i]}</text>'
            
            for j in range(n):
                x = label_w + j * cell_w
                
                if i == j:
                    # Diagonal cell
                    svg += f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" fill="#161b22" stroke="#30363d"/>'
                    svg += f'<text x="{x + cell_w//2}" y="{y + cell_h//2 + 4}" text-anchor="middle" fill="#484f58" font-size="11">—</text>'
                else:
                    # Find estimate
                    key = (self.treatments[i], self.treatments[j])
                    if key in lookup:
                        est = lookup[key]
                        # Color based on significance
                        if est.get("ci_lower", 0) > 1 or est.get("ci_upper", 0) < 1:
                            bg_color = "rgba(34, 197, 94, 0.1)"  # Significant
                            text_color = "#22c55e"
                        else:
                            bg_color = "rgba(255, 255, 255, 0.02)"
                            text_color = "#e6edf3"
                        
                        svg += f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" fill="{bg_color}" stroke="#30363d"/>'
                        effect_text = f'{est["effect"]:.2f}' if est.get("effect") else "N/A"
                        ci_text = f'[{est.get("ci_lower", 0):.2f},{est.get("ci_upper", 0):.2f}]' if est.get("ci_lower") else ""
                        svg += f'<text x="{x + cell_w//2}" y="{y + cell_h//2 - 2}" text-anchor="middle" fill="{text_color}" font-size="11" font-weight="600" font-family="JetBrains Mono,monospace">{effect_text}</text>'
                        svg += f'<text x="{x + cell_w//2}" y="{y + cell_h//2 + 12}" text-anchor="middle" fill="#8b949e" font-size="8" font-family="JetBrains Mono,monospace">{ci_text}</text>'
                    else:
                        svg += f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" fill="#0d1117" stroke="#30363d"/>'
                        svg += f'<text x="{x + cell_w//2}" y="{y + cell_h//2 + 4}" text-anchor="middle" fill="#484f58" font-size="10">No data</text>'
        
        # Legend
        legend_y = y_start + 20 + n * cell_h + 20
        svg += f'<text x="20" y="{legend_y}" fill="#22c55e" font-size="10" font-family="Inter,sans-serif">Green: Significant (CI excludes 1.0)</text>'
        svg += f'<text x="300" y="{legend_y}" fill="#8b949e" font-size="10" font-family="Inter,sans-serif">Row treatment vs Column treatment (OR scale)</text>'
        
        svg += '</svg>'
        return svg


nma_engine = NMAEngine()


@app.post("/api/nma/analyze")
async def api_nma_analyze(request: Request):
    """Run Network Meta-Analysis.
    
    Body JSON:
      comparisons: list of {treatment_a, treatment_b, effect, ci_lower, ci_upper, weight}
    """
    body = await request.json()
    comparisons = body.get("comparisons", [])
    
    if len(comparisons) < 2:
        raise HTTPException(400, "At least 2 comparisons required for NMA")
    
    # Validate
    for c in comparisons:
        if "treatment_a" not in c or "treatment_b" not in c or "effect" not in c:
            raise HTTPException(400, "Each comparison needs treatment_a, treatment_b, effect")
        if "ci_lower" not in c:
            c["ci_lower"] = c["effect"] * 0.8
        if "ci_upper" not in c:
            c["ci_upper"] = c["effect"] * 1.2
        if "weight" not in c:
            c["weight"] = 100
    
    try:
        result = nma_engine.analyze(comparisons)
        if "error" in result:
            raise HTTPException(400, result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/nma/network")
async def api_nma_network(request: Request):
    """Generate NMA network diagram SVG."""
    body = await request.json()
    comparisons = body.get("comparisons", [])
    result = nma_engine.analyze(comparisons)
    return {"svg": result.get("network_svg", ""), "treatments": result.get("treatments", [])}


@app.post("/api/nma/league")
async def api_nma_league(request: Request):
    """Generate NMA league table SVG."""
    body = await request.json()
    comparisons = body.get("comparisons", [])
    result = nma_engine.analyze(comparisons)
    return {"svg": result.get("league_svg", ""), "treatments": result.get("treatments", [])}


@app.get("/api/nma/demo")
async def api_nma_demo():
    """Run NMA demo with sample oncology data."""
    demo_comparisons = [
        {"treatment_a": "Pembrolizumab", "treatment_b": "Chemotherapy", "effect": 0.73, "ci_lower": 0.64, "ci_upper": 0.84},
        {"treatment_a": "Nivolumab", "treatment_b": "Chemotherapy", "effect": 0.78, "ci_lower": 0.67, "ci_upper": 0.91},
        {"treatment_a": "Atezolizumab", "treatment_b": "Chemotherapy", "effect": 0.81, "ci_lower": 0.70, "ci_upper": 0.94},
        {"treatment_a": "Pembrolizumab", "treatment_b": "Nivolumab", "effect": 0.94, "ci_lower": 0.79, "ci_upper": 1.11},
        {"treatment_a": "Chemotherapy", "treatment_b": "Best_Supportive_Care", "effect": 0.75, "ci_lower": 0.62, "ci_upper": 0.91},
        {"treatment_a": "Nivolumab", "treatment_b": "Best_Supportive_Care", "effect": 0.60, "ci_lower": 0.48, "ci_upper": 0.75},
    ]
    
    try:
        result = nma_engine.analyze(demo_comparisons)
        return result
    except Exception as e:
        raise HTTPException(500, str(e))

# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    print("MetaForge v3.0.0 — AI循证医学研究平台")
    print("访问: http://localhost:8000")
    print("工作台: http://localhost:8000/app")
    uvicorn.run(app, host="0.0.0.0", port=8000)
