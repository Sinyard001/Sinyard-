# -*- coding: utf-8 -*-
"""合同要素自动提取：主体、金额、日期、期限、付款计划等台账字段。"""

from __future__ import annotations

import io
import re

from .clauses import Clause


_PARTY_RE = re.compile(
    r"(?m)^\s*(甲方|乙方|委托方|受托方|采购方|服务方|供方|需方)"
    r"(?:\s*[（(][^）)]*[)）])?\s*[:：]\s*([^\n\r:：]+?)\s*$"
)
_AMOUNT_RE = re.compile(
    r"[^。；\n]{0,50}?"
    r"人民币\s*"
    r"([0-9][0-9,，]*(?:\.\d+)?|"
    r"[壹贰叁肆伍陆柒捌玖拾佰仟万亿零一二三四五六七八九十百千万两]+(?:万|亿)?)"
    r"\s*(元|圆|块)"
    r"[^。；\n]{0,20}"
)
_DATE_RE = re.compile(
    r"(20\d{2})\s*[年./\-]\s*(\d{1,2})\s*[月./\-]\s*(\d{1,2})\s*日?"
)
_DURATION_RE = re.compile(
    r"(?:有效期|服务期|合同期限|合同期|期限)\s*(?:为|自)?\s*"
    r"([0-9]+|[一二三四五六七八九十两]+)\s*(年|个月|月|日|天)"
)
_BLANK_DATE_RE = re.compile(r"[_＿×X]{2,}\s*年\s*[_＿×X]{2,}\s*月\s*[_＿×X]{2,}\s*日")

_CN_DIGITS = {
    "零": 0, "一": 1, "壹": 1, "二": 2, "两": 2, "贰": 2,
    "三": 3, "叁": 3, "四": 4, "肆": 4, "五": 5, "伍": 5,
    "六": 6, "陆": 6, "七": 7, "柒": 7, "八": 8, "捌": 8,
    "九": 9, "玖": 9,
}
_CN_UNITS = {
    "十": 10, "拾": 10, "百": 100, "佰": 100,
    "千": 1000, "仟": 1000, "万": 10000, "萬": 10000,
    "亿": 100000000, "億": 100000000,
}


def chinese_number_to_value(text: str) -> float:
    """把“一百二十万”这类中文数字转成数值。"""
    digits = "".join(ch for ch in text if ch not in _CN_UNITS)
    if digits and all(ch in "零一二三四五六七八九两壹贰叁肆伍陆柒捌玖" for ch in digits):
        return _parse_cn_digits(text)
    cleaned = text.replace(",", "").replace("，", "")
    try:
        return float(cleaned)
    except ValueError:
        return float("nan")


def _parse_cn_digits(text: str) -> float:
    total = 0.0
    section = 0.0
    current = 0.0
    for char in text:
        if char in _CN_DIGITS:
            current = _CN_DIGITS[char]
        elif char in _CN_UNITS:
            unit = _CN_UNITS[char]
            if unit >= 10000:
                section = (section + current) * unit
                total += section
                section = 0.0
                current = 0.0
            else:
                section += (current or 1.0) * unit
                current = 0.0
    return total + section + current


def _extract_amounts(text: str) -> list[dict]:
    amounts = []
    seen = set()
    for match in _AMOUNT_RE.finditer(text):
        raw_number = match.group(1).replace(",", "").replace("，", "")
        unit = match.group(2)
        value = chinese_number_to_value(raw_number)
        if not raw_number or value != value:
            continue
        context = match.group(0).strip()
        if context in seen:
            continue
        seen.add(context)
        amounts.append(
            {
                "value": value,
                "unit": unit,
                "text": context,
                "context": context,
            }
        )
    return amounts


def _classify_date(snippet: str) -> str:
    if re.search(r"签订|签署|签字|签章", snippet):
        return "签订日期"
    if re.search(r"生效", snippet):
        return "生效日期"
    if re.search(r"付款|支付|尾款|发票", snippet):
        return "付款相关日期"
    if re.search(r"交付|验收|上线", snippet):
        return "交付/验收日期"
    if re.search(r"终止|届满|到期", snippet):
        return "到期日期"
    return "合同中出现日期"


