---
name: med-replicate
description: 临床研究复现工作流 — 自动复现论文中的统计分析，验证结果一致性
version: 1.0.0
category: medical-research
triggers:
  - 研究复现
  - replicate study
  - 结果验证
  - 统计复现
  - 复现分析
author: MedRoundTable Team
inspired_by: feynman/replication
test_prompts:
  - "复现这篇论文的主要统计分析"
  - "Verify the hazard ratio calculation from Gandhi 2018"
---

# MedRoundTable: 临床研究复现工作流

## 输入格式
```json
{
  "paper": {
    "pmid": "29658856",
    "reported_results": {
      "os_hr": 0.49,
      "os_ci": [0.38, 0.64],
      "pfs_hr": 0.52,
      "pfs_ci": [0.43, 0.64],
      "orr_treatment": 47.6,
      "orr_control": 18.9
    }
  },
  "replicate_level": "full"  // "quick" | "full" | "individual_patient"
}
```

## 工作流程

### Phase 1: 提取报告数据
从论文中提取关键统计量:
- 效应量 (HR/OR/RR/MD)
- 95%置信区间
- P值
- 样本量
- 事件数

### Phase 2: 独立计算
用Python独立重新计算:

```python
import numpy as np
from scipy import stats

# HR置信区间反推SE
hr = 0.49
ci_lower, ci_upper = 0.38, 0.64
log_hr = np.log(hr)
se_log_hr = (np.log(ci_upper) - np.log(ci_lower)) / (2 * 1.96)

# Z检验
z = log_hr / se_log_hr
p_value = 2 * (1 - stats.norm.cdf(abs(z)))
# 期望 p_value ≈ 原文报告值
```

### Phase 3: 一致性验证
```json
{
  "verification": {
    "os_hr": {
      "reported": 0.49,
      "recalculated": 0.49,
      "match": true,
      "tolerance": 0.01
    },
    "os_ci_lower": {
      "reported": 0.38,
      "recalculated": 0.38,
      "match": true
    },
    "p_value": {
      "reported": 0.00001,
      "recalculated": 0.000012,
      "match": true,
      "note": "四舍五入差异"
    }
  },
  "overall_consistency": "PASS"
}
```

### Phase 4: 交叉验证检查
- [ ] 样本量加和正确
- [ ] 事件数与比例一致
- [ ] HR的CI包含点估计
- [ ] P值与CI方向一致
- [ ] 亚组数据与总数据兼容
- [ ] Kaplan-Meier中位数与报告一致

### Phase 5: 输出复现报告

```markdown
# 研究复现报告

## 论文信息
- PMID: 29658856
- 标题: Gandhi 2018 (KEYNOTE-189)

## 复现结果
| 指标 | 原文报告 | 复现计算 | 一致性 |
|------|----------|----------|--------|
| OS HR | 0.49 | 0.49 | ✓ |
| 95% CI | 0.38-0.64 | 0.38-0.64 | ✓ |
| P值 | <0.001 | <0.001 | ✓ |

## 发现的问题
1. ...

## 结论
- 复现状态: [完全一致/基本一致/存在差异]
- 差异分析: ...
```

⚠️ **确认检查点**: 复现报告生成后暂停，等用户确认发现。


## 异常处理
- 输入为空时返回友好提示
- 处理超时时自动重试
