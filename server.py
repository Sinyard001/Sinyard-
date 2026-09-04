#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地笔记 · 简历工作台 后端服务

仅使用 Python 标准库，无需安装任何第三方依赖。
功能：
  - 提供本地网页界面
  - 代理飞书多维表格接口，读取"昨日更新"的记录
  - 代理 OpenAI 兼容的大模型接口，生成简历用语 / 定制简历
  - 将配置保存在同目录下的 config.json
"""

import datetime
import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
HOST = "127.0.0.1"
PORT = 8787

# 中国标准时间（无夏令时）
TZ = datetime.timezone(datetime.timedelta(hours=8))


# ---------------------------------------------------------------------------
# 配置读写
# ---------------------------------------------------------------------------

def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_config(cfg):
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def merge_config(new_cfg):
    """合并新配置；密钥字段传空字符串表示保持不变。"""
    old = load_config()
    merged = dict(old)
    for k in ("app_id", "app_token", "table_id", "view_id",
              "ai_base_url", "ai_model"):
        if k in new_cfg:
            merged[k] = (new_cfg.get(k) or "").strip()
    # 密钥：只有非空才更新，空字符串表示"不修改"
    if (new_cfg.get("app_secret") or "").strip():
        merged["app_secret"] = new_cfg["app_secret"].strip()
    if (new_cfg.get("ai_api_key") or "").strip():
        merged["ai_api_key"] = new_cfg["ai_api_key"].strip()
    # 明确清除（可选）
    for k in ("app_secret", "ai_api_key"):
        if new_cfg.get(k) == "__CLEAR__":
            merged.pop(k, None)
    save_config(merged)
    return merged


def public_config(cfg):
    return {
        "app_id": cfg.get("app_id", ""),
        "app_token": cfg.get("app_token", ""),
        "table_id": cfg.get("table_id", ""),
        "view_id": cfg.get("view_id", ""),
        "app_secret_set": bool(cfg.get("app_secret")),
        "ai_base_url": cfg.get("ai_base_url", ""),
        "ai_model": cfg.get("ai_model", ""),
        "ai_api_key_set": bool(cfg.get("ai_api_key")),
    }


# ---------------------------------------------------------------------------
# 飞书多维表格
# ---------------------------------------------------------------------------

FEISHU_BASE = "https://open.feishu.cn"


def feishu_tenant_token(app_id, app_secret):
    url = FEISHU_BASE + "/open-apis/auth/v3/tenant_access_token/internal"
    body = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json; charset=utf-8"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            obj = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:300]}")
    if obj.get("code") != 0:
        raise RuntimeError(obj.get("msg") or "获取飞书访问令牌失败")
    return obj.get("tenant_access_token")


def feishu_list_records(app_token, table_id, token):
    items = []
    page_token = None
    while True:
        url = (
            f"{FEISHU_BASE}/open-apis/bitable/v1/apps/{app_token}"
            f"/tables/{table_id}/records?page_size=100"
        )
        if page_token:
            url += "&page_token=" + urllib.parse.quote(page_token)
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {token}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                obj = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")
            raise RuntimeError(f"HTTP {exc.code}: {detail[:300]}")
        if obj.get("code") != 0:
            raise RuntimeError(obj.get("msg") or "读取多维表格失败")
        data = obj.get("data") or {}
        items.extend(data.get("items") or [])
        if data.get("has_more"):
            page_token = data.get("page_token")
        else:
            break
    return items


def field_to_text(value):
    """把多维表格字段值尽量转成可读文本。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        # 飞书日期字段返回毫秒时间戳
        if isinstance(value, int) and value >= 1_000_000_000_000:
            try:
                dt = datetime.datetime.fromtimestamp(value / 1000, TZ)
                return dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(
                    item.get("text")
                    or item.get("name")
                    or item.get("en_name")
                    or json.dumps(item, ensure_ascii=False)
                )
            else:
                parts.append(str(item))
        return "、".join([p for p in parts if p])
    if isinstance(value, dict):
        return (
            value.get("text")
            or value.get("name")
            or value.get("en_name")
            or json.dumps(value, ensure_ascii=False)
        )
    return str(value)


