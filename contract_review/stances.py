# -*- coding: utf-8 -*-
"""风险分级与多立场（甲方 / 乙方 / 中立）规则化审查。"""

from __future__ import annotations

from .pipeline import ContractReview


def grade_findings(findings) -> dict:
    """根据高/中/低风险数量给出综合风险指数与等级。"""
    high = sum(1 for item in findings if item.severity == "high")
    medium = sum(1 for item in findings if item.severity == "medium")
    low = sum(1 for item in findings if item.severity == "low")
    score = min(100, high * 30 + medium * 12 + low * 5)
    if high >= 2 or score >= 50:
        level = "高"
    elif high == 1 or medium >= 2 or score >= 20:
        level = "中"
    else:
        level = "低"
    return {
        "level": level,
        "score": score,
        "high": high,
        "medium": medium,
        "low": low,
        "comment": {
            "高": "建议暂缓签署，先解决高风险条款",
            "中": "建议签署前逐项澄清并修改中风险条款",
            "低": "可签署，但仍建议由专业人员复核",
        }[level],
    }


def _default_stance(code: str, severity: str) -> dict:
    mapping = {
        "ARBITRATION_BODY_MISSING": ("双方", "程序不确定性由双方共同承担"),
        "ARBITRATION_LITIGATION_CONFLICT": ("双方", "程序冲突可能被一方利用拖延争议"),
        "BREACH_REMEDY_VAGUE": ("守约方", "损失举证责任落在守约方"),
        "PAYMENT_DEADLINE_VAGUE": ("收款方", "付款时点模糊对收款方更不利"),
        "CONFIDENTIALITY_NO_SURVIVAL": ("披露方", "秘密信息失去合同保护"),
        "FORCE_MAJEURE_NOTICE_MISSING": ("主张免责方", "未及时通知可能影响免责"),
        "ACCEPTANCE_CRITERIA_MISSING": ("双方", "验收合格与否难以判断"),
        "DELIVERY_DEADLINE_MISSING": ("采购/委托方", "交付迟延难以追责"),
        "BREACH_CLAUSE_MISSING": ("守约方", "缺少索赔依据"),
        "DISPUTE_CLAUSE_MISSING": ("双方", "争议解决成本上升"),
        "PAYMENT_CLAUSE_MISSING": ("收款方", "付款安排缺失"),
        "CONFIDENTIALITY_CLAUSE_MISSING": ("披露方", "商业秘密缺少保护"),
        "IP_CLAUSE_MISSING": ("成果出资方", "知识产权归属不明"),
        "ACCEPTANCE_CLAUSE_MISSING": ("采购/委托方", "交付成果质量缺少验收约束"),
        "TERM_CLAUSE_MISSING": ("双方", "合同期限与退出安排缺失"),
    }
    adverse, explanation = mapping.get(
        code, ("双方", "该问题通常由双方共同面对")
    )
    return {"adverse_party": adverse, "explanation": explanation}


def review_stances(review: ContractReview, elements: dict) -> dict:
    """给出每个风险的多立场标注，并按甲方/乙方视角汇总。"""
    party_a = elements.get("parties", {}).get("甲方", "甲方")
    party_b = elements.get("parties", {}).get("乙方", "乙方")

    matrix = []
    for finding in review.findings:
        stance = _default_stance(finding.code, finding.severity)
        adverse = stance["adverse_party"]
        text = finding.clause_number or ""
        code = finding.code
        if code == "UNBALANCED_TERMINATION" and ("甲方" in finding.message or "委托方" in finding.message):
            adverse = party_b
        elif code == "UNILATERAL_TERMINATION_CHECK":
            adverse = party_b if "甲方" in finding.message or "委托方" in finding.message else party_a
        elif code in ("PAYMENT_DEADLINE_VAGUE", "PAYMENT_CLAUSE_MISSING") and "甲方" in finding.message:
            adverse = party_b
        elif code == "BREACH_REMEDY_VAGUE":
            adverse = "双方"

        def impact_for(target: str) -> str:
            if adverse in (target, "双方"):
                return "需关注"
            if adverse == (party_a if target == party_b else party_b):
                return "相对有利"
            return "需按身份确认"

        matrix.append(
            {
                "code": finding.code,
                "title": finding.title,
                "severity": finding.severity,
                "clause_number": finding.clause_number,
                "adverse_party": adverse,
                "party_a_impact": impact_for(party_a),
                "party_b_impact": impact_for(party_b),
                "explanation": stance["explanation"],
                "suggestion": finding.suggestion,
            }
        )

    def count_for(party_name: str) -> dict:
        items = [
            item for item in matrix
            if item["adverse_party"] in (party_name, "双方")
        ]
        high = sum(1 for item in items if item["severity"] == "high")
        medium = sum(1 for item in items if item["severity"] == "medium")
        low = sum(1 for item in items if item["severity"] == "low")
        return {"concerns": len(items), "high": high, "medium": medium, "low": low}

    grading = grade_findings(review.findings)
    return {
        "party_a": party_a,
        "party_b": party_b,
        "matrix": matrix,
        "a_summary": count_for(party_a),
        "b_summary": count_for(party_b),
        "grading": grading,
        "note": (
            "多立场标注为规则化初筛：同一风险对不同签约立场的影响不同，"
            "最终谈判地位需结合行业惯例综合判断。"
        ),
    }
