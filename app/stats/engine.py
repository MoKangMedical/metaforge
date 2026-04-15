"""
MetaForge — 统计分析引擎

实现真实的Meta分析计算：
- 固定效应模型（Mantel-Haenszel）
- 随机效应模型（DerSimonian-Laird）
- 异质性检验（I², Q, τ²）
- 森林图生成（交互式Plotly）
- 漏斗图
- 亚组分析
- 敏感性分析

所有计算基于NumPy/SciPy，不依赖R或STATA
"""

import json
import math
import base64
import io
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from scipy import stats


@dataclass
class StudyInput:
    """单个研究的输入数据"""
    name: str = ""          # 研究名称，如 "Smith 2020"
    pmid: str = ""
    
    # 二分类数据
    e_events: int = 0       # 实验组事件数
    e_total: int = 0        # 实验组总人数
    c_events: int = 0       # 对照组事件数
    c_total: int = 0        # 对照组总人数
    
    # 连续数据
    e_mean: float = 0.0
    e_sd: float = 0.0
    e_n: int = 0
    c_mean: float = 0.0
    c_sd: float = 0.0
    c_n: int = 0
    
    # 分组信息（用于亚组分析）
    subgroup: str = ""
    
    # 数据类型
    data_type: str = "dichotomous"  # "dichotomous" or "continuous"


@dataclass
class StudyResult:
    """单个研究的计算结果"""
    name: str = ""
    pmid: str = ""
    effect: float = 0.0
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    weight: float = 0.0
    se: float = 0.0
    log_effect: float = 0.0
    log_ci_lower: float = 0.0
    log_ci_upper: float = 0.0
    subgroup: str = ""
    
    # 验证信息
    raw_e_events: int = 0
    raw_e_total: int = 0
    raw_c_events: int = 0
    raw_c_total: int = 0


@dataclass
class MetaAnalysisResult:
    """Meta分析完整结果"""
    # 合并效应
    pooled_effect: float = 0.0
    pooled_ci_lower: float = 0.0
    pooled_ci_upper: float = 0.0
    pooled_se: float = 0.0
    z_value: float = 0.0
    p_value: float = 0.0
    
    # 异质性
    i_squared: float = 0.0
    tau_squared: float = 0.0
    q_statistic: float = 0.0
    q_df: int = 0
    q_p_value: float = 0.0
    heterogeneity: str = ""  # "low", "moderate", "high"
    
    # 模型
    model: str = ""  # "fixed" or "random"
    effect_measure: str = ""  # "OR", "RR", "MD"
    
    # 各研究结果
    studies: List[StudyResult] = field(default_factory=list)
    
    # 森林图
    forest_plot_html: str = ""
    forest_plot_base64: str = ""
    
    # 漏斗图
    funnel_plot_html: str = ""
    
    # 亚组分析
    subgroup_results: dict = field(default_factory=dict)


