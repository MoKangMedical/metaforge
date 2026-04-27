"""
MetaForge — 多Agent盲筛仲裁引擎

对标 LivingEBM 的「多脑协同盲筛仲裁」：
- 多个 Agent 独立筛选（模拟双人独立筛选）
- Agent 间互不可见彼此的筛选结果
- 不一致结果由仲裁引擎统一决策
- 每条决策附证据佐证
"""

import json
import time
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum


class ScreeningDecision(Enum):
    INCLUDE = "include"
    EXCLUDE = "exclude"
    UNCERTAIN = "uncertain"


@dataclass
class ScreeningVote:
    """单个 Agent 的筛选投票"""
    agent_id: str
    article_pmid: str
    decision: ScreeningDecision
    reason: str = ""
    confidence: float = 0.0
    evidence_keywords: List[str] = field(default_factory=list)
    timestamp: str = ""


@dataclass
class ArbitrationResult:
    """仲裁结果"""
    article_pmid: str
    final_decision: ScreeningDecision
    votes: List[ScreeningVote] = field(default_factory=list)
    agreement: bool = True            # 是否一致
    arbitration_reason: str = ""      # 仲裁理由
    confidence: float = 0.0
    needs_human_review: bool = False


@dataclass
class BlindScreeningSession:
    """一次完整的盲筛会话"""
    session_id: str = ""
    criteria: dict = field(default_factory=dict)
    n_agents: int = 2                 # Agent 数量（默认双人）
    votes: Dict[str, List[ScreeningVote]] = field(default_factory=dict)  # pmid → votes
    arbitrations: Dict[str, ArbitrationResult] = field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""
    
    @property
    def total_articles(self) -> int:
        return len(self.votes)
    
    @property
    def agreed_count(self) -> int:
        return sum(1 for a in self.arbitrations.values() if a.agreement)
    
    @property
    def disagreed_count(self) -> int:
        return sum(1 for a in self.arbitrations.values() if not a.agreement)
    
    @property
    def agreement_rate(self) -> float:
        if not self.arbitrations:
            return 0.0
        return self.agreed_count / len(self.arbitrations) * 100


