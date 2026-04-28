# MetaForge

> AI循证医学研究平台 — 6大AI Agent协同，将Meta分析从45-90天压缩至1小时

[![Python](https://img.shields.io/badge/python-3.9+-green.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-orange.svg)]()

## 一句话定义

**MetaForge 不卖文献分析工具，卖Meta分析结果。** 输入研究问题，输出结构化Meta分析报告，含森林图、漏斗图、GRADE证据评级。

---

## 核心功能

### 完整闭环 — 输入数据即出结果

```
输入研究数据 → 统计分析 → 森林图/漏斗图/PRISMA → 亚组/敏感性/偏倚检验 → CSV/JSON导出
```

### 统计引擎 (真实计算)

| 功能 | 方法 | 描述 |
|------|------|------|
| **固定效应模型** | Mantel-Haenszel | 经典固定效应Meta分析 |
| **随机效应模型** | DerSimonian-Laird | 考虑研究间异质性 |
| **异质性检验** | I², Q, τ² | Cochran's Q检验 |
| **Egger检验** | 回归法 | 发表偏倚检测 |
| **Begg检验** | 秩相关法 | 发表偏倚检测 |
| **Trim-and-Fill** | Duval & Tweedie | 估计缺失研究并调整效应量 |
| **亚组分析** | 按研究特征分组 | 组间差异检验 |
| **敏感性分析** | Leave-one-out | 逐一剔除评估影响 |
| **累积Meta分析** | 逐步添加研究 | 观察效应量演变 |
| **森林图** | SVG生成 | 发表级图表 |
| **漏斗图** | SVG生成 | 发表偏倚可视化 |
| **PRISMA流程图** | SVG生成 | 符合PRISMA 2020标准 |

### 12个API端点

```
GET  /api/health          健康检查
POST /api/demo            运行演示数据
POST /api/analyze         执行Meta分析
POST /api/bias            发表偏倚检验 (Egger+Begg+TrimFill)
POST /api/cumulative      累积Meta分析
POST /api/prisma          PRISMA流程图
POST /api/forest          森林图
POST /api/funnel          漏斗图
GET  /api/models          统计模型列表
POST /api/export/csv      CSV导出
POST /api/export/json     JSON导出
POST /api/upload/csv      CSV上传分析
```

### Web工作台

- 交互式数据输入表格
- 3个快捷数据集 (NSCLC PD-1 / 他汀类 / 降压药)
- CSV数据导入
- 实时参数切换 (模型/效应量即时更新)
- 发表偏倚检验面板
- 累积分析图表
- CSV/JSON结果导出
- Ctrl+Enter快捷键
- Toast通知

---

## 快速开始

```bash
git clone https://github.com/MoKangMedical/metaforge.git
cd metaforge
pip install -r requirements.txt
python3 -m uvicorn app.main:app --port 8000
```

打开:
- `http://localhost:8000` → Landing Page
- `http://localhost:8000/app` → Web工作台

---

## 技术架构

```
metaforge/
├── app/
│   ├── main.py              # FastAPI后端 (12个API端点 + 统计引擎)
│   ├── templates/
│   │   └── app.html         # Web工作台 (完整交互界面)
│   ├── agents/              # AI Agent系统
│   ├── engines/             # Cochrane合规引擎
│   ├── stats/               # 统计分析模块
│   └── assessment/          # ROB2偏倚评估
├── assets/figures/          # 发表级图表库 (6张)
├── index.html               # Landing Page
├── css/style.css            # 设计系统
├── requirements.txt         # 依赖
└── README.md
```

---

## License

MIT License
