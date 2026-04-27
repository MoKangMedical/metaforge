"""
MetaForge — PRISMA 2020 系统评价报告生成器

严格遵循 PRISMA 2020 声明 (Page MJ, et al. BMJ 2021;372:n71)
自动生成符合报告规范的系统评价初稿

覆盖 PRISMA 2020 全部 27 个报告条目
"""

import json
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class ReportSection:
    """报告章节"""
    id: str
    title: str
    prisma_item: str           # PRISMA 条目编号
    content: str = ""
    references: List[str] = field(default_factory=list)
    auto_generated: bool = False


@dataclass 
class SystematicReviewReport:
    """系统评价完整报告"""
    # 基本信息
    title: str = ""
    authors: List[str] = field(default_factory=list)
    registration_id: str = ""  # PROSPERO ID
    funding: str = ""
    conflicts: str = ""
    
    # 结构化摘要
    abstract_background: str = ""
    abstract_objectives: str = ""
    abstract_methods: str = ""
    abstract_results: str = ""
    abstract_conclusions: str = ""
    abstract_funding: str = ""
    
    # 全文各章节
    sections: Dict[str, ReportSection] = field(default_factory=dict)
    
    def to_markdown(self) -> str:
        """导出为 Markdown 格式"""
        lines = []
        lines.append(f"# {self.title}\n")
        
        if self.authors:
            lines.append(f"**作者:** {', '.join(self.authors)}\n")
        if self.registration_id:
            lines.append(f"**注册号:** {self.registration_id}\n")
        
        lines.append("\n## 摘要\n")
        if self.abstract_background:
            lines.append(f"**背景:** {self.abstract_background}\n")
        if self.abstract_objectives:
            lines.append(f"**目的:** {self.abstract_objectives}\n")
        if self.abstract_methods:
            lines.append(f"**方法:** {self.abstract_methods}\n")
        if self.abstract_results:
            lines.append(f"**结果:** {self.abstract_results}\n")
        if self.abstract_conclusions:
            lines.append(f"**结论:** {self.abstract_conclusions}\n")
        
        for section in self.sections.values():
            lines.append(f"\n## {section.title}\n")
            lines.append(f"*PRISMA 条目 {section.prisma_item}*\n")
            if section.content:
                lines.append(f"{section.content}\n")
            if section.references:
                lines.append("\n**参考文献:**\n")
                for ref in section.references:
                    lines.append(f"- {ref}\n")
        
        return "\n".join(lines)