class BlindScreeningAgent:
    """
    盲筛 Agent
    
    每个 Agent 独立工作，互不可见
    模拟不同筛选者可能的判断差异
    """
    
    # Agent 倾向配置 — 模拟不同筛选者的保守/激进程度
    AGENT_PROFILES = {
        "conservative": {
            "name": "保守型筛选者",
            "confidence_threshold": 0.8,  # 高阈值，宁缺毋滥
            "uncertain_bias": 0.15,       # 倾向标记为不确定
            "exclude_keywords_weight": 1.3,
        },
        "balanced": {
            "name": "平衡型筛选者",
            "confidence_threshold": 0.65,
            "uncertain_bias": 0.05,
            "exclude_keywords_weight": 1.0,
        },
        "inclusive": {
            "name": "包容型筛选者",
            "confidence_threshold": 0.5,  # 低阈值，宁多勿漏
            "uncertain_bias": -0.05,
            "exclude_keywords_weight": 0.8,
        },
    }
    
    EXCLUDE_KEYWORDS = [
        "animal", "mice", "mouse", "rat ", "rats ", "rabbit",
        "in vitro", "cell line", "cell culture",
        "case report", "case series", "letter", "editorial", "comment",
        "protocol", "study protocol",
        "retracted", "retraction",
        "conference", "abstract only", "meeting abstract",
    ]
    
    def __init__(self, agent_id: str, profile: str = "balanced"):
        self.agent_id = agent_id
        self.profile = self.AGENT_PROFILES.get(profile, self.AGENT_PROFILES["balanced"])
        self.profile_name = profile
    
    def screen_article(self, article: dict, criteria: dict) -> ScreeningVote:
        """筛选单篇文献"""
        title = (article.get("title") or "").lower()
        abstract = (article.get("abstract") or "").lower()
        text = f"{title} {abstract}"
        pub_types = [pt.lower() for pt in article.get("publication_types", [])]
        pmid = article.get("pmid", "unknown")
        
        decision = ScreeningDecision.UNCERTAIN
        reason = ""
        confidence = 0.5
        evidence = []
        
        # 规则排除
        for kw in self.EXCLUDE_KEYWORDS:
            kw_match = kw.strip() in text
            if kw_match:
                weight = self.profile["exclude_keywords_weight"]
                # 检查是否为人类研究
                if kw in ("animal", "mice", "mouse", "rat ", "rats ", "rabbit"):
                    if not any(h in text for h in ["human", "patient", "participant"]):
                        decision = ScreeningDecision.EXCLUDE
                        reason = f"排除: 非人类研究（命中'{kw.strip()}'）"
                        confidence = min(0.95, 0.85 * weight)
                        evidence.append(kw.strip())
                        break
                elif kw in ("letter", "editorial", "comment", "news"):
                    for pt in pub_types:
                        if kw in pt:
                            decision = ScreeningDecision.EXCLUDE
                            reason = f"排除: 非研究性文章 ({pt})"
                            confidence = min(0.98, 0.9 * weight)
                            evidence.append(pt)
                            break
        
        # PICOS 匹配
        if decision != ScreeningDecision.EXCLUDE:
            picos_score = 0
            picos_checks = 0
            
            # Population
            pop_include = criteria.get("population_include", "")
            if pop_include:
                terms = [t.strip().lower() for t in pop_include.split(",") if t.strip()]
                pop_found = any(t in text for t in terms)
                picos_checks += 1
                if pop_found:
                    picos_score += 1
                    evidence.extend([t for t in terms if t in text])
                elif self.profile_name == "conservative":
                    decision = ScreeningDecision.UNCERTAIN
                    reason = "未明确包含目标人群"
                    confidence = 0.4
            
            # Intervention
            int_include = criteria.get("intervention_include", "")
            if int_include and decision != ScreeningDecision.UNCERTAIN:
                terms = [t.strip().lower() for t in int_include.split(",") if t.strip()]
                int_found = any(t in text for t in terms)
                picos_checks += 1
                if int_found:
                    picos_score += 1
                    evidence.extend([t for t in terms if t in text])
                else:
                    decision = ScreeningDecision.UNCERTAIN
                    reason = "未明确涉及目标干预"
                    confidence = 0.4
            
            # 排除人群
            pop_exclude = criteria.get("population_exclude", "")
            if pop_exclude:
                terms = [t.strip().lower() for t in pop_exclude.split(",") if t.strip()]
                for t in terms:
                    if t and t in text:
                        decision = ScreeningDecision.EXCLUDE
                        reason = f"排除: 包含排除人群 '{t}'"
                        confidence = 0.85
                        evidence.append(t)
                        break
            
            # 综合判断
            if decision != ScreeningDecision.EXCLUDE and decision != ScreeningDecision.UNCERTAIN:
                threshold = self.profile["confidence_threshold"]
                uncertain_bias = self.profile["uncertain_bias"]
                
                if picos_checks > 0:
                    ratio = picos_score / picos_checks
                else:
                    ratio = 0.7  # 无明确PICOS标准时给默认分
                
                if ratio >= threshold and not abstract:
                    decision = ScreeningDecision.INCLUDE
                    reason = "通过筛选: 标题符合纳入标准"
                    confidence = min(0.85, ratio)
                elif ratio >= threshold:
                    decision = ScreeningDecision.INCLUDE
                    reason = "通过筛选: 符合PICOS标准"
                    confidence = min(0.95, ratio + 0.05)
                elif ratio < threshold - uncertain_bias:
                    decision = ScreeningDecision.EXCLUDE
                    reason = f"排除: PICOS匹配度低 ({ratio:.0%})"
                    confidence = max(0.5, ratio + 0.2)
                else:
                    decision = ScreeningDecision.UNCERTAIN
                    reason = f"不确定: PICOS匹配度中等 ({ratio:.0%})"
                    confidence = 0.55
        
        return ScreeningVote(
            agent_id=self.agent_id,
            article_pmid=pmid,
            decision=decision,
            reason=reason,
            confidence=confidence,
            evidence_keywords=evidence[:5],
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )


