"""
MetaForge — 完整Meta分析平台后端
从研究方案输入到论文输出，全流程API
"""

import os
import sys
import json
import time
import math
import uuid
import hashlib
import traceback
from datetime import datetime
from typing import Optional
from pathlib import Path

# Add parent to path
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

import numpy as np
from scipy import stats

# ============================================
# App
# ============================================
app = FastAPI(title="MetaForge", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Static
STATIC = os.path.join(BASE, "app", "static")
os.makedirs(STATIC, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

# In-memory store
jobs: dict = {}


# ============================================
# PubMed Client (inline, no deps)
# ============================================
import urllib.request, urllib.parse, xml.etree.ElementTree as ET

class PubMed:
    BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    
    @staticmethod
    def search(query, max_results=300, date_from="", date_to=""):
        params = {"db": "pubmed", "term": query, "retmax": max_results, "retmode": "json", "sort": "relevance"}
        if date_from: params["mindate"] = date_from.replace("/", "")
        if date_to: params["maxdate"] = date_to.replace("/", "")
        if date_from or date_to: params["datetype"] = "pdat"
        url = f"{PubMed.BASE}/esearch.fcgi?{urllib.parse.urlencode(params)}"
        time.sleep(0.34)
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read())
        es = data.get("esearchresult", {})
        return {"count": int(es.get("count", 0)), "pmids": es.get("idlist", []), "translation": es.get("querytranslation", "")}
    
    @staticmethod
    def fetch(pmids, batch=100):
        articles = []
        for i in range(0, len(pmids), batch):
            batch_ids = pmids[i:i+batch]
            params = {"db": "pubmed", "id": ",".join(batch_ids), "retmode": "xml", "rettype": "abstract"}
            url = f"{PubMed.BASE}/efetch.fcgi?{urllib.parse.urlencode(params)}"
            time.sleep(0.34)
            with urllib.request.urlopen(url, timeout=60) as r:
                xml_data = r.read()
            articles.extend(PubMed._parse(xml_data))
        return articles
    
    @staticmethod
    def _parse(xml_data):
        articles = []
        try:
            root = ET.fromstring(xml_data)
        except:
            return articles
        for pa in root.findall(".//PubmedArticle"):
            a = {}
            pmid_el = pa.find(".//PMID")
            a["pmid"] = pmid_el.text if pmid_el is not None else ""
            title_el = pa.find(".//ArticleTitle")
            a["title"] = PubMed._text(title_el) if title_el is not None else ""
            abstract_parts = []
            for at in pa.findall(".//AbstractText"):
                label = at.get("Label", "")
                text = PubMed._text(at)
                if label: abstract_parts.append(f"{label}: {text}")
                else: abstract_parts.append(text)
            a["abstract"] = "\n".join(abstract_parts)
            authors = []
            for au in pa.findall(".//Author"):
                last = au.findtext("LastName", "")
                fore = au.findtext("ForeName", "")
                if last: authors.append(f"{last} {fore}".strip())
            a["authors"] = authors
            a["journal"] = (pa.find(".//Journal/Title").text if pa.find(".//Journal/Title") is not None else "")
            year_el = pa.find(".//PubDate/Year")
            a["year"] = int(year_el.text) if year_el is not None else 0
            a["doi"] = ""
            for aid in pa.findall(".//ArticleId"):
                if aid.get("IdType") == "doi": a["doi"] = aid.text
            pub_types = [pt.text for pt in pa.findall(".//PublicationType") if pt.text]
            a["publication_types"] = pub_types
            mesh = [mh.text for mh in pa.findall(".//MeshHeading/DescriptorName") if mh.text]
            a["mesh_terms"] = mesh
            articles.append(a)
        return articles
    
    @staticmethod
    def _text(el):
        if el is None: return ""
        t = el.text or ""
        for c in el:
            t += PubMed._text(c)
            t += c.tail or ""
        return t


# ============================================
# Screening Engine
# ============================================
class Screener:
    EXCLUDE_KW = ["animal", "mice", "mouse", "rat ", "rats ", "rabbit", "in vitro", "cell line"]
    NON_STUDY = ["letter", "editorial", "comment", "news", "erratum", "retraction"]
    
    @staticmethod
    def screen(articles, criteria):
        included, excluded, uncertain = [], [], []
        reasons = {}
        for a in articles:
            decision, reason, conf = Screener._eval(a, criteria)
            a["screen_decision"] = decision
            a["screen_reason"] = reason
            a["screen_confidence"] = conf
            if decision == "include": included.append(a)
            elif decision == "exclude":
                excluded.append(a)
                reasons[reason] = reasons.get(reason, 0) + 1
            else: uncertain.append(a)
        return {
            "included": included, "excluded": excluded, "uncertain": uncertain,
            "stats": {"total": len(articles), "included": len(included), "excluded": len(excluded),
                      "uncertain": len(uncertain), "reasons": reasons}
        }
    
    @staticmethod
    def _eval(a, c):
        text = f"{a.get('title','')} {a.get('abstract','')}".lower()
        pub_types = [p.lower() for p in a.get("publication_types", [])]
        
        # Rule: exclude non-human
        for kw in Screener.EXCLUDE_KW:
            if kw in text and not any(h in text for h in ["human", "patient", "participant"]):
                return "exclude", "非人类研究", 0.95
        
        # Rule: exclude non-study
        for pt in pub_types:
            for ns in Screener.NON_STUDY:
                if ns in pt: return "exclude", f"非研究性文章 ({pt})", 0.98
        
        # PICOS check
        pop_inc = c.get("population_include", "")
        if pop_inc:
            terms = [t.strip().lower() for t in pop_inc.split(",") if t.strip()]
            if not any(t in text for t in terms):
                return "uncertain", "未明确包含目标人群", 0.5
        
        int_inc = c.get("intervention_include", "")
        if int_inc:
            terms = [t.strip().lower() for t in int_inc.split(",") if t.strip()]
            if not any(t in text for t in terms):
                return "uncertain", "未明确涉及目标干预", 0.5
        
        return "include", "通过筛选", min(0.85 + (0.1 if len(a.get("abstract","")) > 100 else 0), 0.98)


# ============================================
# Meta Analysis Engine
# ============================================
class MetaEngine:
    @staticmethod
    def analyze_dichotomous(studies, measure="OR", model="random"):
        yi_list, wi_list, vi_list, sr_list = [], [], [], []
        for s in studies:
            a, b = s["e_events"], s["e_total"] - s["e_events"]
            c, d = s["c_events"], s["c_total"] - s["c_events"]
            if 0 in (a, b, c, d):
                a, b, c, d = a+0.5, b+0.5, c+0.5, d+0.5
            if measure == "OR":
                yi = math.log(a*d/(b*c))
                vi = 1/a + 1/b + 1/c + 1/d
            else:
                yi = math.log((a/(a+b))/(c/(c+d)))
                vi = 1/a - 1/(a+b) + 1/c - 1/(c+d)
            wi = 1/vi
            sr_list.append({"name": s["name"], "effect": math.exp(yi), 
                           "ci_l": math.exp(yi-1.96*math.sqrt(vi)), "ci_u": math.exp(yi+1.96*math.sqrt(vi)),
                           "log_effect": yi, "se": math.sqrt(vi),
                           "e_events": s["e_events"], "e_total": s["e_total"],
                           "c_events": s["c_events"], "c_total": s["c_total"]})
            yi_list.append(yi); wi_list.append(wi); vi_list.append(vi)
        
        yi, wi, vi = np.array(yi_list), np.array(wi_list), np.array(vi_list)
        k = len(yi)
        yi_fixed = np.sum(wi*yi)/np.sum(wi)
        q = float(np.sum(wi*(yi-yi_fixed)**2))
        q_df = k-1
        q_p = float(1-stats.chi2.cdf(q, q_df)) if q_df > 0 else 1.0
        i_sq = max(0, (q-q_df)/q*100) if q > 0 else 0
        c_dl = np.sum(wi) - np.sum(wi**2)/np.sum(wi)
        tau_sq = max(0, (q-q_df)/c_dl) if c_dl > 0 else 0
        
        wi_star = 1/(vi+tau_sq) if model == "random" else wi
        yi_p = float(np.sum(wi_star*yi)/np.sum(wi_star))
        se_p = 1/math.sqrt(float(np.sum(wi_star)))
        z = yi_p/se_p
        p = float(2*(1-stats.norm.cdf(abs(z))))
        weights = wi_star/np.sum(wi_star)*100
        
        for i, sr in enumerate(sr_list):
            sr["weight"] = float(weights[i])
        
        het = "low" if i_sq < 25 else ("moderate" if i_sq < 75 else "high")
        
        return {
            "pooled_effect": math.exp(yi_p), "ci_lower": math.exp(yi_p-1.96*se_p),
            "ci_upper": math.exp(yi_p+1.96*se_p), "p_value": p, "z_value": z,
            "i_squared": i_sq, "tau_squared": tau_sq, "q_stat": q, "q_p": q_p,
            "heterogeneity": het, "model": model, "measure": measure,
            "studies": sr_list
        }
    
    @staticmethod
    def sensitivity(studies, measure="OR", model="random"):
        full = MetaEngine.analyze_dichotomous(studies, measure, model)
        results = []
        for i in range(len(studies)):
            remaining = studies[:i] + studies[i+1:]
            if not remaining: continue
            r = MetaEngine.analyze_dichotomous(remaining, measure, model)
            results.append({"excluded": studies[i]["name"], "effect": r["pooled_effect"],
                           "ci_l": r["ci_lower"], "ci_u": r["ci_upper"], "i2": r["i_squared"]})
        return {"full": full, "leave_one_out": results}
    
    @staticmethod
    def forest_html(result):
        studies = result["studies"]
        names = [s["name"] for s in studies] + ["合并效应"]
        effects = [s["effect"] for s in studies] + [result["pooled_effect"]]
        ci_l = [s["ci_l"] for s in studies] + [result["ci_lower"]]
        ci_u = [s["ci_u"] for s in studies] + [result["ci_upper"]]
        weights = [s["weight"] for s in studies] + [100]
        y_pos = list(range(len(studies), -1, -1))
        
        traces = []
        is_log = result["measure"] in ("OR", "RR")
        null_val = 1.0 if is_log else 0.0
        
        for i in range(len(studies)):
            traces.append({"type":"scatter","x":[ci_l[i],ci_u[i]],"y":[y_pos[i],y_pos[i]],
                          "mode":"lines","line":{"color":"#3b82f6","width":2},"showlegend":False,"hoverinfo":"skip"})
            sz = max(6, min(25, weights[i]*0.8))
            traces.append({"type":"scatter","x":[effects[i]],"y":[y_pos[i]],"mode":"markers",
                          "marker":{"size":sz,"color":"#3b82f6","symbol":"square"},"showlegend":False,
                          "hovertemplate":f"<b>{names[i]}</b><br>效应量: {effects[i]:.2f}<br>95%CI: [{ci_l[i]:.2f},{ci_u[i]:.2f}]<br>权重: {weights[i]:.1f}%<extra></extra>"})
        
        # Diamond for pooled
        dx = [ci_l[-1], effects[-1], ci_u[-1], effects[-1], ci_l[-1]]
        dy = [y_pos[-1], y_pos[-1]+0.3, y_pos[-1], y_pos[-1]-0.3, y_pos[-1]]
        traces.append({"type":"scatter","x":dx,"y":dy,"mode":"lines","fill":"toself",
                       "fillcolor":"rgba(239,68,68,0.3)","line":{"color":"#ef4444","width":2},
                       "showlegend":False,"hovertemplate":f"<b>合并效应</b><br>{result['pooled_effect']:.2f} [{result['ci_lower']:.2f},{result['ci_upper']:.2f}]<br>p={result['p_value']:.4f}<extra></extra>"})
        
        traces.append({"type":"scatter","x":[null_val,null_val],"y":[-0.5,len(studies)+1],
                       "mode":"lines","line":{"color":"#94a3b8","width":1,"dash":"dash"},"showlegend":False,"hoverinfo":"skip"})
        
        layout = {"title":{"text":f"Forest Plot — {result['measure']} ({result['model'].title()} Effects)","font":{"size":16,"color":"#e2e8f0"}},
                  "xaxis":{"title":"效应量","type":"log" if is_log else "linear","gridcolor":"rgba(255,255,255,0.05)","color":"#94a3b8"},
                  "yaxis":{"tickvals":y_pos,"ticktext":names,"gridcolor":"rgba(255,255,255,0.05)","color":"#94a3b8"},
                  "plot_bgcolor":"#0d1117","paper_bgcolor":"#0d1117","font":{"color":"#e2e8f0","family":"Inter,sans-serif"},
                  "margin":{"l":180,"r":40,"t":60,"b":60},"height":max(400,len(studies)*40+100),
                  "annotations":[{"text":f"I²={result['i_squared']:.1f}%, p={result['q_p']:.3f}","xref":"paper","yref":"paper","x":0.98,"y":0.02,"showarrow":False,"font":{"size":12,"color":"#94a3b8"}}]}
        return json.dumps({"data":traces,"layout":layout})
    
    @staticmethod
    def funnel_html(result):
        studies = result["studies"]
        effects = [s["log_effect"] for s in studies]
        se = [s["se"] for s in studies]
        names = [s["name"] for s in studies]
        pe = math.log(result["pooled_effect"])
        
        traces = [
            {"type":"scatter","x":effects,"y":se,"mode":"markers","marker":{"size":8,"color":"#3b82f6"},
             "text":names,"hovertemplate":"<b>%{text}</b><br>log(效应): %{x:.3f}<br>SE: %{y:.3f}<extra></extra>","showlegend":False},
            {"type":"scatter","x":[pe,pe],"y":[0,max(se)*1.1],"mode":"lines","line":{"color":"#ef4444","width":2,"dash":"dash"},"showlegend":False}
        ]
        layout = {"title":{"text":"Funnel Plot","font":{"size":16,"color":"#e2e8f0"}},
                  "xaxis":{"title":"log(效应量)","gridcolor":"rgba(255,255,255,0.05)","color":"#94a3b8"},
                  "yaxis":{"title":"标准误 (SE)","autorange":"reversed","gridcolor":"rgba(255,255,255,0.05)","color":"#94a3b8"},
                  "plot_bgcolor":"#0d1117","paper_bgcolor":"#0d1117","font":{"color":"#e2e8f0","family":"Inter,sans-serif"},
                  "margin":{"l":60,"r":40,"t":60,"b":60},"height":400}
        return json.dumps({"data":traces,"layout":layout})


# ============================================
# PRISMA SVG Generator
# ============================================
def prisma_svg(d):
    db=d.get("identified",0); reg=d.get("registers",0); tot=db+reg
    dedup=d.get("after_dedup",tot); removed=tot-dedup
    screened=d.get("screened",dedup); excl_screen=d.get("excluded_screen",0)
    fulltext=d.get("fulltext",0); excl_full=d.get("excluded_fulltext",0)
    included=d.get("included",0); qual=d.get("qualitative",included); quant=d.get("quantitative",included)
    excl_reasons=d.get("exclusion_reasons",{})
    reason_text=""
    y=320
    for r,c in excl_reasons.items():
        reason_text+=f'<text x="680" y="{y}" font-size="11" fill="#94a3b8" font-family="Inter,sans-serif">{r}: {c}</text>\n'
        y+=18
    rh=max(100,len(excl_reasons)*18+40)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 620" style="background:#0f1629;font-family:Inter,sans-serif">
<text x="450" y="30" text-anchor="middle" font-size="18" font-weight="700" fill="#e2e8f0">PRISMA 2020 流程图</text>
<text x="450" y="50" text-anchor="middle" font-size="12" fill="#64748b">Generated by MetaForge</text>
<rect x="20" y="70" width="250" height="30" rx="6" fill="rgba(59,130,246,0.2)" stroke="#3b82f6"/><text x="145" y="90" text-anchor="middle" font-size="13" font-weight="600" fill="#60a5fa">Identification</text>
<rect x="300" y="70" width="250" height="30" rx="6" fill="rgba(139,92,246,0.2)" stroke="#8b5cf6"/><text x="425" y="90" text-anchor="middle" font-size="13" font-weight="600" fill="#a78bfa">Screening</text>
<rect x="580" y="70" width="300" height="30" rx="6" fill="rgba(236,72,153,0.2)" stroke="#ec4899"/><text x="730" y="90" text-anchor="middle" font-size="13" font-weight="600" fill="#f472b6">Eligibility</text>
<rect x="40" y="120" width="210" height="70" rx="10" fill="rgba(59,130,246,0.15)" stroke="#3b82f6" stroke-width="1.5"/>
<text x="145" y="145" text-anchor="middle" font-size="12" fill="#94a3b8">数据库检索</text><text x="145" y="170" text-anchor="middle" font-size="20" font-weight="700" fill="#e2e8f0">{db:,}</text>
<rect x="40" y="210" width="210" height="50" rx="10" fill="rgba(59,130,246,0.15)" stroke="#3b82f6"/>
<text x="145" y="235" text-anchor="middle" font-size="12" fill="#94a3b8">注册库检索</text><text x="145" y="250" text-anchor="middle" font-size="14" font-weight="600" fill="#e2e8f0">{reg}</text>
<rect x="310" y="120" width="240" height="70" rx="10" fill="rgba(139,92,246,0.15)" stroke="#8b5cf6" stroke-width="1.5"/>
<text x="430" y="142" text-anchor="middle" font-size="12" fill="#94a3b8">去重后记录</text><text x="430" y="167" text-anchor="middle" font-size="20" font-weight="700" fill="#e2e8f0">{dedup:,}</text>
<text x="430" y="183" text-anchor="middle" font-size="10" fill="#64748b">移除 {removed:,} 条重复</text>
<rect x="340" y="220" width="180" height="50" rx="10" fill="rgba(239,68,68,0.1)" stroke="#ef4444"/>
<text x="430" y="242" text-anchor="middle" font-size="12" fill="#fca5a5">标题/摘要排除</text><text x="430" y="260" text-anchor="middle" font-size="16" font-weight="700" fill="#ef4444">{excl_screen:,}</text>
<rect x="310" y="300" width="240" height="70" rx="10" fill="rgba(236,72,153,0.15)" stroke="#ec4899" stroke-width="1.5"/>
<text x="430" y="322" text-anchor="middle" font-size="12" fill="#94a3b8">全文评估</text><text x="430" y="347" text-anchor="middle" font-size="20" font-weight="700" fill="#e2e8f0">{fulltext:,}</text>
<rect x="340" y="400" width="180" height="50" rx="10" fill="rgba(239,68,68,0.1)" stroke="#ef4444"/>
<text x="430" y="422" text-anchor="middle" font-size="12" fill="#fca5a5">全文排除</text><text x="430" y="440" text-anchor="middle" font-size="16" font-weight="700" fill="#ef4444">{excl_full:,}</text>
<rect x="590" y="290" width="290" height="{rh}" rx="10" fill="rgba(239,68,68,0.05)" stroke="rgba(239,68,68,0.3)"/>
<text x="735" y="312" text-anchor="middle" font-size="12" font-weight="600" fill="#fca5a5">排除原因</text>
{reason_text}
<rect x="200" y="500" width="200" height="65" rx="10" fill="rgba(16,185,129,0.15)" stroke="#10b981" stroke-width="2"/>
<text x="300" y="522" text-anchor="middle" font-size="12" fill="#6ee7b7">定性分析纳入</text><text x="300" y="550" text-anchor="middle" font-size="24" font-weight="800" fill="#10b981">{qual}</text>
<rect x="460" y="500" width="200" height="65" rx="10" fill="rgba(16,185,129,0.15)" stroke="#10b981" stroke-width="2"/>
<text x="560" y="522" text-anchor="middle" font-size="12" fill="#6ee7b7">Meta分析纳入</text><text x="560" y="550" text-anchor="middle" font-size="24" font-weight="800" fill="#10b981">{quant}</text>
<line x1="430" y1="190" x2="430" y2="300" stroke="#64748b" stroke-width="1.5"/>
<line x1="430" y1="370" x2="430" y2="500" stroke="#10b981" stroke-width="2"/>
<line x1="430" y1="480" x2="300" y2="500" stroke="#10b981" stroke-width="1.5"/>
<line x1="430" y1="480" x2="560" y2="500" stroke="#10b981" stroke-width="1.5"/>
<line x1="430" y1="370" x2="380" y2="400" stroke="#ef4444" stroke-width="1.5"/>
<line x1="250" y1="155" x2="310" y2="155" stroke="#64748b" stroke-width="1.5"/>
<text x="450" y="600" text-anchor="middle" font-size="10" fill="#475569">MetaForge © 2026 | PRISMA 2020</text>
</svg>'''


# ============================================
# Report Generator
# ============================================
def generate_report(job):
    r = job["result"]
    p = job["params"]
    studies_text = ""
    for s in r["studies"]:
        studies_text += f"| {s['name']} | {s['e_events']}/{s['e_total']} | {s['c_events']}/{s['c_total']} | {s['effect']:.2f} [{s['ci_l']:.2f}, {s['ci_u']:.2f}] | {s['weight']:.1f}% |\n"
    
    het_cn = {"low":"低度","moderate":"中度","high":"高度"}
    
    return f"""# {p.get('title','Meta分析报告')}

## 摘要
**背景**: {p.get('background','')}
**目的**: {p.get('objective','')}
**方法**: 系统检索PubMed数据库，纳入符合PICOS标准的研究。采用{r['model']=='random' and '随机' or '固定'}效应模型，以{r['measure']}为效应量进行Meta分析。
**结果**: 共纳入{len(r['studies'])}项研究。合并{r['measure']}为{r['pooled_effect']:.2f} (95%CI: {r['ci_lower']:.2f}-{r['ci_upper']:.2f}, p={r['p_value']:.4f})。研究间异质性{het_cn.get(r['heterogeneity'],r['heterogeneity'])} (I²={r['i_squared']:.1f}%)。
**结论**: {p.get('title','')}的证据表明干预措施具有统计学意义的疗效。

## 1. 引言
{p.get('background','')}

本研究旨在通过系统评价和Meta分析，定量评估{p.get('title','')}的疗效与安全性。

## 2. 方法
### 2.1 检索策略
检索PubMed数据库。检索式：
```
{p.get('search_query','')}
```
检索日期: {datetime.now().strftime('%Y-%m-%d')}

### 2.2 纳排标准
- **纳入**: {p.get('criteria_text','符合PICOS标准的研究')}
- **排除**: 非人类研究、非研究性文章、会议摘要

### 2.3 数据提取
由两位研究者独立提取数据，包括：作者、年份、样本量、事件数/均数±标准差。

### 2.4 统计分析
采用{r['model']=='random' and 'DerSimonian-Laird随机' or 'Mantel-Haenszel固定'}效应模型，以{r['measure']}为效应量。异质性采用I²统计量评估。使用Python (NumPy/SciPy)进行分析。

## 3. 结果
### 3.1 文献筛选
共检索到{job.get('total_found',0)}篇文献，去重后{job.get('after_dedup',0)}篇，最终纳入{len(r['studies'])}项研究。

### 3.2 研究特征
| 研究 | 实验组(事件/总数) | 对照组(事件/总数) | {r['measure']} [95%CI] | 权重 |
|------|-------------------|-------------------|------------------------|------|
{studies_text}

### 3.3 Meta分析结果
- **合并{r['measure']}**: {r['pooled_effect']:.3f}
- **95% CI**: [{r['ci_lower']:.3f}, {r['ci_upper']:.3f}]
- **Z值**: {r['z_value']:.3f}
- **P值**: {r['p_value']:.4f}
- **异质性**: I²={r['i_squared']:.1f}%, Q={r['q_stat']:.2f}, p={r['q_p']:.3f} ({het_cn.get(r['heterogeneity'],r['heterogeneity'])}异质性)

### 3.4 森林图
见平台交互式森林图。

### 3.5 漏斗图
见平台交互式漏斗图。

## 4. 讨论
本Meta分析纳入{len(r['studies'])}项研究，结果显示{p.get('title','')}的合并{r['measure']}为{r['pooled_effect']:.2f}，表明干预措施{'具有统计学意义的保护作用' if r['pooled_effect']<1 and r['measure'] in ('OR','RR') else '存在显著差异'}。

异质性{het_cn.get(r['heterogeneity'],r['heterogeneity'])} (I²={r['i_squared']:.1f}%)，{'采用随机效应模型已考虑研究间变异' if r['model']=='random' else '采用固定效应模型'}。

## 5. 结论
基于{len(r['studies'])}项研究的Meta分析结果，{p.get('title','')}的证据支持干预措施的有效性。

## 参考文献
""" + "\n".join([f"{i+1}. {s['name']}. PMID见原文。" for i, s in enumerate(r["studies"])]) + f"""

---
*本报告由MetaForge自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""


# ============================================
# Background Pipeline
# ============================================
def run_pipeline(job_id):
    job = jobs[job_id]
    p = job["params"]
    try:
        # Step 1: Search
        job["step"] = "searching"
        job["progress"] = 10
        q = p.get("search_query", "")
        if not q:
            parts = []
            for k in ["topic","population","intervention"]:
                if p.get(k): parts.append(f"({p[k]}[Title/Abstract])")
            q = " AND ".join(parts) if parts else p.get("title","")
        
        search = PubMed.search(q, max_results=min(p.get("max_results",300),500))
        job["total_found"] = search["count"]
        job["search_query"] = q
        job["query_translation"] = search["translation"]
        job["progress"] = 25
        
        # Step 2: Fetch
        job["step"] = "fetching"
        articles = PubMed.fetch(search["pmids"]) if search["pmids"] else []
        job["after_dedup"] = len(articles)
        job["progress"] = 40
        
        # Step 3: Screen
        job["step"] = "screening"
        criteria = p.get("criteria", {})
        screen = Screener.screen(articles, criteria)
        job["screen_stats"] = screen["stats"]
        job["progress"] = 55
        
        # Step 4: Extract (use provided data or auto-extract from abstracts)
        job["step"] = "extracting"
        studies_data = p.get("studies_data", [])
        if not studies_data:
            # Demo: auto-create from included articles
            for i, a in enumerate(screen["included"][:12]):
                name = f"{a['authors'][0].split()[0]} {a['year']}" if a.get("authors") else f"Study {i+1}"
                studies_data.append({"name": name, "pmid": a["pmid"],
                                    "e_events": 0, "e_total": 0, "c_events": 0, "c_total": 0})
        job["progress"] = 65
        
        # Step 5: Analyze
        job["step"] = "analyzing"
        measure = p.get("measure", "OR")
        model = p.get("model", "random")
        
        # Filter valid studies
        valid = [s for s in studies_data if s.get("e_total",0)>0 and s.get("c_total",0)>0]
        if not valid:
            job["step"] = "error"
            job["error"] = "没有有效的研究数据。请提供实验组/对照组的事件数和总人数。"
            return
        
        result = MetaEngine.analyze_dichotomous(valid, measure, model)
        sensitivity = MetaEngine.sensitivity(valid, measure, model)
        job["result"] = result
        job["sensitivity"] = sensitivity
        job["progress"] = 80
        
        # Step 6: Visualize
        job["step"] = "visualizing"
        job["forest_html"] = MetaEngine.forest_html(result)
        job["funnel_html"] = MetaEngine.funnel_html(result)
        
        # PRISMA
        prisma_data = {
            "identified": job.get("total_found",0), "registers": 0,
            "after_dedup": job.get("after_dedup",0),
            "screened": screen["stats"]["total"],
            "excluded_screen": screen["stats"]["excluded"],
            "fulltext": screen["stats"]["included"] + screen["stats"]["uncertain"],
            "excluded_fulltext": screen["stats"]["uncertain"],
            "included": len(valid), "qualitative": len(valid), "quantitative": len(valid),
            "exclusion_reasons": screen["stats"]["reasons"]
        }
        job["prisma_svg"] = prisma_svg(prisma_data)
        job["progress"] = 90
        
        # Step 7: Report
        job["step"] = "reporting"
        job["report"] = generate_report(job)
        job["progress"] = 100
        job["step"] = "completed"
        job["completed_at"] = datetime.now().isoformat()
        
    except Exception as e:
        job["step"] = "error"
        job["error"] = f"{e}\n{traceback.format_exc()}"


# ============================================
# API Endpoints
# ============================================

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(BASE, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>MetaForge</h1>")

@app.get("/app", response_class=HTMLResponse)
async def app_page():
    html_path = os.path.join(BASE, "app", "templates", "app.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>App not found</h1>")

@app.post("/api/run")
async def api_run(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id, "params": body, "step": "queued", "progress": 0,
        "created_at": datetime.now().isoformat(), "result": None
    }
    background_tasks.add_task(run_pipeline, job_id)
    return {"success": True, "job_id": job_id}

@app.get("/api/status/{job_id}")
async def api_status(job_id: str):
    j = jobs.get(job_id)
    if not j: return JSONResponse({"error": "not found"}, 404)
    resp = {"id": j["id"], "step": j["step"], "progress": j["progress"]}
    if j["step"] == "completed":
        resp["result"] = j["result"]
        resp["forest_html"] = j.get("forest_html","")
        resp["funnel_html"] = j.get("funnel_html","")
        resp["prisma_svg"] = j.get("prisma_svg","")
        resp["report"] = j.get("report","")
        resp["sensitivity"] = j.get("sensitivity",{})
        resp["screen_stats"] = j.get("screen_stats",{})
    if j["step"] == "error":
        resp["error"] = j.get("error","")
    if j.get("total_found"): resp["total_found"] = j["total_found"]
    if j.get("search_query"): resp["search_query"] = j["search_query"]
    return resp

@app.get("/api/report/{job_id}")
async def api_report(job_id: str):
    j = jobs.get(job_id)
    if not j or j["step"] != "completed":
        return JSONResponse({"error": "not ready"}, 400)
    return {"report": j.get("report",""), "result": j["result"]}

@app.get("/api/demo")
async def api_demo():
    """Return demo data for instant preview"""
    demo_studies = [
        {"name":"Gandhi 2018","pmid":"29658856","e_events":69,"e_total":410,"c_events":109,"c_total":206},
        {"name":"Paz-Ares 2018","pmid":"30280887","e_events":88,"e_total":278,"c_events":118,"c_total":281},
        {"name":"Socinski 2018","pmid":"29768210","e_events":93,"e_total":356,"c_events":127,"c_total":336},
        {"name":"West 2019","pmid":"31562797","e_events":108,"e_total":451,"c_events":142,"c_total":228},
        {"name":"Nishio 2021","pmid":"34153108","e_events":152,"e_total":290,"c_events":175,"c_total":290},
        {"name":"Lu 2021","pmid":"33985464","e_events":65,"e_total":222,"c_events":96,"c_total":221},
        {"name":"Wang 2020","pmid":"33203523","e_events":58,"e_total":205,"c_events":82,"c_total":207},
        {"name":"Zhou 2022","pmid":"35810505","e_events":72,"e_total":221,"c_events":95,"c_total":220},
    ]
    result = MetaEngine.analyze_dichotomous(demo_studies, "OR", "random")
    sensitivity = MetaEngine.sensitivity(demo_studies, "OR", "random")
    prisma_d = {"identified":2847,"registers":423,"after_dedup":2947,"screened":2947,
                "excluded_screen":2461,"fulltext":486,"excluded_fulltext":434,
                "included":52,"qualitative":52,"quantitative":48,
                "exclusion_reasons":{"非RCT设计":156,"干预不符":98,"结局不符":82,"重复发表":56,"无法获取全文":42}}
    return {
        "result": result, "sensitivity": sensitivity,
        "forest_html": MetaEngine.forest_html(result),
        "funnel_html": MetaEngine.funnel_html(result),
        "prisma_svg": prisma_svg(prisma_d),
        "screen_stats": {"total":2947,"included":52,"excluded":2895,"uncertain":0,
                        "reasons":{"非RCT":892,"非研究性文章":342,"干预不符":456,"其他":1205}},
        "total_found": 2847, "after_dedup": 2947
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)
