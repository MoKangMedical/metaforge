---
name: med-lit-review
description: 医学文献综述工作流 — 针对特定临床问题，系统检索、筛选、综合分析医学文献，输出结构化综述报告
version: 1.0.0
category: medical-research
triggers:
  - 文献综述
  - literature review
  - 医学综述
  - 系统评价
  - 综述报告
  - lit review
author: MedRoundTable Team
inspired_by: feynman/literature-review
test_prompts:
  - "对PD-1抑制剂联合化疗治疗晚期NSCLC做一篇文献综述"
  - "Review the current evidence for GLP-1 receptor agonists in obesity"
  - "罕见病基因治疗的最新进展综述"
---

# MedRoundTable: 医学文献综述工作流

受 [Feynman AI科研代理](https://github.com/getcompanion-ai/feynman) 启发，
针对医学场景深度定制。

## 输入格式
```json
{
  "clinical_question": "PD-1抑制剂联合化疗治疗晚期NSCLC的疗效与安全性",
  "scope": "systematic_overview",  // "narrative" | "systematic_overview" | "rapid_review"
  "databases": ["pubmed", "cochrane", "embase", "cnki"],
  "date_range": "2015-2026",
  "language": "zh,en",
  "output_format": "structured_report"
}
```

## 工作流程

### Phase 1: 问题构建 (5分钟)
使用PICO/PECO框架结构化临床问题：
- **P** (Population): 晚期NSCLC患者
- **I/E** (Intervention/Exposure): PD-1抑制剂+铂类化疗
- **C** (Comparison): 单纯化疗
- **O** (Outcomes): OS, PFS, ORR, 不良事件

⚠️ **确认检查点**: 展示结构化问题，等用户确认。

### Phase 2: 文献检索 (10分钟)
调用 MetaForge Agent-Seeker:
```python
from agents.seeker import SearchAgent
agent = SearchAgent()
results = agent.execute_search({
    "search_query": "(PD-1[MeSH] OR pembrolizumab[tiab]) AND (NSCLC[MeSH]) AND (chemotherapy[tiab])",
    "max_results": 500
})
```

检索策略文档:
- PubMed检索式完整记录
- Cochrane检索式完整记录
- 检索日期和检索人

### Phase 3: 文献筛选 (5分钟)
调用 MetaForge Agent-Filter:
```python
from agents.filter import ScreeningAgent
screened = agent.screen_title_abstract(articles, criteria)
```

输出PRISMA流程图数据:
- 检索记录数
- 去重后数
- 标题/摘要排除数及原因
- 全文纳入数

### Phase 4: 数据综合 (15分钟)
对纳入文献进行综合分析：

#### 4a. 研究特征汇总表
| 研究 | 年份 | 设计 | 样本量 | 干预 | 对照 | 随访 |
|------|------|------|--------|------|------|------|
| Gandhi 2018 | 2018 | III期RCT | 616 | PEM+化疗 | 安慰剂+化疗 | 10.5月 |

#### 4b. 疗效数据汇总
| 研究 | OS HR [95%CI] | PFS HR [95%CI] | ORR |
|------|---------------|----------------|-----|
| Gandhi 2018 | 0.49 [0.38-0.64] | 0.52 [0.43-0.64] | 47.6% |

#### 4c. 安全性数据汇总
| 研究 | 3-4级AE | TRAE导致停药 | 免疫相关AE |
|------|---------|-------------|------------|

#### 4d. Meta分析(如适用)
调用 MetaForge 统计引擎:
```python
from stats.engine import MetaAnalysisEngine
result = engine.analyze(studies, "OR", "random")
```

### Phase 5: 证据质量评估
使用GRADE框架评估每项结局：
- 研究设计局限性
- 不一致性
- 间接性
- 不精确性
- 发表偏倚

### Phase 6: 报告生成
输出结构化综述报告:

```markdown
# [临床问题] — 文献综述

## 摘要
- 背景: ...
- 方法: 检索了PubMed/Cochrane/Embase/CNKI，纳入X篇研究
- 结果: ...
- 结论: ...

## 1. 引言
## 2. 方法
### 2.1 检索策略
### 2.2 纳排标准
### 2.3 数据提取
### 2.4 质量评价
## 3. 结果
### 3.1 文献筛选 (PRISMA流程图)
### 3.2 研究特征
### 3.3 疗效分析
### 3.4 安全性分析
### 3.5 证据质量
## 4. 讨论
## 5. 结论
## 参考文献
```

⚠️ **确认检查点**: 报告初稿生成后，暂停等用户确认。

## 异常处理

| 场景 | 处理方式 |
|------|----------|
| 检索结果<10篇 | 提示扩大检索范围或放宽纳排标准 |
| 无RCT纳入 | 降级为叙述性综述，标注证据等级 |
| 异质性极高(I²>80%) | 不做Meta分析，改为描述性综合 |
| 全文获取失败 | 标注"仅基于摘要"，降低证据等级 |

## 数据溯源
每个数据点必须标注:
- PMID
- 原文位置(表格/图)
- 提取置信度
- 是否已交叉验证

## 参考文件
- 检索引擎: `~/Desktop/metaforge/app/agents/seeker.py`
- 筛选引擎: `~/Desktop/metaforge/app/agents/filter.py`
- 统计引擎: `~/Desktop/metaforge/app/stats/engine.py`
- PRISMA生成: `~/Desktop/metaforge/app/stats/prisma.py`
- 数据模型: `~/Desktop/metaforge/app/core/models.py`