class ArbitrationEngine:
    """
    仲裁引擎
    
    处理多个 Agent 之间的不一致筛选结果
    """
    
    def arbitrate(self, votes: List[ScreeningVote]) -> ArbitrationResult:
        """
        仲裁多个 Agent 的投票
        
        规则：
        1. 全票一致 → 直接采纳
        2. 多数决 → 采纳多数意见
        3. 完全分歧 → 标记需人工审核
        4. 任何一方为 uncertain → 倾向纳入或标为需审核
        """
        if not votes:
            return ArbitrationResult(
                article_pmid="",
                final_decision=ScreeningDecision.UNCERTAIN,
                needs_human_review=True,
            )
        
        pmid = votes[0].article_pmid
        
        # 统计各决策的投票
        decision_counts = {d: 0 for d in ScreeningDecision}
        for v in votes:
            decision_counts[v.decision] += 1
        
        includes = decision_counts[ScreeningDecision.INCLUDE]
        excludes = decision_counts[ScreeningDecision.EXCLUDE]
        uncertain = decision_counts[ScreeningDecision.UNCERTAIN]
        total = len(votes)
        
        # 规则 1: 全票一致
        if includes == total:
            return ArbitrationResult(
                article_pmid=pmid,
                final_decision=ScreeningDecision.INCLUDE,
                votes=votes,
                agreement=True,
                arbitration_reason="全票通过：所有筛选者一致纳入",
                confidence=min(v.confidence for v in votes),
            )
        
        if excludes == total:
            return ArbitrationResult(
                article_pmid=pmid,
                final_decision=ScreeningDecision.EXCLUDE,
                votes=votes,
                agreement=True,
                arbitration_reason="全票排除：所有筛选者一致排除",
                confidence=min(v.confidence for v in votes),
            )
        
        if uncertain == total:
            return ArbitrationResult(
                article_pmid=pmid,
                final_decision=ScreeningDecision.UNCERTAIN,
                votes=votes,
                agreement=False,
                arbitration_reason="全部不确定：标记需人工审核",
                confidence=0.3,
                needs_human_review=True,
            )
        
        # 规则 2: 多数决
        if includes > excludes and includes > uncertain:
            return ArbitrationResult(
                article_pmid=pmid,
                final_decision=ScreeningDecision.INCLUDE,
                votes=votes,
                agreement=False,
                arbitration_reason=f"多数纳入 ({includes}/{total})：采纳多数意见",
                confidence=0.7,
            )
        
        if excludes > includes and excludes > uncertain:
            return ArbitrationResult(
                article_pmid=pmid,
                final_decision=ScreeningDecision.EXCLUDE,
                votes=votes,
                agreement=False,
                arbitration_reason=f"多数排除 ({excludes}/{total})：采纳多数意见",
                confidence=0.7,
            )
        
        # 规则 3: 完全分歧或有不确定票
        # Cochrane 建议：分歧时倾向纳入，全文阶段再排除
        if uncertain > 0:
            return ArbitrationResult(
                article_pmid=pmid,
                final_decision=ScreeningDecision.INCLUDE,
                votes=votes,
                agreement=False,
                arbitration_reason=f"存在不确定意见 ({uncertain}/{total})：按Cochrane规范倾向纳入",
                confidence=0.5,
                needs_human_review=True,
            )
        
        # 完全分歧（include vs exclude）
        return ArbitrationResult(
            article_pmid=pmid,
            final_decision=ScreeningDecision.INCLUDE,
            votes=votes,
            agreement=False,
            arbitration_reason=f"完全分歧 (纳入:{includes} vs 排除:{excludes})：按Cochrane规范纳入",
            confidence=0.4,
            needs_human_review=True,
        )


