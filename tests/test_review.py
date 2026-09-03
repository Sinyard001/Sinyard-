# -*- coding: utf-8 -*-
"""端到端测试：切分 -> 分类标注 -> 风险识别 -> 报告生成。"""

from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from contract_review.clauses import split_clauses
from contract_review.docxio import read_document
from contract_review.pipeline import review_contract
from contract_review.report import export_report


SAMPLE = PROJECT_ROOT / "data" / "sample_contract.txt"


class ClauseSplitterTest(unittest.TestCase):
    def test_split_sample_contract(self):
        clauses, preamble = split_clauses(SAMPLE.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(clauses), 10)
        self.assertEqual(clauses[0].number, "第一条")
        self.assertIn("智能软件开发服务合同", preamble)
        self.assertEqual(clauses[-1].number, "第十二条")

    def test_split_keeps_full_text(self):
        text = SAMPLE.read_text(encoding="utf-8")
        clauses, _ = split_clauses(text)
        for clause in clauses:
            self.assertTrue(clause.start < clause.end)
            self.assertLessEqual(clause.end, len(text))


class EndToEndReviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SAMPLE.read_text(encoding="utf-8")
        cls.review = review_contract(cls.text, title="智能软件开发服务合同（演示样本）")

    def test_key_clauses_are_annotated(self):
        expected = {
            "第一条": "定义与解释",
            "第四条": "付款条款",
            "第五条": "交付与验收",
            "第六条": "知识产权",
            "第七条": "保密义务",
            "第八条": "违约责任",
            "第九条": "不可抗力",
            "第十条": "通知与送达",
            "第十一条": "争议解决",
            "第十二条": "一般条款",
        }
        by_number = {clause.number: clause for clause in self.review.clauses}
        self.assertEqual(len(by_number), len(self.review.clauses))
        for number, expected_label in expected.items():
            self.assertIn(number, by_number)
            clause = by_number[number]
            self.assertEqual(clause.label, expected_label, msg=clause.text)
            self.assertGreater(clause.confidence, 0.5)

    def test_risk_findings_include_core_issues(self):
        codes = {finding.code for finding in self.review.findings}
        self.assertIn("BREACH_REMEDY_VAGUE", codes)
        self.assertIn("ARBITRATION_BODY_MISSING", codes)
        self.assertIn("PAYMENT_DEADLINE_VAGUE", codes)
        self.assertIn("UNBALANCED_TERMINATION", codes)

    def test_report_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path, md_path, json_path = export_report(
                self.review, tmp, name="test_report"
            )
            self.assertIn("违约责任", html_path.read_text(encoding="utf-8"))
            self.assertIn("风险清单", md_path.read_text(encoding="utf-8"))
            self.assertIn('"clauses"', json_path.read_text(encoding="utf-8"))


class DocxReaderTest(unittest.TestCase):
    def test_reads_simple_docx(self):
        with tempfile.TemporaryDirectory() as tmp:
            docx_path = Path(tmp) / "sample.docx"
            _create_minimal_docx(docx_path, "第一条 测试条款\n甲方应向乙方付款。")
            text = read_document(docx_path)
        self.assertIn("第一条", text)
        self.assertIn("付款", text)


def _create_minimal_docx(path: Path, paragraphs_text: str) -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    paragraphs = "".join(
        '<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:r><w:t xml:space=\"preserve\">{line}</w:t></w:r></w:p>"
        for line in paragraphs_text.split("\n")
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)


if __name__ == "__main__":
    unittest.main(verbosity=2)
