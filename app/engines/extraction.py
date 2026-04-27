"""
MetaForge — 标准化数据提取引擎

支持结构化数据提取，覆盖RCT核心数据项
每个数据点支持原文溯源回链
"""

import json
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class DataPoint:
    """单个数据提取点"""
    field_name: str          # 字段名
    value: str = ""          # 提取的值
    unit: str = ""           # 单位
    source_text: str = ""    # 原文出处
    page_ref: str = ""       # 页码/表格引用
    confidence: float = 1.0  # 置信度
    verified: bool = False   # 是否经人工核实
    pmid: str = ""           # 来源 PMID


@dataclass
class ExtractedStudy:
    """单个研究的完整提取数据"""
    # 基本信息
    study_id: DataPoint = field(default_factory=lambda: DataPoint("study_id"))
    first_author: DataPoint = field(default_factory=lambda: DataPoint("first_author"))
    publication_year: DataPoint = field(default_factory=lambda: DataPoint("publication_year"))
    journal: DataPoint = field(default_factory=lambda: DataPoint("journal"))
    country: DataPoint = field(default_factory=lambda: DataPoint("country"))
    funding: DataPoint = field(default_factory=lambda: DataPoint("funding"))
    pmid: DataPoint = field(default_factory=lambda: DataPoint("pmid"))
    
    # 研究设计
    study_design: DataPoint = field(default_factory=lambda: DataPoint("study_design"))
    randomization_method: DataPoint = field(default_factory=lambda: DataPoint("randomization_method"))
    allocation_concealment: DataPoint = field(default_factory=lambda: DataPoint("allocation_concealment"))
    blinding: DataPoint = field(default_factory=lambda: DataPoint("blinding"))
    
    # 参与者
    sample_size_total: DataPoint = field(default_factory=lambda: DataPoint("sample_size_total"))
    sample_size_intervention: DataPoint = field(default_factory=lambda: DataPoint("sample_size_intervention"))
    sample_size_control: DataPoint = field(default_factory=lambda: DataPoint("sample_size_control"))
    age_mean: DataPoint = field(default_factory=lambda: DataPoint("age_mean"))
    age_sd: DataPoint = field(default_factory=lambda: DataPoint("age_sd"))
    sex_male_pct: DataPoint = field(default_factory=lambda: DataPoint("sex_male_pct"))
    population_desc: DataPoint = field(default_factory=lambda: DataPoint("population_desc"))
    inclusion_criteria: DataPoint = field(default_factory=lambda: DataPoint("inclusion_criteria"))
    exclusion_criteria: DataPoint = field(default_factory=lambda: DataPoint("exclusion_criteria"))
    
    # 干预措施
    intervention_name: DataPoint = field(default_factory=lambda: DataPoint("intervention_name"))
    intervention_dose: DataPoint = field(default_factory=lambda: DataPoint("intervention_dose"))
    intervention_route: DataPoint = field(default_factory=lambda: DataPoint("intervention_route"))
    intervention_duration: DataPoint = field(default_factory=lambda: DataPoint("intervention_duration"))
    control_name: DataPoint = field(default_factory=lambda: DataPoint("control_name"))
    control_dose: DataPoint = field(default_factory=lambda: DataPoint("control_dose"))
    
    # 结局指标（二分类）
    outcome_name: DataPoint = field(default_factory=lambda: DataPoint("outcome_name"))
    events_intervention: DataPoint = field(default_factory=lambda: DataPoint("events_intervention"))
    total_intervention: DataPoint = field(default_factory=lambda: DataPoint("total_intervention"))
    events_control: DataPoint = field(default_factory=lambda: DataPoint("events_control"))
    total_control: DataPoint = field(default_factory=lambda: DataPoint("total_control"))
    
    # 结局指标（连续性）
    mean_intervention: DataPoint = field(default_factory=lambda: DataPoint("mean_intervention"))
    sd_intervention: DataPoint = field(default_factory=lambda: DataPoint("sd_intervention"))
    n_intervention: DataPoint = field(default_factory=lambda: DataPoint("n_intervention"))
    mean_control: DataPoint = field(default_factory=lambda: DataPoint("mean_control"))
    sd_control: DataPoint = field(default_factory=lambda: DataPoint("sd_control"))
    n_control: DataPoint = field(default_factory=lambda: DataPoint("n_control"))
    
    # 效应量
    effect_measure: DataPoint = field(default_factory=lambda: DataPoint("effect_measure"))
    effect_value: DataPoint = field(default_factory=lambda: DataPoint("effect_value"))
    ci_lower: DataPoint = field(default_factory=lambda: DataPoint("ci_lower"))
    ci_upper: DataPoint = field(default_factory=lambda: DataPoint("ci_upper"))
    p_value: DataPoint = field(default_factory=lambda: DataPoint("p_value"))
    
    # 随访
    followup_duration: DataPoint = field(default_factory=lambda: DataPoint("followup_duration"))
    dropout_rate: DataPoint = field(default_factory=lambda: DataPoint("dropout_rate"))
    
    # 自定义字段
    custom_fields: Dict[str, DataPoint] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        result = {}
        for attr_name in dir(self):
            if attr_name.startswith('_') or attr_name in ('to_dict', 'to_meta_analysis_input', 'custom_fields'):
                continue
            attr = getattr(self, attr_name)
            if isinstance(attr, DataPoint):
                result[attr_name] = {
                    "value": attr.value,
                    "unit": attr.unit,
                    "source": attr.source_text[:100] if attr.source_text else "",
                    "verified": attr.verified,
                    "confidence": attr.confidence,
                }
        result["custom_fields"] = {
            k: {"value": v.value, "source": v.source_text[:100]}
            for k, v in self.custom_fields.items()
        }
        return result
    
    def to_meta_analysis_input(self) -> dict:
        """转换为 Meta 分析引擎输入格式"""
        try:
            e_events = int(self.events_intervention.value) if self.events_intervention.value else 0
            e_total = int(self.total_intervention.value) if self.total_intervention.value else 0
            c_events = int(self.events_control.value) if self.events_control.value else 0
            c_total = int(self.total_control.value) if self.total_control.value else 0
            
            return {
                "name": f"{self.first_author.value} {self.publication_year.value}",
                "pmid": self.pmid.value,
                "e_events": e_events,
                "e_total": e_total,
                "c_events": c_events,
                "c_total": c_total,
                "e_mean": float(self.mean_intervention.value or 0),
                "e_sd": float(self.sd_intervention.value or 0),
                "e_n": int(self.n_intervention.value or 0),
                "c_mean": float(self.mean_control.value or 0),
                "c_sd": float(self.sd_control.value or 0),
                "c_n": int(self.n_control.value or 0),
            }
        except (ValueError, TypeError):
            return {}


