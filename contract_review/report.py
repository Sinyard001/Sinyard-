# -*- coding: utf-8 -*-
"""把审查结果导出为 HTML / Markdown / JSON 报告。"""

from __future__ import annotations

import html
import json
from pathlib import Path

from .pipeline import ContractReview
from .training_data import CATEGORY_KEYWORDS


_CATEGORY_COLORS = {
    "定义与解释": ("#7c8ca6", "#eef1f6"),
    "服务内容与范围": ("#2e8b8b", "#e2f3f3"),
    "权利与义务": ("#5b8def", "#e8f0fe"),
    "付款条款": ("#00897b", "#e0f2f1"),
    "交付与验收": ("#5e6ad2", "#e9ebfc"),
    "知识产权": ("#8e5bd0", "#f1e8fc"),
    "保密义务": ("#c2568c", "#fbe7f1"),
    "违约责任": ("#d64545", "#fdeaea"),
    "期限与终止": ("#b8870a", "#fdf3d8"),
    "不可抗力": ("#3f7fbf", "#e4f0fa"),
    "通知与送达": ("#5f9ea0", "#e7f3f3"),
    "争议解决": ("#e0662e", "#fceee6"),
    "一般条款": ("#6b7b6b", "#eaecea"),
}

_SEVERITY_COLORS = {
    "high": ("#c62828", "#fdecea"),
    "medium": ("#e07b00", "#fff4e5"),
    "low": ("#607d8b", "#eceff1"),
}

_SEVERITY_ICON = {"high": "高风险", "medium": "中风险", "low": "提示"}


def _keyword_evidence(label: str, text: str) -> list[str]:
    hits = [word for word in CATEGORY_KEYWORDS.get(label, []) if word in text]
    return hits[:4]


def to_dict(review: ContractReview) -> dict:
    clauses = []
    for clause in review.clauses:
        clauses.append(
            {
                "index": clause.index,
                "number": clause.number,
                "label": clause.label,
                "confidence": clause.confidence,
                "text": clause.text,
                "start": clause.start,
                "end": clause.end,
                "keyword_evidence": _keyword_evidence(clause.label or "", clause.text),
                "risks": [finding.to_dict() for finding in clause.risks],
            }
        )
    return {
        "title": review.title,
        "preamble": review.preamble,
        "summary": review.summary(),
        "clauses": clauses,
        "risks": [finding.to_dict() for finding in review.findings],
    }


def render_json(review: ContractReview) -> str:
    return json.dumps(to_dict(review), ensure_ascii=False, indent=2)


def render_markdown(review: ContractReview) -> str:
    lines = [
        f"# 智能合同审查报告：{review.title}",
        "",
        f"- 识别条款：{len(review.clauses)} 条",
        "- 风险统计：" + "、".join(
            f"{_SEVERITY_ICON[key]} {count} 项"
            for key, count in review.summary()["risks"].items()
            if count > 0
        ),
        "",
        "## 一、条款自动标注",
        "",
    ]
    for clause in review.clauses:
        confidence = f"{clause.confidence * 100:.0f}%" if clause.confidence else "-"
        lines.append(
            f"> **{clause.number}** — 【{clause.label or '未分类'}】"
            f"（置信度 {confidence}）"
        )
        lines.append(">")
        lines.append("> " + clause.text.replace("\n", "\n> "))
        if clause.risks:
            lines.append(">")
            lines.append(
                "> " + "；".join(
                    f"⚠ {finding.title}" for finding in clause.risks
                )
            )
        lines.append("")

    lines += ["## 二、风险清单", ""]
    if not review.findings:
        lines.append("未发现明显风险点。")
    for severity in ("high", "medium", "low"):
        items = [
            finding
            for finding in review.findings
            if finding.severity == severity
        ]
        if not items:
            continue
        lines.append(f"### {_SEVERITY_ICON[severity]}（{len(items)} 项）")
        lines.append("")
        for idx, finding in enumerate(items, start=1):
            position = finding.clause_number or "整份合同"
            lines.append(
                f"{idx}. **{finding.title}**（{position}，"
                f"编号 {finding.code}）"
            )
            lines.append(f"   - 问题：{finding.message}")
            lines.append(f"   - 建议：{finding.suggestion}")
        lines.append("")
    lines.append(
        "---"
        "\n*本报告由 NLP 条款分类器自动生成，风险规则基于常见合同审查要点；"
        "结论仅供专业人员在正式签约前复核，不构成法律意见。*"
    )
    return "\n".join(lines)


def _render_risk_cards(findings) -> str:
    cards = []
    for severity in ("high", "medium", "low"):
        items = [item for item in findings if item.severity == severity]
        if not items:
            continue
        color, background = _SEVERITY_COLORS[severity]
        cards.append(
            f'<section class="risk-group"><h3 style="color:{color}">'
            f'{_SEVERITY_ICON[severity]} · {len(items)} 项</h3>'
        )
        for finding in items:
            position = finding.clause_number or "整份合同"
            cards.append(
                f'<div class="risk-card" style="border-left-color:{color}">'
                f'<div class="risk-head"><strong>{html.escape(finding.title)}</strong>'
                f'<span class="risk-meta">{html.escape(position)} · '
                f'{html.escape(finding.code)}</span></div>'
                f'<p>{html.escape(finding.message)}</p>'
                f'<p class="suggestion">建议：{html.escape(finding.suggestion)}</p>'
                "</div>"
            )
        cards.append("</section>")
    return "\n".join(cards)


