"""题干与选项的可比文本。

小数点会在去掉标点之前先收成整数形式，因此「100.0」和「100」相同。
若先删掉小数点，「100.0」会变成「1000」。
"""

from __future__ import annotations

import math
import re

_EMPTY_BRACKETS = re.compile(r"[(（\[【〔{｛]\s*[)）\]】〕}｝]")
_LEADING_INDEX = re.compile(r"^\s*(?:第\s*)?\d{1,3}\s*[.、．:：)\]】]\s*(?!\d)")
_LEADING_PAREN_INDEX = re.compile(r"^\s*[（(]\s*\d{1,3}\s*[)）]\s*")
_LEADING_TYPE = re.compile(
    r"^\s*(?:"
    r"【\s*(?:单项选择题|多项选择题|单选题|多选题|判断题|单选|多选|判断)\s*】"
    r"|(?:单项选择题|多项选择题|单选题|多选题|判断题)(?=\s|[:：.、])"
    r")\s*"
)
_DECIMAL = re.compile(r"\d+\.\d+")
_DROP = re.compile(r"[^\u4e00-\u9fffa-z0-9]+")
_OPTION_PREFIX = re.compile(r"^[A-F]\s*[.、．:：)）]\s*", re.IGNORECASE)

_ANALYSIS_PLACEHOLDERS = {
    "",
    "无",
    "【无】",
    "暂无",
    "暂无解析",
    "无解析",
    "未提供",
    "none",
    "null",
    "n/a",
    "na",
    "-",
    "—",
}


def to_halfwidth(text: str) -> str:
    chars: list[str] = []
    for ch in text:
        code = ord(ch)
        if code == 0x3000:
            chars.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            chars.append(chr(code - 0xFEE0))
        else:
            chars.append(ch)
    return "".join(chars)


def strip_empty_brackets(text: str) -> str:
    previous = None
    while previous != text:
        previous = text
        text = _EMPTY_BRACKETS.sub("", text)
    return text


def canonicalize_decimals(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        try:
            value = float(raw)
        except ValueError:
            return raw
        if not math.isfinite(value):
            return raw
        if value.is_integer():
            return str(int(value))
        rendered = format(value, "f").rstrip("0").rstrip(".")
        return rendered

    return _DECIMAL.sub(replace, text)


def normalize_match_text(text: object) -> str:
    """去掉空白、空括号和标点，只保留汉字、字母和数字，并处理小数。"""
    if text is None:
        return ""
    cleaned = to_halfwidth(str(text))
    cleaned = strip_empty_brackets(cleaned)
    cleaned = canonicalize_decimals(cleaned)
    cleaned = cleaned.lower()
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = _DROP.sub("", cleaned)
    return cleaned


def stem_fingerprint(text: object) -> str:
    if text is None:
        return ""
    cleaned = to_halfwidth(str(text)).strip()
    cleaned = strip_empty_brackets(cleaned)
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = _LEADING_INDEX.sub("", cleaned).strip()
        cleaned = _LEADING_PAREN_INDEX.sub("", cleaned).strip()
        cleaned = _LEADING_TYPE.sub("", cleaned).strip()
    return normalize_match_text(cleaned)


def cell_to_str(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return str(value)
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


def strip_option_prefix(text: str) -> str:
    return _OPTION_PREFIX.sub("", text.strip(), count=1).strip()


def clean_analysis(value: object) -> str:
    text = cell_to_str(value).strip()
    if text.lower() in _ANALYSIS_PLACEHOLDERS or text in _ANALYSIS_PLACEHOLDERS:
        return ""
    return text
