# -*- coding: utf-8 -*-
"""合同智能问答：本地语义检索 + 规则化意图识别，基于当前合同回答。"""

from __future__ import annotations

import re
from collections import Counter

from .entities import extract_contract_elements
from .missing import build_gap_suggestions
from .nlp import iter_char_ngrams
from .pipeline import review_contract
from .stances import review_stances


_CATEGORY_TOPICS = {
    "违约责任": ["违约", "违约金", "赔偿", "责任"],
    "争议解决": ["争议", "仲裁", "诉讼", "法院", "管辖"],
    "保密义务": ["保密", "商业秘密", "泄露", "披露"],
    "知识产权": ["知识产权", "著作权", "版权", "代码", "归属"],
    "交付与验收": ["交付", "验收", "交期", "整改"],
    "期限与终止": ["解除", "终止", "续签", "届满"],
    "不可抗力": ["不可抗力", "免责"],
    "通知与送达": ["通知", "送达"],
}

_CN_NUM = "一二三四五六七八九十百千万零〇两"


def _clean(question: str) -> str:
    return re.sub(r"\s+", "", question)


def _clause_by_number(clauses, question: str):
    match = re.search(r"第\s*([0-9" + _CN_NUM + r"]+)\s*条", question)
    if not match:
        return None
    wanted = "第" + match.group(1).strip() + "条"
    return next((clause for clause in clauses if clause.number == wanted), None)


def _topics_in_question(question: str) -> list[tuple[str, int]]:
    cleaned = _clean(question)
    results = []
    for category, keywords in _CATEGORY_TOPICS.items():
        score = sum(1 for keyword in keywords if keyword in cleaned)
        if score:
            results.append((category, score))
    results.sort(key=lambda item: item[1], reverse=True)
    return results


def _short(text: str, limit: int = 160) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + "……"


def _find_relevant(clauses, question: str, limit: int = 3) -> list:
    query_grams = set(iter_char_ngrams(_clean(question)))
    scored = []
    for clause in clauses:
        clause_grams = set(iter_char_ngrams(clause.text))
        overlap = len(query_grams & clause_grams)
        label_score = 0
        if clause.label and any(kw in question for kw in _CATEGORY_TOPICS.get(clause.label, [])):
            label_score = 2
        scored.append((overlap + label_score, clause))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] <= 0:
        return []
    return [
        {
            "number": clause.number,
            "label": clause.label,
            "confidence": clause.confidence,
            "text": _short(clause.text),
            "risks": [finding.title for finding in clause.risks],
        }
        for _, clause in scored[:limit]
        if _[0] > 0
    ]


def _topic_answer(category: str, clauses) -> tuple[str, list]:
    targets = [clause for clause in clauses if clause.label == category]
    if not targets:
        return f"当前合同里未单独识别出“{category}”条款，建议核对正文。", []
    numbers = "、".join(clause.number for clause in targets)
    quotes = "\n\n".join(f"{clause.number}：{_short(clause.text, 300)}" for clause in targets[:2])
    risks = []
    for clause in targets:
        risks.extend(finding.title for finding in clause.risks)
    suffix = ("\n\n需要关注的表述：" + "；".join(dict.fromkeys(risks))) if risks else ""
    answer = f"“{category}”相关内容约定在 {numbers}。\n\n{quotes}{suffix}"
    references = [
        {
            "number": clause.number,
            "label": clause.label,
            "confidence": clause.confidence,
            "text": _short(clause.text),
            "risks": [finding.title for finding in clause.risks],
        }
        for clause in targets[:2]
    ]
    return answer, references


