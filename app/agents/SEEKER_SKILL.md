---
name: metaforge-agent-seeker
description: MetaForge文献检索Agent — 连接PubMed/Cochrane等学术数据库，AI辅助构建检索策略，返回去重后的文献列表
version: 1.1.0
category: research
triggers:
  - 检索文献
  - search literature
  - PubMed搜索
  - 找论文
  - 查文献
  - 检索策略
author: MetaForge Team
test_prompts:
  - "帮我检索PD-1抑制剂治疗非小细胞肺癌的RCT研究"
  - "Search for meta-analysis of statin therapy in cardiovascular disease"
---

# Agent-Seeker: 文献检索智能体

## 输入格式
```json
{
  "query": "PD-1 inhibitor AND NSCLC",
  "max_results": 200,
  "databases": ["pubmed", "cochrane"],
  "date_range": "2015-2026",
  "study_type": "randomized controlled trial"
}
```

## 工作流程

### Step 1: 解析研究问题 (PICOS提取)
从用户输入中提取PICOS要素：
- **P** (Population): 目标人群 — 例如 "非小细胞肺癌患者"
- **I** (Intervention): 干预措施 — 例如 "PD-1抑制剂 (pembrolizumab, nivolumab)"
- **C** (Comparator): 对照组 — 例如 "标准化疗"
- **O** (Outcome): 结局指标 — 例如 "总生存期(OS), 无进展生存期(PFS)"
- **S** (Study Design): 研究设计 — 例如 "RCT, 系统评价"

⚠️ **确认检查点**: 提取完PICOS后，展示给用户确认再继续。

### Step 2: 构建检索策略
```python
# 检索策略构建示例
query = build_strategy(
    topic="(PD-1[MeSH] OR pembrolizumab[tiab] OR nivolumab[tiab])",
    population="(NSCLC[tiab] OR non-small cell lung cancer[MeSH])",
    intervention="(chemotherapy[tiab] OR platinum[tiab])",
    study_type="(randomized controlled trial[pt])"
)
# 输出: (PD-1[MeSH] OR pembrolizumab[tiab] ...) AND (NSCLC[tiab] ...) AND ...
```

参考文件: `~/Desktop/metaforge/app/agents/seeker.py` 中的 `PubMedClient.build_strategy()`

### Step 3: 执行检索
连接PubMed API (`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`)：
```python
client = PubMedClient(email="user@metaforge.ai")
result = client.search(query, max_results=500)
pmids = result["pmids"]  # ["12345678", "23456789", ...]
articles = client.fetch_details(pmids)
```

- 最大结果数: 500（可配置）
- 自动去重基于PMID
- 速率限制: 无API Key时3请求/秒

⚠️ **确认检查点**: 结果>1000篇时，提示用户添加过滤条件。

### Step 4: 返回结果
```json
{
  "success": true,
  "total_found": 2847,
  "returned_count": 200,
  "after_dedup": 2947,
  "articles": [
    {
      "pmid": "29658856",
      "title": "Pembrolizumab plus Chemotherapy in Metastatic NSCLC",
      "authors": ["Gandhi L", "Rodríguez-Abreu D"],
      "year": 2018,
      "journal": "N Engl J Med",
      "abstract": "...",
      "provenance": [{"source": "pubmed_api", "confidence": 1.0}]
    }
  ],
  "audit": {
    "timestamp": "2026-04-15T10:30:00",
    "database": "PubMed",
    "query": "...",
    "translation": "(('PD-1'[MeSH]) AND ...)"
  }
}
```

## 异常处理

### 边界条件
| 场景 | 处理方式 |
|------|----------|
| 检索词为空 | 返回错误: `{"error": "检索词不能为空"}` |
| PubMed API超时 | 重试3次，间隔2秒，仍失败返回缓存数据 |
| 结果为0 | 建议放宽检索条件，提供MeSH扩展建议 |
| 网络断开 | 使用本地缓存（`~/.metaforge/cache/`），提示离线模式 |
| API限速(429) | 自动降速等待，指数退避 |

### 错误恢复
- 检索中断时保存已获取的结果
- 支持断点续传（从上次PMID继续）

## 数据溯源要求
每个文献必须包含以下溯源字段：
```json
{
  "provenance": [{
    "id": "search-pmid-12345",
    "pmid": "12345678",
    "source_url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
    "raw_text": "检索结果: 文献标题",
    "extraction_method": "pubmed_api",
    "confidence": 1.0,
    "verified": true
  }]
}
```

## 实测用例

### 测试1: 标准PICOS检索
**输入**: "PD-1抑制剂联合化疗治疗晚期NSCLC的RCT"
**期望输出**: 
- 检索到 >1000篇文献
- 去重后 <原数量
- 包含 KEYNOTE-189, IMpower150 等关键研究
- 所有文献有PMID和溯源

### 测试2: 空查询
**输入**: ""
**期望输出**: `{"error": "检索词不能为空"}`

### 测试3: 窄查询
**输入**: "pembrolizumab squamous NSCLC 2023"
**期望输出**: <100篇，高相关度
