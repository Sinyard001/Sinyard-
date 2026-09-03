# -*- coding: utf-8 -*-
"""命令行入口：python -m contract_review.cli --help"""

from __future__ import annotations

import argparse
from pathlib import Path

from .docxio import read_document
from .pipeline import review_contract
from .report import export_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contract-review",
        description="智能合同审查助手：自动切分并标注条款，输出风险报告",
    )
    parser.add_argument("file", type=Path, help="合同文件路径（.txt / .docx）")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="报告输出目录（默认与输入文件相同）",
    )
    parser.add_argument("--name", default=None, help="报告文件名前缀")
    parser.add_argument("--title", default=None, help="报告中的合同名称")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    text = read_document(args.file)
    title = args.title or args.file.stem
    review = review_contract(text, title=title)
    output_dir = args.output_dir or args.file.parent
    name = args.name or f"{args.file.stem}_审查报告"
    html_path, md_path, json_path = export_report(review, output_dir, name=name)

    summary = review.summary()
    print(f"合同已审查：{len(review.clauses)} 个条款")
    print(f"风险统计：高 {summary['risks']['high']} / "
          f"中 {summary['risks']['medium']} / 低 {summary['risks']['low']}")
    print(f"HTML 报告：{html_path}")
    print(f"Markdown：{md_path}")
    print(f"JSON 数据：{json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
