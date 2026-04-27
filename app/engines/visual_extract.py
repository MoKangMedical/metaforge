"""
MetaForge — PDF 视觉解析引擎

对标 LivingEBM 的「视觉+语义双引擎提取」：
- PDF 表格自动识别与数据提取
- 统计图像（森林图、Kaplan-Meier曲线）坐标取值
- 结局指标智能换算
- 每个数值带回原文证据回链

依赖: pdfplumber (表格), Pillow (图像), 可选: pytesseract (OCR)
"""

import json
import re
import io
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple


@dataclass
class ExtractedTable:
    """从 PDF 提取的表格"""
    page: int = 0
    table_index: int = 0
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    caption: str = ""
    source_ref: str = ""        # 原文引用（Table X）
    
    def to_dict(self) -> dict:
        return {
            "page": self.page,
            "headers": self.headers,
            "rows": self.rows,
            "caption": self.caption,
            "n_rows": len(self.rows),
            "n_cols": len(self.headers),
        }
    
    def find_cell(self, row_keyword: str, col_keyword: str) -> Optional[str]:
        """按行列关键词查找单元格值"""
        row_idx = None
        col_idx = None
        
        for i, row in enumerate(self.rows):
            if any(row_keyword.lower() in str(cell).lower() for cell in row):
                row_idx = i
                break
        
        for j, header in enumerate(self.headers):
            if col_keyword.lower() in header.lower():
                col_idx = j
                break
        
        if row_idx is not None and col_idx is not None:
            return self.rows[row_idx][col_idx]
        return None


@dataclass
class ExtractedStatistic:
    """从表格或文本中提取的统计量"""
    field_name: str = ""
    value: str = ""
    unit: str = ""
    ci_lower: str = ""
    ci_upper: str = ""
    p_value: str = ""
    source: str = ""            # "table" / "text" / "figure"
    source_ref: str = ""        # 具体出处
    confidence: float = 1.0


@dataclass
class FigureDataPoint:
    """从图表中读取的数据点"""
    figure_type: str = ""       # "forest_plot" / "km_curve" / "funnel_plot"
    x_value: float = 0.0
    y_value: float = 0.0
    label: str = ""
    group: str = ""


