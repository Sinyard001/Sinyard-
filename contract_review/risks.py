# -*- coding: utf-8 -*-
"""条款风险识别：在 NLP 分类结果之上做可解释的风险规则检查。

风险规则覆盖合同审查中常见的重点，例如违约金是否量化、仲裁条款是否
明确、付款期限是否模糊、单方解除权是否失衡等。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .clauses import Clause


@dataclass
class RiskFinding:
    code: str
    severity: str          # high / medium / low
    title: str
    message: str
    suggestion: str
    clause_number: str | None = None
    clause_label: str | None = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "suggestion": self.suggestion,
            "clause_number": self.clause_number,
            "clause_label": self.clause_label,
        }


_AMOUNT_PATTERN = re.compile(
    r"(日万分之|日千分之|万分之|千分之|百分之"
    r"|违约金\s*(?:人民币)?\s*[0-9０-９壹贰叁肆伍陆柒捌玖拾佰仟万亿]+"
    r"|违约金率|违约金标准|违约金计算方式|损失赔偿额)"
)
_SPECIFIC_ARBITRATION = re.compile(
    r"(仲裁委员会|仲裁院|仲裁中心|中国国际经济贸易仲裁委员会"
    r"|贸仲|北仲|上仲|广仲|深国仲|上海仲裁委员会|北京仲裁委员会"
    r"|广州仲裁委员会|深圳国际仲裁院)"
)


def _check_breach(text: str) -> list[RiskFinding]:
    findings = []
    if re.search(r"违约金|赔偿损失|承担违约责任", text) and not _AMOUNT_PATTERN.search(
        text
    ):
        findings.append(
            RiskFinding(
                code="BREACH_REMEDY_VAGUE",
                severity="medium",
                title="违约后果未量化，后续索赔可能难以执行",
                message=(
                    "本条款虽然约定了违约责任，但没有写明违约金数额/比例、"
                    "每日逾期费率或损失计算方式。发生违约时，守约方需要另行"
                    "证明实际损失，容易产生争议并增加维权成本。"
                ),
                suggestion=(
                    "建议补充具体违约金（如按未付款项每日万分之五）或损失计算"
                    "口径，并明确违约金不足时的差额赔偿规则。可参考"
                    "《民法典》第 585 条关于违约金调整的规定。"
                ),
            )
        )
    return findings


def _check_dispute(text: str) -> list[RiskFinding]:
    findings = []
    if "仲裁" in text and not _SPECIFIC_ARBITRATION.search(text):
        findings.append(
            RiskFinding(
                code="ARBITRATION_BODY_MISSING",
                severity="high",
                title="仲裁条款未指定明确的仲裁机构",
                message=(
                    "条款只写了提交仲裁，未写明具体仲裁委员会或仲裁院。"
                    "依据《仲裁法》第 16 条，仲裁协议必须具有选定的仲裁委员会，"
                    "否则可能被认定无效，争议仍需通过诉讼解决。"
                ),
                suggestion=(
                    "建议写明唯一确定的仲裁机构全称，例如“提交上海仲裁委员会”"
                    "并注明适用其现行仲裁规则。"
                ),
            )
        )
    if ("仲裁" in text and "诉讼" in text) or ("仲裁" in text and "法院" in text):
        findings.append(
            RiskFinding(
                code="ARBITRATION_LITIGATION_CONFLICT",
                severity="high",
                title="同一争议条款同时约定仲裁与诉讼",
                message=(
                    "仲裁与诉讼是相互排斥的争议解决方式，同时约定会让条款"
                    "效力产生不确定性，一方可能利用该矛盾拖延程序。"
                ),
                suggestion=(
                    "应删除其中一种方式，只保留诉讼或只保留仲裁，并写明管辖法院"
                    "或仲裁机构。"
                ),
            )
        )
    return findings


def _check_payment(text: str) -> list[RiskFinding]:
    findings = []
    has_vague_word = bool(
        re.search(r"及时|尽快|适时|按约定时间|另行通知|根据进度", text)
    )
    has_explicit_date = bool(
        re.search(r"日内|工作日内|当日|次日|每月|每季度|每半年|每年|月\s*\d|日前", text)
    )
    if has_vague_word and not has_explicit_date:
        findings.append(
            RiskFinding(
                code="PAYMENT_DEADLINE_VAGUE",
                severity="medium",
                title="付款期限表述模糊",
                message=(
                    "条款使用“及时付款”“尽快支付”等表述，没有可计算的具体"
                    "付款起算日与期限，逾期付款的违约责任也难以落地。"
                ),
                suggestion=(
                    "建议改成确定的可计算日期，例如“甲方应于收到发票后 10 个工作"
                    "日内付款”或“于每月 25 日前支付”。"
                ),
            )
        )
    return findings


def _check_delivery(text: str) -> list[RiskFinding]:
    findings = []
    if "验收" in text:
        has_standard = bool(
            re.search(r"验收标准|功能清单|需求规格|验收清单|标准|指标|依据|说明书", text)
        )
        has_window = bool(re.search(r"日内|工作日内|期限|时间", text))
        if not has_standard and not has_window:
            findings.append(
                RiskFinding(
                    code="ACCEPTANCE_CRITERIA_MISSING",
                    severity="medium",
                    title="验收标准与验收期限均不明确",
                    message=(
                        "条款约定了验收但没有明确依据什么标准、在多长期限内"
                        "验收，双方对“是否验收合格”容易各执一词。"
                    ),
                    suggestion=(
                        "建议将验收标准、验收期限、验收异议处理和不合格整改"
                        "机制一并写入条款。"
                    ),
                )
            )
    if re.search(r"交付|交货", text) and not re.search(
        r"日内|工作日内|交付期限|交货期|日期|时间", text
    ):
        findings.append(
            RiskFinding(
                code="DELIVERY_DEADLINE_MISSING",
                severity="medium",
                title="交付期限未约定",
                message="条款未写明交付或交货的具体期限，延误交付难以认定。",
                suggestion="建议明确交付起算点与期限，例如“合同生效后 30 个工作日内”。",
            )
        )
    return findings


def _check_termination(text: str) -> list[RiskFinding]:
    findings = []
    has_unilateral = bool(
        re.search(
            r"(甲方|委托方|采购方).{0,40}(有权|可以|即可).{0,20}(解除|终止)本合同",
            text,
        )
    )
    excludes_other_side = bool(
        re.search(r"(乙方|受托方|服务方).{0,15}不得.{0,15}(解除|终止)", text)
    )
    no_compensation = bool(
        re.search(
            r"(无须|无需|不需|不需要|免于|免除).{0,30}(支付|赔偿|补偿|违约金|对价|承担责任)",
            text,
        )
    )
    if has_unilateral and (excludes_other_side or no_compensation):
        findings.append(
            RiskFinding(
                code="UNBALANCED_TERMINATION",
                severity="high",
                title="单方解除权明显失衡，可能构成不公平条款",
                message=(
                    "条款赋予甲方低成本单方终止权，同时禁止乙方解除合同，"
                    "双方权利义务不对等。若属于格式条款，可能因不合理地"
                    "加重乙方责任而受到《民法典》第 497 条规制。"
                ),
                suggestion=(
                    "建议为甲方单方终止设置合理补偿或已履行部分的对价，并赋予"
                    "乙方在甲方根本违约等情形下同等的解除权。"
                ),
            )
        )
    elif has_unilateral:
        findings.append(
            RiskFinding(
                code="UNILATERAL_TERMINATION_CHECK",
                severity="low",
                title="存在单方终止权，建议核对补偿安排",
                message="条款允许一方提前终止合同，请核对是否约定了通知期与已履行部分的对价结算。",
                suggestion="建议补充提前通知期、结算方式和责任承担规则。",
            )
        )
    return findings


def _check_confidentiality(text: str) -> list[RiskFinding]:
    findings = []
    if re.search(r"保密义务.{0,25}(解除|终止|失效)", text) and not re.search(
        r"保密期限|仍.{0,4}(有效|继续)|本条款.{0,10}(有效|适用)|不因.*终止", text
    ):
        findings.append(
            RiskFinding(
                code="CONFIDENTIALITY_NO_SURVIVAL",
                severity="medium",
                title="保密义务随合同终止而解除，商业秘密可能失去保护",
                message=(
                    "如果保密义务在合同解除或终止后即告失效，接收方在合同结束后"
                    "披露此前掌握的商业秘密将没有合同约束。"
                ),
                suggestion=(
                    "建议增加存续条款，例如“保密义务不因本合同终止而终止，"
                    "保密期限为合同终止后 3 年”。"
                ),
            )
        )
    return findings


def _check_force_majeure(text: str) -> list[RiskFinding]:
    findings = []
    if "不可抗力" in text and not re.search(r"通知|告知|证明", text):
        findings.append(
            RiskFinding(
                code="FORCE_MAJEURE_NOTICE_MISSING",
                severity="low",
                title="不可抗力条款缺少通知与举证要求",
                message="条款未约定受影响方的通知期限和证明义务，可能影响免责主张。",
                suggestion="建议增加“及时书面通知并提供证明”的机制。",
            )
        )
    return findings


def _clause_rule_risks(clause: Clause) -> list[RiskFinding]:
    label = clause.label or ""
    text = clause.text
    all_findings: list[RiskFinding] = []
    checkers = {
        "违约责任": _check_breach,
        "争议解决": _check_dispute,
        "付款条款": _check_payment,
        "交付与验收": _check_delivery,
        "期限与终止": _check_termination,
        "保密义务": _check_confidentiality,
        "不可抗力": _check_force_majeure,
    }
    checker = checkers.get(label)
    if checker is not None:
        all_findings = checker(text)
    for finding in all_findings:
        finding.clause_number = clause.number
        finding.clause_label = label
    return all_findings


_REQUIRED_AFTER_CATEGORIES = {
    "违约责任": {
        "severity": "high",
        "code": "BREACH_CLAUSE_MISSING",
        "title": "未检索到独立的违约责任条款",
        "message": "违约责任是合同核心条款，缺少时将难以主张违约金或赔偿。",
        "suggestion": "建议增加违约责任条款，明确违约金、损失赔偿和补救方式。",
    },
    "争议解决": {
        "severity": "high",
        "code": "DISPUTE_CLAUSE_MISSING",
        "title": "未检索到争议解决条款",
        "message": "缺少争议解决条款时，一旦发生纠纷需按法定管辖确定法院，可能增加成本。",
        "suggestion": "建议约定协商、诉讼或仲裁机制及管辖地点。",
    },
}

_RECOMMENDED_AFTER_CATEGORIES = {
    "付款条款": ("PAYMENT_CLAUSE_MISSING", "建议核对是否缺少付款与发票条款"),
    "保密义务": ("CONFIDENTIALITY_CLAUSE_MISSING", "涉及商业秘密/客户资料时建议增加保密条款"),
    "知识产权": ("IP_CLAUSE_MISSING", "涉及软件、设计等智力成果时建议明确知识产权归属"),
    "交付与验收": ("ACCEPTANCE_CLAUSE_MISSING", "涉及交付/服务时建议核对交付标准与验收机制"),
    "期限与终止": ("TERM_CLAUSE_MISSING", "建议核对合同期限、终止与续签安排"),
}


def contract_level_risks(clauses: list[Clause]) -> list[RiskFinding]:
    """对整份合同做“关键条款缺失”层面的核对。"""
    labels = {clause.label for clause in clauses}
    findings: list[RiskFinding] = []
    for category, info in _REQUIRED_AFTER_CATEGORIES.items():
        if category not in labels:
            findings.append(
                RiskFinding(
                    code=info["code"],
                    severity=info["severity"],
                    title=info["title"],
                    message=info["message"],
                    suggestion=info["suggestion"],
                )
            )
    for category, (code, message) in _RECOMMENDED_AFTER_CATEGORIES.items():
        if category not in labels:
            findings.append(
                RiskFinding(
                    code=code,
                    severity="low",
                    title=f"建议核对：未识别到{category}",
                    message=message,
                    suggestion="如本合同确实不需要该类条款，可忽略本提示。",
                )
            )
    return findings


def analyze_clauses(clauses: list[Clause]) -> list[RiskFinding]:
    """合并条款级与整份合同级风险。"""
    findings: list[RiskFinding] = []
    for clause in clauses:
        clause.risks = _clause_rule_risks(clause)
        findings.extend(clause.risks)
    findings.extend(contract_level_risks(clauses))
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda item: severity_rank.get(item.severity, 3))
    return findings