def _payment_stage(text: str) -> str:
    for stage in ("预付款", "首付款", "进度款", "尾款", "余款", "质保金", "服务费", "合同款项"):
        if stage in text:
            return stage
    if "支付" in text or "付款" in text:
        return "付款安排"
    return "付款安排"


def _payment_plan(clauses: list[Clause]) -> list[dict]:
    plan = []
    sentences = []
    for clause in clauses:
        if clause.label != "付款条款":
            continue
        sentences.extend(
            part.strip()
            for part in re.split(r"(?<=[。；])|\n", clause.text)
            if part.strip()
        )
    for sentence in sentences:
        if not re.search(r"支付|付款|预付款|尾款|余款|发票|到账|扣款|分期", sentence):
            continue
        if len(sentence) <= 10 or re.match(r"^\s*第[^，。；\n]{0,10}条", sentence):
            continue
        stage = _payment_stage(sentence)
        ratio_match = re.search(r"百分之([0-9零一二三四五六七八九十两]+)|([0-9]{1,3})\s*%", sentence)
        ratio = None
        if ratio_match:
            raw = ratio_match.group(1) or ratio_match.group(2)
            if ratio_match.group(1) and re.search(r"[零一二三四五六七八九十两壹贰叁肆伍陆柒捌玖]", raw):
                ratio = chinese_number_to_value(raw)
            else:
                ratio = float(raw)
            ratio = f"{ratio:g}%"
        deadline = None
        if re.search(r"日内|工作日内|当日|次日", sentence):
            deadline_match = re.search(
                r"([0-9一二三四五六七八九十两]+\s*个?\s*(?:工作日?|日)|当日|次日)", sentence
            )
            deadline = deadline_match.group(1) if deadline_match else "约定期限内"
        elif re.search(r"及时|尽快", sentence):
            deadline = "及时（建议改为明确期限）"
        plan.append(
            {
                "stage": stage,
                "ratio": ratio,
                "deadline": deadline,
                "condition": sentence,
            }
        )
    return plan


def _dispute_method(text: str) -> str:
    if "仲裁委员会" in text or "仲裁院" in text:
        match = re.search(r"提交\s*([^，。；]{0,30}(?:仲裁委员会|仲裁院|仲裁中心))", text)
        return f"仲裁（{match.group(1).strip()}）" if match else "仲裁"
    if "仲裁" in text:
        return "仲裁（未写明机构，存在风险）"
    if "人民法院" in text or "法院" in text:
        match = re.search(r"提交\s*([^，。；]{0,30}(?:人民法院|法院))", text)
        return f"诉讼（{match.group(1).strip()}）" if match else "诉讼"
    return "未约定"