class PDFVisualEngine:
    """
    PDF 视觉解析引擎
    
    功能：
    1. 表格提取 — 使用 pdfplumber 提取 PDF 中的表格
    2. 统计量解析 — 从表格和文本中提取 OR/HR/RR/CI/P值
    3. 智能换算 — 单位转换、百分比计算等
    """
    
    # 常见统计量的正则模式
    STAT_PATTERNS = {
        "or": [
            r'OR\s*=?\s*([\d.]+)\s*(?:\(|,)?\s*(?:95%?\s*CI)?[:\s]*([\d.]+)\s*[-–—to]+\s*([\d.]+)',
            r'odds\s*ratio\s*=?\s*([\d.]+)',
        ],
        "rr": [
            r'RR\s*=?\s*([\d.]+)\s*(?:\(|,)?\s*(?:95%?\s*CI)?[:\s]*([\d.]+)\s*[-–—to]+\s*([\d.]+)',
            r'risk\s*ratio\s*=?\s*([\d.]+)',
        ],
        "hr": [
            r'HR\s*=?\s*([\d.]+)\s*(?:\(|,)?\s*(?:95%?\s*CI)?[:\s]*([\d.]+)\s*[-–—to]+\s*([\d.]+)',
            r'hazard\s*ratio\s*=?\s*([\d.]+)',
        ],
        "p_value": [
            r'[pP]\s*[<>=]\s*([\d.]+)',
            r'[pP]\s*-?\s*value\s*[<>=]\s*([\d.]+)',
        ],
        "mean_sd": [
            r'([\d.]+)\s*±\s*([\d.]+)',
            r'mean\s*=?\s*([\d.]+)\s*(?:\(|,)?\s*SD\s*=?\s*([\d.]+)',
        ],
        "events_total": [
            r'(\d+)\s*/\s*(\d+)',
            r'(\d+)\s*\((\d+(?:\.\d+)?)%\)',
        ],
    }
    
    def __init__(self):
        self.tables: List[ExtractedTable] = []
        self.statistics: List[ExtractedStatistic] = []
    
    def extract_tables_from_text(self, text: str, page: int = 0) -> List[ExtractedTable]:
        """
        从纯文本中识别表格结构
        
        用于处理已转为文本的 PDF 内容
        """
        tables = []
        lines = text.strip().split('\n')
        
        current_table = None
        table_started = False
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                if current_table and table_started:
                    tables.append(current_table)
                    current_table = None
                    table_started = False
                continue
            
            # 检测表格开始（包含多个制表符或多列分隔）
            if '\t' in line or '  ' in line:
                # 清理分隔
                cells = re.split(r'\t|\s{2,}', line)
                cells = [c.strip() for c in cells if c.strip()]
                
                if len(cells) >= 2:
                    if not table_started:
                        # 新表格 — 第一行作为表头
                        current_table = ExtractedTable(
                            page=page,
                            headers=cells,
                            table_index=len(tables),
                        )
                        table_started = True
                    else:
                        # 数据行
                        if current_table:
                            current_table.rows.append(cells)
        
        # 收尾
        if current_table and table_started:
            tables.append(current_table)
        
        self.tables.extend(tables)
        return tables
    
    def extract_statistics_from_text(self, text: str) -> List[ExtractedStatistic]:
        """从文本中提取统计量"""
        stats = []
        
        for stat_type, patterns in self.STAT_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    groups = match.groups()
                    
                    stat = ExtractedStatistic(
                        field_name=stat_type.upper(),
                        value=groups[0] if groups else "",
                        source="text",
                        source_ref=match.group()[:100],
                    )
                    
                    if stat_type in ("or", "rr", "hr") and len(groups) >= 3:
                        stat.ci_lower = groups[1]
                        stat.ci_upper = groups[2]
                    elif stat_type == "mean_sd" and len(groups) >= 2:
                        stat.field_name = "MEAN (SD)"
                        stat.value = f"{groups[0]} ± {groups[1]}"
                    elif stat_type == "events_total" and len(groups) >= 2:
                        stat.field_name = "EVENTS/TOTAL"
                        stat.value = f"{groups[0]}/{groups[1]}"
                    
                    stats.append(stat)
        
        self.statistics.extend(stats)
        return stats
    
    def parse_table_to_extraction(self, table: ExtractedTable, study_name: str = "") -> dict:
        """
        将提取的表格解析为数据提取格式
        
        自动识别常见的RCT数据表格结构
        """
        result = {
            "study_name": study_name,
            "source": f"Table (page {table.page})",
            "data": {},
            "raw": table.to_dict(),
        }
        
        headers_lower = [h.lower() for h in table.headers]
        
        # 识别列
        col_map = {}
        for j, h in enumerate(headers_lower):
            if any(k in h for k in ["event", "n (%)", "n/%"]):
                col_map["events"] = j
            elif any(k in h for k in ["total", "n", "patient"]):
                col_map["total"] = j
            elif any(k in h for k in ["mean", "average"]):
                col_map["mean"] = j
            elif any(k in h for k in ["sd", "std", "se"]):
                col_map["sd"] = j
            elif any(k in h for k in ["group", "arm", "treatment", "intervention"]):
                col_map["group"] = j
            elif any(k in h for k in ["control", "placebo", "comparator"]):
                col_map["control"] = j
        
        # 提取数据
        for row in table.rows:
            if len(row) < 2:
                continue
            
            # 尝试识别事件数/总人数格式 (e.g., "45/120")
            for cell in row:
                events_match = re.match(r'(\d+)\s*/\s*(\d+)', cell)
                if events_match:
                    result["data"].setdefault("events_total_pairs", []).append({
                        "events": int(events_match.group(1)),
                        "total": int(events_match.group(2)),
                        "source": cell,
                    })
                
                # 均数±标准差格式
                mean_sd_match = re.match(r'([\d.]+)\s*±\s*([\d.]+)', cell)
                if mean_sd_match:
                    result["data"].setdefault("mean_sd_pairs", []).append({
                        "mean": float(mean_sd_match.group(1)),
                        "sd": float(mean_sd_match.group(2)),
                        "source": cell,
                    })
                
                # P值
                p_match = re.match(r'[pP]\s*[<>=]\s*([\d.]+)', cell)
                if p_match:
                    result["data"].setdefault("p_values", []).append({
                        "value": float(p_match.group(1)),
                        "source": cell,
                    })
                
                # OR/HR/RR with CI
                effect_match = re.match(r'(OR|HR|RR)\s*=?\s*([\d.]+)\s*\(?([\d.]+)[-–]([\d.]+)', cell, re.IGNORECASE)
                if effect_match:
                    result["data"].setdefault("effect_sizes", []).append({
                        "type": effect_match.group(1).upper(),
                        "value": float(effect_match.group(2)),
                        "ci_lower": float(effect_match.group(3)),
                        "ci_upper": float(effect_match.group(4)),
                        "source": cell,
                    })
        
        return result
    
    def compute_unit_conversion(self, value: float, from_unit: str, to_unit: str) -> Optional[float]:
        """
        智能单位换算
        
        支持常见医学单位转换
        """
        conversions = {
            ("mg/dl", "mmol/l"): lambda v: v / 18.0182,        # 血糖
            ("mmol/l", "mg/dl"): lambda v: v * 18.0182,
            ("ng/ml", "nmol/l"): lambda v: v * 3.67,            # 维生素D
            ("nmol/l", "ng/ml"): lambda v: v / 3.67,
            ("kg", "lb"): lambda v: v * 2.20462,
            ("lb", "kg"): lambda v: v / 2.20462,
            ("cm", "in"): lambda v: v / 2.54,
            ("in", "cm"): lambda v: v * 2.54,
            ("%", "decimal"): lambda v: v / 100,
            ("decimal", "%"): lambda v: v * 100,
        }
        
        key = (from_unit.lower(), to_unit.lower())
        converter = conversions.get(key)
        if converter:
            return round(converter(value), 4)
        return None
    
    def generate_extraction_report(self) -> dict:
        """生成视觉提取报告"""
        return {
            "tables_extracted": len(self.tables),
            "statistics_extracted": len(self.statistics),
            "tables": [t.to_dict() for t in self.tables],
            "statistics": [
                {
                    "field": s.field_name,
                    "value": s.value,
                    "ci": f"{s.ci_lower}-{s.ci_upper}" if s.ci_lower else "",
                    "source": s.source_ref[:80],
                }
                for s in self.statistics
            ],
        }


# 便捷函数
def extract_pdf_tables(pdf_path: str) -> List[ExtractedTable]:
    """从 PDF 文件提取表格（需要 pdfplumber）"""
    try:
        import pdfplumber
    except ImportError:
        return []
    
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            page_tables = page.extract_tables()
            for idx, table_data in enumerate(page_tables):
                if table_data and len(table_data) > 1:
                    table = ExtractedTable(
                        page=page_num + 1,
                        table_index=idx,
                        headers=table_data[0] if table_data[0] else [],
                        rows=table_data[1:],
                    )
                    tables.append(table)
    return tables


def extract_stats_from_table(table_data: List[List[str]]) -> List[ExtractedStatistic]:
    """从表格数据快速提取统计量"""
    engine = PDFVisualEngine()
    text = "\n".join(["\t".join(row) for row in table_data if row])
    return engine.extract_statistics_from_text(text)
