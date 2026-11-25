"""官方题库模板。表头与现有 Excel 导入一致，示例行不是正式题目。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

TEMPLATE_FILENAME = "stinger-question-template.xlsx"
TEMPLATE_HEADERS = [
    "题型",
    "题目",
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
    "答案",
    "难度",
    "试题依据",
    "试题解析",
    "保命题",
]
EXAMPLE_ROWS = [
    [
        "单选题",
        "【示例】这行只演示单选题怎么填，不是正式题目",
        "示例甲",
        "示例乙",
        "示例丙",
        "示例丁",
        "",
        "",
        "A",
        "易",
        "示例依据",
        "示例解析，可以留空",
        "",
    ],
    [
        "多选题",
        "【示例】这行只演示多选题怎么填，不是正式题目",
        "示例一",
        "示例二",
        "示例三",
        "示例四",
        "",
        "",
        "A,B,C",
        "",
        "",
        "",
        "",
    ],
    [
        "判断题",
        "【示例】这行只演示判断题怎么填，不是正式题目",
        "正确",
        "错误",
        "",
        "",
        "",
        "",
        "错误",
        "",
        "",
        "",
        "是",
    ],
]


def bundled_template_path() -> Path | None:
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    roots.append(Path(__file__).resolve().parents[2])
    for root in roots:
        candidate = root / "assets" / TEMPLATE_FILENAME
        if candidate.is_file():
            return candidate
    return None


def build_template_workbook():
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "题库模板"
    sheet.append(list(TEMPLATE_HEADERS))
    for row in EXAMPLE_ROWS:
        sheet.append(list(row))
    return workbook


def write_template(path: str | Path) -> Path:
    target = Path(path)
    if target.suffix.lower() != ".xlsx":
        target = target.with_suffix(".xlsx")
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook = build_template_workbook()
    workbook.save(target)
    return target


def export_template(path: str | Path) -> Path:
    """把随程序带上的模板写到用户选定的位置。没有打包文件时按同样内容现写。"""
    target = Path(path)
    if target.suffix.lower() != ".xlsx":
        target = target.with_suffix(".xlsx")
    target.parent.mkdir(parents=True, exist_ok=True)
    bundled = bundled_template_path()
    if bundled is not None and bundled.resolve() != target.resolve():
        shutil.copyfile(bundled, target)
        return target
    return write_template(target)