def format_record(record):
    fields = record.get("fields") or {}
    return {
        "record_id": record.get("record_id"),
        "last_modified_time": record.get("last_modified_time"),
        "last_modified_by": (record.get("last_modified_by") or {}).get("name", ""),
        "fields": [
            {"name": k, "value": field_to_text(v)} for k, v in fields.items()
        ],
    }


# ---------------------------------------------------------------------------
# AI（OpenAI 兼容 Chat Completions）
# ---------------------------------------------------------------------------

def chat_completion(base_url, api_key, model, messages, temperature=None, max_tokens=None, json_mode=False):
    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"

    def build(temp, jm):
        payload = {"model": model, "messages": messages}
        if temp is not None:
            payload["temperature"] = temp
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if jm:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def request(payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read().decode("utf-8")), None
        except urllib.error.HTTPError as exc:
            return None, (exc.code, exc.read().decode("utf-8", "ignore"))

    obj, err = request(build(temperature, json_mode))
    if err:
        code, body = err
        low = body.lower()
        if code == 400 and "temperature" in low:
            obj, err = request(build(None, json_mode))
        elif code == 400 and "response_format" in low:
            obj, err = request(build(temperature, False))
    if err:
        raise RuntimeError(f"HTTP {err[0]}：{err[1][:500]}")

    try:
        content = obj["choices"][0]["message"]["content"]
    except Exception:
        raise RuntimeError("AI 返回格式异常：" + json.dumps(obj, ensure_ascii=False)[:500])
    if not content:
        raise RuntimeError("AI 返回内容为空")
    return content


def extract_json(text):
    """从模型输出中稳健地提取 JSON（对象或数组）。"""
    text = (text or "").strip()
    # 去掉 ```json ... ``` 代码块
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start = -1
    for i, ch in enumerate(text):
        if ch in "{[":
            start = i
            break
    if start < 0:
        raise ValueError("未找到 JSON 内容")
    stack = []
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if stack:
                    stack.pop()
                if not stack:
                    return json.loads(text[start:i + 1])
    raise ValueError("JSON 内容未闭合")


BULLETS_SYSTEM = (
    "你是一位资深的中文简历写作专家，擅长把口语化、零散的经历改写成"
    "书面、专业、有说服力的简历要点。\n\n"
    "改写要求：\n"
    "1. 语言正式、书面、专业，避免口语词。\n"
    "2. 用动词开头（如：负责、主导、参与、搭建、统筹、优化、完成、撰写）。\n"
    "3. 尽量体现能力、方法与成果；对可合理推断的量化结果可用约数表达"
    "（如“提升约20%”），但严禁编造原经历中不存在的具体数据或事实。\n"
    "4. 忠于原经历，不添加原经历中没有的内容。\n"
    "5. 每条独立成句、简洁有力，长度约 15~40 字。\n"
    "6. 只输出一个 JSON 对象，不要输出任何解释、标题或 Markdown 代码块。\n\n"
    '输出格式示例：{"bullets":["负责策划并落地校园公益项目，覆盖300余名学生",'
    '"主导调研问卷设计与数据分析，产出万字结题报告"]}'
)


TAILOR_SYSTEM = (
    "你是一位资深简历优化专家，擅长根据候选人的多份简历与经历汇总，"
    "针对具体岗位 JD 写出一份完整、匹配的简历。\n\n"
    "优化原则：\n"
    "1. 突出与岗位最匹配的经历、技能和关键词，可重新排序或精简无关内容。\n"
    "2. 把经历要点改写得更贴合岗位术语与要求，但不得虚构经历或数据。\n"
    "3. 个人总结（summary）需针对该岗位重新撰写，点明核心匹配点。\n"
    "4. 保留真实的姓名、联系方式、教育背景等事实信息，综合多份经历取最相关者。\n"
    "5. 严格只输出一个 JSON 对象，不要 Markdown 代码块、不要多余文字。\n\n"
    '输出结构（示例）：\n'
    '{\n'
    '  "summary": "用2-4句话说明本次做了哪些优化调整",\n'
    '  "resume": {\n'
    '    "name": "", "target": "", "phone": "", "email": "", "location": "",\n'
    '    "summary": "",\n'
    '    "education": [{"school":"","degree":"","major":"","time":""}],\n'
    '    "experience": [{"org":"","title":"","time":"","bullets":[""]}],\n'
    '    "projects": [{"name":"","role":"","time":"","bullets":[""]}],\n'
    '    "skills": [""],\n'
    '    "awards": [""]\n'
    '  }\n'
    '}'
)


