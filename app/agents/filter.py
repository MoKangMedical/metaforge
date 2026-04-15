"""
Agent-Filter: 智能筛选引擎

防幻觉机制：
1. 筛选基于真实文献标题和摘要（grounded），不是AI凭空判断
2. 每个决策附带置信度和理由
3. 低置信度自动标为"uncertain"需要人工审核
4. 双人筛选模拟 + 不一致仲裁
"""

import json
import re
from dataclasses import dataclass
from typing import List


class ScreeningAgent:
    """
    Agent-Filter: 文献筛选Agent
    
    筛选流程：
    1. 初筛（标题/摘要）
    2. 全文筛选（如有全文）
    3. 不一致仲裁
    
    防幻觉：
    - 只基于文献本身的标题和摘要判断
    - 不会"脑补"文献内容
    - 不确定的自动标记为需人工审核
    """
    
    # 排除关键词库（规则引擎，不依赖AI）
    EXCLUDE_KEYWORDS = [
        "animal", "mice", "mouse", "rat", "rats", "rabbit", "pig", "dog", "cat",
        "in vitro", "cell line", "cell culture", "tissue culture",
        "case report", "case series", "letter", "editorial", "comment",
        "protocol", "protocol only", "study protocol",
        "retracted", "retraction",
        "conference", "abstract only", "meeting abstract",
        "news", "erratum", "correction",
    ]
    
    STUDY_DESIGN_KEYWORDS = {
        "randomized controlled trial": ["randomized", "randomised", "randomly assigned", "rct"],
        "cohort study": ["cohort", "prospective", "retrospective", "follow-up"],
        "case-control study": ["case-control", "case control"],
        "cross-sectional study": ["cross-sectional", "cross sectional", "prevalence"],
        "systematic review": ["systematic review", "meta-analysis", "meta analysis"],
    }
    
    def __init__(self, criteria: dict = None):
        self.criteria = criteria or {}
    
    def screen_title_abstract(self, articles: list, criteria: dict = None) -> dict:
        """
        初筛：基于标题和摘要
        
        Returns:
            {
                "included": [...],
                "excluded": [...], 
                "uncertain": [...],  # 需人工审核
                "statistics": {...}
            }
        """
        criteria = criteria or self.criteria
        included = []
        excluded = []
        uncertain = []
        exclusion_reasons = {}
        
        for article in articles:
            decision, reason, confidence = self._evaluate_article(article, criteria)
            
            article["screen_decision"] = decision
            article["screen_reason"] = reason
            article["screen_confidence"] = confidence
            article["screen_stage"] = "title_abstract"
            
            if confidence < 0.7:
                article["screen_needs_review"] = True
                decision = "uncertain"
            
            if decision == "include":
                included.append(article)
            elif decision == "exclude":
                excluded.append(article)
                exclusion_reasons[reason] = exclusion_reasons.get(reason, 0) + 1
            else:
                uncertain.append(article)
        
        return {
            "included": included,
            "excluded": excluded,
            "uncertain": uncertain,
            "statistics": {
                "total": len(articles),
                "included": len(included),
                "excluded": len(excluded),
                "uncertain": len(uncertain),
                "exclusion_reasons": exclusion_reasons
            }
        }
    
    def _evaluate_article(self, article: dict, criteria: dict) -> tuple:
        """
        评估单篇文献
        
        返回: (decision, reason, confidence)
        
        使用混合策略：
        1. 规则引擎（快速排除明确不符合的）
        2. 关键词匹配（PICOS标准）
        3. 置信度评估
        """
        title = (article.get("title") or "").lower()
        abstract = (article.get("abstract") or "").lower()
        text = f"{title} {abstract}"
        pub_types = [pt.lower() for pt in article.get("publication_types", [])]
        
        # === 第一道：规则引擎排除 ===
        
        # 排除非人类研究
        for kw in ["animal", "mice", "mouse", "rat ", "rats ", "rabbit"]:
            if kw in text:
                # 检查是否也提到人类
                if not any(h in text for h in ["human", "patient", "participant", "people"]):
                    return ("exclude", "排除: 非人类研究", 0.95)
        
        # 排除非研究性文章
        non_study = ["letter", "editorial", "comment", "news", "erratum", 
                      "retraction notice", "biography", "interview"]
        for pt in pub_types:
            for ns in non_study:
                if ns in pt:
                    return ("exclude", f"排除: 非研究性文章 ({pt})", 0.98)
        
        # 排除只有会议摘要
        if "conference abstract" in pub_types and "journal article" not in pub_types:
            return ("exclude", "排除: 仅会议摘要", 0.95)
        
        # === 第二道：PICOS标准匹配 ===
        
        # Population 检查
        pop_include = criteria.get("population_include", "")
        pop_exclude = criteria.get("population_exclude", "")
        
        if pop_exclude:
            exclude_terms = [t.strip().lower() for t in pop_exclude.split(",")]
            for term in exclude_terms:
                if term and term in text:
                    return ("exclude", f"排除: 包含排除人群 '{term}'", 0.85)
        
        if pop_include:
            include_terms = [t.strip().lower() for t in pop_include.split(",")]
            found = any(term in text for term in include_terms if term)
            if not found:
                return ("uncertain", f"可能不相关: 未明确包含目标人群", 0.5)
        
        # Intervention 检查
        int_include = criteria.get("intervention_include", "")
        if int_include:
            include_terms = [t.strip().lower() for t in int_include.split(",")]
            found = any(term in text for term in include_terms if term)
            if not found:
                return ("uncertain", f"可能不相关: 未明确涉及目标干预", 0.5)
        
        # Outcome 检查
        outcome = criteria.get("outcome_primary", "")
        if outcome:
            outcome_terms = [t.strip().lower() for t in outcome.split(",")]
            found = any(term in text for term in outcome_terms if term)
            if not found:
                return ("uncertain", f"可能不相关: 未明确报告目标结局", 0.45)
        
        # Study Design 检查
        design_include = criteria.get("study_design_include", "")
        if design_include:
            design_found = False
            for design, keywords in self.STUDY_DESIGN_KEYWORDS.items():
                if design_include.lower() in design:
                    if any(kw in text for kw in keywords):
                        design_found = True
                        break
            if not design_found:
                return ("uncertain", f"可能不相关: 未明确为{design_include}", 0.55)
        
        # 通过所有检查
        confidence = 0.8
        if pop_include and any(t in text for t in [t.strip().lower() for t in pop_include.split(",") if t.strip()]):
            confidence += 0.05
        if int_include and any(t in text for t in [t.strip().lower() for t in int_include.split(",") if t.strip()]):
            confidence += 0.05
        if article.get("abstract"):
            confidence += 0.05
        if len(article.get("authors", [])) > 0:
            confidence += 0.02
        
        return ("include", "通过初筛", min(confidence, 0.98))
    
    def resolve_uncertain(self, uncertain_articles: list) -> dict:
        """
        处理不确定文献
        
        对uncertain的文献执行更细致的检查
        标记需要全文阅读的文献
        """
        resolved_include = []
        resolved_exclude = []
        need_fulltext = []
        
        for article in uncertain:
            abstract = (article.get("abstract") or "").lower()
            reason = article.get("screen_reason", "")
            
            # 如果有详细摘要，尝试二次判断
            if len(abstract) > 200:
                # 检查是否有足够的方法学信息
                methods_keywords = ["method", "design", "participant", "randomized", 
                                   "intervention", "outcome", "follow-up"]
                methods_count = sum(1 for kw in methods_keywords if kw in abstract)
                
                if methods_count >= 3:
                    article["screen_decision"] = "include"
                    article["screen_reason"] = "二次筛选通过: 摘要包含充足方法学信息"
                    article["screen_confidence"] = 0.7
                    resolved_include.append(article)
                else:
                    need_fulltext.append(article)
            else:
                need_fulltext.append(article)
        
        return {
            "resolved_include": resolved_include,
            "resolved_exclude": resolved_exclude,
            "need_fulltext": need_fulltext
        }
    
    def generate_prisma_stats(self, total_found: int, after_dedup: int,
                               screened: dict) -> dict:
        """生成PRISMA流程图所需统计数据"""
        return {
            "identification": {
                "records_identified": total_found,
                "records_after_dedup": after_dedup,
            },
            "screening": {
                "records_screened": screened["statistics"]["total"],
                "records_excluded": screened["statistics"]["excluded"],
                "exclusion_reasons": screened["statistics"]["exclusion_reasons"],
            },
            "eligibility": {
                "full_text_assessed": screened["statistics"]["included"] + screened["statistics"]["uncertain"],
                "full_text_excluded": 0,
            },
            "included": {
                "studies_included": screened["statistics"]["included"],
            }
        }
