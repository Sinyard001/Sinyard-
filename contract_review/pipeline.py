# -*- coding: utf-8 -*-
"""合同审查主流程：切分 -> 分类 -> 风险识别。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .classifier import ClauseClassifier
from .clauses import Clause, split_clauses
from .risks import RiskFinding, analyze_clauses


@dataclass
class ContractReview:
    title: str
    preamble: str
    clauses: list[Clause]
    findings: list[RiskFinding] = field(default_factory=list)

    def summary(self) -> dict:
        category_counter: dict[str, int] = {}
        for clause in self.clauses:
            label = clause.label or "未分类"
            category_counter[label] = category_counter.get(label, 0) + 1
        risk_counter = {"high": 0, "medium": 0, "low": 0}
        for finding in self.findings:
            risk_counter[finding.severity] += 1
        return {
            "clause_count": len(self.clauses),
            "categories": category_counter,
            "risks": risk_counter,
        }


_MODEL: ClauseClassifier | None = None


def get_default_classifier() -> ClauseClassifier:
    """懒加载全局分类器，避免重复训练。"""
    global _MODEL
    if _MODEL is None:
        _MODEL = ClauseClassifier()
    return _MODEL


def review_contract(text: str, title: str | None = None) -> ContractReview:
    """审查一份合同正文，返回带标注与风险的完整结果。"""
    clauses, preamble = split_clauses(text)
    model = get_default_classifier()
    for clause in clauses:
        label, confidence = model.classify(clause.text)
        clause.label = label
        clause.confidence = round(confidence, 4)
    findings = analyze_clauses(clauses)
    return ContractReview(
        title=title or "合同文本",
        preamble=preamble,
        clauses=clauses,
        findings=findings,
    )
