# -*- coding: utf-8 -*-
"""完整审查分析：条款标注 + 风险 + 要素台账 + 多立场 + 缺失补漏。"""

from __future__ import annotations

from .entities import extract_contract_elements
from .missing import build_gap_suggestions
from .pipeline import review_contract
from .report import to_dict
from .stances import review_stances


def analyze_contract(text: str, title: str | None = None, include_text: bool = False) -> dict:
    review = review_contract(text, title=title)
    elements = extract_contract_elements(text, review.clauses)
    stances = review_stances(review, elements)
    gaps = build_gap_suggestions(review, elements)

    result = to_dict(review)
    result["text"] = text if include_text else None
    result["entities"] = elements
    result["stances"] = stances
    result["gap_suggestions"] = gaps
    return result
