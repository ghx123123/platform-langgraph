"""教学成果报告导出：Markdown 与 PDF。

针对 workflows 的运行记录结构实现，不复用 teaching/pdf_report_service.py
（后者耦合旧版 TeachingSession/QuizResult 模型，改造量大于重写）。
"""
from __future__ import annotations

import io
import re
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.workflows.models import RunRecord


PHASE_LABELS = {
    "design": "教学设计",
    "teach_knowledge": "教师讲授",
    "student_question": "学生提问",
    "teacher_answer": "教师答疑",
    "supervisor_comment": "督导点评",
    "iteration_complete": "本轮完成",
}
LEVEL_LABELS = {"high": "拓展型", "medium": "进阶型", "low": "基础型"}
EXERCISE_LEVEL_LABELS = {"high": "拓展", "medium": "进阶", "low": "基础"}
_CJK_FONT_CANDIDATES = (
    ("MicrosoftYaHei", r"C:\Windows\Fonts\msyh.ttc"),
    ("SimHei", r"C:\Windows\Fonts\simhei.ttf"),
    ("SimSun", r"C:\Windows\Fonts\simsun.ttc"),
    ("NotoSansCJK", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
)


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name).strip(" .") or "教学成果"
    return cleaned[:80]


def _register_cjk_font() -> str:
    """注册可用的中文字体，失败时回退 Helvetica（中文会显示为方块）。"""
    for name, path in _CJK_FONT_CANDIDATES:
        if name in pdfmetrics.getRegisteredFontNames():
            return name
        try:
            pdfmetrics.registerFont(TTFont(name, path))
            return name
        except Exception:
            continue
    return "Helvetica"


def build_markdown(run: RunRecord, student: bool = False) -> str:
    """完整教学成果报告，含课堂全过程记录。

    student=True 输出学生版学案：不含督导评价与课堂记录，练习隐藏答案。
    """
    teaching = run.teaching_data or {}
    analysis = teaching.get("content_analysis") or {}
    framework = teaching.get("teaching_framework") or {}
    review = run.review or {}
    messages = teaching.get("messages") or []

    lines: list[str] = [f"# {run.objective}教学设计成果", ""]
    lines += [
        "| 项目 | 内容 |",
        "| --- | --- |",
        f"| 课程材料 | {teaching.get('document_name') or '-'} |",
        f"| 教学迭代 | {teaching.get('current_iteration', 0)} / {teaching.get('max_iterations', 0)} 轮 |",
        f"| 综合评分 | {review.get('score', '-')} |",
        f"| 生成模型 | {run.provider} |",
        f"| 生成时间 | {run.updated_at:%Y-%m-%d %H:%M} |",
        "",
    ]
    if run.context:
        lines += ["## 补充教学要求", "", run.context, ""]

    lines += ["## 一、课程内容剖析", ""]
    if analysis.get("summary"):
        lines += [analysis["summary"], ""]
    for title, key in (
        ("教学重点", "key_points"),
        ("学习难点", "difficult_points"),
        ("先备知识", "prerequisites"),
        ("常见误区", "learner_misconceptions"),
    ):
        items = analysis.get(key) or []
        if items:
            lines += [f"### {title}", ""] + [f"{i}. {item}" for i, item in enumerate(items, 1)] + [""]

    lines += ["## 二、教学方案", ""]
    objectives = framework.get("learning_objectives") or []
    if objectives:
        lines += ["### 学习目标", ""] + [f"{i}. {item}" for i, item in enumerate(objectives, 1)] + [""]
    stages = framework.get("stages") or []
    if stages:
        lines += ["### 教学环节", "", "| # | 环节 | 时长 | 活动设计 | 教学意图 |", "| --- | --- | --- | --- | --- |"]
        for index, stage in enumerate(stages, 1):
            activity = str(stage.get("activity", "")).replace("|", "／").replace("\n", " ")
            purpose = str(stage.get("purpose", "")).replace("|", "／").replace("\n", " ")
            lines.append(f"| {index} | {stage.get('name', '')} | {stage.get('minutes', '-')} 分钟 | {activity} | {purpose} |")
        lines.append("")
    for title, key in (("教学策略", "strategies"), ("评价方式", "assessment")):
        items = framework.get(key) or []
        if items:
            lines += [f"### {title}", ""] + [f"- {item}" for item in items] + [""]

    exercises = framework.get("exercises") or []
    if exercises:
        lines += ["### 课堂练习", ""]
        for index, exercise in enumerate(exercises, 1):
            level = EXERCISE_LEVEL_LABELS.get(exercise.get("level", ""), "")
            lines += [f"{index}. 【{level or '练习'}】{exercise.get('question', '')}", ""]
            if not student:
                lines += [f"   - 答案：{exercise.get('answer', '')}", ""]
        lines += [""]

    if not student:
        lines += ["## 三、督导评价", ""]
    if review:
        lines += [f"**综合评分：{review.get('score', '-')} 分**", ""]
        dimensions = review.get("dimensions") or {}
        if dimensions:
            lines += ["| 评价维度 | 得分 |", "| --- | --- |"]
            lines += [f"| {name} | {score} |" for name, score in dimensions.items()]
            lines.append("")
        for title, key in (("教学亮点", "strengths"), ("主要不足", "weaknesses"), ("改进建议", "suggestions")):
            items = review.get(key) or []
            if items:
                lines += [f"### {title}", ""] + [f"{i}. {item}" for i, item in enumerate(items, 1)] + [""]
        if review.get("next_focus"):
            lines += ["### 下一轮重点", "", review["next_focus"], ""]
    else:
        lines += ["_本次运行未生成督导评价。_", ""]

    if not student:
        lines += ["## 四、课堂全过程记录", ""]
        if messages:
            current = None
            for message in messages:
                iteration = message.get("iteration", 0)
                if iteration != current:
                    current = iteration
                    lines += [f"### {'教学准备' if iteration == 0 else f'第 {iteration} 轮教学'}", ""]
                level = LEVEL_LABELS.get(message.get("level") or "", "")
                label = f"{message.get('agent_name', '')}{f'（{level}）' if level else ''}"
                lines += [f"**{label}** · {PHASE_LABELS.get(message.get('phase', ''), message.get('phase', ''))}", "", message.get("content", ""), "", "---", ""]
        else:
            lines += ["_暂无课堂记录。_", ""]

    return "\n".join(lines)


