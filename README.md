# MetaForge

> AI循证医学研究平台 — 6大AI Agent协同，将Meta分析从45-90天压缩至1小时

[![Python](https://img.shields.io/badge/python-3.9+-green.svg)]()
[![Agents](https://img.shields.io/badge/AI_Agents-6-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-orange.svg)]()

## 一句话定义

**MetaForge 不卖文献分析工具，卖Meta分析结果。** 输入研究问题，输出结构化Meta分析报告，含森林图、漏斗图、GRADE证据评级。

---

## 解决什么问题

| 痛点 | 传统Meta分析 | MetaForge |
|------|------------|-----------|
| 耗时 | 45-90天 | 1小时 |
| 文献筛选 | 手动逐一审查 | AI自动筛选 |
| 数据提取 | 人工表格录入 | AI自动提取 |
| 统计分析 | 需统计学专家 | 自动执行 |
| 偏倚评估 | 复杂、主观 | 标准化AI评估 |

---

## 6大AI Agent

1. **文献检索Agent** — PubMed/Cochrane自动检索
2. **筛选Agent** — 纳入排除标准自动筛选（盲法评审）
3. **数据提取Agent** — 效应量/CI/样本量自动提取
4. **统计Agent** — 随机/固定效应模型、亚组分析、敏感性分析
5. **偏倚Agent** — ROB2、Newcastle-Ottawa量表
6. **报告Agent** — 森林图/漏斗图/PRISMA流程图/GRADE评级

---

## 发表级图表库

自动生成Nature/NEJM级Meta分析图表：

- **主分析森林图** — 固定/随机效应模型合并结果
- **扩展分析森林图** — 多模型对比（M-H、D-L、REML）
- **PRISMA 2020流程图** — 文献筛选全流程
- **亚组分析** — 按干预剂量/随访时间/人群分组
- **逐一剔除分析** — Leave-one-out敏感性分析
- **漏斗图** — 发表偏倚评估（Egger检验 + Trim-and-Fill）

所有图表均支持交互式查看和导出。

---

## 技术架构

```
metaforge/
├── app/
│   ├── main.py              # FastAPI后端
│   ├── agents/              # 6大AI Agent
│   │   ├── seeker.py        # 文献检索Agent
│   │   └── filter.py        # 筛选Agent
│   ├── engines/             # 核心引擎
│   │   ├── cochrane_engine.py   # Cochrane合规引擎
│   │   ├── extraction.py        # 数据提取引擎
│   │   ├── blind_screening.py   # 盲法筛选引擎
│   │   ├── visual_extract.py    # PDF视觉提取
│   │   └── report_generator.py  # PRISMA 2020报告
│   ├── stats/               # 统计分析
│   │   ├── engine.py        # Meta分析计算引擎
│   │   └── prisma.py        # PRISMA流程图
│   └── assessment/          # 质量评价
│       └── rob2.py          # ROB2偏倚评估
├── assets/figures/          # 发表级图表库
├── index.html               # 平台Landing Page
├── css/style.css            # 设计系统
└── js/main.js               # 交互逻辑
```

---

## 快速开始

```bash
git clone https://github.com/MoKangMedical/metaforge.git
cd metaforge
pip install -r requirements.txt
python -m app.main
```

---

## API接口

- `POST /api/search` — PubMed文献检索
- `POST /api/screen` — AI文献筛选
- `POST /api/analyze` — Meta统计分析
- `POST /api/prisma` — PRISMA流程图生成
- `GET  /api/demo` — 运行演示

---

## Harness理论

```
Meta分析Harness = 检索策略编码 + 筛选规则 + 数据提取模板 + 统计流程 + 偏倚评估标准
```

模型会过时，Meta分析方法论持续进化。MetaForge是方法论的工程化实现。

---

## License

MIT License
