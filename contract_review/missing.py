# -*- coding: utf-8 -*-
"""缺失条款智能补漏：识别缺项并生成可直接参考的补充条款。"""

from __future__ import annotations

from .pipeline import ContractReview


_TEMPLATES = {
    "违约责任": (
        "高",
        "违约责任是合同履行保障的核心条款，缺失时将难以主张违约金或赔偿。",
        "违约责任：任何一方不履行或不完全履行本合同义务的，应向守约方承担违约责任；"
        "违约方逾期付款或逾期交付的，每逾期一日按合同总金额的万分之五向守约方支付违约金；"
        "违约金不足以弥补守约方实际损失的，违约方还应赔偿差额。",
    ),
    "争议解决": (
        "高",
        "缺失争议解决条款时，纠纷需按法定管辖处理，地点与程序不可控。",
        "争议解决：因本合同引起的争议，双方应先友好协商；协商不成的，任何一方均可向"
        "合同签订地有管辖权的人民法院提起诉讼。争议解决期间，双方应继续履行不涉及争议的条款。",
    ),
    "付款条款": (
        "中",
        "未识别到独立的费用与付款条款，收款与开票安排缺失。",
        "付款条款：本合同总金额为〔合同总金额〕元（含税）。甲方应于收到乙方开具的合法发票后"
        "10 个工作日内支付；双方对付款节点另有约定的，以附件付款计划为准。",
    ),
    "保密义务": (
        "中",
        "合同涉及商业秘密或客户资料，未识别到保密条款。",
        "保密条款：双方对履约中知悉的对方商业秘密与保密信息承担保密义务，未经书面同意不得向"
        "第三方披露；保密义务不因本合同终止而失效，保密期限为合同终止后三年。",
    ),
    "知识产权": (
        "中",
        "合同可能产生代码、文档、设计等智力成果，未明确归属。",
        "知识产权：乙方为履行本合同形成的工作成果，知识产权归甲方所有；乙方保留其既有知识"
        "产权并授予甲方在本合同目的下的使用许可。乙方保证交付成果不侵犯第三方知识产权。",
    ),
    "交付与验收": (
        "中",
        "涉及交付成果或服务，未识别到交付标准与验收安排。",
        "交付与验收：乙方应于〔交付日期〕前完成交付；甲方应在收到交付物后 10 个工作日内按"
        "〔验收标准/附件〕验收，逾期未书面提出异议视为验收合格，不合格的乙方应限期免费整改。",
    ),
    "期限与终止": (
        "中",
        "未识别到合同期限、续签与退出机制。",
        "合同期限：本合同自双方签字盖章之日起生效，期限为〔期限〕；期限届满前 30 日双方可协商"
        "续签。任何一方提前终止的，应提前 30 日书面通知并结清已履行部分的对价。",
    ),
}


def build_gap_suggestions(review: ContractReview, elements: dict) -> list[dict]:
    """依据分类结果生成缺失条款清单与建议文本。"""
    labels = {clause.label for clause in review.clauses}
    missing = [
        {"category": category, "urgency": urgency, "reason": reason, "template": template}
        for category, (urgency, reason, template) in _TEMPLATES.items()
        if category not in labels
    ]
    suggestions = []
    for item in missing:
        text = item["template"]
        text = text.replace("甲方", elements.get("parties", {}).get("甲方", "甲方"))
        text = text.replace("乙方", elements.get("parties", {}).get("乙方", "乙方"))
        suggestions.append(
            {
                "category": item["category"],
                "urgency": item["urgency"],
                "reason": item["reason"],
                "suggested_text": text,
                "note": "以上为建议补丁，请按实际交易调整金额、地点与期限后签署。",
            }
        )
    return suggestions
