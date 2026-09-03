# -*- coding: utf-8 -*-
"""读取 .txt 与 .docx 合同文件。"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile


def read_document(path: str | Path) -> str:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix == ".docx":
        return _read_docx(file_path)
    return _read_text(file_path)


def _read_text(file_path: Path) -> str:
    data = file_path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("无法识别合同文本编码")


def _read_docx(file_path: Path) -> str:
    paragraphs: list[str] = []
    with ZipFile(file_path) as archive:
        if "word/document.xml" not in archive.namelist():
            raise ValueError("不是有效的 .docx 文件（缺少 document.xml）")
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraph_tag = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
    for node in root.iter(paragraph_tag):
        paragraphs.append("".join(node.itertext()))
    return "\n".join(paragraphs)