INTERVIEW_ANSWERS_SYSTEM = (
    "你是一位资深的面试辅导专家，擅长把候选人的真实经历改写成结构清晰、"
    "专业可信的面试回答。\n\n"
    "请根据用户提供的经历，生成若干道面试官很可能提问的问题，并给出高质量的面试回答。\n"
    "要求：\n"
    "1. 问题要贴合该经历，覆盖常见行为面试维度（项目/成果、困难与解决、团队协作、"
    "自我认知、动机、压力处理等）。\n"
    "2. 每个回答用「STAR 或 总分总」结构：先一句话结论，再讲背景-行动-结果，"
    "结尾点出能力或收获。\n"
    "3. 语言专业、口语化、适合面试现场表达；不要编造经历里没有的事实或数据。\n"
    "4. 只输出一个 JSON 对象，不要任何解释、标题或 Markdown 代码块。\n\n"
    '输出格式示例：{"items":[{"question":"请介绍一下你最有成就感的一段经历","answer":"……"}]}'
)


INTERVIEW_QUESTIONS_SYSTEM = (
    "你是一位熟悉各行业招聘的资深面试官。\n"
    "请根据用户的经历和（可选的）目标行业/岗位，设想面试官可能会问的问题，"
    "并为每个问题给出简短的答题要点。\n"
    "要求：\n"
    "1. 问题要专业、有区分度，覆盖该行业/岗位的真实考察点"
    "（专业技能、行为面、行业认知、情境题等）。\n"
    "2. 答题要点只需 1-2 句，指出回答方向或关键得分点。\n"
    "3. 如果用户没有指定行业，就按「通用 + 各行业常见」来设想。\n"
    "4. 只输出一个 JSON 对象，不要任何解释、标题或 Markdown 代码块。\n\n"
    '输出格式示例：{"items":[{"question":"……","point":"……"}]}'
)


INTERVIEW_ANSWER_SYSTEM = (
    "你是一位资深面试辅导专家。\n"
    "请根据用户的经历，回答面试官提出的具体问题，给出一个合格、专业的面试回答。\n"
    "要求：\n"
    "1. 直接回答问题，结构清晰（推荐 STAR 或总分总），有具体细节和量化结果（若有）。\n"
    "2. 语言专业但口语化，适合现场直接说；篇幅约 150-300 字，不要啰嗦。\n"
    "3. 忠于经历，不编造经历中没有的事实或数据。\n"
    "4. 只输出一个 JSON 对象，不要任何解释、标题或 Markdown 代码块。\n\n"
    '输出格式示例：{"answer":"……"}'
)


POLISH_SYSTEM = (
    "你是一位资深中文简历写作专家。\n"
    "请把用户提供的简历文字润色得更专业、书面、有说服力，用于正式简历。\n"
    "要求：\n"
    "1. 保留原意与事实，不编造、不夸大。\n"
    "2. 语言更精炼、专业，动词开头，突出能力与成果。\n"
    "3. 可量化的尽量用数据或合理约数表达。\n"
    "4. 若输入是多行要点，保持行数不变、每行一条输出；多行之间用换行分隔。\n"
    "5. 只输出一个 JSON 对象，不要任何解释、标题或 Markdown 代码块。\n\n"
    '输出格式示例：{"result":"润色后的文字"}'
)


