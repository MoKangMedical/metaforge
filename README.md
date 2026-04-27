# MetaForge

AI循证医学研究平台 — 6大AI Agent协同，将Meta分析从45-90天压缩至1小时

## 一句话定义

MetaForge 不卖文献分析工具，卖Meta分析结果。输入研究问题，输出结构化Meta分析报告，含森林图、漏斗图、GRADE证据评级。

## 解决什么问题

| 痛点 | 传统Meta分析 | MetaForge |
|------|------------|-----------|
| 耗时 | 45-90天 | 1小时 |
| 文献筛选 | 手动逐一审查 | AI自动筛选 |
| 数据提取 | 人工表格录入 | AI自动提取 |
| 统计分析 | 需统计学专家 | 自动执行 |
| 偏倚评估 | 复杂、主观 | 标准化AI评估 |

## 6大AI Agent

1. 文献检索Agent: PubMed/Cochrane自动检索
2. 筛选Agent: 纳入排除标准自动筛选
3. 数据提取Agent: 效应量/CI/样本量自动提取
4. 统计Agent: 随机/固定效应模型、亚组分析
5. 偏倚Agent: ROB2、Newcastle-Ottawa量表
6. 报告Agent: 森林图/漏斗图/GRADE评级

## Harness理论

Meta分析Harness = 检索策略编码 + 筛选规则 + 数据提取模板 + 统计流程 + 偏倚评估标准

模型会过时，Meta分析方法论持续进化。

## 快速开始

    git clone https://github.com/MoKangMedical/metaforge.git
    cd metaforge
    pip install -r requirements.txt
    python src/main.py --topic "GLP-1 and cardiovascular outcomes"

MIT License