class BlindScreeningEngine:
    """
    多Agent盲筛引擎
    
    完整流程：
    1. 创建多个不同倾向的 Agent
    2. 各 Agent 独立盲筛（互不可见）
    3. 仲裁引擎统一决策
    4. 输出纳入/排除/需人工审核列表
    """
    
    def __init__(self, n_agents: int = 2, profiles: List[str] = None):
        """
        Args:
            n_agents: Agent 数量
            profiles: 各 Agent 的倾向配置，默认 ["conservative", "inclusive"]
        """
        if profiles is None:
            profiles = ["conservative", "inclusive"] if n_agents == 2 else ["conservative", "balanced", "inclusive"][:n_agents]
        
        self.agents = [
            BlindScreeningAgent(agent_id=f"agent_{i+1}", profile=profiles[i])
            for i in range(min(n_agents, len(profiles)))
        ]
        self.arbitrator = ArbitrationEngine()
    
    def screen_all(self, articles: List[dict], criteria: dict) -> BlindScreeningSession:
        """
        执行完整盲筛流程
        
        Args:
            articles: 文献列表
            criteria: PICOS 筛选标准
        
        Returns:
            BlindScreeningSession 包含所有投票和仲裁结果
        """
        session = BlindScreeningSession(
            session_id=hashlib.md5(time.strftime("%Y%m%d%H%M%S").encode()).hexdigest()[:8],
            criteria=criteria,
            n_agents=len(self.agents),
            started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        
        for article in articles:
            pmid = article.get("pmid", f"unknown_{hash(str(article))}")
            
            # 各 Agent 独立筛选
            votes = []
            for agent in self.agents:
                vote = agent.screen_article(article, criteria)
                votes.append(vote)
            
            session.votes[pmid] = votes
            
            # 仲裁
            arbitration = self.arbitrator.arbitrate(votes)
            session.arbitrations[pmid] = arbitration
        
        session.completed_at = time.strftime("%Y-%m-%d %H:%M:%S")
        return session
    
    def get_results(self, session: BlindScreeningSession) -> dict:
        """获取筛选结果汇总"""
        included = []
        excluded = []
        uncertain = []
        needs_review = []
        
        for pmid, arb in session.arbitrations.items():
            article_info = {"pmid": pmid, "decision": arb.final_decision.value, 
                          "reason": arb.arbitration_reason, "confidence": arb.confidence,
                          "agreement": arb.agreement}
            
            if arb.needs_human_review:
                needs_review.append(article_info)
            
            if arb.final_decision == ScreeningDecision.INCLUDE:
                included.append(article_info)
            elif arb.final_decision == ScreeningDecision.EXCLUDE:
                excluded.append(article_info)
            else:
                uncertain.append(article_info)
        
        return {
            "session_id": session.session_id,
            "n_agents": session.n_agents,
            "total_articles": session.total_articles,
            "agreement_rate": f"{session.agreement_rate:.1f}%",
            "agreed_count": session.agreed_count,
            "disagreed_count": session.disagreed_count,
            "included": {"count": len(included), "articles": included[:50]},
            "excluded": {"count": len(excluded), "articles": excluded[:50]},
            "uncertain": {"count": len(uncertain), "articles": uncertain[:50]},
            "needs_human_review": {"count": len(needs_review), "articles": needs_review[:50]},
            "exclusion_reasons": self._count_exclusion_reasons(excluded),
        }
    
    def _count_exclusion_reasons(self, excluded: list) -> dict:
        """统计排除原因"""
        reasons = {}
        for item in excluded:
            reason = item.get("reason", "未分类")
            reasons[reason] = reasons.get(reason, 0) + 1
        return reasons