# RCT 核心数据提取模板
RCT_EXTRACTION_TEMPLATE = {
    "sections": [
        {
            "name": "基本信息",
            "fields": [
                {"name": "study_id", "label": "研究标识", "type": "text", "required": True},
                {"name": "first_author", "label": "第一作者", "type": "text", "required": True},
                {"name": "publication_year", "label": "发表年份", "type": "number", "required": True},
                {"name": "journal", "label": "期刊", "type": "text"},
                {"name": "country", "label": "国家/地区", "type": "text"},
                {"name": "funding", "label": "资助来源", "type": "text"},
                {"name": "pmid", "label": "PMID", "type": "text"},
            ]
        },
        {
            "name": "研究设计",
            "fields": [
                {"name": "study_design", "label": "研究设计", "type": "select", 
                 "options": ["RCT", "准RCT", "交叉试验", "整群RCT"]},
                {"name": "randomization_method", "label": "随机化方法", "type": "text"},
                {"name": "allocation_concealment", "label": "分配隐藏", "type": "select",
                 "options": ["充分", "不充分", "不清楚"]},
                {"name": "blinding", "label": "盲法", "type": "select",
                 "options": ["双盲", "单盲", "开放", "不清楚"]},
            ]
        },
        {
            "name": "参与者",
            "fields": [
                {"name": "sample_size_total", "label": "总样本量", "type": "number", "required": True},
                {"name": "sample_size_intervention", "label": "干预组人数", "type": "number", "required": True},
                {"name": "sample_size_control", "label": "对照组人数", "type": "number", "required": True},
                {"name": "age_mean", "label": "平均年龄", "type": "number"},
                {"name": "age_sd", "label": "年龄标准差", "type": "number"},
                {"name": "sex_male_pct", "label": "男性比例(%)", "type": "number"},
                {"name": "population_desc", "label": "人群描述", "type": "textarea"},
                {"name": "inclusion_criteria", "label": "纳入标准", "type": "textarea"},
                {"name": "exclusion_criteria", "label": "排除标准", "type": "textarea"},
            ]
        },
        {
            "name": "干预措施",
            "fields": [
                {"name": "intervention_name", "label": "干预名称", "type": "text", "required": True},
                {"name": "intervention_dose", "label": "干预剂量", "type": "text"},
                {"name": "intervention_route", "label": "给药途径", "type": "text"},
                {"name": "intervention_duration", "label": "干预时长", "type": "text"},
                {"name": "control_name", "label": "对照名称", "type": "text", "required": True},
                {"name": "control_dose", "label": "对照剂量", "type": "text"},
            ]
        },
        {
            "name": "结局指标（二分类）",
            "fields": [
                {"name": "outcome_name", "label": "结局名称", "type": "text"},
                {"name": "events_intervention", "label": "干预组事件数", "type": "number"},
                {"name": "total_intervention", "label": "干预组总人数", "type": "number"},
                {"name": "events_control", "label": "对照组事件数", "type": "number"},
                {"name": "total_control", "label": "对照组总人数", "type": "number"},
            ]
        },
        {
            "name": "结局指标（连续性）",
            "fields": [
                {"name": "mean_intervention", "label": "干预组均数", "type": "number"},
                {"name": "sd_intervention", "label": "干预组标准差", "type": "number"},
                {"name": "n_intervention", "label": "干预组人数", "type": "number"},
                {"name": "mean_control", "label": "对照组均数", "type": "number"},
                {"name": "sd_control", "label": "对照组标准差", "type": "number"},
                {"name": "n_control", "label": "对照组人数", "type": "number"},
            ]
        },
        {
            "name": "效应量",
            "fields": [
                {"name": "effect_measure", "label": "效应量类型", "type": "select",
                 "options": ["OR", "RR", "HR", "MD", "SMD"]},
                {"name": "effect_value", "label": "效应量值", "type": "number"},
                {"name": "ci_lower", "label": "95%CI下限", "type": "number"},
                {"name": "ci_upper", "label": "95%CI上限", "type": "number"},
                {"name": "p_value", "label": "P值", "type": "number"},
            ]
        },
        {
            "name": "随访",
            "fields": [
                {"name": "followup_duration", "label": "随访时长", "type": "text"},
                {"name": "dropout_rate", "label": "脱落率(%)", "type": "number"},
            ]
        },
    ]
}


class DataExtractionEngine:
    """数据提取引擎"""
    
    def __init__(self):
        self.extractions: Dict[str, ExtractedStudy] = {}
        self.template = RCT_EXTRACTION_TEMPLATE
    
    def create_extraction(self, study_name: str, pmid: str = "") -> ExtractedStudy:
        """创建新的数据提取记录"""
        study = ExtractedStudy()
        study.study_id.value = study_name
        if pmid:
            study.pmid.value = pmid
        self.extractions[study_name] = study
        return study
    
    def get_template(self) -> dict:
        """获取提取模板"""
        return self.template
    
    def get_all_for_meta_analysis(self) -> list:
        """获取所有研究的 Meta 分析输入数据"""
        return [
            study.to_meta_analysis_input()
            for study in self.extractions.values()
            if study.to_meta_analysis_input()
        ]
    
    def export_csv_data(self) -> list:
        """导出为 CSV 格式数据"""
        rows = []
        for name, study in self.extractions.items():
            row = study.to_dict()
            row["study_name"] = name
            rows.append(row)
        return rows
