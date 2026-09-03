# -*- coding: utf-8 -*-
"""从合同正文中自动切分出逐条条款。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 支持“第一条 / 第 1 条 / 第１条”等常见写法
_CN_NUM = r"一二三四五六七八九十百千万零〇两"
_MARKER_RE = re.compile(
    r"^第\s*([0-9０-９" + _CN_NUM + r"]+)\s*条(?:\s*[:：、.．，,，]?\s*)?(.*)$"
)


@dataclass
class Clause:
    index: int
    number: str          # 原始编号，例如“第三条”
    text: str            # 条款完整文本（含标题行与后续内容）
    start: int           # 在原始文本中的起始偏移
    end: int             # 在原始文本中的结束偏移
    label: str | None = None
    confidence: float | None = None
    risks: list = field(default_factory=list)


def _numbered_lines(text: str):
    """按行切分，同时保留每行在原文中的偏移。"""
    lines = []
    cursor = 0
    for raw_line in text.splitlines(keepends=True):
        content = raw_line.rstrip("\r\n")
        lines.append((content, cursor, cursor + len(raw_line)))
        cursor += len(raw_line)
    if not text.endswith(("\n", "\r")) and cursor < len(text):
        lines.append((text[cursor:], cursor, len(text)))
    return lines


def split_clauses(text: str):
    """将合同文本切分为条款列表（以及未编号的序言部分）。"""
    clauses: list[Clause] = []
    preamble_lines: list[str] = []
    current: dict | None = None

    for content, start, end in _numbered_lines(text):
        stripped = content.strip()
        match = _MARKER_RE.match(stripped) if stripped else None
        if match:
            if current is not None:
                clauses.append(_finalize_clause(current))
            number = "第" + match.group(1).strip() + "条"
            current = {
                "number": number,
                "text": content,
                "start": start,
                "end": end,
                "lines": [content],
            }
        else:
            if current is not None:
                current["text"] += "\n" + content
                current["end"] = end
                current["lines"].append(content)
            else:
                preamble_lines.append(content)

    if current is not None:
        clauses.append(_finalize_clause(current))

    for idx, clause in enumerate(clauses, start=1):
        clause.index = idx

    preamble = "\n".join(preamble_lines).strip()
    return clauses, preamble


def _finalize_clause(data: dict) -> Clause:
    text = data["text"].strip("\r\n")
    return Clause(
        index=0,
        number=data["number"],
        text=text,
        start=data["start"],
        end=data["end"],
    )
