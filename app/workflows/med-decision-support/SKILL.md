---
name: med-decision-support
description: 循证临床决策支持工作流 — 针对具体患者场景，综合最新证据给出分级推荐
version: 1.0.0
category: clinical
triggers:
  - 临床决策
  - 治疗方案
  - clinical decision
  - 循证推荐
  - 第二意见
  - 诊疗建议
author: MedRoundTable Team
inspired_by: feynman/deep-research
test_prompts:
  - "一位65岁EGFR突变IIIA期NSCLC患者，术后辅助治疗如何选择？"
  - "What is the optimal treatment for treatment-naive CLL with TP53 mutation?"
---

# MedRoundTable: 循证临床决策支持工作流

## 输入格式
```json
{
  "patient": {
    "age": 65,
    "gender": "male",
    "diagnosis": "NSCLC EGFR L858R+ IIIA",
    "stage": "IIIA",
    "prior_treatment": ["手术切除"],
    "comorbidities": ["高血压", "糖尿病"],
    "performance_status": "ECOG 0",
    "lab_values": {"EGFR": "L858R突变", "PD-L1": "TPS 10%"}
  },
  "question": "术后辅助治疗最佳方案",
  "evidence_standard": "GRADE"
}
```

## 工作流程

### Phase 1: 问题分解
将临床问题分解为可检索的子问题:
1. EGFR+ NSCLC IIIA术后辅助靶向 vs 辅助化疗?
2. 辅助靶向的最佳药物?
3. 辅助治疗的最佳疗程?
4. 特殊人群(老年/合并症)的调整?

### Phase 2: 证据检索
对每个子问题检索最新证据:
- 指南 (NCCN, ESMO, CSCO, ASCO)
- 系统评价/Meta分析
- 关键RCT (ADAURA, EVAN, EVIDENCE等)
- 真实世界数据

### Phase 3: 证据综合
对检索到的证据进行综合:

| 证据维度 | 评估 |
|----------|------|
| 研究质量 | III期RCT, 多中心 |
| 效应量 | OS HR 0.17 [0.11-0.26] |
| 精确度 | CI窄, 大样本 |
| 一致性 | 多项研究方向一致 |
| 直接性 | 直接比较, 人群匹配 |
| **GRADE等级** | **高** |

### Phase 4: 推荐生成
按GRADE Evidence-to-Decision框架:

```json
{
  "recommendation": {
    "direction": "for",
    "strength": "strong",
    "certainty": "high",
    "statement": "推荐奥希替尼辅助治疗3年 (强推荐，高质量证据)",
    "evidence_basis": [
      {
        "study": "ADAURA (NCT02511106)",
        "pmid": "32955177",
        "finding": "奥希替尼 vs 安慰剂: DFS HR 0.17, OS HR 0.49",
        "quality": "high"
      }
    ],
    "alternatives": [
      {
        "option": "辅助化疗 (顺铂+培美曲塞)",
        "evidence": "中等",
        "note": "如不能耐受靶向治疗"
      }
    ],
    "special_considerations": [
      "老年患者需评估肾功能",
      "合并糖尿病注意药物相互作用"
    ]
  }
}
```

### Phase 5: 生成决策报告

```markdown
# 循证临床决策报告

## 患者概况
- 65岁男性，NSCLC EGFR L858R+ IIIA
- ECOG 0，已行手术切除
- 合并高血压、糖尿病

## 临床问题
术后辅助治疗最佳方案

## 推荐方案

### 🟢 强推荐: 奥希替尼辅助治疗 3年

**证据基础:**
- ADAURA研究 (III期RCT, N=682)
- DFS HR 0.17 (95%CI 0.11-0.26)
- OS HR 0.49 (95%CI 0.33-0.72)
- GRADE: 高质量证据

**用法:** 奥希替尼 80mg QD × 3年

**监测:**
- 每3月CT复查
- 心电图监测QT间期
- 肝功能监测

### 替代方案
1. 辅助化疗 (如不耐受靶向)
2. 辅助化疗+奥希替尼序贯 (证据不足)

### ⚠️ 特殊考量
- 老年患者: 监测肾功能
- 合并糖尿病: 注意低血糖风险

## 参考文献
1. Wu YL, et al. N Engl J Med. 2020;383(18):1711-1723. PMID: 32955177
2. Herbst RS, et al. J Clin Oncol. 2023;41(14_suppl):8500

## 免责声明
⚠️ 本报告为AI辅助循证参考，非最终诊疗决策。
最终治疗方案需由主治医师结合患者具体情况决定。
```

⚠️ **确认检查点**: 
1. 证据综合后暂停，展示给医生确认
2. 推荐生成后暂停，等医生确认
3. 报告输出前确认免责声明

## 安全合规
- 所有输出包含免责声明
- 不替代医生临床判断
- 引用文献可追溯
- 符合HIPAA/GDPR
