# -*- coding: utf-8 -*-
"""条款分类器：字符 n-gram 特征 + softmax 逻辑回归。

模型完全使用 NumPy 实现，训练数据来自 contract_review.training_data，
不依赖 sklearn 等外部机器学习库。
"""

from __future__ import annotations

import random

import numpy as np

from .nlp import CharNGramVectorizer
from .training_data import build_training_corpus, categories


class _SoftmaxRegression:
    def __init__(self, n_classes: int, n_features: int, seed: int = 42):
        rng = np.random.default_rng(seed)
        self.n_classes = n_classes
        self.n_features = n_features
        self.weights = rng.normal(0.0, 0.01, size=(n_features, n_classes))
        self.bias = np.zeros(n_classes)

    @staticmethod
    def _row_normalize(matrix: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms

    def fit(
        self,
        X: list[dict[int, int]],
        y: np.ndarray,
        epochs: int = 40,
        batch_size: int = 128,
        learning_rate: float = 2.5,
        l2: float = 0.0001,
        seed: int = 42,
    ) -> "_SoftmaxRegression":
        n_samples = len(X)
        one_hot = np.zeros((n_samples, self.n_classes))
        one_hot[np.arange(n_samples), y] = 1.0

        rng = np.random.default_rng(seed)
        velocity = np.zeros_like(self.weights)

        for _ in range(epochs):
            order = rng.permutation(n_samples)
            for batch_start in range(0, n_samples, batch_size):
                batch_idx = order[batch_start : batch_start + batch_size]
                size = len(batch_idx)
                batch = np.zeros((size, self.n_features), dtype=np.float64)
                for local_i, doc_id in enumerate(batch_idx):
                    for feature_id, count in X[doc_id].items():
                        batch[local_i, feature_id] = count
                batch = self._row_normalize(batch)

                logits = batch @ self.weights + self.bias
                logits -= logits.max(axis=1, keepdims=True)
                probabilities = np.exp(logits)
                probabilities /= probabilities.sum(axis=1, keepdims=True)

                target = one_hot[batch_idx]
                gradient = (batch.T @ (probabilities - target)) / size
                gradient += l2 * self.weights
                velocity = 0.9 * velocity + 0.1 * gradient
                self.weights -= learning_rate * velocity
        return self

    def predict_proba(self, X: list[dict[int, int]]) -> np.ndarray:
        matrix = np.zeros((len(X), self.n_features), dtype=np.float64)
        for row_id, features in enumerate(X):
            for feature_id, count in features.items():
                matrix[row_id, feature_id] = count
        matrix = self._row_normalize(matrix)
        logits = matrix @ self.weights + self.bias
        logits -= logits.max(axis=1, keepdims=True)
        probabilities = np.exp(logits)
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        return probabilities


class ClauseClassifier:
    """面向合同条款的中文分类器。"""

    def __init__(self, corpus=None, random_state: int = 42, fit: bool = True):
        if corpus is None:
            corpus = build_training_corpus()
        self.classes = categories()
        self._class_to_idx = {name: i for i, name in enumerate(self.classes)}
        documents = [text for text, _ in corpus]
        labels = np.array([self._class_to_idx[label] for _, label in corpus])

        self.vectorizer = CharNGramVectorizer().fit(documents)
        X = self.vectorizer.transform(documents)
        self.model = _SoftmaxRegression(
            n_classes=len(self.classes),
            n_features=self.vectorizer.num_features(),
            seed=random_state,
        )
        if fit:
            self.model.fit(X, labels, seed=random_state)

    def classify(self, text: str) -> tuple[str, float]:
        """返回 (最可能的条款类别, 置信度)。"""
        row = self.vectorizer.transform_one(text)
        probabilities = self.model.predict_proba([row])[0]
        best_idx = int(np.argmax(probabilities))
        return self.classes[best_idx], float(probabilities[best_idx])

    def predict_proba_map(self, text: str) -> dict[str, float]:
        row = self.vectorizer.transform_one(text)
        probabilities = self.model.predict_proba([row])[0]
        return {
            name: float(probabilities[idx])
            for idx, name in enumerate(self.classes)
        }

    def evaluate(self, corpus=None, fraction: float = 0.2, seed: int = 7):
        """留出法评测，返回 (准确率, 分类明细)。"""
        if corpus is None:
            corpus = build_training_corpus()
        docs = [text for text, _ in corpus]
        true_labels = [label for _, label in corpus]
        indices = list(range(len(docs)))
        random.Random(seed).shuffle(indices)
        cut = max(1, int(len(indices) * fraction))
        test_idx = indices[:cut]

        test_docs = [docs[i] for i in test_idx]
        test_true = [true_labels[i] for i in test_idx]
        rows = self.vectorizer.transform(test_docs)
        probabilities = self.model.predict_proba(rows)
        predictions = [self.classes[int(np.argmax(p))] for p in probabilities]

        correct = sum(1 for pred, true in zip(predictions, test_true) if pred == true)
        accuracy = correct / len(test_true)
        details = list(zip(test_true, predictions))
        return accuracy, details
