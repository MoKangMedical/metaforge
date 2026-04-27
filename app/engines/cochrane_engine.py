"""
MetaForge — Cochrane 方法学合规引擎

严格遵循 Cochrane Handbook for Systematic Reviews of Interventions
在每个阶段嵌入质量控制检查点，确保系统评价的方法学严谨性

8阶段流程：
1. 选题注册 (Protocol Registration)
2. 文献检索 (Literature Search)
3. 初筛 (Title/Abstract Screening)
4. 全文获取 (Full-text Retrieval)
5. 全文复筛 (Full-text Screening)
6. 数据提取 (Data Extraction)
7. 质量评估 (Risk of Bias Assessment)
8. 统计分析与报告 (Analysis & Reporting)
"""

import json
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum


class ReviewStage(Enum):
    """系统评价8阶段"""
    PROTOCOL = "protocol"           # 选题注册
    SEARCH = "search"               # 文献检索
    TITLE_ABSTRACT_SCREEN = "title_abstract_screen"  # 初筛
    FULLTEXT_RETRIEVE = "fulltext_retrieve"          # 全文获取
    FULLTEXT_SCREEN = "fulltext_screen"              # 全文复筛
    DATA_EXTRACTION = "data_extraction"              # 数据提取
    BIAS_ASSESSMENT = "bias_assessment"              # 质量评估
    ANALYSIS_REPORT = "analysis_report"              # 统计分析与报告


class QualityLevel(Enum):
    """GRADE 证据质量等级"""
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    VERY_LOW = "very_low"


@dataclass
class QualityCheckpoint:
    """质量检查点"""
    stage: ReviewStage
    name: str
    description: str
    passed: bool = False
    details: str = ""
    cochrane_reference: str = ""  # Cochrane Handbook 章节
    timestamp: str = ""


@dataclass
class PICOSElements:
    """PICOS 五要素结构化定义"""
    # P - Population/Patient/Problem
    population: str = ""
    population_include: List[str] = field(default_factory=list)
    population_exclude: List[str] = field(default_factory=list)
    population_details: str = ""  # 年龄、性别、疾病分期等
    
    # I - Intervention
    intervention: str = ""
    intervention_include: List[str] = field(default_factory=list)
    intervention_dose: str = ""
    intervention_duration: str = ""
    
    # C - Comparison/Control
    comparison: str = ""
    comparison_include: List[str] = field(default_factory=list)
    
    # O - Outcome
    outcome_primary: List[str] = field(default_factory=list)   # 主要结局
    outcome_secondary: List[str] = field(default_factory=list) # 次要结局
    outcome_timepoints: str = ""
    
    # S - Study Design
    study_design: str = ""
    study_design_include: List[str] = field(default_factory=list)
    
    def to_search_criteria(self) -> dict:
        """转换为检索筛选标准"""
        return {
            "population_include": ", ".join(self.population_include) if self.population_include else self.population,
            "population_exclude": ", ".join(self.population_exclude),
            "intervention_include": ", ".join(self.intervention_include) if self.intervention_include else self.intervention,
            "comparison_include": ", ".join(self.comparison_include),
            "outcome_primary": ", ".join(self.outcome_primary),
            "study_design_include": self.study_design,
        }
    
    def to_summary(self) -> str:
        """生成 PICOS 结构化摘要"""
        lines = []
        if self.population:
            lines.append(f"**P** (人群): {self.population}")
        if self.intervention:
            lines.append(f"**I** (干预): {self.intervention}")
        if self.comparison:
            lines.append(f"**C** (对照): {self.comparison}")
        if self.outcome_primary:
            lines.append(f"**O** (结局): {', '.join(self.outcome_primary)}")
        if self.study_design:
            lines.append(f"**S** (设计): {self.study_design}")
        return "\n".join(lines)


@dataclass
class ProtocolRegistration:
    """系统评价方案注册"""
    title: str = ""
    registration_id: str = ""       # PROSPERO ID
    registration_url: str = ""
    review_type: str = "intervention"  # intervention / diagnostic / prognostic / qualitative
    picos: PICOSElements = field(default_factory=PICOSElements)
    search_strategy: str = ""
    inclusion_criteria: List[str] = field(default_factory=list)
    exclusion_criteria: List[str] = field(default_factory=list)
    outcome_measures: str = ""
    data_synthesis: str = ""        # 定量/定性综合方法
    registration_date: str = ""
    status: str = "draft"           # draft / registered / completed


@dataclass
class StageAudit:
    """阶段审计记录"""
    stage: ReviewStage
    started_at: str = ""
    completed_at: str = ""
    checkpoints: List[QualityCheckpoint] = field(default_factory=list)
    decisions_log: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    @property
    def all_passed(self) -> bool:
        return all(cp.passed for cp in self.checkpoints)
    
    @property
    def pass_rate(self) -> float:
        if not self.checkpoints:
            return 0.0
        return sum(1 for cp in self.checkpoints if cp.passed) / len(self.checkpoints)