# ---------------------------------------------------------------------------
# HTTP 服务
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "NoteApp/1.0"

    MIME = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
    }

    def log_message(self, fmt, *args):
        # 保持控制台安静，只记录错误
        pass

    # -- 工具方法 -----------------------------------------------------------
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, rel_path, ctype):
        target = (APP_DIR / rel_path).resolve()
        if APP_DIR not in target.parents and target != APP_DIR:
            self._send_json({"error": "禁止访问"}, 403)
            return
        if not target.exists():
            self._send_json({"error": "文件不存在"}, 404)
            return
        data = target.read_bytes()
        self.send_response(200)
        if not ctype:
            ctype = self.MIME.get(target.suffix.lower(), "application/octet-stream")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    # -- 请求入口 -----------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self._send_file("index.html", "text/html; charset=utf-8")
        elif path == "/api/health":
            self._send_json({"ok": True, "time": datetime.datetime.now(TZ).isoformat()})
        elif path == "/api/config":
            self._send_json(public_config(load_config()))
        elif path == "/api/feishu/sync":
            self.handle_sync(parsed)
        else:
            self._send_file(path.lstrip("/"), None)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}
        if path == "/api/config":
            merged = merge_config(payload)
            self._send_json({"ok": True, "config": public_config(merged)})
        elif path == "/api/ai/bullets":
            self.handle_bullets(payload)
        elif path == "/api/ai/tailor":
            self.handle_tailor(payload)
        elif path == "/api/ai/interview":
            self.handle_interview(payload)
        elif path == "/api/ai/polish":
            self.handle_polish(payload)
        elif path == "/api/ai/test":
            self.handle_ai_test(payload)
        elif path == "/api/shutdown":
            self.handle_shutdown(payload)
        else:
            self._send_json({"error": "未找到接口"}, 404)

    # -- 飞书同步 -----------------------------------------------------------
    def handle_sync(self, parsed):
        cfg = load_config()
        need = ("app_id", "app_secret", "app_token", "table_id")
        if not all(cfg.get(k) for k in need):
            self._send_json(
                {"error": "请先在「设置」中完成飞书应用配置", "code": "no_feishu"}, 400
            )
            return
        qs = parse_qs(parsed.query)
        date_str = (qs.get("date") or [None])[0]
        try:
            if date_str:
                y, m, d = (int(x) for x in date_str.split("-"))
                target = datetime.date(y, m, d)
            else:
                target = datetime.datetime.now(TZ).date() - datetime.timedelta(days=1)
            start = datetime.datetime(target.year, target.month, target.day, tzinfo=TZ)
            end = start + datetime.timedelta(days=1)
            start_ms = int(start.timestamp() * 1000)
            end_ms = int(end.timestamp() * 1000)
        except Exception:
            self._send_json({"error": "日期格式错误"}, 400)
            return
        try:
            token = feishu_tenant_token(cfg["app_id"], cfg["app_secret"])
            items = feishu_list_records(cfg["app_token"], cfg["table_id"], token)
        except Exception as exc:
            self._send_json({"error": f"飞书接口调用失败：{exc}"}, 502)
            return
        matched = [
            format_record(r)
            for r in items
            if start_ms <= int(r.get("last_modified_time") or 0) < end_ms
        ]
        matched.sort(key=lambda r: r.get("last_modified_time") or 0, reverse=True)
        self._send_json(
            {
                "date": target.isoformat(),
                "count": len(matched),
                "records": matched,
            }
        )

    # -- AI 简历用语 --------------------------------------------------------
    def handle_bullets(self, payload):
        cfg = load_config()
        if not (cfg.get("ai_base_url") and cfg.get("ai_api_key") and cfg.get("ai_model")):
            self._send_json(
                {"error": "请先在「设置」中配置 AI 接口", "code": "no_ai"}, 400
            )
            return
        sentence = (payload.get("sentence") or "").strip()
        if not sentence:
            self._send_json({"error": "请先填写你的大学经历"}, 400)
            return
        context = (payload.get("context") or "").strip()
        style = (payload.get("style") or "通用").strip()
        try:
            count = int(payload.get("count") or 4)
        except Exception:
            count = 4
        count = max(2, min(8, count))
        user = f"大学经历（一句话）：{sentence}\n"
        if context:
            user += f"目标岗位方向：{context}\n"
        user += f"期望要点数量：{count} 条\n风格倾向：{style}"
        try:
            text = chat_completion(
                cfg["ai_base_url"], cfg["ai_api_key"], cfg["ai_model"],
                [
                    {"role": "system", "content": BULLETS_SYSTEM},
                    {"role": "user", "content": user},
                ],
                temperature=0.6,
                json_mode=True,
            )
            obj = extract_json(text)
            if not isinstance(obj, dict) or "bullets" not in obj:
                raise ValueError("AI 返回结构不完整")
            bullets = [str(x).strip() for x in obj.get("bullets", []) if str(x).strip()][:count]
            if not bullets:
                raise ValueError("AI 未返回任何要点")
            self._send_json({"bullets": bullets})
        except Exception as exc:
            self._send_json({"error": f"AI 生成失败：{exc}"}, 502)

    # -- AI 定制简历 --------------------------------------------------------
    def handle_tailor(self, payload):
        cfg = load_config()
        if not (cfg.get("ai_base_url") and cfg.get("ai_api_key") and cfg.get("ai_model")):
            self._send_json(
                {"error": "请先在「设置」中配置 AI 接口", "code": "no_ai"}, 400
            )
            return
        resumes = payload.get("resumes") or []
        pool = (payload.get("experience_pool") or "").strip()
        job = (payload.get("job_description") or "").strip()
        if not job:
            self._send_json({"error": "请粘贴岗位要求（JD）"}, 400)
            return
        if not resumes and not pool:
            self._send_json({"error": "请先填写简历或经历大汇总"}, 400)
            return

        parts = []
        if resumes:
            parts.append(
                "我的简历（可能有多份，请综合参考）：\n"
                + json.dumps(resumes, ensure_ascii=False)
            )
        if pool:
            parts.append("我的经历大汇总：\n" + pool)
        parts.append("岗位要求（JD）：\n" + job)
        user = "\n\n".join(parts)
        try:
            text = chat_completion(
                cfg["ai_base_url"], cfg["ai_api_key"], cfg["ai_model"],
                [
                    {"role": "system", "content": TAILOR_SYSTEM},
                    {"role": "user", "content": user},
                ],
                temperature=0.4,
                json_mode=True,
            )
            obj = extract_json(text)
            if not isinstance(obj, dict) or "resume" not in obj:
                raise ValueError("AI 返回结构不完整")
            self._send_json(
                {
                    "summary": obj.get("summary", ""),
                    "resume": obj.get("resume", {}),
                }
            )
        except Exception as exc:
            self._send_json({"error": f"AI 定制失败：{exc}"}, 502)

    # -- AI 面试助手 --------------------------------------------------------
    def handle_interview(self, payload):
        cfg = load_config()
        if not (cfg.get("ai_base_url") and cfg.get("ai_api_key") and cfg.get("ai_model")):
            self._send_json(
                {"error": "请先在「设置」中配置 AI 接口", "code": "no_ai"}, 400
            )
            return
        mode = payload.get("mode") or "answers"
        experience = (payload.get("experience") or "").strip()
        context = (payload.get("context") or "").strip()

        if mode == "answer":
            question = (payload.get("question") or "").strip()
            if not question:
                self._send_json({"error": "请输入面试官的问题"}, 400)
                return
            if not experience:
                self._send_json({"error": "请填写你的经历，以便回答更有针对性"}, 400)
                return
            system = INTERVIEW_ANSWER_SYSTEM
            user = f"我的经历：{experience}\n"
            if context:
                user += f"目标行业/岗位：{context}\n"
            user += f"面试官问题：{question}"
        else:
            if not experience:
                self._send_json({"error": "请先填写你的经历"}, 400)
                return
            try:
                count = int(payload.get("count") or (4 if mode == "answers" else 5))
            except Exception:
                count = 4 if mode == "answers" else 5
            count = max(2, min(8, count))
            system = INTERVIEW_QUESTIONS_SYSTEM if mode == "questions" else INTERVIEW_ANSWERS_SYSTEM
            user = f"我的经历：{experience}\n"
            if context:
                user += f"目标行业/岗位：{context}\n"
            user += f"生成数量：{count} 道\n"

        try:
            text = chat_completion(
                cfg["ai_base_url"], cfg["ai_api_key"], cfg["ai_model"],
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.7,
                json_mode=True,
            )
            obj = extract_json(text)
        except Exception as exc:
            self._send_json({"error": f"AI 生成失败：{exc}"}, 502)
            return

        if mode == "answer":
            if not isinstance(obj, dict) or not obj.get("answer"):
                self._send_json({"error": "AI 返回结构不完整"}, 502)
                return
            self._send_json({"answer": str(obj["answer"]).strip()})
            return

        raw_items = obj.get("items", []) if isinstance(obj, dict) else []
        if not isinstance(raw_items, list):
            self._send_json({"error": "AI 返回结构不完整"}, 502)
            return
        items = []
        for x in raw_items:
            if isinstance(x, dict) and x.get("question"):
                items.append({
                    "question": str(x.get("question", "")).strip(),
                    "text": str(x.get("answer") or x.get("point") or "").strip(),
                })
            elif isinstance(x, str):
                items.append({"question": x.strip(), "text": ""})
        items = [it for it in items if it["question"]][:count]
        if not items:
            self._send_json({"error": "AI 未返回任何内容"}, 502)
            return
        self._send_json({"items": items})

    # -- AI 简历润色 --------------------------------------------------------
    def handle_polish(self, payload):
        cfg = load_config()
        if not (cfg.get("ai_base_url") and cfg.get("ai_api_key") and cfg.get("ai_model")):
            self._send_json(
                {"error": "请先在「设置」中配置 AI 接口", "code": "no_ai"}, 400
            )
            return
        text = (payload.get("text") or "").strip()
        if not text:
            self._send_json({"error": "没有内容可润色"}, 400)
            return
        kind = payload.get("kind") or "summary"
        type_desc = "多行简历要点（保持行数、每条独立成句）" if kind == "bullets" else "个人总结段落"
        user = f"润色类型：{type_desc}\n\n原文：\n{text}"
        try:
            out = chat_completion(
                cfg["ai_base_url"], cfg["ai_api_key"], cfg["ai_model"],
                [
                    {"role": "system", "content": POLISH_SYSTEM},
                    {"role": "user", "content": user},
                ],
                temperature=0.4,
                json_mode=True,
            )
            obj = extract_json(out)
            if not isinstance(obj, dict) or not obj.get("result"):
                raise ValueError("AI 返回结构不完整")
            self._send_json({"result": str(obj["result"]).strip()})
        except Exception as exc:
            self._send_json({"error": f"AI 润色失败：{exc}"}, 502)

    # -- AI 连接测试 --------------------------------------------------------
    def handle_ai_test(self, payload):
        cfg = load_config()
        if not (cfg.get("ai_base_url") and cfg.get("ai_api_key") and cfg.get("ai_model")):
            self._send_json(
                {"ok": False, "error": "尚未配置完整的 AI 接口（需填写接口地址、API Key、模型名称）"},
                400,
            )
            return
        try:
            text = chat_completion(
                cfg["ai_base_url"], cfg["ai_api_key"], cfg["ai_model"],
                [{"role": "user", "content": "请只回复两个字：正常"}],
            )
            self._send_json({"ok": True, "model": cfg["ai_model"], "reply": text.strip()})
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, 502)

    # -- 退出软件 -----------------------------------------------------------
    def handle_shutdown(self, payload):
        self._send_json({"ok": True})
        threading.Timer(0.3, lambda: os._exit(0)).start()


class SingleInstanceServer(ThreadingHTTPServer):
    # 关闭端口复用：若 8787 已被占用，会直接报错而不是悄悄叠加多个实例
    allow_reuse_address = False


def main():
    try:
        server = SingleInstanceServer((HOST, PORT), Handler)
    except OSError:
        print("=" * 52)
        print("  启动失败：端口 8787 已被占用。")
        print("  可能已经有一个「我的笔记」在运行。")
        print("  请关闭之前的黑色窗口后重试；")
        print("  若仍不行，请重启电脑后再试。")
        print("=" * 52)
        try:
            input("  按回车键退出...")
        except (EOFError, OSError):
            pass
        return
    print("=" * 52)
    print("  我的笔记 · 简历工作台 已启动")
    print(f"  请在浏览器打开：http://{HOST}:{PORT}")
    print("  按 Ctrl+C 停止服务")
    print("=" * 52)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        server.server_close()


if __name__ == "__main__":
    main()