def answer_contract_question(question: str, text: str, title: str = "") -> dict:
    """对当前合同回答一个问题，返回答案与引用条款。"""
    cleaned = _clean(question)
    if not cleaned:
        return {"intent": "invalid", "answer": "请输入问题后再发送。", "references": []}

    review = review_contract(text, title=title or "合同文本")
    elements = extract_contract_elements(text, review.clauses)
    stances = review_stances(review, elements)
    clauses = review.clauses
    findings = review.findings

    clause_match = _clause_by_number(clauses, cleaned)
    if clause_match:
        risks = "；".join(finding.title for finding in clause_match.risks) if clause_match.risks else "暂未发现明显风险"
        answer = (
            f"{clause_match.number}被识别为“{clause_match.label}”条款"
            f"（识别置信度 {clause_match.confidence * 100:.0f}%）。"
            f"\n\n原文摘录：{_short(clause_match.text, 300)}"
            f"\n\n该条款提示：{risks}。"
        )
        return {
            "intent": "clause_lookup",
            "answer": answer,
            "references": [
                {
                    "number": clause_match.number,
                    "label": clause_match.label,
                    "confidence": clause_match.confidence,
                    "text": _short(clause_match.text),
                    "risks": [finding.title for finding in clause_match.risks],
                }
            ],
        }

    parties = elements.get("parties", {})
    total = elements.get("total_amount")
    if re.search(r"谁|名称|主体|哪个公司", cleaned) and re.search(r"甲方|委托方|采购方", cleaned):
        value = parties.get("甲方") or "未识别"
        return {"intent": "party_a", "answer": f"本合同的甲方（委托方）识别为：{value}。", "references": []}
    if re.search(r"谁|名称|主体|哪个公司", cleaned) and re.search(r"乙方|受托方|服务方", cleaned):
        value = parties.get("乙方") or "未识别"
        return {"intent": "party_b", "answer": f"本合同的乙方（受托方/服务方）识别为：{value}。", "references": []}

    if re.search(r"金额|总价|费用|多少钱|价格|价款", cleaned):
        if total:
            answer = f"合同金额识别为：{total['context']}（约折合 {total['value']:,.2f} 元）。"
            ref = _find_relevant(clauses, "付款 金额")
            if ref:
                answer += "\n\n相关条款：" + ref[0]["number"] + "：" + ref[0]["text"]
            return {"intent": "amount", "answer": answer, "references": ref}
        return {
            "intent": "amount",
            "answer": "未从当前合同文本中识别出明确的合同总金额，请核对正文中“人民币……元”的表述。",
            "references": [],
        }

    if re.search(r"付款计划|怎么付|付款安排|如何支付|付款时间|付款节点|什么时候付|尾款|预付款", cleaned):
        plan = elements.get("payment_plan", [])
        if not plan:
            return {
                "intent": "payment_plan",
                "answer": "未识别到付款计划，请确认合同中是否存在“支付/付款”类条款。",
                "references": [],
            }
        lines = []
        for item in plan:
            ratio = f"，占比 {item['ratio']}" if item.get("ratio") else ""
            deadline = f"，时间要求：{item['deadline']}" if item.get("deadline") else ""
            lines.append(f"- {item['stage']}{ratio}：{item['condition']}{deadline}")
        refs = [
            {
                "number": clause.number,
                "label": clause.label,
                "confidence": clause.confidence,
                "text": _short(clause.text),
                "risks": [finding.title for finding in clause.risks],
            }
            for clause in clauses
            if clause.label == "付款条款"
        ]
        return {
            "intent": "payment_plan",
            "answer": "当前合同识别的付款安排如下：\n\n" + "\n".join(lines),
            "references": refs,
        }

    if re.search(r"签订日期|签署日期|签订时间|生效日期|什么时候签|哪天", cleaned):
        dates = elements.get("dates", [])
        sign = next((item for item in dates if item["label"] in ("签订日期", "生效日期")), None)
        if sign:
            return {
                "intent": "date",
                "answer": f"合同{sign['label']}识别为：{sign['date']}。",
                "references": [],
            }
        if elements.get("blank_sign_date"):
            return {
                "intent": "date",
                "answer": "合同签署日期处仍是空白（如“____年__月__日”），签署时请务必填写完整日期。",
                "references": [],
            }
        return {"intent": "date", "answer": "未识别到明确的签署/生效日期。", "references": []}

    if re.search(r"期限|有效期|服务期|多久|多长时间", cleaned):
        duration = elements.get("duration")
        if duration:
            return {
                "intent": "duration",
                "answer": f"合同期限识别为：{duration['text']}（约 {duration['value']:g} {duration['unit']}）。",
                "references": _find_relevant(clauses, "合同期限 有效期"),
            }
        return {"intent": "duration", "answer": "未识别到明确的合同期限。", "references": []}

    if re.search(r"风险|隐患|注意|问题", cleaned):
        if not findings:
            return {
                "intent": "risk",
                "answer": "按当前规则检查，暂未发现明显风险点。建议再由专业人员复核。",
                "references": [],
            }
        high = [item for item in findings if item.severity == "high"]
        medium = [item for item in findings if item.severity == "medium"]
        lines = []
        for severity, items in (("高风险", high), ("中风险", medium)):
            for item in items:
                lines.append(f"- 【{severity}】{item.title}（{item.clause_number or '整份合同'}）")
        lines.append(f"\n综合风险等级：{stances['grading']['level']}（风险指数 {stances['grading']['score']}/100）。")
        return {
            "intent": "risk",
            "answer": "\n".join(lines),
            "references": [
                {
                    "number": item.clause_number,
                    "label": item.clause_label,
                    "text": item.message,
                    "risks": [item.title],
                }
                for item in (high + medium)[:5]
                if item.clause_number
            ],
        }

    if re.search(r"缺失|补漏|补充条款|少了什么|缺什么|遗漏", cleaned):
        gaps = build_gap_suggestions(review, elements)
        if not gaps:
            return {
                "intent": "gaps",
                "answer": "按当前规则未发现明显缺失的核心条款，仍建议结合交易类型核对。",
                "references": [],
            }
        lines = [f"- 【{item['urgency']}】{item['category']}：{item['reason']}" for item in gaps]
        return {
            "intent": "gaps",
            "answer": "建议补齐以下条款：\n\n" + "\n".join(lines) + "\n\n可在“审查报告 → 缺失补漏”中复制拟补文本。",
            "references": [],
        }

    topic_results = _topics_in_question(cleaned)
    if topic_results:
        category = topic_results[0][0]
        answer, references = _topic_answer(category, clauses)
        return {"intent": category, "answer": answer, "references": references}

    relevant = _find_relevant(clauses, cleaned)
    if not relevant:
        return {
            "intent": "general",
            "answer": (
                "这个问题我没有找到很明确的答案。你可以换一种问法，例如：\n"
                "“违约责任怎么约定的？”“付款计划是什么？”“有哪些风险？”\n"
                "或者直接问“第八条是什么条款”。"
            ),
            "references": [],
        }
    ref_text = "\n\n".join(
        f"{item['number']}【{item['label']}】：{item['text']}" for item in relevant
    )
    return {
        "intent": "general",
        "answer": f"结合当前合同文本，最相关的条款如下：\n\n{ref_text}",
        "references": relevant,
    }
