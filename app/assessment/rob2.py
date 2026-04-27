"""
MetaForge — Cochrane RoB 2.0 偏倚风险评估引擎

严格遵循 Cochrane Risk of Bias 2.0 工具
评估随机对照试验的5个偏倚域，输出整体偏倚判断

参考: Sterne JAC, et al. BMJ 2019;366:l4898
"""

import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum


class BiasJudgment(Enum):
    """偏倚判断结果"""
    LOW = "low"                         # 低风险
    SOME_CONCERNS = "some_concerns"     # 有一定顾虑
    HIGH = "high"                       # 高风险


class Domain(Enum):
    """RoB 2.0 五个偏倚域"""
    D1_RANDOMIZATION = "domain1"        # 随机化过程中的偏倚
    D2_DEVIATION = "domain2"            # 偏离预期干预的偏倚
    D3_OUTCOME = "domain3"              # 结局数据缺失的偏倚
    D4_MEASUREMENT = "domain4"          # 结局测量的偏倚
    D5_SELECTION = "domain5"            # 选择性报告结果的偏倚


@dataclass
class SignalingQuestion:
    """信号问题 (Signaling Question)"""
    domain: Domain
    question_id: str
    question: str
    answer: str = ""           # Yes / Probably Yes / No / Probably No / No Information
    support: str = ""          # 支持判断的原文证据
    page_ref: str = ""         # 页码/段落引用


@dataclass
class DomainAssessment:
    """单个偏倚域的评估结果"""
    domain: Domain
    domain_name: str
    signaling_questions: List[SignalingQuestion] = field(default_factory=list)
    judgment: BiasJudgment = BiasJudgment.LOW
    rationale: str = ""        # 判断理由
    evidence: str = ""         # 原文证据


@dataclass
class StudyBiasAssessment:
    """单个研究的偏倚风险评估"""
    study_name: str = ""
    pmid: str = ""
    assessors: List[str] = field(default_factory=list)  # 评估者
    
    # 五个域的评估
    domain1: Optional[DomainAssessment] = None
    domain2: Optional[DomainAssessment] = None
    domain3: Optional[DomainAssessment] = None
    domain4: Optional[DomainAssessment] = None
    domain5: Optional[DomainAssessment] = None
    
    overall_judgment: BiasJudgment = BiasJudgment.LOW
    overall_rationale: str = ""
    
    @property
    def domains(self) -> List[DomainAssessment]:
        return [d for d in [self.domain1, self.domain2, self.domain3, self.domain4, self.domain5] if d]
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "study_name": self.study_name,
            "pmid": self.pmid,
            "overall_judgment": self.overall_judgment.value,
            "overall_rationale": self.overall_rationale,
            "domains": [
                {
                    "name": d.domain_name,
                    "judgment": d.judgment.value,
                    "rationale": d.rationale,
                    "questions": [
                        {
                            "id": q.question_id,
                            "question": q.question,
                            "answer": q.answer,
                            "support": q.support,
                        }
                        for q in d.signaling_questions
                    ]
                }
                for d in self.domains
            ]
        }


