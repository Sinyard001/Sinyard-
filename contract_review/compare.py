# -*- coding: utf-8 -*-
"""合同版本比对：按条文编号对齐，输出差异与风险变化。"""

from __future__ import annotations

from difflib import SequenceMatcher

from .clauses import Clause
from .pipeline import review_contract


def _clauses_by_number(clauses: list[Clause]) -> dict[str, Clause]:
    return {clause.number: clause for clause in clauses}


def _diff_chunks(old_text: str, new_text: str) -> list[dict]:
    matcher = SequenceMatcher(None, old_text, new_text, autojunk=False)
    chunks = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        old = old_text[i1:i2]
        new = new_text[j1:j2]
        if tag == "equal":
            if old:
                chunks.append({"type": "equal", "text": old})
        elif tag == "delete":
            chunks.append({"type": "delete", "old": old, "new": "", "text": old})
        elif tag == "insert":
            chunks.append({"type": "insert", "old": "", "new": new, "text": new})
        else:
            chunks.append({"type": "replace", "old": old, "new": new, "text": new or old})
    return chunks


def compare_contracts(
    old_text: str,
    new_text: str,
    old_title: str = "旧版合同",
    new_title: str = "新版合同",
) -> dict:
    """比较两个版本：条款差异 + 风险差异。"""
    old_review = review_contract(old_text, title=old_title)
    new_review = review_contract(new_text, title=new_title)

    old_by_number = _clauses_by_number(old_review.clauses)
    new_by_number = _clauses_by_number(new_review.clauses)
    new_numbers = set(new_by_number)
    old_numbers = set(old_by_number)

    items = []
    added = 0
    removed = 0
    modified = 0
    unchanged = 0

    for old_clause in old_review.clauses:
        new_clause = new_by_number.get(old_clause.number)
        if new_clause is None:
            removed += 1
            items.append(
                {
                    "number": old_clause.number,
                    "kind": "removed",
                    "old_label": old_clause.label,
                    "new_label": None,
                    "old_text": old_clause.text,
                    "new_text": "",
                    "similarity": 0.0,
                    "chunks": [{"type": "delete", "old": old_clause.text, "new": "", "text": old_clause.text}],
                }
            )
            continue
        old_text = old_clause.text
        new_text = new_clause.text
        similarity = SequenceMatcher(None, old_text, new_text, autojunk=False).ratio()
        label_same = old_clause.label == new_clause.label
        if similarity >= 0.98 and label_same:
            unchanged += 1
            kind = "unchanged"
        else:
            modified += 1
            kind = "modified"
        items.append(
            {
                "number": old_clause.number,
                "kind": kind,
                "old_label": old_clause.label,
                "new_label": new_clause.label,
                "old_text": old_text,
                "new_text": new_text,
                "similarity": round(similarity, 4),
                "label_changed": old_clause.label != new_clause.label,
                "chunks": _diff_chunks(old_text, new_text) if kind != "unchanged" else [],
            }
        )

    for new_number in sorted(new_numbers - old_numbers, key=lambda num: new_by_number[num].index):
        added += 1
        new_clause = new_by_number[new_number]
        items.append(
            {
                "number": new_clause.number,
                "kind": "added",
                "old_label": None,
                "new_label": new_clause.label,
                "old_text": "",
                "new_text": new_clause.text,
                "similarity": 0.0,
                "chunks": [{"type": "insert", "old": "", "new": new_clause.text, "text": new_clause.text}],
            }
        )
    rank = {}
    for clause in old_review.clauses:
        rank[clause.number] = clause.index
    for clause in new_review.clauses:
        rank.setdefault(clause.number, clause.index + len(old_review.clauses))
    items.sort(key=lambda item: rank.get(item["number"], 9999))

    old_findings = {finding.code: finding for finding in old_review.findings}
    new_findings = {finding.code: finding for finding in new_review.findings}
    risk_delta = {
        "removed": [
            {"code": code, "title": finding.title}
            for code, finding in old_findings.items()
            if code not in new_findings
        ],
        "added": [
            {"code": code, "title": finding.title}
            for code, finding in new_findings.items()
            if code not in old_findings
        ],
        "kept": [
            {"code": code, "title": finding.title}
            for code, finding in old_findings.items()
            if code in new_findings
        ],
        "old_summary": old_review.summary()["risks"],
        "new_summary": new_review.summary()["risks"],
    }

    return {
        "old_title": old_review.title,
        "new_title": new_review.title,
        "summary": {
            "old_clauses": len(old_review.clauses),
            "new_clauses": len(new_review.clauses),
            "unchanged": unchanged,
            "modified": modified,
            "added": added,
            "removed": removed,
        },
        "items": items,
        "risk_delta": risk_delta,
        "note": "条款按“第X条”编号对齐；若两个版本重排条文编号，请人工复核移位后的对应关系。",
    }
