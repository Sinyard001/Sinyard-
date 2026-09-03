# -*- coding: utf-8 -*-
"""智能合同审查助手（Web 版）本地服务。

运行方式：
    python webapp.py            # 默认在 http://127.0.0.1:8765 启动
    python webapp.py --port 9000
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
SAMPLE_FILE = ROOT / "data" / "sample_contract.txt"
SAMPLE_V2_FILE = ROOT / "data" / "sample_contract_v2.txt"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contract_review.docxio import read_document
from contract_review.pipeline import get_default_classifier, review_contract
from contract_review.report import to_dict
from contract_review.analysis import analyze_contract
from contract_review.compare import compare_contracts
from contract_review.qa import answer_contract_question


_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}


def _run_review(title: str, text: str) -> dict:
    if not text or len(text.strip()) < 20:
        raise ValueError("合同正文太短，请粘贴完整合同内容后重试。")
    review = review_contract(text, title=title or "未命名合同")
    return {"ok": True, "result": to_dict(review)}


def _run_analysis(title: str, text: str, include_text: bool = False) -> dict:
    if not text or len(text.strip()) < 20:
        raise ValueError("合同正文太短，请粘贴完整合同内容后重试。")
    result = analyze_contract(text, title=title or "未命名合同", include_text=include_text)
    return {"ok": True, "result": result}


class WebHandler(BaseHTTPRequestHandler):
    server_version = "ContractReview/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send_bytes(self, payload: bytes, content_type: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, obj: dict, status: int = 200):
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send_bytes(payload, "application/json; charset=utf-8", status=status)

    def _serve_static(self, path: str):
        relative = Path(path.lstrip("/"))
        if relative.name in ("", "index.html"):
            file_path = WEB_DIR / "index.html"
        else:
            file_path = (WEB_DIR / relative).resolve()
            if WEB_DIR.resolve() not in file_path.parents and file_path != WEB_DIR.resolve():
                self._send_json({"ok": False, "error": "禁止访问的路径"}, 403)
                return
        if not file_path.is_file():
            self._send_json({"ok": False, "error": "资源不存在"}, 404)
            return
        content_type = _CONTENT_TYPES.get(file_path.suffix.lower(), "application/octet-stream")
        self._send_bytes(file_path.read_bytes(), content_type)

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/api/sample":
            if not SAMPLE_FILE.is_file():
                self._send_json({"ok": False, "error": "演示合同文件不存在"}, 404)
                return
            self._send_json(
                {
                    "ok": True,
                    "filename": "sample_contract.txt",
                    "title": "智能软件开发服务合同（演示样本）",
                    "text": SAMPLE_FILE.read_text(encoding="utf-8"),
                }
            )
            return
        if self.path.split("?", 1)[0] == "/api/sample-v2":
            if not SAMPLE_V2_FILE.is_file():
                self._send_json({"ok": False, "error": "新版演示合同文件不存在"}, 404)
                return
            self._send_json(
                {
                    "ok": True,
                    "filename": "sample_contract_v2.txt",
                    "title": "智能软件开发服务合同（修订版演示）",
                    "text": SAMPLE_V2_FILE.read_text(encoding="utf-8"),
                }
            )
            return
        if self.path.split("?", 1)[0] == "/api/health":
            self._send_json({"ok": True, "service": "contract-review"})
            return
        if self.path.startswith("/api/"):
            self._send_json({"ok": False, "error": "接口不存在"}, 404)
            return
        self._serve_static(self.path)

    def do_POST(self):
        route = self.path.split("?", 1)[0]
        if route not in (
            "/api/review",
            "/api/review-upload",
            "/api/analyze",
            "/api/ask",
            "/api/compare",
        ):
            self._send_json({"ok": False, "error": "接口不存在"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 32 * 1024 * 1024:
                self._send_json({"ok": False, "error": "文件过大，请控制在 32MB 以内"}, 413)
                return
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self._send_json({"ok": False, "error": "请求数据无法解析"}, 400)
            return

        try:
            if route == "/api/review":
                text = payload.get("text", "")
                if isinstance(text, str):
                    text = text.replace("\u0000", "")
                result = _run_review(payload.get("title", ""), text)
            elif route == "/api/review-upload":
                result = _handle_upload(payload)
            elif route == "/api/analyze":
                text = payload.get("text", "")
                if isinstance(text, str):
                    text = text.replace("\u0000", "")
                result = _run_analysis(payload.get("title", ""), text)
            elif route == "/api/ask":
                question = (payload.get("question") or "").strip()
                if not question:
                    raise ValueError("请输入问题后再发送。")
                text = payload.get("text", "")
                if len(text.strip()) < 20:
                    raise ValueError("尚未载入合同文本，请先在“审查工作台”粘贴或上传合同。")
                answer = answer_contract_question(
                    question, text, title=payload.get("title") or "合同文本"
                )
                result = {"ok": True, "result": answer}
            elif route == "/api/compare":
                old_text = payload.get("old_text") or payload.get("text_a") or ""
                new_text = payload.get("new_text") or payload.get("text_b") or ""
                if len(old_text.strip()) < 20 or len(new_text.strip()) < 20:
                    raise ValueError("请同时提供旧版与新版合同文本。")
                comparison = compare_contracts(
                    old_text,
                    new_text,
                    old_title=payload.get("old_title") or "旧版合同",
                    new_title=payload.get("new_title") or "新版合同",
                )
                result = {"ok": True, "result": comparison}
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)}, 400)
            return
        except Exception as exc:
            self._send_json(
                {"ok": False, "error": f"审查失败：{exc.__class__.__name__}: {exc}"},
                500,
            )
            return
        self._send_json(result)


def _handle_upload(payload: dict) -> dict:
    filename = (payload.get("filename") or "contract.txt").strip()
    encoded = payload.get("content", "")
    if not encoded:
        raise ValueError("未接收到文件内容。")
    try:
        raw = base64.b64decode(encoded)
    except Exception:
        raise ValueError("文件内容解码失败，请重新选择文件。")
    if not raw:
        raise ValueError("文件内容为空。")

    suffix = Path(filename).suffix.lower() or ".txt"
    if suffix not in (".txt", ".docx", ".doc"):
        raise ValueError("仅支持 .txt 或 .docx 合同文件。")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(raw)
            temp_path = handle.name
        text = read_document(temp_path)
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)
    title = payload.get("title") or Path(filename).stem
    return _run_analysis(title, text, include_text=True)


def create_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), WebHandler)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="智能合同审查助手（Web 版）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    args = parser.parse_args(argv)

    print("正在加载合同审查模型，请稍候……")
    get_default_classifier()
    print("模型加载完成。")

    server = create_server(args.host, args.port)
    host, port = server.server_address[:2]
    url = f"http://{host}:{port}"
    print(f"智能合同审查助手已启动：{url}")
    print("按 Ctrl+C 停止服务。")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