class RoB2Engine:
    """
    Cochrane Risk of Bias 2.0 评估引擎
    
    自动生成信号问题，辅助判断偏倚风险等级
    """
    
    # RoB 2.0 标准信号问题
    DEFAULT_SIGNALING_QUESTIONS = {
        Domain.D1_RANDOMIZATION: [
            SignalingQuestion(Domain.D1_RANDOMIZATION, "1.1", "研究是否使用了适当的随机化过程？"),
            SignalingQuestion(Domain.D1_RANDOMIZATION, "1.2", "随机化序列是否得到了适当的分配隐藏？"),
            SignalingQuestion(Domain.D1_RANDOMIZATION, "1.3", "基线特征是否平衡？是否存在因随机化过程不当导致的基线差异？"),
        ],
        Domain.D2_DEVIATION: [
            SignalingQuestion(Domain.D2_DEVIATION, "2.1", "试验期间参与者是否知晓分配的干预？"),
            SignalingQuestion(Domain.D2_DEVIATION, "2.2", "试验期间实施者是否知晓分配的干预？"),
            SignalingQuestion(Domain.D2_DEVIATION, "2.3", "是否存在偏离预期干预的情况？如有，是否进行了适当的分析？"),
            SignalingQuestion(Domain.D2_DEVIATION, "2.4", "分析中是否适当地比较了分配的干预组？(ITT分析)"),
        ],
        Domain.D3_OUTCOME: [
            SignalingQuestion(Domain.D3_OUTCOME, "3.1", "结局数据是否完整？"),
            SignalingQuestion(Domain.D3_OUTCOME, "3.2", "结局数据缺失是否可能与真实结局相关？"),
            SignalingQuestion(Domain.D3_OUTCOME, "3.3", "是否对缺失数据进行了适当的处理？"),
        ],
        Domain.D4_MEASUREMENT: [
            SignalingQuestion(Domain.D4_MEASUREMENT, "4.1", "结局测量方法是否适当？"),
            SignalingQuestion(Domain.D4_MEASUREMENT, "4.2", "结局评估者是否知晓干预分配？"),
            SignalingQuestion(Domain.D4_MEASUREMENT, "4.3", "结局评估在各组间是否一致？"),
        ],
        Domain.D5_SELECTION: [
            SignalingQuestion(Domain.D5_SELECTION, "5.1", "研究是否可能报告了所有预期的结局？"),
            SignalingQuestion(Domain.D5_SELECTION, "5.2", "是否根据结果选择了报告的分析？"),
            SignalingQuestion(Domain.D5_SELECTION, "5.3", "研究报告是否包含研究方案中预先指定的全部结果？"),
        ],
    }
    
    def __init__(self):
        self.assessments: Dict[str, StudyBiasAssessment] = {}
    
    def create_assessment(self, study_name: str, pmid: str = "", assessors: List[str] = None) -> StudyBiasAssessment:
        """创建新的偏倚评估"""
        assessment = StudyBiasAssessment(
            study_name=study_name,
            pmid=pmid,
            assessors=assessors or [],
        )
        
        # 初始化五个域
        for domain in Domain:
            questions = [
                SignalingQuestion(
                    domain=q.domain,
                    question_id=q.question_id,
                    question=q.question,
                )
                for q in self.DEFAULT_SIGNALING_QUESTIONS[domain]
            ]
            
            domain_names = {
                Domain.D1_RANDOMIZATION: "D1: 随机化过程",
                Domain.D2_DEVIATION: "D2: 偏离预期干预",
                Domain.D3_OUTCOME: "D3: 结局数据缺失",
                Domain.D4_MEASUREMENT: "D4: 结局测量",
                Domain.D5_SELECTION: "D5: 选择性报告",
            }
            
            da = DomainAssessment(
                domain=domain,
                domain_name=domain_names[domain],
                signaling_questions=questions,
            )
            
            setattr(assessment, domain.value, da)
        
        self.assessments[study_name] = assessment
        return assessment
    
    def answer_question(self, study_name: str, question_id: str, 
                        answer: str, support: str = ""):
        """回答信号问题"""
        assessment = self.assessments.get(study_name)
        if not assessment:
            return
        
        for domain_assessment in assessment.domains:
            for sq in domain_assessment.signaling_questions:
                if sq.question_id == question_id:
                    sq.answer = answer
                    sq.support = support
                    break
    
    def judge_domain(self, study_name: str, domain: Domain, 
                     judgment: BiasJudgment, rationale: str = ""):
        """判断单个域的偏倚风险"""
        assessment = self.assessments.get(study_name)
        if not assessment:
            return
        
        domain_assessment = getattr(assessment, domain.value, None)
        if domain_assessment:
            domain_assessment.judgment = judgment
            domain_assessment.rationale = rationale
    
    def compute_overall(self, study_name: str) -> BiasJudgment:
        """
        计算整体偏倚风险
        
        RoB 2.0 规则：
        - 任一域为 High → 整体 High
        - 任一域为 Some Concerns → 整体 Some Concerns
        - 全部域为 Low → 整体 Low
        """
        assessment = self.assessments.get(study_name)
        if not assessment:
            return BiasJudgment.LOW
        
        judgments = [d.judgment for d in assessment.domains]
        
        if BiasJudgment.HIGH in judgments:
            assessment.overall_judgment = BiasJudgment.HIGH
            high_domains = [d.domain_name for d in assessment.domains if d.judgment == BiasJudgment.HIGH]
            assessment.overall_rationale = f"以下域存在高风险偏倚: {', '.join(high_domains)}"
        elif BiasJudgment.SOME_CONCERNS in judgments:
            assessment.overall_judgment = BiasJudgment.SOME_CONCERNS
            concern_domains = [d.domain_name for d in assessment.domains if d.judgment == BiasJudgment.SOME_CONCERNS]
            assessment.overall_rationale = f"以下域存在顾虑: {', '.join(concern_domains)}"
        else:
            assessment.overall_judgment = BiasJudgment.LOW
            assessment.overall_rationale = "所有域均为低风险偏倚"
        
        return assessment.overall_judgment
    
    def generate_summary(self) -> dict:
        """生成所有研究的偏倚风险汇总"""
        if not self.assessments:
            return {"studies": [], "summary": {}}
        
        studies_data = []
        judgment_counts = {j.value: 0 for j in BiasJudgment}
        
        for name, assessment in self.assessments.items():
            studies_data.append(assessment.to_dict())
            judgment_counts[assessment.overall_judgment.value] += 1
        
        total = len(self.assessments)
        
        return {
            "studies": studies_data,
            "summary": {
                "total_studies": total,
                "low_risk": judgment_counts["low"],
                "some_concerns": judgment_counts["some_concerns"],
                "high_risk": judgment_counts["high"],
                "low_risk_pct": f"{judgment_counts['low']/total*100:.1f}%" if total else "0%",
                "some_concerns_pct": f"{judgment_counts['some_concerns']/total*100:.1f}%" if total else "0%",
                "high_risk_pct": f"{judgment_counts['high_risk'] if 'high_risk' in judgment_counts else judgment_counts['high']}/{total*100:.1f}%" if total else "0%",
            },
            "tool": "Cochrane Risk of Bias 2.0 (RoB 2.0)",
            "reference": "Sterne JAC, Savović J, Page MJ, et al. BMJ 2019;366:l4898",
        }
    
    def generate_traffic_light_html(self, assessments: List[StudyBiasAssessment] = None) -> str:
        """
        生成交通灯图（Traffic Light Plot）HTML
        
        每个研究一行，5个域一列，颜色表示偏倚风险
        """
        assessments = assessments or list(self.assessments.values())
        if not assessments:
            return "<p>无评估数据</p>"
        
        colors = {
            BiasJudgment.LOW: "#10b981",        # 绿
            BiasJudgment.SOME_CONCERNS: "#f59e0b",  # 黄
            BiasJudgment.HIGH: "#ef4444",        # 红
        }
        
        icons = {
            BiasJudgment.LOW: "●",
            BiasJudgment.SOME_CONCERNS: "●",
            BiasJudgment.HIGH: "●",
        }
        
        # 表头
        header = '''
        <tr style="border-bottom:2px solid rgba(255,255,255,0.1);">
            <th style="padding:12px;text-align:left;color:#94a3b8;font-weight:600;">研究</th>
            <th style="padding:12px;text-align:center;color:#94a3b8;font-weight:600;">D1</th>
            <th style="padding:12px;text-align:center;color:#94a3b8;font-weight:600;">D2</th>
            <th style="padding:12px;text-align:center;color:#94a3b8;font-weight:600;">D3</th>
            <th style="padding:12px;text-align:center;color:#94a3b8;font-weight:600;">D4</th>
            <th style="padding:12px;text-align:center;color:#94a3b8;font-weight:600;">D5</th>
            <th style="padding:12px;text-align:center;color:#94a3b8;font-weight:600;">整体</th>
        </tr>
        '''
        
        rows = ""
        for a in assessments:
            cells = ""
            for da in a.domains:
                color = colors[da.judgment]
                cells += f'<td style="padding:10px;text-align:center;"><span style="color:{color};font-size:1.4rem;" title="{da.domain_name}: {da.judgment.value}">{icons[da.judgment]}</span></td>'
            
            overall_color = colors[a.overall_judgment]
            cells += f'<td style="padding:10px;text-align:center;"><span style="color:{overall_color};font-weight:700;">{a.overall_judgment.value}</span></td>'
            
            rows += f'<tr style="border-bottom:1px solid rgba(255,255,255,0.05);"><td style="padding:10px;color:#e2e8f0;font-weight:500;">{a.study_name}</td>{cells}</tr>'
        
        # 汇总行
        total = len(assessments)
        low_count = sum(1 for a in assessments if a.overall_judgment == BiasJudgment.LOW)
        concern_count = sum(1 for a in assessments if a.overall_judgment == BiasJudgment.SOME_CONCERNS)
        high_count = sum(1 for a in assessments if a.overall_judgment == BiasJudgment.HIGH)
        
        return f'''
        <div style="background:#0f1629;border-radius:16px;padding:24px;border:1px solid rgba(255,255,255,0.06);overflow-x:auto;">
            <h3 style="color:#e2e8f0;margin:0 0 8px 0;">🚦 Cochrane RoB 2.0 偏倚风险评估</h3>
            <div style="color:#94a3b8;font-size:0.85rem;margin-bottom:16px;">
                D1=随机化过程 | D2=偏离干预 | D3=结局数据 | D4=结局测量 | D5=选择性报告
            </div>
            <table style="width:100%;border-collapse:collapse;font-size:0.9rem;">
                {header}
                {rows}
            </table>
            <div style="margin-top:16px;display:flex;gap:16px;justify-content:center;">
                <span style="color:#10b981;">● 低风险: {low_count} ({low_count/total*100:.0f}%)</span>
                <span style="color:#f59e0b;">● 有一定顾虑: {concern_count} ({concern_count/total*100:.0f}%)</span>
                <span style="color:#ef4444;">● 高风险: {high_count} ({high_count/total*100:.0f}%)</span>
            </div>
        </div>
        '''