def extract_contract_elements(text: str, clauses: list[Clause] | None = None) -> dict:
    """提取合同台账要素。"""
    clauses = clauses or []

    parties: dict[str, str] = {}
    for match in _PARTY_RE.finditer(text):
        role = match.group(1)
        name = match.group(2).strip()
        if not name or len(name) > 60:
            continue
        if role in ("甲方", "委托方", "采购方", "需方"):
            if not parties.get("甲方"):
                parties["甲方"] = name
        elif role in ("乙方", "受托方", "服务方", "供方"):
            if not parties.get("乙方"):
                parties["乙方"] = name

    amounts = _extract_amounts(text)
    total_amount = None
    for item in amounts:
        if re.search(r"总价|总金额|合同金额|服务费总额|价款总额|总费用", item["context"]):
            if total_amount is None or item["value"] > total_amount["value"]:
                total_amount = item
    if total_amount is None and amounts:
        total_amount = max(amounts, key=lambda item: item["value"])

    dates = []
    for match in _DATE_RE.finditer(text):
        year, month, day = match.groups()
        snippet = text[max(0, match.start() - 12) : min(len(text), match.end() + 6)]
        dates.append(
            {
                "date": f"{year}-{int(month):02d}-{int(day):02d}",
                "label": _classify_date(snippet),
                "snippet": snippet.strip(),
            }
        )

    duration_match = _DURATION_RE.search(text)
    duration = None
    if duration_match:
        raw = duration_match.group(1)
        unit = duration_match.group(2)
        value = chinese_number_to_value(raw)
        duration = {
            "text": f"{raw}{unit}",
            "value": value,
            "unit": unit,
        }
    elif "服务期为十二个月" in text:
        duration = {"text": "十二个月", "value": 12, "unit": "个月"}

    payment_plan = _payment_plan(clauses)
    dispute_clause = next(
        (clause for clause in clauses if clause.label == "争议解决"), None
    )
    breach_clause = next(
        (clause for clause in clauses if clause.label == "违约责任"), None
    )
    confidentiality_clause = next(
        (clause for clause in clauses if clause.label == "保密义务"), None
    )
    ip_clause = next((clause for clause in clauses if clause.label == "知识产权"), None)
    acceptance_clause = next(
        (clause for clause in clauses if clause.label == "交付与验收"), None
    )

    ledger = [
        ["甲方", parties.get("甲方", "未识别")],
        ["乙方", parties.get("乙方", "未识别")],
        [
            "合同金额",
            total_amount["context"] if total_amount else "未识别",
        ],
        [
            "签订日期",
            next((item["date"] for item in dates if item["label"] == "签订日期"), "未识别"),
        ],
        [
            "合同期限",
            duration["text"] if duration else "未识别",
        ],
        [
            "付款安排",
            "；".join(f"{item['stage']}({item['ratio'] or '金额另定'})" for item in payment_plan)
            or "未识别",
        ],
        [
            "争议解决",
            _dispute_method(dispute_clause.text) if dispute_clause else "未约定",
        ],
    ]

    def short_snippet(clause: Clause | None, pattern: str) -> str | None:
        if clause is None:
            return None
        match = re.search(pattern, clause.text)
        return match.group(0).strip() if match else None

    extra_fields = {
        "违约金约定": short_snippet(
            breach_clause,
            r"[^。；\n]{0,80}(?:违约金|赔偿)[^。；\n]{0,40}",
        ),
        "保密期限": short_snippet(
            confidentiality_clause,
            r"[^。；\n]{0,60}保密期限[^。；\n]{0,40}",
        ),
        "知识产权归属": short_snippet(
            ip_clause,
            r"[^。；\n]{0,40}(?:著作权|源代码|知识产权)[^。；\n]{0,50}归[甲乙][^。；\n]{0,10}",
        ),
        "验收安排": short_snippet(
            acceptance_clause,
            r"[^。；\n]{0,40}(?:验收|交付)[^。；\n]{0,60}",
        ),
    }
    ledger.extend([key, value or "未识别"] for key, value in extra_fields.items())

    return {
        "parties": parties,
        "amounts": amounts,
        "total_amount": total_amount,
        "dates": dates,
        "duration": duration,
        "payment_plan": payment_plan,
        "dispute_method": _dispute_method(dispute_clause.text) if dispute_clause else "未约定",
        "blank_sign_date": bool(_BLANK_DATE_RE.search(text)),
        "ledger": ledger,
        "extra_fields": extra_fields,
    }


def render_ledger_csv(entries: list[dict]) -> str:
    """把多个合同的台账行合并成 CSV（带 BOM，方便 Excel 打开）。"""
    output = io.StringIO()
    output.write("\ufeff")
    headers = ["合同名称", "甲方", "乙方", "合同金额", "签订日期", "合同期限", "付款安排", "争议解决"]
    output.write(",".join(_csv_cell(item) for item in headers) + "\n")
    for entry in entries:
        fields = entry.get("ledger", {})
        lookup = dict(fields) if isinstance(fields, list) else fields
        values = [
            entry.get("title", ""),
            _lookup(lookup, "甲方"),
            _lookup(lookup, "乙方"),
            _lookup(lookup, "合同金额"),
            _lookup(lookup, "签订日期"),
            _lookup(lookup, "合同期限"),
            _lookup(lookup, "付款安排"),
            _lookup(lookup, "争议解决"),
        ]
        output.write(",".join(_csv_cell(value) for value in values) + "\n")
    return output.getvalue()


def _lookup(table, key: str) -> str:
    if isinstance(table, dict):
        return str(table.get(key, "") or "")
    for row in table:
        if row and row[0] == key:
            return str(row[1] or "")
    return ""


def _csv_cell(value) -> str:
    text = str(value or "").replace('"', '""')
    if "," in text or '"' in text or "\n" in text:
        return f'"{text}"'
    return text