class CochraneComplianceEngine:
    """
    Cochrane 方法学合规引擎
    
    确保每个阶段都符合 Cochrane Handbook 要求
    参考: Cochrane Handbook for Systematic Reviews of Interventions v6.4
    """
    
    # 各阶段的质量检查点定义
    STAGE_CHECKPOINTS = {
        ReviewStage.PROTOCOL: [
            {
                "name": "研究问题明确",
                "desc": "PICOS 五要素完整定义，研究问题清晰可回答",
                "ref": "Chapter 2.1: Defining the review question"
            },
            {
                "name": "方案预注册",
                "desc": "在 PROSPERO 或其他注册平台公开注册研究方案",
                "ref": "Chapter 2.2: Developing a protocol"
            },
            {
                "name": "纳入排除标准",
                "desc": "纳入和排除标准基于 PICOS 明确定义",
                "ref": "Chapter 3.3: Eligibility criteria"
            },
            {
                "name": "结局指标定义",
                "desc": "主要和次要结局指标明确定义，包含测量方法和时间点",
                "ref": "Chapter 3.4: Selecting outcomes"
            },
        ],
        ReviewStage.SEARCH: [
            {
                "name": "多数据库检索",
                "desc": "至少检索 PubMed、Embase、Cochrane Library 三个数据库",
                "ref": "Chapter 4.3: Sources to search"
            },
            {
                "name": "检索策略完整",
                "desc": "包含 MeSH 词和自由词的完整布尔检索策略",
                "ref": "Chapter 4.4: Designing search strategies"
            },
            {
                "name": "灰色文献纳入",
                "desc": "检索临床试验注册库、会议摘要等灰色文献",
                "ref": "Chapter 4.3.2: Searching other resources"
            },
            {
                "name": "检索策略可复现",
                "desc": "检索策略完整记录，可供他人完全复现",
                "ref": "Chapter 4.5: Documenting and reporting the search"
            },
        ],
        ReviewStage.TITLE_ABSTRACT_SCREEN: [
            {
                "name": "双人独立筛选",
                "desc": "至少两人独立筛选，降低偏倚风险",
                "ref": "Chapter 4.6: Selecting studies"
            },
            {
                "name": "分歧解决机制",
                "desc": "不一致的筛选结果有明确的仲裁机制",
                "ref": "Chapter 4.6.2: Achieving consensus"
            },
            {
                "name": "预设标准执行",
                "desc": "严格按照预注册的纳入排除标准筛选",
                "ref": "Chapter 4.6.1: Applying the eligibility criteria"
            },
        ],
        ReviewStage.FULLTEXT_SCREEN: [
            {
                "name": "全文获取完整",
                "desc": "获取所有通过初筛文献的全文",
                "ref": "Chapter 4.6: Selecting studies"
            },
            {
                "name": "排除原因记录",
                "desc": "每篇排除文献记录具体排除原因",
                "ref": "Chapter 4.6.3: Recording the decision process"
            },
            {
                "name": "PRISMA流程图",
                "desc": "生成符合 PRISMA 2020 的筛选流程图",
                "ref": "Chapter 4.6.5: Flow diagrams"
            },
        ],
        ReviewStage.DATA_EXTRACTION: [
            {
                "name": "标准化提取表",
                "desc": "使用预先设计的标准化数据提取表",
                "ref": "Chapter 5.3: Data collection forms"
            },
            {
                "name": "双人独立提取",
                "desc": "至少两人独立提取数据，交叉核对",
                "ref": "Chapter 5.4: How many review authors should extract data?"
            },
            {
                "name": "数据溯源",
                "desc": "每个提取数据点可追溯到原文出处",
                "ref": "Chapter 5.5: Sources to contact for further information"
            },
        ],
        ReviewStage.BIAS_ASSESSMENT: [
            {
                "name": "偏倚评估工具",
                "desc": "使用 Cochrane RoB 2.0 工具评估偏倚风险",
                "ref": "Chapter 8.2: The Cochrane risk-of-bias tool for randomized trials"
            },
            {
                "name": "双人独立评估",
                "desc": "至少两人独立评估偏倚风险",
                "ref": "Chapter 8.3: Planning the assessment of risk of bias"
            },
            {
                "name": "证据质量评级",
                "desc": "使用 GRADE 方法评估证据质量",
                "ref": "Chapter 14: Summarizing findings using GRADE"
            },
        ],
        ReviewStage.ANALYSIS_REPORT: [
            {
                "name": "统计方法适当",
                "desc": "Meta 分析统计方法选择适当（固定/随机效应）",
                "ref": "Chapter 10: Analysing data and undertaking meta-analyses"
            },
            {
                "name": "异质性评估",
                "desc": "系统评估研究间异质性（I², Q, τ²）",
                "ref": "Chapter 10.10: Heterogeneity"
            },
            {
                "name": "敏感性分析",
                "desc": "执行敏感性分析验证结果稳健性",
                "ref": "Chapter 10.14: Sensitivity analyses"
            },
            {
                "name": "报告偏倚评估",
                "desc": "评估发表偏倚（漏斗图、Egger检验等）",
                "ref": "Chapter 13.3: Assessing risk of bias due to missing results"
            },
            {
                "name": "PRISMA报告规范",
                "desc": "报告严格遵循 PRISMA 2020 声明",
                "ref": "Chapter 5.5: PRISMA checklist"
            },
        ],
    }
    
    def __init__(self):
        self.audits: Dict[ReviewStage, StageAudit] = {}
        self.protocol: Optional[ProtocolRegistration] = None
        self.current_stage = ReviewStage.PROTOCOL
    
    def create_protocol(self, **kwargs) -> ProtocolRegistration:
        """创建系统评价方案"""
        self.protocol = ProtocolRegistration(**kwargs)
        self.protocol.registration_date = time.strftime("%Y-%m-%d")
        return self.protocol
    
    def extract_picos_from_query(self, query: str) -> PICOSElements:
        """
        从自然语言研究问题中提取 PICOS 要素
        
        这是 AI 辅助功能，提取后需人工确认
        """
        # 基于关键词模式匹配的 PICOS 提取
        picos = PICOSElements()
        
        query_lower = query.lower()
        
        # 常见人群关键词映射
        population_patterns = {
            "nsclc": ("非小细胞肺癌患者", ["NSCLC", "non-small cell lung cancer"]),
            "breast cancer": ("乳腺癌患者", ["breast cancer", "breast neoplasm"]),
            "diabetes": ("糖尿病患者", ["diabetes mellitus", "diabetic"]),
            "copd": ("慢性阻塞性肺疾病患者", ["COPD", "chronic obstructive pulmonary disease"]),
            "heart failure": ("心力衰竭患者", ["heart failure", "cardiac failure"]),
            "stroke": ("脑卒中患者", ["stroke", "cerebrovascular accident"]),
            "hypertension": ("高血压患者", ["hypertension", "high blood pressure"]),
        }
        
        for key, (desc, terms) in population_patterns.items():
            if key in query_lower:
                picos.population = desc
                picos.population_include = terms
                break
        
        # 干预关键词
        intervention_patterns = {
            "pd-1": ("PD-1/PD-L1抑制剂", ["PD-1", "PD-L1", "pembrolizumab", "nivolumab", "atezolizumab"]),
            "chemotherapy": ("化疗", ["chemotherapy", "platinum-based"]),
            "immunotherapy": ("免疫治疗", ["immunotherapy", "immune checkpoint"]),
            "statin": ("他汀类药物", ["statin", "HMG-CoA reductase inhibitor"]),
            "acei": ("ACE抑制剂", ["ACE inhibitor", "angiotensin-converting enzyme"]),
            "arbi": ("ARB", ["angiotensin receptor blocker", "ARB"]),
        }
        
        for key, (desc, terms) in intervention_patterns.items():
            if key in query_lower:
                picos.intervention = desc
                picos.intervention_include = terms
                break
        
        # 研究设计
        design_patterns = {
            "meta分析": "meta-analysis",
            "meta-analysis": "meta-analysis",
            "系统评价": "systematic review",
            "systematic review": "systematic review",
            "rct": "randomized controlled trial",
            "随机对照": "randomized controlled trial",
            "cohort": "cohort study",
            "队列": "cohort study",
        }
        
        for key, design in design_patterns.items():
            if key in query_lower:
                picos.study_design = design
                picos.study_design_include = [design]
                break
        
        # 结局指标
        outcome_patterns = {
            "os": ("总生存期", ["overall survival", "OS"]),
            "pfs": ("无进展生存期", ["progression-free survival", "PFS"]),
            "orr": ("客观缓解率", ["objective response rate", "ORR"]),
            "mortality": ("死亡率", ["mortality", "death rate"]),
        }
        
        for key, (desc, terms) in outcome_patterns.items():
            if key in query_lower:
                picos.outcome_primary.append(desc)
        
        return picos
    
    def start_stage(self, stage: ReviewStage) -> StageAudit:
        """开始一个新阶段"""
        self.current_stage = stage
        checkpoints_def = self.STAGE_CHECKPOINTS.get(stage, [])
        
        checkpoints = [
            QualityCheckpoint(
                stage=stage,
                name=cp["name"],
                description=cp["desc"],
                cochrane_reference=cp["ref"],
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
            )
            for cp in checkpoints_def
        ]
        
        audit = StageAudit(
            stage=stage,
            started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            checkpoints=checkpoints,
        )
        
        self.audits[stage] = audit
        return audit
    
    def pass_checkpoint(self, stage: ReviewStage, checkpoint_name: str, details: str = ""):
        """通过一个检查点"""
        audit = self.audits.get(stage)
        if not audit:
            return
        
        for cp in audit.checkpoints:
            if cp.name == checkpoint_name:
                cp.passed = True
                cp.details = details
                break
    
    def complete_stage(self, stage: ReviewStage) -> StageAudit:
        """完成一个阶段"""
        audit = self.audits.get(stage)
        if audit:
            audit.completed_at = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # 检查是否所有检查点都通过
            if not audit.all_passed:
                failed = [cp.name for cp in audit.checkpoints if not cp.passed]
                audit.warnings.append(
                    f"阶段 {stage.value} 有未通过的检查点: {', '.join(failed)}"
                )
        
        return audit
    
    def get_compliance_report(self) -> dict:
        """生成合规报告"""
        total_checkpoints = 0
        passed_checkpoints = 0
        stages_status = {}
        
        for stage in ReviewStage:
            audit = self.audits.get(stage)
            if audit:
                total = len(audit.checkpoints)
                passed = sum(1 for cp in audit.checkpoints if cp.passed)
                total_checkpoints += total
                passed_checkpoints += passed
                
                stages_status[stage.value] = {
                    "status": "completed" if audit.completed_at else "in_progress",
                    "checkpoints": total,
                    "passed": passed,
                    "rate": f"{passed/total*100:.0f}%" if total > 0 else "N/A",
                    "warnings": audit.warnings,
                }
        
        overall_rate = (passed_checkpoints / total_checkpoints * 100) if total_checkpoints > 0 else 0
        
        return {
            "overall_compliance": f"{overall_rate:.1f}%",
            "total_checkpoints": total_checkpoints,
            "passed": passed_checkpoints,
            "stages": stages_status,
            "cochrane_handbook_version": "6.4",
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    
    def can_proceed_to_next(self, stage: ReviewStage) -> tuple:
        """检查是否可以进入下一阶段"""
        audit = self.audits.get(stage)
        if not audit:
            return False, "当前阶段尚未开始"
        
        if not audit.all_passed:
            failed = [cp.name for cp in audit.checkpoints if not cp.passed]
            return False, f"以下检查点未通过: {', '.join(failed)}"
        
        return True, "所有检查点通过，可以进入下一阶段"


# ============================================
# 便捷函数
# ============================================

def create_default_checkpoints(stage: ReviewStage) -> List[QualityCheckpoint]:
    """为指定阶段创建默认检查点"""
    engine = CochraneComplianceEngine()
    audit = engine.start_stage(stage)
    return audit.checkpoints


def generate_compliance_html(report: dict) -> str:
    """生成合规报告 HTML"""
    stages_html = ""
    for stage_name, stage_data in report.get("stages", {}).items():
        status_icon = "✅" if stage_data["status"] == "completed" else "🔄"
        color = "#10b981" if stage_data.get("rate", "0%").replace("%", "") == "100" else "#f59e0b"
        
        stages_html += f'''
        <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:16px;margin-bottom:12px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="color:#e2e8f0;font-weight:600;">{status_icon} {stage_name}</span>
                <span style="color:{color};font-weight:700;">{stage_data.get("rate", "N/A")}</span>
            </div>
            <div style="color:#94a3b8;font-size:0.85rem;margin-top:4px;">
                {stage_data.get("passed", 0)}/{stage_data.get("checkpoints", 0)} 检查点通过
            </div>
        </div>
        '''
    
    overall = report.get("overall_compliance", "0%")
    overall_color = "#10b981" if float(overall.replace("%", "")) >= 80 else "#f59e0b"
    
    return f'''
    <div style="background:#0f1629;border-radius:16px;padding:24px;border:1px solid rgba(255,255,255,0.06);">
        <h3 style="color:#e2e8f0;margin:0 0 8px 0;">📋 Cochrane 方法学合规报告</h3>
        <div style="color:#94a3b8;font-size:0.85rem;margin-bottom:16px;">
            Cochrane Handbook v{report.get("cochrane_handbook_version", "6.4")} | 
            生成时间: {report.get("generated_at", "")}
        </div>
        <div style="text-align:center;margin:24px 0;">
            <div style="font-size:3rem;font-weight:800;color:{overall_color};">{overall}</div>
            <div style="color:#94a3b8;">总体合规率</div>
            <div style="color:#64748b;font-size:0.85rem;">{report.get("passed", 0)}/{report.get("total_checkpoints", 0)} 检查点通过</div>
        </div>
        {stages_html}
    </div>
    '''
