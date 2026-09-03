# -*- coding: utf-8 -*-
"""智能合同审查助手（NLP 条款分类 + 风险识别）。"""

from .classifier import ClauseClassifier
from .clauses import Clause, split_clauses
from .pipeline import ContractReview, review_contract
from .risks import RiskFinding

__version__ = "0.1.0"

__all__ = [
    "Clause",
    "ClauseClassifier",
    "ContractReview",
    "RiskFinding",
    "review_contract",
    "split_clauses",
]
