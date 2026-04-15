---
name: med-deep-research
description: 医学深度研究工作流 — 多Agent协同完成从问题定义到结论输出的全流程深度研究
version: 1.0.0
category: medical-research
triggers:
  - 深度研究
  - deep research
  - 全面分析
  - 综合研究
  - 课题研究
author: MedRoundTable Team
inspired_by: feynman/deep-research
---

# MedRoundTable: 医学深度研究工作流

## Agent编排
```
协调员 (Orchestrator)
├── Agent-Seeker  → 文献检索
├── Agent-Filter  → 文献筛选  
├── Agent-Extractor → 数据提取
├── Agent-Evaluator → 质量评价
├── Agent-Analyst → 统计分析
├── Agent-Writer → 报告生成
└── Agent-Reviewer → 内部审查
```

## 工作流程

### Step 1: 问题定义 (协调员)
- 与用户对话明确研究问题
- 分解为可操作的子问题
- 确定研究范围和输出格式

### Step 2: 多Agent并行执行
```python
# 协调员同时启动多个Agent
tasks = [
    seeker.execute_search(query_pubmed),
    seeker.execute_search(query_cochrane),
    seeker.execute_search(query_cnki),
]
# 结果汇总后传给Filter
screened = filter.screen_title_abstract(all_articles, criteria)
# Filter输出传给Extractor
extracted = extractor.extract_data(screened["included"])
# Evaluator并行评价质量
evaluated = evaluator.assess_rob(extracted)
# Analyst执行统计
result = analyst.meta_analyze(evaluated)
# Writer生成报告
report = writer.generate(result)
```

### Step 3: 内部审查 (Agent-Reviewer)
- 检查报告完整性
- 验证数据一致性
- 确认结论有证据支持
- 标注需要人工确认的部分

### Step 4: Human Checkpoint
- 展示完整研究摘要
- 等用户确认
- 根据反馈调整

### Step 5: 输出
- 完整研究报告 (中/英)
- PRISMA流程图
- 森林图/漏斗图
- 数据提取表
- GRADE证据概要
