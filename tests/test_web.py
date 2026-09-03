# -*- coding: utf-8 -*-
"""网页版端到端测试：静态页面 + 审查 API + 文件上传 API。"""

from __future__ import annotations

import base64
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webapp import create_server  # noqa: E402


SAMPLE = PROJECT_ROOT / "data" / "sample_contract.txt"


class WebAppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True
        )
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def request(self, method, path, body=None):
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
            content_type = response.headers.get("Content-Type", "")
            if "json" in content_type:
                return json.loads(payload.decode("utf-8"))
            return payload.decode("utf-8", errors="replace")

    def test_static_pages_serve(self):
        html = self.request("GET", "/")
        self.assertIn("智能合同工作台", html)
        self.assertIn("智能问答", html)
        self.assertIn("版本比对", html)
        self.assertIn("合同台账", html)
        css = self.request("GET", "/style.css")
        self.assertIn("--red: #d21f26", css)
        js = self.request("GET", "/app.js")
        self.assertIn("requestAnalyze", js)
        self.assertIn("runCompare", js)
        self.assertIn("exportLedgerCsv", js)

    def test_api_sample(self):
        data = self.request("GET", "/api/sample")
        self.assertTrue(data["ok"])
        self.assertIn("第一条", data["text"])

    def test_api_sample_v2(self):
        data = self.request("GET", "/api/sample-v2")
        self.assertTrue(data["ok"])
        self.assertIn("修订版", data["title"])
        self.assertIn("上海仲裁委员会", data["text"])

    def test_analyze_api_with_entities(self):
        text = SAMPLE.read_text(encoding="utf-8")
        data = self.request(
            "POST",
            "/api/analyze",
            {"title": "要素测试合同", "text": text},
        )
        self.assertTrue(data["ok"])
        result = data["result"]
        entities = result["entities"]
        self.assertEqual(entities["parties"]["甲方"], "星辰科技有限公司")
        self.assertEqual(entities["parties"]["乙方"], "远航信息技术有限公司")
        self.assertAlmostEqual(entities["total_amount"]["value"], 1200000.0)
        self.assertEqual(entities["duration"]["text"], "十二个月")
        stages = [item["stage"] for item in entities["payment_plan"]]
        self.assertIn("预付款", stages)
        self.assertIn("尾款", stages)
        self.assertEqual(result["stances"]["grading"]["level"], "高")
        self.assertGreaterEqual(len(result["gap_suggestions"]), 0)

    def test_gap_suggestions_when_clauses_missing(self):
        short_contract = (
            "简版服务合同\n\n"
            "第一条 服务费用与支付\n甲方应于收到乙方发票后十个工作日内，"
            "向乙方支付合同总价款人民币十万元整。\n"
            "第二条 一般条款\n本合同一式两份，自双方签字盖章之日起生效。\n"
        )
        data = self.request(
            "POST",
            "/api/analyze",
            {"title": "缺项测试合同", "text": short_contract},
        )
        self.assertTrue(data["ok"])
        gaps = data["result"]["gap_suggestions"]
        categories = {gap["category"] for gap in gaps}
        self.assertIn("违约责任", categories)
        self.assertIn("争议解决", categories)
        self.assertTrue(all(gap["suggested_text"] for gap in gaps))

    def test_ask_api(self):
        text = SAMPLE.read_text(encoding="utf-8")
        data = self.request(
            "POST",
            "/api/ask",
            {
                "question": "违约责任怎么约定的？",
                "title": "问答测试",
                "text": text,
            },
        )
        self.assertTrue(data["ok"])
        answer = data["result"]
        self.assertIn("违约责任", answer["answer"])
        self.assertTrue(answer["references"])

    def test_compare_api(self):
        old_text = SAMPLE.read_text(encoding="utf-8")
        new_text = (
            PROJECT_ROOT / "data" / "sample_contract_v2.txt"
        ).read_text(encoding="utf-8")
        data = self.request(
            "POST",
            "/api/compare",
            {
                "old_text": old_text,
                "new_text": new_text,
                "old_title": "旧版",
                "new_title": "新版",
            },
        )
        self.assertTrue(data["ok"])
        result = data["result"]
        self.assertEqual(result["summary"]["modified"], 4)
        removed = {item["code"] for item in result["risk_delta"]["removed"]}
        self.assertIn("ARBITRATION_BODY_MISSING", removed)
        self.assertIn("UNBALANCED_TERMINATION", removed)
        self.assertEqual(result["risk_delta"]["new_summary"]["high"], 0)

    def test_review_paste_api(self):
        text = SAMPLE.read_text(encoding="utf-8")
        data = self.request(
            "POST",
            "/api/review",
            {"title": "网页版测试合同", "text": text},
        )
        self.assertTrue(data["ok"])
        result = data["result"]
        by_number = {clause["number"]: clause for clause in result["clauses"]}
        self.assertEqual(
            by_number["第八条"]["label"], "违约责任"
        )
        self.assertEqual(
            by_number["第十一条"]["label"], "争议解决"
        )
        self.assertIn("第七条", by_number)
        codes = {finding["code"] for finding in result["risks"]}
        self.assertIn("ARBITRATION_BODY_MISSING", codes)
        self.assertIn("UNBALANCED_TERMINATION", codes)

    def test_review_upload_docx_api(self):
        paragraphs = (
            "网页测试合同\n\n"
            "第一条 违约责任\n甲方逾期付款的，每逾期一日应按未付款项的万分之五支付违约金。\n"
            "第二条 争议解决\n协商不成的，任何一方可向上海仲裁委员会申请仲裁。\n"
        )
        content = _create_docx_bytes(paragraphs)
        data = self.request(
            "POST",
            "/api/review-upload",
            {
                "filename": "网页测试合同.docx",
                "title": "网页测试合同",
                "content": base64.b64encode(content).decode("ascii"),
            },
        )
        self.assertTrue(data["ok"], data.get("error"))
        result = data["result"]
        labels = [clause["label"] for clause in result["clauses"]]
        self.assertIn("违约责任", labels)
        self.assertIn("争议解决", labels)

    def test_invalid_contract_rejected(self):
        try:
            self.request(
                "POST",
                "/api/review",
                {"title": "", "text": "内容太短"},
            )
            self.fail("短文本应返回 400")
        except urllib.error.HTTPError as error:
            self.assertEqual(error.code, 400)
            body = json.loads(error.read().decode("utf-8"))
            self.assertFalse(body["ok"])

    def test_missing_route_returns_404(self):
        try:
            self.request("GET", "/api/not-exist")
            self.fail("应返回 404")
        except urllib.error.HTTPError as error:
            self.assertEqual(error.code, 404)


def _create_docx_bytes(text: str) -> bytes:
    paragraphs = "".join(
        '<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:r><w:t xml:space="preserve">{line}</w:t></w:r></w:p>'
        for line in text.split("\n")
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    buffer_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp:
            buffer_path = temp.name
        with zipfile.ZipFile(buffer_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("_rels/.rels", rels)
            archive.writestr("word/document.xml", document)
        return Path(buffer_path).read_bytes()
    finally:
        if buffer_path:
            Path(buffer_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