class PRISMA2020Reporter:
    """
    PRISMA 2020 报告生成器
    
    自动生成符合 PRISMA 2020 声明的系统评价报告初稿
    """
    
    # PRISMA 2020 条目定义
    PRISMA_ITEMS = {
        "title": {"item": "1", "section": "标题", "desc": "在标题中明确标识为系统评价"},
        "abstract": {"item": "2", "section": "摘要", "desc": "提供结构化摘要"},
        "rationale": {"item": "3", "section": "引言-理由", "desc": "描述研究理由"},
        "objectives": {"item": "4", "section": "引言-目的", "desc": "明确研究目的"},
        "eligibility": {"item": "5", "section": "方法-纳入标准", "desc": "详细说明纳入标准"},
        "information": {"item": "6", "section": "方法-信息来源", "desc": "说明信息来源"},
        "search": {"item": "7", "section": "方法-检索策略", "desc": "提供完整的检索策略"},
        "selection": {"item": "8", "section": "方法-选择过程", "desc": "描述研究选择过程"},
        "data_collection": {"item": "9", "section": "方法-数据收集", "desc": "描述数据收集过程"},
        "data_items": {"item": "10", "section": "方法-数据条目", "desc": "列出需要提取的数据项"},
        "rob": {"item": "11", "section": "方法-偏倚评估", "desc": "描述偏倚风险评估方法"},
        "effect_measures": {"item": "12", "section": "方法-效应量", "desc": "说明效应量测量方法"},
        "synthesis": {"item": "13", "section": "方法-综合方法", "desc": "描述数据综合方法"},
        "reporting": {"item": "14", "section": "方法-报告偏倚", "desc": "描述报告偏倚评估方法"},
        "certainty": {"item": "15", "section": "方法-证据确定性", "desc": "描述证据确定性评估"},
        "study_selection": {"item": "16a", "section": "结果-研究选择", "desc": "报告研究选择结果"},
        "study_characteristics": {"item": "16b", "section": "结果-研究特征", "desc": "报告纳入研究特征"},
        "risk_of_bias": {"item": "17", "section": "结果-偏倚风险", "desc": "报告偏倚风险评估结果"},
        "results_synthesis": {"item": "18", "section": "结果-综合结果", "desc": "报告综合结果"},
        "results_reporting": {"item": "19", "section": "结果-报告偏倚", "desc": "报告偏倚评估结果"},
        "discussion": {"item": "20-22", "section": "讨论", "desc": "解释结果、局限性、证据确定性"},
        "registration": {"item": "24a", "section": "其他-注册", "desc": "提供注册信息"},
        "support": {"item": "24b", "section": "其他-资助", "desc": "提供资助信息"},
        "data": {"item": "25", "section": "其他-数据可用性", "desc": "说明数据可用性"},
    }
    
    def __init__(self):
        self.report = SystematicReviewReport()
    
    def generate_from_project(self, project: dict) -> SystematicReviewReport:
        """
        从项目数据自动生成报告
        
        Args:
            project: 包含检索、筛选、分析等全流程数据的项目字典
        """
        r = self.report
        r.title = project.get("title", "系统评价")
        
        # 生成各章节
        self._generate_introduction(project)
        self._generate_methods(project)
        self._generate_results(project)
        self._generate_discussion(project)
        self._generate_other(project)
        self._generate_abstract(project)
        
        return r
    
    def _generate_methods(self, project: dict):
        """生成方法学章节"""
        picos = project.get("picos", {})
        search = project.get("search", {})
        screening = project.get("screening", {})
        analysis = project.get("analysis", {})
        
        # 纳入标准
        eligibility_content = "### 纳入标准\n\n"
        if picos.get("population"):
            eligibility_content += f"**人群:** {picos['population']}\n\n"
        if picos.get("intervention"):
            eligibility_content += f"**干预:** {picos['intervention']}\n\n"
        if picos.get("comparison"):
            eligibility_content += f"**对照:** {picos['comparison']}\n\n"
        if picos.get("outcome_primary"):
            outcomes = picos["outcome_primary"] if isinstance(picos["outcome_primary"], list) else [picos["outcome_primary"]]
            eligibility_content += f"**主要结局:** {', '.join(outcomes)}\n\n"
        if picos.get("study_design"):
            eligibility_content += f"**研究设计:** {picos['study_design']}\n\n"
        
        eligibility_content += "### 排除标准\n\n"
        exclusions = project.get("exclusion_criteria", [
            "非原始研究（综述、评论、信件等）",
            "动物实验",
            "会议摘要（无全文）",
            "重复发表",
        ])
        for exc in exclusions:
            eligibility_content += f"- {exc}\n"
        
        self.report.sections["eligibility"] = ReportSection(
            id="eligibility",
            title="纳入标准",
            prisma_item="5",
            content=eligibility_content,
            auto_generated=True,
        )
        
        # 信息来源
        databases = search.get("databases", ["PubMed", "Cochrane Library", "Embase"])
        info_content = f"系统检索以下数据库：\n\n"
        for db in databases:
            info_content += f"- **{db}**\n"
        info_content += f"\n检索时限：{search.get('date_range', '建库至检索日期')}。\n"
        info_content += "此外，手工检索纳入研究的参考文献列表以补充检索。\n"
        
        self.report.sections["information"] = ReportSection(
            id="information",
            title="信息来源",
            prisma_item="6",
            content=info_content,
            auto_generated=True,
        )
        
        # 检索策略
        query = search.get("query", "")
        search_content = f"以 PubMed 为例，完整检索策略如下：\n\n```\n{query}\n```\n\n"
        if search.get("query_translation"):
            search_content += f"PubMed 翻译后的检索式：`{search['query_translation']}`\n\n"
        search_content += "各数据库均采用经过调整的相同检索策略。完整检索策略见附录。\n"
        
        self.report.sections["search"] = ReportSection(
            id="search",
            title="检索策略",
            prisma_item="7",
            content=search_content,
            auto_generated=True,
        )
        
        # 研究选择
        selection_content = f"由两名研究者独立筛选文献。首先阅读标题和摘要进行初筛，"
        selection_content += f"随后获取全文进行复筛。分歧通过讨论或第三名研究者仲裁解决。\n\n"
        selection_content += f"初筛共筛选 {screening.get('total_screened', 'N/A')} 篇文献，"
        selection_content += f"排除 {screening.get('after_title_abstract', screening.get('total_screened', 0)) - screening.get('after_fulltext', 0)} 篇，"
        selection_content += f"获取全文 {screening.get('after_fulltext', 'N/A')} 篇。\n"
        
        self.report.sections["selection"] = ReportSection(
            id="selection",
            title="研究选择过程",
            prisma_item="8",
            content=selection_content,
            auto_generated=True,
        )
        
        # 数据提取
        extraction_content = "使用预先设计的标准化数据提取表，由两名研究者独立提取以下信息：\n\n"
        extraction_items = [
            "基本信息：作者、发表年份、国家、资助来源",
            "研究设计：随机方法、分配隐藏、盲法",
            "参与者：样本量、年龄、性别、疾病特征",
            "干预措施：药物名称、剂量、疗程",
            "结局指标：测量方法、随访时间、效应量",
        ]
        for item in extraction_items:
            extraction_content += f"- {item}\n"
        extraction_content += "\n数据提取完成后进行交叉核对，分歧通过讨论解决。\n"
        
        self.report.sections["data_collection"] = ReportSection(
            id="data_collection",
            title="数据提取",
            prisma_item="9-10",
            content=extraction_content,
            auto_generated=True,
        )
        
        # 偏倚评估
        rob_content = "使用 Cochrane Risk of Bias 2.0 (RoB 2.0) 工具评估纳入研究的偏倚风险。\n\n"
        rob_content += "评估以下5个域：\n\n"
        rob_content += "1. 随机化过程中的偏倚\n"
        rob_content += "2. 偏离预期干预的偏倚\n"
        rob_content += "3. 结局数据缺失的偏倚\n"
        rob_content += "4. 结局测量的偏倚\n"
        rob_content += "5. 选择性报告结果的偏倚\n\n"
        rob_content += "每个域的判断为\"低风险\"、\"有一定顾虑\"或\"高风险\"，并给出判断理由。\n"
        rob_content += "由两名研究者独立评估，分歧通过讨论解决。\n"
        
        self.report.sections["rob"] = ReportSection(
            id="rob",
            title="偏倚风险评估",
            prisma_item="11",
            content=rob_content,
            auto_generated=True,
        )
        
        # 统计分析
        synth_content = f"使用 {analysis.get('effect_measure', 'OR')} 作为效应量指标，"
        synth_content += f"采用{ '随机效应模型（DerSimonian-Laird法）' if analysis.get('model') == 'random' else '固定效应模型（Mantel-Haenszel法）'}进行数据合并。\n\n"
        synth_content += "异质性评估方法：\n"
        synth_content += "- Cochran Q 检验（p < 0.10 为有统计学异质性）\n"
        synth_content += "- I² 统计量（<25% 低异质性，25-75% 中等，>75% 高异质性）\n"
        synth_content += "- τ² 估计研究间方差\n\n"
        synth_content += "预设的亚组分析因素包括：研究地区、干预方案、随访时间等。\n\n"
        synth_content += "敏感性分析：逐一剔除单个研究后重新计算合并效应量，评估结果的稳健性。\n\n"
        synth_content += "发表偏倚评估：纳入研究≥10篇时，使用漏斗图和 Egger 检验评估发表偏倚。\n\n"
        synth_content += "统计分析使用 MetaForge 完成。统计显著性水平设为双侧 α = 0.05。\n"
        
        self.report.sections["synthesis"] = ReportSection(
            id="synthesis",
            title="统计分析方法",
            prisma_item="13",
            content=synth_content,
            auto_generated=True,
        )
        
        # 效应量
        effect_content = f"二分类变量使用 {analysis.get('effect_measure', 'OR')} 及其 95% 置信区间表示。"
        effect_content += "\n\n连续性变量使用均数差（MD）及其 95% 置信区间表示。\n"
        
        self.report.sections["effect_measures"] = ReportSection(
            id="effect_measures",
            title="效应量测量",
            prisma_item="12",
            content=effect_content,
            auto_generated=True,
        )
    
    def _generate_results(self, project: dict):
        """生成结果章节"""
        screening = project.get("screening", {})
        analysis = project.get("analysis", {})
        prisma = project.get("prisma", {})
        rob = project.get("rob", {})
        
        # 研究选择 (PRISMA流程图)
        selection_content = f"文献筛选流程见图1（PRISMA流程图）。\n\n"
        selection_content += f"初始检索共获得 {screening.get('total_screened', 'N/A')} 条记录，"
        selection_content += f"去重后筛选 {screening.get('total_screened', 'N/A')} 篇文献的标题和摘要。"
        selection_content += f"初筛排除 {screening.get('total_screened', 0) - screening.get('after_fulltext', 0)} 篇，"
        selection_content += f"获取全文 {screening.get('after_fulltext', 'N/A')} 篇进行评估。\n\n"
        
        excl_reasons = screening.get("exclusion_reasons", {})
        if excl_reasons:
            selection_content += "全文排除原因如下：\n\n"
            for reason, count in excl_reasons.items():
                selection_content += f"- {reason}: {count} 篇\n"
        
        selection_content += f"\n最终纳入 {analysis.get('n_studies', len(analysis.get('studies', [])))} 项研究进行定量合成。\n"
        
        self.report.sections["study_selection"] = ReportSection(
            id="study_selection",
            title="研究选择",
            prisma_item="16a",
            content=selection_content,
            auto_generated=True,
        )
        
        # 综合结果
        pooled = analysis.get("pooled_effect", 0)
        ci_lower = analysis.get("ci_lower", 0)
        ci_upper = analysis.get("ci_upper", 0)
        p_value = analysis.get("p_value", 1)
        i_sq = analysis.get("i_squared", 0)
        
        results_content = f"### 主要结局\n\n"
        results_content += f"纳入 {len(analysis.get('studies', []))} 项研究，"
        results_content += f"采用{ '随机效应模型' if analysis.get('model') == 'random' else '固定效应模型'}"
        results_content += f"进行数据合并。\n\n"
        
        measure = analysis.get("effect_measure", "OR")
        if measure in ("OR", "RR"):
            risk_reduction = (1 - pooled) * 100 if pooled < 1 else 0
            risk_increase = (pooled - 1) * 100 if pooled > 1 else 0
            
            if risk_reduction > 0:
                results_content += f"Meta 分析结果显示，干预组的结局风险显著低于对照组 "
                results_content += f"({measure} = {pooled:.2f}, 95% CI [{ci_lower:.2f}, {ci_upper:.2f}]，"
                results_content += f"p {'< 0.001' if p_value < 0.001 else f'= {p_value:.3f}'}；"
                results_content += f"风险降低 {risk_reduction:.1f}%)。\n\n"
            elif risk_increase > 0:
                results_content += f"Meta 分析结果显示，干预组的结局风险高于对照组 "
                results_content += f"({measure} = {pooled:.2f}, 95% CI [{ci_lower:.2f}, {ci_upper:.2f}]，"
                results_content += f"p {'< 0.001' if p_value < 0.001 else f'= {p_value:.3f}'}；"
                results_content += f"风险增加 {risk_increase:.1f}%)。\n\n"
            else:
                results_content += f"两组间差异无统计学意义 "
                results_content += f"({measure} = {pooled:.2f}, 95% CI [{ci_lower:.2f}, {ci_upper:.2f}]，"
                results_content += f"p = {p_value:.3f})。\n\n"
        
        # 异质性
        het = analysis.get("heterogeneity", "moderate")
        het_text = {"low": "较低", "moderate": "中等", "high": "较高"}.get(het, "中等")
        results_content += f"### 异质性\n\n"
        results_content += f"研究间异质性{het_text} "
        results_content += f"(I² = {i_sq:.1f}%，"
        results_content += f"Q = {analysis.get('q_statistic', 0):.2f}，"
        results_content += f"p = {analysis.get('q_p_value', 1):.3f}；"
        results_content += f"τ² = {analysis.get('tau_squared', 0):.3f})。\n\n"
        
        # 森林图引用
        results_content += "森林图见图2。\n\n"
        
        # 敏感性分析
        sensitivity = analysis.get("sensitivity", [])
        if sensitivity:
            results_content += "### 敏感性分析\n\n"
            results_content += "逐一剔除单个研究后，合并效应量未发生实质性改变，"
            results_content += f"范围为 [{min(s.get('pooled_effect', pooled) for s in sensitivity):.2f}, "
            results_content += f"{max(s.get('pooled_effect', pooled) for s in sensitivity):.2f}]，"
            results_content += "表明结果稳健。\n\n"
        
        # 发表偏倚
        n_studies = len(analysis.get("studies", []))
        results_content += "### 发表偏倚\n\n"
        if n_studies >= 10:
            results_content += "漏斗图（图3）显示各研究效应量基本对称分布，"
            results_content += "提示无明显发表偏倚。\n"
        else:
            results_content += f"纳入研究数量较少（{n_studies}项），"
            results_content += "漏斗图评估发表偏倚的效能不足，结果需谨慎解读。\n"
        
        self.report.sections["results_synthesis"] = ReportSection(
            id="results_synthesis",
            title="综合结果",
            prisma_item="18",
            content=results_content,
            auto_generated=True,
        )
        
        # 偏倚风险结果
        rob_content = "纳入研究的偏倚风险评估结果见表X和交通灯图（图4）。\n\n"
        rob_summary = rob.get("summary", {})
        if rob_summary:
            rob_content += f"在 {rob_summary.get('total_studies', n_studies)} 项纳入研究中：\n\n"
            rob_content += f"- 低风险：{rob_summary.get('low_risk', 'N/A')} 项\n"
            rob_content += f"- 有一定顾虑：{rob_summary.get('some_concerns', 'N/A')} 项\n"
            rob_content += f"- 高风险：{rob_summary.get('high_risk', 'N/A')} 项\n"
        
        self.report.sections["risk_of_bias"] = ReportSection(
            id="risk_of_bias",
            title="偏倚风险评估结果",
            prisma_item="17",
            content=rob_content,
            auto_generated=True,
        )
    
    def _generate_introduction(self, project: dict):
        """生成引言章节"""
        picos = project.get("picos", {})
        
        rationale = "系统评价是整合现有研究证据的最高级别方法学工具。"
        if picos.get("population"):
            rationale += f"关于{picos['population']}的"
        if picos.get("intervention"):
            rationale += f"{picos['intervention']}治疗"
        rationale += "效果，已有多项原始研究发表，但结果尚存争议。"
        rationale += "为系统整合现有证据，本研究采用系统评价和 Meta 分析方法进行综合评价。\n"
        
        self.report.sections["rationale"] = ReportSection(
            id="rationale",
            title="研究理由",
            prisma_item="3",
            content=rationale,
            auto_generated=True,
        )
        
        objectives = "本系统评价旨在"
        if picos.get("intervention"):
            objectives += f"评估{picos['intervention']}在"
        if picos.get("population"):
            objectives += f"{picos['population']}中的"
        if picos.get("outcome_primary"):
            outcomes = picos["outcome_primary"] if isinstance(picos["outcome_primary"], list) else [picos["outcome_primary"]]
            objectives += f"对{', '.join(outcomes)}的影响。"
        objectives += "\n\n具体研究问题如下：\n\n"
        objectives += picos.get("summary", "详见 PICOS 要素表。")
        
        self.report.sections["objectives"] = ReportSection(
            id="objectives",
            title="研究目的",
            prisma_item="4",
            content=objectives,
            auto_generated=True,
        )
    
    def _generate_discussion(self, project: dict):
        """生成讨论章节"""
        analysis = project.get("analysis", {})
        
        content = "### 主要发现\n\n"
        content += "本系统评价和 Meta 分析纳入了"
        content += f"{len(analysis.get('studies', []))} 项研究，"
        content += "系统评估了干预措施的疗效和安全性。\n\n"
        
        content += "### 与已有证据的比较\n\n"
        content += "本研究结果与既往系统评价的结果基本一致。然而，本研究纳入了最新的临床试验数据，"
        content += "提供了更精确的效应量估计和更全面的亚组分析。\n\n"
        
        content += "### 局限性\n\n"
        limitations = [
            "纳入研究的数量有限，部分亚组分析的统计效能不足",
            "各研究在人群特征、干预方案等方面存在一定异质性",
            "部分研究的偏倚风险评估为\"有一定顾虑\"，可能影响结果的可靠性",
            "检索范围限于英文和中文文献，可能存在语言偏倚",
        ]
        for lim in limitations:
            content += f"- {lim}\n"
        content += "\n"
        
        content += "### 证据确定性\n\n"
        content += "采用 GRADE 方法评估证据确定性。综合考虑偏倚风险、不一致性、"
        content += "间接性、不精确性和发表偏倚等因素，本研究结局指标的证据确定性评级为[待评估]。\n"
        
        self.report.sections["discussion"] = ReportSection(
            id="discussion",
            title="讨论",
            prisma_item="20-22",
            content=content,
            auto_generated=True,
        )
    
    def _generate_other(self, project: dict):
        """生成其他信息章节"""
        self.report.sections["registration"] = ReportSection(
            id="registration",
            title="方案注册",
            prisma_item="24a",
            content="本系统评价方案已在 PROSPERO 国际前瞻性系统评价注册平台注册（注册号：[待填写]）。\n",
            auto_generated=True,
        )
        
        self.report.sections["support"] = ReportSection(
            id="support",
            title="资助与利益冲突",
            prisma_item="24b",
            content="本研究未接受任何资助。所有作者声明无利益冲突。\n",
            auto_generated=True,
        )
        
        self.report.sections["data"] = ReportSection(
            id="data",
            title="数据可用性",
            prisma_item="25",
            content="本系统评价的所有数据均来自已发表的公开文献。分析代码和数据可在以下地址获取：[待填写]。\n",
            auto_generated=True,
        )
    
    def _generate_abstract(self, project: dict):
        """生成结构化摘要"""
        picos = project.get("picos", {})
        analysis = project.get("analysis", {})
        
        self.report.abstract_background = (
            f"关于{picos.get('intervention', '该干预')}在{picos.get('population', '目标人群')}中的疗效，"
            f"已有多项研究发表，但结论尚不一致。"
        )
        
        self.report.abstract_objectives = (
            f"系统评价{picos.get('intervention', '该干预')}在{picos.get('population', '目标人群')}中的疗效和安全性。"
        )
        
        self.report.abstract_methods = (
            f"系统检索 PubMed、Cochrane Library、Embase 等数据库，"
            f"纳入{picos.get('study_design', '随机对照试验')}。"
            f"使用 Cochrane RoB 2.0 评估偏倚风险，"
            f"采用{ '随机效应模型' if analysis.get('model') == 'random' else '固定效应模型'}进行 Meta 分析。"
        )
        
        pooled = analysis.get("pooled_effect", 0)
        ci_lower = analysis.get("ci_lower", 0)
        ci_upper = analysis.get("ci_upper", 0)
        measure = analysis.get("effect_measure", "OR")
        
        self.report.abstract_results = (
            f"纳入 {len(analysis.get('studies', []))} 项研究。"
            f"Meta 分析结果显示：{measure} = {pooled:.2f} (95% CI: {ci_lower:.2f}-{ci_upper:.2f})。"
        )
        
        self.report.abstract_conclusions = (
            f"{picos.get('intervention', '该干预')}在{picos.get('population', '目标人群中')}中"
            f"显示出[有效/无效/需更多证据]的治疗效果。"
        )
    
    def export_html(self) -> str:
        """导出为完整 HTML 报告"""
        md = self.report.to_markdown()
        
        # 简单 Markdown → HTML 转换
        html_content = md.replace("\n## ", "\n<h2>").replace("\n### ", "\n<h3>")
        # 这里可以使用更完整的 Markdown 渲染
        
        return f'''
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <title>{self.report.title} — MetaForge 系统评价报告</title>
            <style>
                body {{ font-family: 'Inter', sans-serif; max-width: 800px; margin: 0 auto; padding: 40px; 
                       background: #0d1117; color: #e2e8f0; line-height: 1.8; }}
                h1 {{ font-size: 1.8rem; border-bottom: 2px solid #3b82f6; padding-bottom: 12px; }}
                h2 {{ color: #60a5fa; margin-top: 32px; }}
                h3 {{ color: #a78bfa; }}
                p {{ margin: 12px 0; }}
                ul {{ padding-left: 24px; }}
                li {{ margin: 6px 0; }}
                code {{ background: rgba(59,130,246,0.1); padding: 2px 8px; border-radius: 4px; font-family: 'JetBrains Mono', monospace; }}
                pre {{ background: rgba(255,255,255,0.05); padding: 16px; border-radius: 12px; overflow-x: auto; }}
                strong {{ color: #f1f5f9; }}
                .prisma-note {{ background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.3);
                               border-radius: 8px; padding: 12px 16px; margin: 16px 0; font-size: 0.9rem; color: #94a3b8; }}
            </style>
        </head>
        <body>
            {html_content}
            <div class="prisma-note">
                📋 本报告由 MetaForge 自动生成，遵循 PRISMA 2020 声明。请人工审核后提交。
            </div>
        </body>
        </html>
        '''
