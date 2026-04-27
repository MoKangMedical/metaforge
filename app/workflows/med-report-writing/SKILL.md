---
name: med-report-writing
description: 医学研究报告写作工作流 — 生成符合CONSORT/STROBE/PRISMA规范的结构化研究报告
version: 1.0.0
category: medical-research
triggers:
  - 写论文
  - 论文写作
  - 研究报告
  - paper writing
  - 学术写作
  - 临床报告
author: MedRoundTable Team
inspired_by: feynman/paper-writing
test_prompts:
  - "帮我写一篇PD-1抑制剂联合化疗的Meta分析报告"
  - "Generate a PRISMA-compliant systematic review report"
---

# MedRoundTable: 医学研究报告写作工作流

## 输入格式
```json
{
  "study_type": "systematic_review",  // "rct" | "cohort" | "case_control" | "systematic_review" | "case_report"
  "reporting_standard": "PRISMA_2020",  // "CONSORT" | "STROBE" | "PRISMA_2020" | "CARE"
  "language": "zh",  // "zh" | "en" | "both"
  "data": {
    "title": "...",
    "search_results": [...],
    "included_studies": [...],
    "meta_analysis_results": {...}
  }
}
```

## 报告规范映射

| 研究类型 | 报告规范 | 检查项数 |
|----------|----------|----------|
| RCT | CONSORT 2010 | 25项 |
| 队列/病例对照/横断面 | STROBE | 22项 |
| 系统评价/Meta分析 | PRISMA 2020 | 27项 |
| 病例报告 | CARE | 30项 |
| 诊断准确性 | STARD | 30项 |

## 工作流程

### Phase 1: 选择模板
根据研究类型自动选择报告规范模板

### Phase 2: 数据填充
将分析结果填入模板:
- 标题 (含研究设计)
- 结构化摘要 (Background/Methods/Results/Conclusions)
- 引言 (3段式: 背景/知识空白/研究目的)
- 方法 (按检查清单逐项填写)
- 结果 (PRISMA流程图 + 特征表 + 分析结果)
- 讨论 (5段式: 主要发现/与前人对比/机制/局限/结论)
- 参考文献 (自动格式化)

### Phase 3: 合规性检查
逐条检查报告规范:
```
[✓] 1a. 标题明确研究设计
[✓] 1b. 结构化摘要
[ ] 3a. 纳排标准 (需要补充PICOS细节)
[✓] 5a. 研究方案注册号
...
合规率: 24/27 = 89%
```

### Phase 4: 输出报告
- Word (.docx) 格式
- LaTeX 格式
- 中英双语版本

⚠️ **确认检查点**: 初稿生成后暂停，等用户确认内容。

## 参考文件
- 统计引擎: `~/Desktop/metaforge/app/stats/engine.py`
- PRISMA生成: `~/Desktop/metaforge/app/stats/prisma.py`
