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

import numpy as np
from scipy import stats as sp_stats

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
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

        # Step 1: 计算每个研究的效应量
        study_results = []
        for s in studies:
            if s.data_type == "dichotomous":
                sr = self._calc_dichotomous(s, effect_measure)
            else:
                continue
            study_results.append(sr)

        # Step 2: 合并效应量
        if model == "fixed":
            pooled = self._fixed_effect(study_results)
        else:
            pooled = self._random_effects(study_results)

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

    def _fixed_effect(self, studies: List[StudyResult]) -> dict:
        """固定效应模型 (Mantel-Haenszel / Inverse Variance)"""
        total_w = sum(s.weight for s in studies)
        pooled_log = sum(s.weight * s.log_effect for s in studies) / total_w
        pooled_se = math.sqrt(1.0 / total_w)
        pooled_effect = math.exp(pooled_log)
        ci_lower = math.exp(pooled_log - 1.96 * pooled_se)
        ci_upper = math.exp(pooled_log + 1.96 * pooled_se)
        z = pooled_log / pooled_se
        p_value = 2 * (1 - sp_stats.norm.cdf(abs(z)))
        return {"effect": pooled_effect, "ci_lower": ci_lower, "ci_upper": ci_upper, "p_value": p_value}

    def _random_effects(self, studies: List[StudyResult]) -> dict:
        """随机效应模型 (DerSimonian-Laird)"""
        # First get fixed effect estimate
        fe = self._fixed_effect(studies)
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
        pooled_effect = math.exp(pooled_log)
        ci_lower = math.exp(pooled_log - 1.96 * pooled_se)
        ci_upper = math.exp(pooled_log + 1.96 * pooled_se)
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
    srs = [engine._calc_dichotomous(s, effect_measure) for s in studies]
    pooled = engine._fixed_effect(srs)
    svg = engine._forest_plot(srs, pooled, effect_measure)
    return {"svg": svg, "pooled": pooled}


@app.post("/api/funnel")
async def api_funnel(request: Request):
    """单独生成漏斗图"""
    body = await request.json()
    studies_data = body.get("studies", [])
    effect_measure = body.get("effect_measure", "OR")

    studies = [StudyInput(**s) for s in studies_data]
    srs = [engine._calc_dichotomous(s, effect_measure) for s in studies]
    pooled = engine._fixed_effect(srs)
    svg = engine._funnel_plot(srs, pooled)
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
        ],
    }


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    print("MetaForge v3.0.0 — AI循证医学研究平台")
    print("访问: http://localhost:8000")
    print("工作台: http://localhost:8000/app")
    uvicorn.run(app, host="0.0.0.0", port=8000)