def build_pdf(run: RunRecord, student: bool = False) -> bytes:
    """生成 A4 教学成果报告。以结构化排版为主，不逐字转译 Markdown。

    student=True 输出学生版学案：不含督导评价与课堂记录，练习隐藏答案。
    """
    font = _register_cjk_font()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"{run.objective}教学设计成果", author="课程教学智能体平台",
    )
    base = getSampleStyleSheet()
    title_style = ParagraphStyle("CJKTitle", parent=base["Title"], fontName=font, fontSize=19, leading=26, alignment=TA_CENTER)
    h2 = ParagraphStyle("CJKH2", parent=base["Heading2"], fontName=font, fontSize=13, leading=19, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#1f5c46"))
    h3 = ParagraphStyle("CJKH3", parent=base["Heading3"], fontName=font, fontSize=11, leading=16, spaceBefore=8, spaceAfter=4, textColor=colors.HexColor("#33413a"))
    body = ParagraphStyle("CJKBody", parent=base["BodyText"], fontName=font, fontSize=9.5, leading=15.5)
    meta = ParagraphStyle("CJKMeta", parent=body, fontSize=8.5, textColor=colors.HexColor("#6a746e"), alignment=TA_CENTER)

    def escape(text: Any) -> str:
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    teaching = run.teaching_data or {}
    analysis = teaching.get("content_analysis") or {}
    framework = teaching.get("teaching_framework") or {}
    review = run.review or {}
    story: list[Any] = [
        Paragraph(escape(f"{run.objective}教学设计成果"), title_style),
        Spacer(1, 4 * mm),
        Paragraph(
            escape(
                f"课程材料：{teaching.get('document_name') or '-'}　|　"
                f"教学迭代：{teaching.get('current_iteration', 0)}/{teaching.get('max_iterations', 0)} 轮　|　"
                f"综合评分：{review.get('score', '-')}　|　"
                f"生成时间：{run.updated_at:%Y-%m-%d %H:%M}"
            ),
            meta,
        ),
        Spacer(1, 7 * mm),
    ]

    def add_list(title: str, items: list[Any]) -> None:
        if not items:
            return
        story.append(Paragraph(escape(title), h3))
        for index, item in enumerate(items, 1):
            story.append(Paragraph(f"{index}. {escape(item)}", body))
        story.append(Spacer(1, 2 * mm))

    if run.context:
        story.append(Paragraph("补充教学要求", h2))
        story.append(Paragraph(escape(run.context), body))

    story.append(Paragraph("一、课程内容剖析", h2))
    if analysis.get("summary"):
        story.append(Paragraph(escape(analysis["summary"]), body))
        story.append(Spacer(1, 2 * mm))
    add_list("教学重点", analysis.get("key_points") or [])
    add_list("学习难点", analysis.get("difficult_points") or [])
    add_list("先备知识", analysis.get("prerequisites") or [])
    add_list("常见误区", analysis.get("learner_misconceptions") or [])

    story.append(Paragraph("二、教学方案", h2))
    add_list("学习目标", framework.get("learning_objectives") or [])
    stages = framework.get("stages") or []
    if stages:
        story.append(Paragraph("教学环节", h3))
        data = [[Paragraph(f"<b>{escape(text)}</b>", body) for text in ("#", "环节", "时长", "活动设计", "教学意图")]]
        for index, stage in enumerate(stages, 1):
            data.append([
                Paragraph(str(index), body),
                Paragraph(escape(stage.get("name", "")), body),
                Paragraph(f"{stage.get('minutes', '-')} 分", body),
                Paragraph(escape(stage.get("activity", "")), body),
                Paragraph(escape(stage.get("purpose", "")), body),
            ])
        table = Table(data, colWidths=[8 * mm, 26 * mm, 14 * mm, 72 * mm, 50 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f1ec")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d5ce")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story += [table, Spacer(1, 3 * mm)]
    add_list("教学策略", framework.get("strategies") or [])
    add_list("评价方式", framework.get("assessment") or [])
    exercises = framework.get("exercises") or []
    if exercises:
        story.append(Paragraph("课堂练习", h3))
        for index, exercise in enumerate(exercises, 1):
            level = EXERCISE_LEVEL_LABELS.get(exercise.get("level", ""), "")
            label = f"【{level or '练习'}】"
            story.append(Paragraph(f"{index}. {label} {escape(exercise.get('question', ''))}", body))
            if not student and exercise.get("answer"):
                story.append(Paragraph(f"答案：{escape(exercise.get('answer', ''))}", body))
            story.append(Spacer(1, 2 * mm))

    if not student:
        story.append(Paragraph("三、督导评价", h2))
    if review:
        dimensions = review.get("dimensions") or {}
        if dimensions:
            data = [[Paragraph(f"<b>{escape(name)}</b>", body) for name in dimensions]]
            data.append([Paragraph(escape(score), body) for score in dimensions.values()])
            table = Table(data, colWidths=[(170 / max(len(dimensions), 1)) * mm] * len(dimensions))
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f4ecec")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dcc8ca")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]))
            story += [table, Spacer(1, 3 * mm)]
        add_list("教学亮点", review.get("strengths") or [])
        add_list("主要不足", review.get("weaknesses") or [])
        add_list("改进建议", review.get("suggestions") or [])
        if review.get("next_focus"):
            story.append(Paragraph("下一轮重点", h3))
            story.append(Paragraph(escape(review["next_focus"]), body))
    else:
        story.append(Paragraph("本次运行未生成督导评价。", body))

    messages = teaching.get("messages") or []
    if not student and messages:
        story.append(PageBreak())
        story.append(Paragraph("四、课堂全过程记录", h2))
        current = None
        for message in messages:
            iteration = message.get("iteration", 0)
            if iteration != current:
                current = iteration
                story.append(Paragraph(escape("教学准备" if iteration == 0 else f"第 {iteration} 轮教学"), h3))
            level = LEVEL_LABELS.get(message.get("level") or "", "")
            header = f"{message.get('agent_name', '')}{f'（{level}）' if level else ''} · {PHASE_LABELS.get(message.get('phase', ''), '')}"
            story.append(Paragraph(f"<b>{escape(header)}</b>", body))
            for block in str(message.get("content", "")).split("\n"):
                if block.strip():
                    story.append(Paragraph(escape(block.strip()), body))
            story.append(Spacer(1, 2.5 * mm))

    document.build(story)
    return buffer.getvalue()


