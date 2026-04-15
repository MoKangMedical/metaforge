---
name: med-peer-review
description: 医学论文同行评审工作流 — 按GRADE/Cochrane标准审校临床研究论文，输出结构化评审意见
version: 1.0.0
category: medical-research
triggers:
  - 论文评审
  - peer review
  - 审稿
  - 临床研究评估
  - 论文审校
author: MedRoundTable Team
inspired_by: feynman/peer-review
test_prompts:
  - "评审这篇关于PD-L1抑制剂的III期RCT论文"
  - "Review this phase III clinical trial on osimertinib"
---

# MedRoundTable: 医学论文同行评审工作流

## 输入格式
```json
{
  "paper": {
    "pmid": "29658856",
    "title": "Pembrolizumab plus Chemotherapy in Metastatic NSCLC",
    "abstract": "...",
    "full_text": "..."  // 可选，有全文更佳
  },
  "review_type": "full",  // "quick" | "full" | "statistical" | "methodological"
  "reviewer_perspective": "clinician"  // "clinician" | "statistician" | "methodologist"
}
```

## 工作流程

### Phase 1: 论文结构解析
自动识别并提取:
- 研究设计类型 (RCT/队列/病例对照/横断面)
- PICOS要素
- 主要/次要结局
- 统计方法
- 主要结果

### Phase 2: 方法学质量评估
按研究类型选择评估工具:

| 研究类型 | 评估工具 |
|----------|----------|
| RCT | Cochrane RoB 2.0 |
| 非随机研究 | ROBINS-I |
| 观察性研究 | NOS (Newcastle-Ottawa) |
| 诊断准确性 | QUADAS-2 |

逐维度评估:
```json
{
  "rob_2": {
    "randomization_process": {"rating": "low", "support": "计算机随机序列，分配隐藏良好"},
    "deviations_from_intervention": {"rating": "some_concerns", "support": "开放标签设计"},
    "missing_outcome_data": {"rating": "low", "support": "ITT分析，失访<5%"},
    "measurement_of_outcome": {"rating": "low", "support": "独立评审委员会"},
    "selection_of_reported_result": {"rating": "low", "support": "预注册终点"}
  },
  "overall_rating": "some_concerns"
}
```

### Phase 3: 统计学审查
检查清单:
- [ ] 样本量计算是否合理
- [ ] 随机化方法是否恰当
- [ ] 主要分析是否遵循ITT原则
- [ ] 多重比较是否校正
- [ ] 亚组分析是否预设
- [ ] 置信区间是否报告
- [ ] P值解释是否恰当
- [ ] Kaplan-Meier曲线删失是否合理
- [ ] Cox比例风险假设是否检验

### Phase 4: 临床意义评估
- 效应量的临床意义（不只是统计意义）
- NNT/NNH 计算
- 绝对获益 vs 相对获益
- 安全性信号

### Phase 5: 生成评审报告

```markdown
# 论文评审报告

## 论文信息
- 标题: ...
- PMID: ...
- 期刊: ...

## 总体评价
- 推荐: [接收/小修/大修/拒稿]
- 置信度: [高/中/低]

## 1. 优点
1. ...
2. ...

## 2. 主要问题 (Major)
### 问题1: [标题]
- 描述: ...
- 建议: ...

### 问题2: [标题]
- 描述: ...
- 建议: ...

## 3. 次要问题 (Minor)
1. ...

## 4. 方法学评估
[偏倚风险评估表]

## 5. 统计学评估
[统计审查清单]

## 6. 临床意义评估
[NNT/NNH, 绝对获益]

## 详细评论
...
```

⚠️ **确认检查点**: 评审报告生成后暂停，等用户确认修改意见。

## 异常处理
| 场景 | 处理方式 |
|------|----------|
| 无全文 | 仅基于摘要评审，标注"基于摘要" |
| 统计方法描述不清 | 列出需要补充的信息 |
| 数据不一致 | 标注具体不一致之处 |
