---
name: metaforge-agent-filter
description: MetaForge文献筛选Agent — 基于PICOS标准自动筛选文献，双人独立筛选+仲裁机制，输出纳入/排除/待审核列表
version: 1.1.0
category: research
triggers:
  - 筛选文献
  - screen articles
  - PICOS筛选
  - 纳排标准
  - 文献筛选
author: MetaForge Team
test_prompts:
  - "根据PICOS标准筛选这200篇文献：P=NSCLC, I=PD-1抑制剂, O=OS"
---

# Agent-Filter: 文献筛选智能体

## 输入格式
```json
{
  "articles": [{"pmid": "...", "title": "...", "abstract": "..."}],
  "criteria": {
    "population_include": "NSCLC, non-small cell lung cancer",
    "population_exclude": "SCLC, small cell",
    "intervention_include": "PD-1, pembrolizumab, nivolumab, atezolizumab",
    "outcome_primary": "overall survival, progression-free survival",
    "study_design_include": "randomized controlled trial",
    "language": "无限制",
    "date_range": "2015-2026"
  }
}
```

## 工作流程

### Step 1: 规则引擎预筛选 (3秒内完成)
快速排除明确不符合的文献：

| 规则 | 匹配条件 | 动作 |
|------|----------|------|
| R1: 非人类研究 | "animal" AND NOT "human" | 排除 |
| R2: 非研究性文章 | publication_type ∈ {letter, editorial, comment, news} | 排除 |
| R3: 仅会议摘要 | "conference abstract" AND NOT "journal article" | 排除 |
| R4: 已撤稿 | "retracted" in title/abstract | 排除 |

⚠️ **确认检查点**: 规则排除后，展示排除数量和原因，等用户确认。

### Step 2: AI深度筛选 (PICOS匹配)
对通过预筛选的文献逐篇评估：
```
对每篇文献:
  1. 检查 Population: 标题/摘要中是否包含目标人群关键词
  2. 检查 Intervention: 是否涉及目标干预
  3. 检查 Outcome: 是否报告了目标结局
  4. 检查 Study Design: 是否为指定研究类型
  5. 计算综合置信度 (0-1)
  
  决策规则:
  - 置信度 >= 0.85 → include
  - 置信度 0.5-0.85 → uncertain (需人工审核)
  - 置信度 < 0.5 或命中排除规则 → exclude
```

### Step 3: 处理不确定文献
```python
for article in uncertain_articles:
    if len(article.abstract) > 200:  # 有详细摘要
        methods_keywords = ["method", "design", "participant", "randomized"]
        if count_matches(article.abstract, methods_keywords) >= 3:
            article.decision = "include"
        else:
            article.needs_fulltext = True
    else:
        article.needs_fulltext = True
```

⚠️ **确认检查点**: uncertain列表必须人工确认后才能进入下一步。

### Step 4: 输出筛选结果
```json
{
  "statistics": {
    "total": 2947,
    "included": 486,
    "excluded": 2461,
    "uncertain": 0,
    "exclusion_reasons": {
      "排除: 非人类研究": 342,
      "排除: 非研究性文章": 156,
      "可能不相关: 未明确涉及目标干预": 892
    }
  },
  "included": [...],
  "excluded": [...]
}
```

## 异常处理

| 场景 | 处理方式 |
|------|----------|
| 文献无摘要 | 仅基于标题筛选，置信度上限0.7 |
| AI服务不可用 | 降级为纯规则引擎 |
| 纳入比例>80% | 触发警告: "筛选可能过松，请检查纳入标准" |
| 纳入比例<5% | 触发警告: "筛选可能过严，请检查排除标准" |
| 批量处理中断 | 保存已处理结果，支持断点续筛 |

## 数据溯源
每个筛选决策附带：
```json
{
  "screen_provenance": {
    "pmid": "29658856",
    "decision": "include",
    "reason": "通过初筛: 明确涉及PD-1抑制剂+NSCLC+RCT",
    "confidence": 0.92,
    "rules_fired": [],
    "keywords_matched": ["PD-1", "NSCLC", "randomized"],
    "timestamp": "2026-04-15T10:35:00"
  }
}
```

## 参考文件
- 筛选逻辑: `~/Desktop/metaforge/app/agents/filter.py`
- 数据模型: `~/Desktop/metaforge/app/core/models.py`
- 抗幻觉引擎: `~/Desktop/metaforge/app/core/models.py` 中的 `AntiHallucinationValidator`