def build_teacher_draft_pdf(run: RunRecord, markdown: str) -> bytes:
    """Render the teacher-edited Markdown while preserving common teaching-document structures."""
    font = _register_cjk_font()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"{run.objective}教学设计成果",
        author="课程教学智能体平台",
    )
    base = getSampleStyleSheet()
    styles = {
        1: ParagraphStyle("DraftH1", parent=base["Title"], fontName=font, fontSize=19, leading=26, spaceAfter=10),
        2: ParagraphStyle("DraftH2", parent=base["Heading2"], fontName=font, fontSize=13, leading=19, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#1f5c46")),
        3: ParagraphStyle("DraftH3", parent=base["Heading3"], fontName=font, fontSize=11, leading=16, spaceBefore=8, spaceAfter=4, textColor=colors.HexColor("#33413a")),
    }
    body = ParagraphStyle("DraftBody", parent=base["BodyText"], fontName=font, fontSize=9.5, leading=15.5)
    quote = ParagraphStyle("DraftQuote", parent=body, leftIndent=8 * mm, textColor=colors.HexColor("#59645e"))
    code = ParagraphStyle("DraftCode", parent=body, leftIndent=4 * mm, backColor=colors.HexColor("#f2f5f3"), borderPadding=5)

    def escape(text: Any) -> str:
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story: list[Any] = []
    lines = markdown.splitlines()
    index = 0
    in_code = False
    code_lines: list[str] = []
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        if stripped.startswith("```"):
            if in_code:
                story.append(Paragraph("<br/>".join(escape(line) or " " for line in code_lines), code))
                story.append(Spacer(1, 2 * mm))
                code_lines = []
            in_code = not in_code
            index += 1
            continue
        if in_code:
            code_lines.append(raw)
            index += 1
            continue
        if not stripped:
            story.append(Spacer(1, 1.5 * mm))
            index += 1
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading:
            level = len(heading.group(1))
            story.append(Paragraph(escape(heading.group(2)), styles[level]))
            index += 1
            continue
        if stripped.startswith("|") and index + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-+", lines[index + 1]):
            table_lines = [stripped]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in table_lines]
            column_count = max(len(row) for row in rows)
            data = [[Paragraph(escape(cell), body) for cell in row + [""] * (column_count - len(row))] for row in rows]
            table = Table(
                data,
                colWidths=[170 * mm / max(column_count, 1)] * column_count,
                repeatRows=1,
                splitByRow=1,
                splitInRow=1,
            )
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f1ec")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d5ce")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story += [table, Spacer(1, 2 * mm)]
            continue
        list_item = re.match(r"^(?:[-*]|\d+\.)\s+(.+)$", stripped)
        if list_item:
            story.append(Paragraph(f"• {escape(list_item.group(1))}", body))
        elif stripped.startswith(">"):
            story.append(Paragraph(escape(stripped.lstrip("> ")), quote))
        else:
            story.append(Paragraph(escape(stripped), body))
        index += 1
    if code_lines:
        story.append(Paragraph("<br/>".join(escape(line) or " " for line in code_lines), code))
    document.build(story)
    return buffer.getvalue()


def report_filename(run: RunRecord, extension: str, student: bool = False) -> str:
    suffix = "-学生版" if student else ""
    return f"{_safe_filename(run.objective)}-教学设计成果{suffix}.{extension}"
