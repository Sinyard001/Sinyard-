# -*- coding: utf-8 -*-
"""轻量中文 NLP 工具：文本规范化 + 字符 N-gram 向量化。

中文不像英文那样有天然空格分词，因此这里采用字符 n-gram
（2~4 字滑动片段）作为特征，例如“违约金”会产生“违约”“约金”
等片段，足以支撑条款主题分类，且不依赖外部分词库。
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter


NGRAM_MIN = 2
NGRAM_MAX = 4

_TOKEN_RE = re.compile(r"[a-z\u4e00-\u9fff]+")
_DIGIT_RE = re.compile(r"[0-9０-９]+")


def normalize_text(text: str) -> str:
    """NFKC 统一全角/半角，去除数字（防止模型死记具体金额和日期）。"""
    norm = unicodedata.normalize("NFKC", text).lower()
    return _DIGIT_RE.sub("", norm)


def iter_char_ngrams(text: str):
    """产出文本中的字符 n-gram（不跨标点/数字边界）。"""
    norm = normalize_text(text)
    for token in _TOKEN_RE.findall(norm):
        length = len(token)
        if length < NGRAM_MIN:
            continue
        upper = min(length, NGRAM_MAX)
        for n in range(NGRAM_MIN, upper + 1):
            for i in range(length - n + 1):
                yield token[i : i + n]


class CharNGramVectorizer:
    """把条款文本转成 {特征编号: 词频} 的稀疏表示。"""

    def __init__(self, min_df: int = 2, max_features: int = 30000):
        self.min_df = min_df
        self.max_features = max_features
        self.vocabulary_: dict[str, int] = {}
        self.feature_names_: list[str] = []

    def fit(self, documents: list[str]) -> "CharNGramVectorizer":
        doc_sets: list[set[str]] = []
        for doc in documents:
            grams = list(iter_char_ngrams(doc))
            doc_sets.append(set(grams))

        doc_freq: Counter = Counter()
        for gram_set in doc_sets:
            doc_freq.update(gram_set)

        selected = [
            gram
            for gram, freq in doc_freq.items()
            if freq >= self.min_df
        ]
        selected.sort(key=lambda g: (-doc_freq[g], g))
        selected = selected[: self.max_features]

        self.feature_names_ = selected
        self.vocabulary_ = {gram: idx for idx, gram in enumerate(selected)}
        return self

    def transform(self, documents: list[str]) -> list[dict[int, int]]:
        result = []
        for doc in documents:
            counter: Counter = Counter(iter_char_ngrams(doc))
            row: dict[int, int] = {}
            for gram, count in counter.items():
                feature_id = self.vocabulary_.get(gram)
                if feature_id is not None:
                    row[feature_id] = count
            result.append(row)
        return result

    def transform_one(self, document: str) -> dict[int, int]:
        return self.transform([document])[0]

    def num_features(self) -> int:
        return len(self.feature_names_)
