# MedRoundTable 工作流索引

受 [Feynman AI科研代理](https://github.com/getcompanion-ai/feynman) 启发，
为医学/临床研究场景深度定制的6大专业工作流。

## 工作流目录

| 工作流 | 触发词 | 描述 | 对标Feynman |
|--------|--------|------|-------------|
| [med-lit-review](med-lit-review/) | 文献综述 | 系统检索+综合分析 | literature-review |
| [med-peer-review](med-peer-review/) | 论文评审 | GRADE/Cochrane标准审校 | peer-review |
| [med-replicate](med-replicate/) | 研究复现 | 统计分析独立验证 | replication |
| [med-clinical-audit](med-clinical-audit/) | 临床审计 | 数据完整性+一致性审查 | paper-code-audit |
| [med-report-writing](med-report-writing/) | 论文写作 | CONSORT/STROBE/PRISMA规范 | paper-writing |
| [med-decision-support](med-decision-support/) | 临床决策 | 循证推荐+GRADE分级 | deep-research |
| [med-deep-research](med-deep-research/) | 深度研究 | 多Agent全流程研究 | deep-research |

## 使用方式

### 在MedRoundTable中调用
```
用户: "帮我做一篇PD-1联合化疗治疗NSCLC的文献综述"
→ 系统自动匹配 med-lit-review 工作流
```

### 通过API调用
```python
POST /api/workflow/med-lit-review
{
  "clinical_question": "PD-1抑制剂联合化疗治疗晚期NSCLC",
  "scope": "systematic_overview",
  "databases": ["pubmed", "cochrane"]
}
```

## 与MetaForge的集成
所有工作流底层调用MetaForge的核心模块:
- `agents/seeker.py` — 文献检索
- `agents/filter.py` — 文献筛选
- `stats/engine.py` — 统计分析
- `stats/prisma.py` — PRISMA流程图
- `core/models.py` — 数据模型+溯源