class MetaAnalysisEngine:
    """
    统计分析引擎
    
    核心算法完全用Python实现（NumPy/SciPy），
    不依赖R或STATA，确保可复现性。
    """
    
    def analyze(self, studies: List[StudyInput], 
                effect_measure: str = "OR",
                model: str = "random") -> MetaAnalysisResult:
        """
        执行Meta分析
        
        Args:
            studies: 研究数据列表
            effect_measure: 效应量类型 "OR" (odds ratio), "RR" (risk ratio), "MD" (mean difference)
            model: 统计模型 "fixed" (固定效应) or "random" (随机效应)
        """
        if not studies:
            return MetaAnalysisResult()
        
        result = MetaAnalysisResult(model=model, effect_measure=effect_measure)
        
        if effect_measure in ("OR", "RR"):
            result = self._analyze_dichotomous(studies, effect_measure, model)
        elif effect_measure == "MD":
            result = self._analyze_continuous(studies, model)
        
        # 生成森林图
        result.forest_plot_html = self._generate_forest_plot_html(result)
        
        # 生成漏斗图
        result.funnel_plot_html = self._generate_funnel_plot_html(result)
        
        # 亚组分析
        result.subgroup_results = self._subgroup_analysis(studies, effect_measure, model)
        
        return result
    
    def _analyze_dichotomous(self, studies: List[StudyInput], 
                              measure: str, model: str) -> MetaAnalysisResult:
        """二分类数据Meta分析（Mantel-Haenszel法）"""
        result = MetaAnalysisResult(model=model, effect_measure=measure)
        
        study_results = []
        yi_list = []  # log效应量
        wi_list = []  # 权重
        vi_list = []  # 方差
        
        for s in studies:
            if s.e_total == 0 or s.c_total == 0:
                continue
            
            # 添加0.5连续性校正（如果有零单元格）
            a = s.e_events
            b = s.e_total - s.e_events
            c = s.c_events
            d = s.c_total - s.c_events
            
            if 0 in (a, b, c, d):
                a += 0.5
                b += 0.5
                c += 0.5
                d += 0.5
            
            n = a + b + c + d
            
            if measure == "OR":
                # log(OR)
                yi = math.log(a * d / (b * c))
                # 方差 = 1/a + 1/b + 1/c + 1/d
                vi = 1/a + 1/b + 1/c + 1/d
            else:  # RR
                yi = math.log((a / (a + b)) / (c / (c + d)))
                vi = 1/a - 1/(a+b) + 1/c - 1/(c+d)
            
            # 固定效应权重
            wi = 1 / vi
            
            sr = StudyResult(
                name=s.name,
                pmid=s.pmid,
                effect=math.exp(yi),
                ci_lower=math.exp(yi - 1.96 * math.sqrt(vi)),
                ci_upper=math.exp(yi + 1.96 * math.sqrt(vi)),
                log_effect=yi,
                log_ci_lower=yi - 1.96 * math.sqrt(vi),
                log_ci_upper=yi + 1.96 * math.sqrt(vi),
                se=math.sqrt(vi),
                subgroup=s.subgroup,
                raw_e_events=s.e_events,
                raw_e_total=s.e_total,
                raw_c_events=s.c_events,
                raw_c_total=s.c_total,
            )
            
            study_results.append(sr)
            yi_list.append(yi)
            wi_list.append(wi)
            vi_list.append(vi)
        
        if not yi_list:
            return result
        
        yi = np.array(yi_list)
        wi = np.array(wi_list)
        vi = np.array(vi_list)
        
        # Q统计量（异质性检验）
        yi_fixed = np.sum(wi * yi) / np.sum(wi)
        q = np.sum(wi * (yi - yi_fixed) ** 2)
        k = len(yi)
        q_df = k - 1
        q_p = 1 - stats.chi2.cdf(q, q_df) if q_df > 0 else 1.0
        
        # I²
        i_sq = max(0, (q - q_df) / q * 100) if q > 0 else 0
        
        # τ² (DerSimonian-Laird)
        c_dl = np.sum(wi) - np.sum(wi ** 2) / np.sum(wi)
        tau_sq = max(0, (q - q_df) / c_dl) if c_dl > 0 else 0
        
        # 合并效应
        if model == "random":
            wi_star = 1 / (vi + tau_sq)
        else:
            wi_star = wi
        
        yi_pooled = np.sum(wi_star * yi) / np.sum(wi_star)
        se_pooled = 1 / math.sqrt(np.sum(wi_star))
        
        z = yi_pooled / se_pooled
        p = 2 * (1 - stats.norm.cdf(abs(z)))
        
        # 归一化权重
        weights = wi_star / np.sum(wi_star) * 100
        
        for i, sr in enumerate(study_results):
            sr.weight = weights[i]
        
        result.pooled_effect = math.exp(yi_pooled)
        result.pooled_ci_lower = math.exp(yi_pooled - 1.96 * se_pooled)
        result.pooled_ci_upper = math.exp(yi_pooled + 1.96 * se_pooled)
        result.pooled_se = se_pooled
        result.z_value = z
        result.p_value = p
        result.i_squared = i_sq
        result.tau_squared = tau_sq
        result.q_statistic = q
        result.q_df = q_df
        result.q_p_value = q_p
        result.studies = study_results
        
        # 异质性判断
        if i_sq < 25:
            result.heterogeneity = "low"
        elif i_sq < 75:
            result.heterogeneity = "moderate"
        else:
            result.heterogeneity = "high"
        
        return result
    
    def _analyze_continuous(self, studies: List[StudyInput], model: str) -> MetaAnalysisResult:
        """连续数据Meta分析（逆方差法）"""
        result = MetaAnalysisResult(model=model, effect_measure="MD")
        
        study_results = []
        yi_list = []
        wi_list = []
        vi_list = []
        
        for s in studies:
            if s.e_n == 0 or s.c_n == 0:
                continue
            
            # 均数差 (Mean Difference)
            yi = s.e_mean - s.c_mean
            # 方差
            vi = (s.e_sd ** 2 / s.e_n) + (s.c_sd ** 2 / s.c_n)
            wi = 1 / vi
            
            sr = StudyResult(
                name=s.name,
                pmid=s.pmid,
                effect=yi,
                ci_lower=yi - 1.96 * math.sqrt(vi),
                ci_upper=yi + 1.96 * math.sqrt(vi),
                log_effect=yi,
                se=math.sqrt(vi),
                subgroup=s.subgroup,
            )
            
            study_results.append(sr)
            yi_list.append(yi)
            wi_list.append(wi)
            vi_list.append(vi)
        
        if not yi_list:
            return result
        
        yi = np.array(yi_list)
        wi = np.array(wi_list)
        vi = np.array(vi_list)
        
        # Q统计量
        yi_fixed = np.sum(wi * yi) / np.sum(wi)
        q = np.sum(wi * (yi - yi_fixed) ** 2)
        k = len(yi)
        q_df = k - 1
        q_p = 1 - stats.chi2.cdf(q, q_df) if q_df > 0 else 1.0
        i_sq = max(0, (q - q_df) / q * 100) if q > 0 else 0
        
        # τ²
        c_dl = np.sum(wi) - np.sum(wi ** 2) / np.sum(wi)
        tau_sq = max(0, (q - q_df) / c_dl) if c_dl > 0 else 0
        
        if model == "random":
            wi_star = 1 / (vi + tau_sq)
        else:
            wi_star = wi
        
        yi_pooled = np.sum(wi_star * yi) / np.sum(wi_star)
        se_pooled = 1 / math.sqrt(np.sum(wi_star))
        z = yi_pooled / se_pooled
        p = 2 * (1 - stats.norm.cdf(abs(z)))
        
        weights = wi_star / np.sum(wi_star) * 100
        for i, sr in enumerate(study_results):
            sr.weight = weights[i]
        
        result.pooled_effect = yi_pooled
        result.pooled_ci_lower = yi_pooled - 1.96 * se_pooled
        result.pooled_ci_upper = yi_pooled + 1.96 * se_pooled
        result.pooled_se = se_pooled
        result.z_value = z
        result.p_value = p
        result.i_squared = i_sq
        result.tau_squared = tau_sq
        result.q_statistic = q
        result.q_df = q_df
        result.q_p_value = q_p
        result.studies = study_results
        result.heterogeneity = "low" if i_sq < 25 else ("moderate" if i_sq < 75 else "high")
        
        return result
    
    def _subgroup_analysis(self, studies: List[StudyInput], 
                           effect_measure: str, model: str) -> dict:
        """亚组分析"""
        subgroups = {}
        for s in studies:
            if s.subgroup:
                subgroups.setdefault(s.subgroup, []).append(s)
        
        if len(subgroups) <= 1:
            return {}
        
        results = {}
        for name, sg_studies in subgroups.items():
            sg_result = self._analyze_dichotomous(sg_studies, effect_measure, model) \
                if effect_measure in ("OR", "RR") else self._analyze_continuous(sg_studies, model)
            
            results[name] = {
                "pooled_effect": sg_result.pooled_effect,
                "ci_lower": sg_result.pooled_ci_lower,
                "ci_upper": sg_result.pooled_ci_upper,
                "p_value": sg_result.p_value,
                "i_squared": sg_result.i_squared,
                "n_studies": len(sg_studies),
            }
        
        return results
    
    def _generate_forest_plot_html(self, result: MetaAnalysisResult) -> str:
        """生成交互式森林图（Plotly HTML）"""
        if not result.studies:
            return ""
        
        studies = result.studies
        names = [s.name for s in studies]
        effects = [s.effect for s in studies]
        ci_lower = [s.ci_lower for s in studies]
        ci_upper = [s.ci_upper for s in studies]
        weights = [s.weight for s in studies]
        
        # Y轴位置（倒序，第一个研究在最上面）
        y_pos = list(range(len(studies), 0, -1))
        
        # 添加合并效应行
        names.append("合并效应 (Meta-analysis)")
        effects.append(result.pooled_effect)
        ci_lower.append(result.pooled_ci_lower)
        ci_upper.append(result.pooled_ci_upper)
        weights.append(100)
        y_pos.append(0)
        
        # 构建Plotly数据
        traces = []
        
        # 每个研究的点和CI线
        for i in range(len(studies)):
            # CI线
            traces.append({
                "type": "scatter",
                "x": [ci_lower[i], ci_upper[i]],
                "y": [y_pos[i], y_pos[i]],
                "mode": "lines",
                "line": {"color": "#3b82f6", "width": 2},
                "showlegend": False,
                "hoverinfo": "skip",
            })
            # 效应量点（大小与权重成正比）
            size = max(6, min(25, weights[i] * 0.8))
            traces.append({
                "type": "scatter",
                "x": [effects[i]],
                "y": [y_pos[i]],
                "mode": "markers",
                "marker": {"size": size, "color": "#3b82f6", "symbol": "square"},
                "showlegend": False,
                "hovertemplate": f"<b>{names[i]}</b><br>"
                                f"效应量: {effects[i]:.2f}<br>"
                                f"95% CI: [{ci_lower[i]:.2f}, {ci_upper[i]:.2f}]<br>"
                                f"权重: {weights[i]:.1f}%<extra></extra>",
            })
        
        # 合并效应菱形
        diamond_x = [ci_lower[-1], effects[-1], ci_upper[-1], effects[-1], ci_lower[-1]]
        diamond_y = [y_pos[-1], y_pos[-1] + 0.3, y_pos[-1], y_pos[-1] - 0.3, y_pos[-1]]
        traces.append({
            "type": "scatter",
            "x": diamond_x,
            "y": diamond_y,
            "mode": "lines",
            "fill": "toself",
            "fillcolor": "rgba(239, 68, 68, 0.3)",
            "line": {"color": "#ef4444", "width": 2},
            "showlegend": False,
            "hovertemplate": f"<b>合并效应</b><br>"
                            f"效应量: {result.pooled_effect:.2f}<br>"
                            f"95% CI: [{result.pooled_ci_lower:.2f}, {result.pooled_ci_upper:.2f}]<br>"
                            f"p = {result.p_value:.4f}<extra></extra>",
        })
        
        # 无效线
        null_value = 1.0 if result.effect_measure in ("OR", "RR") else 0.0
        traces.append({
            "type": "scatter",
            "x": [null_value, null_value],
            "y": [-0.5, len(studies) + 1],
            "mode": "lines",
            "line": {"color": "#94a3b8", "width": 1, "dash": "dash"},
            "showlegend": False,
            "hoverinfo": "skip",
        })
        
        layout = {
            "title": {
                "text": f"森林图 — {result.effect_measure} (Random Effects Model)" 
                        if result.model == "random" 
                        else f"森林图 — {result.effect_measure} (Fixed Effect Model)",
                "font": {"size": 16, "color": "#e2e8f0"},
            },
            "xaxis": {
                "title": "效应量 (Odds Ratio)" if result.effect_measure == "OR" else "效应量",
                "type": "log" if result.effect_measure in ("OR", "RR") else "linear",
                "gridcolor": "rgba(255,255,255,0.05)",
                "color": "#94a3b8",
            },
            "yaxis": {
                "tickvals": y_pos,
                "ticktext": names,
                "gridcolor": "rgba(255,255,255,0.05)",
                "color": "#94a3b8",
            },
            "plot_bgcolor": "#0d1117",
            "paper_bgcolor": "#0d1117",
            "font": {"color": "#e2e8f0", "family": "Inter, sans-serif"},
            "margin": {"l": 180, "r": 40, "t": 60, "b": 60},
            "height": max(400, len(studies) * 40 + 100),
            "annotations": [
                {
                    "text": f"I² = {result.i_squared:.1f}%, p = {result.q_p_value:.3f}",
                    "xref": "paper", "yref": "paper",
                    "x": 0.98, "y": 0.02,
                    "showarrow": False,
                    "font": {"size": 12, "color": "#94a3b8"},
                }
            ],
        }
        
        # 包装成完整HTML
        plot_json = json.dumps({"data": traces, "layout": layout})
        
        return f"""
        <div id="forest-plot" style="width:100%;height:{max(400, len(studies)*40+100)}px;"></div>
        <script>
            if(typeof Plotly !== 'undefined') {{
                Plotly.newPlot('forest-plot', {plot_json}.data, {plot_json}.layout, {{responsive: true}});
            }}
        </script>
        """
    
    def _generate_funnel_plot_html(self, result: MetaAnalysisResult) -> str:
        """生成漏斗图"""
        if not result.studies:
            return ""
        
        effects = [s.log_effect for s in result.studies]
        se = [s.se for s in result.studies]
        names = [s.name for s in result.studies]
        
        traces = [
            {
                "type": "scatter",
                "x": effects,
                "y": se,
                "mode": "markers",
                "marker": {"size": 8, "color": "#3b82f6"},
                "text": names,
                "hovertemplate": "<b>%{text}</b><br>log(效应量): %{x:.3f}<br>SE: %{y:.3f}<extra></extra>",
                "showlegend": False,
            },
            # 合并效应线
            {
                "type": "scatter",
                "x": [math.log(result.pooled_effect), math.log(result.pooled_effect)],
                "y": [0, max(se) * 1.1],
                "mode": "lines",
                "line": {"color": "#ef4444", "width": 2, "dash": "dash"},
                "showlegend": False,
                "name": "合并效应",
            }
        ]
        
        layout = {
            "title": {"text": "漏斗图 (Funnel Plot)", "font": {"size": 16, "color": "#e2e8f0"}},
            "xaxis": {"title": "log(效应量)", "gridcolor": "rgba(255,255,255,0.05)", "color": "#94a3b8"},
            "yaxis": {"title": "标准误 (SE)", "autorange": "reversed", "gridcolor": "rgba(255,255,255,0.05)", "color": "#94a3b8"},
            "plot_bgcolor": "#0d1117",
            "paper_bgcolor": "#0d1117",
            "font": {"color": "#e2e8f0", "family": "Inter, sans-serif"},
            "margin": {"l": 60, "r": 40, "t": 60, "b": 60},
            "height": 400,
        }
        
        plot_json = json.dumps({"data": traces, "layout": layout})
        
        return f"""
        <div id="funnel-plot" style="width:100%;height:400px;"></div>
        <script>
            if(typeof Plotly !== 'undefined') {{
                Plotly.newPlot('funnel-plot', {plot_json}.data, {plot_json}.layout, {{responsive: true}});
            }}
        </script>
        """


def sensitivity_analysis(studies: List[StudyInput], 
                         effect_measure: str = "OR",
                         model: str = "random") -> list:
    """
    敏感性分析：逐一剔除研究，观察合并效应变化
    """
    engine = MetaAnalysisEngine()
    results = []
    
    full_result = engine.analyze(studies, effect_measure, model)
    
    for i, excluded_study in enumerate(studies):
        remaining = studies[:i] + studies[i+1:]
        if not remaining:
            continue
        
        result = engine.analyze(remaining, effect_measure, model)
        results.append({
            "excluded": excluded_study.name,
            "pooled_effect": result.pooled_effect,
            "ci_lower": result.pooled_ci_lower,
            "ci_upper": result.pooled_ci_upper,
            "i_squared": result.i_squared,
            "change": abs(result.pooled_effect - full_result.pooled_effect),
        })
    
    return results