def render_html(review: ContractReview) -> str:
    summary = review.summary()
    risk_summary = summary["risks"]

    legend = "".join(
        f'<span class="legend-item"><span class="dot" style="background:{color}">'
        f"</span>{html.escape(category)}</span>"
        for category, (color, _) in _CATEGORY_COLORS.items()
    )

    clause_html: list[str] = []
    for clause in review.clauses:
        label = clause.label or "未分类"
        color, background = _CATEGORY_COLORS.get(label, ("#555", "#eee"))
        confidence = f"{clause.confidence * 100:.0f}%" if clause.confidence else "-"
        evidence = "、".join(_keyword_evidence(label, clause.text)) or "—"

        risk_marks = ""
        if clause.risks:
            marks = []
            for finding in clause.risks:
                severity_color, _ = _SEVERITY_COLORS[finding.severity]
                marks.append(
                    f'<span class="risk-mark" style="color:{severity_color}">'
                    f"⚠ {html.escape(finding.title)}</span>"
                )
            risk_marks = '<div class="clause-risks">' + "".join(marks) + "</div>"

        clause_html.append(
            f'<article class="clause">'
            f'<div class="clause-header">'
            f'<span class="badge" style="background:{background};color:{color};'
            f'border:1px solid {color}">{html.escape(label)}</span>'
            f'<span class="clause-number">{html.escape(clause.number)}</span>'
            f'<span class="confidence">置信度 {confidence}</span>'
            f'<span class="evidence">要点：{html.escape(evidence)}</span>'
            "</div>"
            f'<div class="clause-text">{html.escape(clause.text)}</div>'
            + risk_marks
            + "</article>"
        )

    risk_summary_html = "".join(
        f'<span class="stat" style="color:{_SEVERITY_COLORS[key][0]}">'
        f"{_SEVERITY_ICON[key]} {value} 项</span>"
        for key, value in risk_summary.items()
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>智能合同审查报告</title>
<style>
  body {{ font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
         background:#f5f6f8; margin:0; color:#263238; }}
  .wrap {{ max-width:1000px; margin:0 auto; padding:28px 20px 60px; }}
  header {{ background:#1d2b45; color:#fff; border-radius:14px;
           padding:22px 26px; margin-bottom:20px; }}
  header h1 {{ margin:0 0 8px; font-size:24px; }}
  header p {{ margin:2px 0; opacity:.85; }}
  .stats {{ display:flex; gap:12px; flex-wrap:wrap; margin:16px 0 6px; }}
  .stat {{ background:#fff; border:1px solid #e0e4ea; border-radius:10px;
          padding:8px 14px; font-size:14px; font-weight:600; }}
  h2 {{ font-size:19px; margin:30px 0 10px; }}
  .legend {{ background:#fff; border:1px solid #e0e4ea; border-radius:10px;
            padding:10px 14px; display:flex; flex-wrap:wrap; gap:8px 16px;
            font-size:13px; color:#455a64; }}
  .legend-item {{ display:inline-flex; align-items:center; gap:6px; }}
  .dot {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
  .clause {{ background:#fff; border:1px solid #e0e4ea; border-left:4px solid #b0bec5;
            border-radius:10px; padding:14px 18px; margin:12px 0; }}
  .clause-header {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap;
                   margin-bottom:8px; }}
  .badge {{ padding:3px 12px; border-radius:999px; font-size:13px; font-weight:600; }}
  .clause-number {{ font-weight:700; color:#37474f; }}
  .confidence {{ font-size:12px; color:#78909c; }}
  .evidence {{ font-size:12px; color:#607d8b; background:#f2f5f8;
              padding:3px 8px; border-radius:6px; }}
  .clause-text {{ white-space:pre-wrap; line-height:1.75; font-size:14px; }}
  .clause-risks {{ margin-top:8px; border-top:1px dashed #e0e4ea;
                  padding-top:8px; display:flex; flex-direction:column; gap:4px; }}
  .risk-mark {{ font-size:13px; }}
  .risk-group {{ background:#fff; border:1px solid #e0e4ea; border-radius:12px;
                padding:4px 18px 16px; margin:12px 0; }}
  .risk-group h3 {{ margin:14px 0 8px; }}
  .risk-card {{ border-left:4px solid; background:#fafafa; border-radius:8px;
               padding:10px 14px; margin:8px 0; }}
  .risk-head {{ display:flex; justify-content:space-between; gap:12px;
               flex-wrap:wrap; }}
  .risk-meta {{ font-size:12px; color:#90a4ae; }}
  .risk-card p {{ margin:6px 0 2px; font-size:14px; line-height:1.7; }}
  .suggestion {{ color:#455a64; }}
  .footer {{ color:#90a4ae; font-size:12px; text-align:center; margin-top:26px; }}
</style>
</head>
<body><div class="wrap">
<header>
  <h1>智能合同审查报告</h1>
  <p>合同名称：{html.escape(review.title)}</p>
  <p>识别条款：{len(review.clauses)} 条</p>
</header>
<div class="stats">
  <span class="stat">条款总数 {len(review.clauses)}</span>
  {risk_summary_html}
</div>
<h2>一、条款自动标注</h2>
<div class="legend">{legend}</div>
{"".join(clause_html)}
<h2>二、风险清单</h2>
{_render_risk_cards(review.findings)}
<p class="footer">本报告由 NLP 条款分类器自动生成，风险规则基于常见合同审查要点；
结论仅供专业人员在正式签约前复核，不构成法律意见。</p>
</div></body></html>"""


def export_report(review: ContractReview, output_dir: str | Path, name: str = "合同审查报告"):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    html_path = output / f"{name}.html"
    md_path = output / f"{name}.md"
    json_path = output / f"{name}.json"
    html_path.write_text(render_html(review), encoding="utf-8")
    md_path.write_text(render_markdown(review), encoding="utf-8")
    json_path.write_text(render_json(review), encoding="utf-8")
    return html_path, md_path, json_path
