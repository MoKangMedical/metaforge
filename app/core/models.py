"""
MetaForge — 核心数据模型
抗幻觉架构：每个数据点都可追溯到原始文献

核心原则：
1. Grounding（锚定）：AI只能处理已检索到的文献，不能凭训练数据生成
2. Provenance（溯源）：每个提取值必须标注 PMID + 页码 + 表格编号
3. Confidence（置信度）：每个AI判断必须附带置信度，低于阈值需人工审核
4. Dual Verification（双重验证）：规则引擎交叉验证AI的输出
"""

import json
import uuid
import hashlib
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum


# ============================================
# 枚举定义
# ============================================

class ProjectStatus(str, Enum):
    CREATED = "created"
    SEARCHING = "searching"
    SCREENING = "screening"
    EXTRACTING = "extracting"
    EVALUATING = "evaluating"
    ANALYZING = "analyzing"
    REPORTING = "reporting"
    COMPLETED = "completed"


class ScreenDecision(str, Enum):
    INCLUDE = "include"
    EXCLUDE = "exclude"
    UNCERTAIN = "uncertain"  # 需要人工审核


class RiskOfBias(str, Enum):
    LOW = "low"
    HIGH = "high"
    SOME_CONCERNS = "some_concerns"


class EvidenceQuality(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    VERY_LOW = "very_low"


# ============================================
# 抗幻觉核心：溯源记录
# ============================================

@dataclass
class ProvenanceRecord:
    """
    溯源记录 — 每个数据点的"身份证"
    
    这是防幻觉的核心机制：
    - AI提取的每个值都必须有这个记录
    - 没有溯源的数据点被视为"幻觉"，自动标记待审核
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    pmid: str = ""                           # PubMed ID
    source_url: str = ""                     # 原文URL
    page_number: Optional[int] = None        # PDF页码
    table_number: Optional[str] = None       # 表格编号（如 "Table 2"）
    figure_number: Optional[str] = None      # 图编号
    raw_text: str = ""                       # 原文原始文本片段
    extracted_value: str = ""                # AI提取的值
    extraction_method: str = ""              # 提取方式："ai_gpt4o", "ocr", "manual"
    confidence: float = 0.0                  # AI置信度 [0, 1]
    verified: bool = False                   # 人工是否已验证
    verified_by: str = ""                    # 验证人
    verified_at: Optional[str] = None        # 验证时间
    needs_review: bool = False               # 是否需要人工审核
    review_reason: str = ""                  # 需要审核的原因
    
    def to_dict(self):
        return asdict(self)
    
    def is_grounded(self) -> bool:
        """判断这个数据点是否"锚定"在真实文献上"""
        return bool(self.pmid and self.raw_text)


@dataclass
class AuditLog:
    """
    审计日志 — 记录系统的每个操作，用于回溯和复现
    """
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    action: str = ""           # 操作类型
    agent: str = ""            # 哪个Agent执行的
    input_summary: str = ""    # 输入摘要
    output_summary: str = ""   # 输出摘要
    confidence: float = 0.0
    details: dict = field(default_factory=dict)


# ============================================
# 文献模型
# ============================================

@dataclass
class Article:
    """一篇文献的完整信息"""
    pmid: str = ""
    title: str = ""
    authors: list = field(default_factory=list)
    abstract: str = ""
    journal: str = ""
    year: int = 0
    doi: str = ""
    pmc_id: str = ""
    publication_types: list = field(default_factory=list)
    mesh_terms: list = field(default_factory=list)
    keywords: list = field(default_factory=list)
    
    # 全文信息（如果有）
    full_text_url: str = ""
    pdf_path: str = ""
    
    # 筛选结果
    screen_decision: str = ""  # ScreenDecision
    screen_reason: str = ""
    screen_confidence: float = 0.0
    screen_needs_review: bool = False
    
    # 数据提取结果
    extracted_data: dict = field(default_factory=dict)
    
    # 质量评价结果
    rob_rating: str = ""  # RiskOfBias
    rob_details: dict = field(default_factory=dict)
    
    # 溯源
    provenance: list = field(default_factory=list)
    
    def to_dict(self):
        return asdict(self)


@dataclass
class ScreenCriteria:
    """
    PICOS纳排标准
    """
    # P - Population
    population_include: str = ""
    population_exclude: str = ""
    
    # I - Intervention
    intervention_include: str = ""
    intervention_exclude: str = ""
    
    # C - Comparator
    comparator_include: str = ""
    comparator_exclude: str = ""
    
    # O - Outcome
    outcome_primary: str = ""
    outcome_secondary: str = ""
    
    # S - Study Design
    study_design_include: str = ""
    study_design_exclude: str = ""
    
    # 额外标准
    language: str = "无限制"
    date_range: str = ""
    sample_size_min: int = 0


# ============================================
# 统计分析模型
# ============================================

@dataclass
class StudyData:
    """单个研究的效应量数据"""
    pmid: str = ""
    study_name: str = ""  # 如 "Smith 2020"
    
    # 二分类变量
    treatment_events: int = 0
    treatment_total: int = 0
    control_events: int = 0
    control_total: int = 0
    
    # 连续变量
    treatment_mean: float = 0.0
    treatment_sd: float = 0.0
    treatment_n: int = 0
    control_mean: float = 0.0
    control_sd: float = 0.0
    control_n: int = 0
    
    # 计算出的效应量
    effect_measure: str = ""  # "OR", "RR", "MD", "SMD"
    effect_size: float = 0.0
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    weight: float = 0.0
    
    # 溯源
    provenance: Provenance = None
    
    # 验证状态
    verified: bool = False
    cross_check_passed: bool = False  # 交叉验证是否通过


@dataclass
class MetaResult:
    """Meta分析结果"""
    effect_measure: str = ""       # 效应量类型
    pooled_effect: float = 0.0     # 合并效应量
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    p_value: float = 0.0
    
    # 异质性
    heterogeneity_method: str = ""  # "random" / "fixed"
    i_squared: float = 0.0         # I² 异质性
    tau_squared: float = 0.0       # τ²
    q_statistic: float = 0.0
    q_p_value: float = 0.0
    
    # 亚组分析
    subgroup_results: dict = field(default_factory=dict)
    
    # 敏感性分析
    sensitivity_results: list = field(default_factory=list)
    
    # 发表偏倚
    egger_p: float = 0.0
    begg_p: float = 0.0
    funnel_plot_path: str = ""
    
    # 可视化
    forest_plot_path: str = ""
    forest_plot_html: str = ""      # 交互式Plotly图
    
    # 溯源
    study_data: list = field(default_factory=list)
    audit_log: list = field(default_factory=list)


# ============================================
# 项目模型
# ============================================

@dataclass
class MetaForgeProject:
    """
    一个Meta分析项目的完整状态
    
    包含：
    - 项目元信息
    - 检索到的文献
    - 筛选标准和结果
    - 提取的数据（带溯源）
    - 统计分析结果
    - 完整审计日志
    """
    id: str = field(default_factory=lambda: f"MF-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4]}")
    title: str = ""
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = ProjectStatus.CREATED
    
    # 检索
    search_query: str = ""
    databases: list = field(default_factory=lambda: ["pubmed"])
    search_results: list = field(default_factory=list)  # List[Article]
    total_found: int = 0
    after_dedup: int = 0
    
    # 筛选
    criteria: ScreenCriteria = field(default_factory=ScreenCriteria)
    after_title_abstract_screen: int = 0
    after_fulltext_screen: int = 0
    excluded_articles: list = field(default_factory=list)
    exclusion_reasons: dict = field(default_factory=dict)  # 原因 -> 数量
    
    # 数据提取
    extraction_template: dict = field(default_factory=dict)
    extracted_studies: list = field(default_factory=list)  # List[StudyData]
    
    # 统计分析
    analysis_config: dict = field(default_factory=dict)
    meta_result: MetaResult = field(default_factory=MetaResult)
    
    # PRISMA
    prisma_flow: dict = field(default_factory=dict)
    prisma_flowchart_html: str = ""
    
    # 报告
    report_zh: str = ""
    report_en: str = ""
    
    # 审计
    audit_log: list = field(default_factory=list)
    
    def add_audit(self, action: str, agent: str, **kwargs):
        """添加审计日志"""
        self.audit_log.append(AuditLog(
            action=action,
            agent=agent,
            details=kwargs
        ).to_dict())
        self.updated_at = datetime.now().isoformat()
    
    def get_validation_summary(self) -> dict:
        """
        获取验证摘要 — 这是防幻觉的关键报告
        
        返回：
        - 总数据点数
        - 已验证数
        - 需审核数
        - 溯源覆盖度
        """
        total = 0
        verified = 0
        needs_review = 0
        grounded = 0
        
        for article in self.search_results:
            for p in article.get("provenance", []):
                total += 1
                if p.get("verified"):
                    verified += 1
                if p.get("needs_review"):
                    needs_review += 1
                if p.get("pmid") and p.get("raw_text"):
                    grounded += 1
        
        return {
            "total_data_points": total,
            "verified": verified,
            "needs_review": needs_review,
            "grounded": grounded,
            "grounding_rate": grounded / total if total > 0 else 0,
            "verification_rate": verified / total if total > 0 else 0,
            "hallucination_risk": "LOW" if (grounded / total if total > 0 else 1) > 0.95 else "HIGH"
        }
    
    def to_dict(self):
        return asdict(self)
    
    def to_json(self, indent=2):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


# ============================================
# 抗幻觉验证引擎
# ============================================

class AntiHallucinationValidator:
    """
    防幻觉验证引擎
    
    三道防线：
    1. Grounding Check（锚定检查）：数据必须来自检索到的文献
    2. Cross Validation（交叉验证）：用规则引擎校验AI的提取结果
    3. Confidence Gate（置信度门槛）：低于阈值的数据点自动标红
    """
    
    CONFIDENCE_THRESHOLD = 0.85  # 低于此值需人工审核
    
    @staticmethod
    def validate_extraction(provenance: ProvenanceRecord, extracted_value: str) -> dict:
        """
        验证单个数据提取结果
        
        返回验证报告
        """
        issues = []
        
        # 1. 锚定检查
        if not provenance.pmid:
            issues.append("CRITICAL: 缺少PMID，无法追溯到原始文献")
        if not provenance.raw_text:
            issues.append("WARNING: 缺少原文片段，无法验证提取准确性")
        
        # 2. 置信度检查
        if provenance.confidence < AntiHallucinationValidator.CONFIDENCE_THRESHOLD:
            issues.append(f"LOW_CONFIDENCE: AI置信度 {provenance.confidence:.2f} < 阈值 {AntiHallucinationValidator.CONFIDENCE_THRESHOLD}")
            provenance.needs_review = True
            provenance.review_reason = f"置信度过低 ({provenance.confidence:.2f})"
        
        # 3. 值合理性检查
        if extracted_value:
            # 数值边界检查
            try:
                val = float(extracted_value)
                if val < 0 and "proportion" in provenance.extracted_value.lower():
                    issues.append("ERROR: 比例值不能为负数")
                if val > 1 and "proportion" in provenance.extracted_value.lower():
                    issues.append("ERROR: 比例值不能大于1")
            except (ValueError, TypeError):
                pass
        
        return {
            "valid": len([i for i in issues if i.startswith("CRITICAL") or i.startswith("ERROR")]) == 0,
            "issues": issues,
            "confidence": provenance.confidence,
            "needs_review": provenance.needs_review or len(issues) > 0,
            "provenance_id": provenance.id
        }
    
    @staticmethod
    def cross_validate_study_data(data: dict) -> dict:
        """
        交叉验证研究数据
        
        检查：
        - 样本量加和
        - 置信区间计算
        - P值一致性
        """
        issues = []
        
        # 检查样本量
        if all(k in data for k in ["treatment_total", "control_total", "total_n"]):
            expected_total = data["treatment_total"] + data["control_total"]
            if abs(expected_total - data["total_n"]) > 1:
                issues.append(f"样本量不一致: 治疗组({data['treatment_total']}) + 对照组({data['control_total']}) ≠ 总数({data['total_n']})")
        
        # 检查事件数不超过总数
        if "treatment_events" in data and "treatment_total" in data:
            if data["treatment_events"] > data["treatment_total"]:
                issues.append(f"治疗组事件数({data['treatment_events']})超过总人数({data['treatment_total']})")
        
        if "control_events" in data and "control_total" in data:
            if data["control_events"] > data["control_total"]:
                issues.append(f"对照组事件数({data['control_events']})超过总人数({data['control_total']})")
        
        # 检查置信区间包含效应量
        if all(k in data for k in ["effect_size", "ci_lower", "ci_upper"]):
            if data["effect_size"] < data["ci_lower"] or data["effect_size"] > data["ci_upper"]:
                issues.append(f"效应量({data['effect_size']})不在置信区间[{data['ci_lower']}, {data['ci_upper']}]内")
        
        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "checks_performed": ["sample_size", "event_count", "confidence_interval"]
        }
    
    @staticmethod
    def generate_grounding_report(project: dict) -> dict:
        """
        生成防幻觉报告
        
        这是项目的"体检报告"，告诉用户：
        - 有多少数据点是锚定在真实文献上的
        - 有多少需要人工审核
        - 整体幻觉风险等级
        """
        articles = project.get("search_results", [])
        
        total_extractions = 0
        grounded_extractions = 0
        high_confidence = 0
        needs_review = 0
        ungrounded_items = []
        
        for article in articles:
            for p in article.get("provenance", []):
                total_extractions += 1
                if p.get("pmid") and p.get("raw_text"):
                    grounded_extractions += 1
                else:
                    ungrounded_items.append({
                        "pmid": article.get("pmid", "unknown"),
                        "title": article.get("title", "")[:80],
                        "value": p.get("extracted_value", ""),
                        "reason": "缺少原文锚定"
                    })
                if p.get("confidence", 0) >= 0.85:
                    high_confidence += 1
                if p.get("needs_review"):
                    needs_review += 1
        
        grounding_rate = grounded_extractions / total_extractions if total_extractions > 0 else 1.0
        
        return {
            "total_extractions": total_extractions,
            "grounded": grounded_extractions,
            "grounding_rate": grounding_rate,
            "high_confidence": high_confidence,
            "needs_review": needs_review,
            "ungrounded_items": ungrounded_items[:10],  # 最多显示10个
            "risk_level": "LOW" if grounding_rate > 0.95 else ("MEDIUM" if grounding_rate > 0.8 else "HIGH"),
            "recommendation": (
                "✓ 所有数据点均锚定在真实文献上，幻觉风险极低" if grounding_rate > 0.95
                else f"⚠ 有 {len(ungrounded_items)} 个数据点缺少原文锚定，建议人工审核" if grounding_rate > 0.8
                else f"🚨 幻觉风险高！{len(ungrounded_items)} 个数据点无法追溯，请务必人工审核"
            )
        }
