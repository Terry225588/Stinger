"""把 OCR 文本拆成题干和 A–F 选项。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from screenmatch.normalize import normalize_match_text, stem_fingerprint, to_halfwidth

_CHROME = {
    "上一题",
    "下一题",
    "提交",
    "提交答案",
    "收藏",
    "收藏本题",
    "标记本题",
}
_CHROME_NORM = {normalize_match_text(item) for item in _CHROME}
_LINE_OPTION = re.compile(r"^\s*([A-F])\s*[.、．:：)）]\s*(.*)$", re.IGNORECASE)
_INLINE_OPTION = re.compile(r"([A-F])\s*[.、．:：)）]\s*", re.IGNORECASE)
_STOP_LINE = re.compile(r"^(?:解析|试题解析|答案|我的答案|正确答案)\s*[:：]")
_JUDGMENT_WORD = {
    "正确": "正确",
    "对": "正确",
    "错误": "错误",
    "错": "错误",
}


@dataclass(frozen=True)
class ParsedScreen:
    raw: str
    stem: str
    options: dict[str, str]
    fingerprint: str


def parse_ocr_text(raw: str) -> ParsedScreen:
    lines = _prepare_lines(raw or "")
    options, first_index = _options_from_lines(lines)
    if len(options) >= 2 and first_index is not None:
        stem = "\n".join(lines[:first_index]).strip()
    else:
        inline_options, inline_stem = _options_inline("\n".join(lines))
        if len(inline_options) >= 2:
            options = inline_options
            stem = inline_stem.strip()
        else:
            judged = _judgment_options(lines)
            if len(judged) >= 2:
                options = judged
                stem = "\n".join(
                    line
                    for line in lines
                    if normalize_match_text(line) not in _JUDGMENT_WORD
                ).strip()
            else:
                stem = "\n".join(lines).strip()
                options = options if len(options) >= 2 else {}
    return ParsedScreen(
        raw=raw or "",
        stem=stem,
        options=options,
        fingerprint=stem_fingerprint(stem),
    )


def join_ocr_lines(result: list) -> str:
    """按框的垂直位置把 RapidOCR 的分块收成多行文本。"""
    rows: list[tuple[float, float, str]] = []
    for item in result:
        if not item or len(item) < 2:
            continue
        box, text = item[0], str(item[1]).strip()
        if not text or not box:
            continue
        ys = [float(point[1]) for point in box]
        xs = [float(point[0]) for point in box]
        rows.append((sum(ys) / len(ys), min(xs), text))
    rows.sort()
    lines: list[list[tuple[float, str]]] = []
    current_y: float | None = None
    for y, x, text in rows:
        if current_y is None or abs(y - current_y) > 18:
            lines.append([(x, text)])
            current_y = y
        else:
            lines[-1].append((x, text))
    rendered: list[str] = []
    for line in lines:
        line.sort()
        rendered.append(" ".join(part for _, part in line if part))
    return "\n".join(rendered)


def _prepare_lines(raw: str) -> list[str]:
    text = to_halfwidth(raw).replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if normalize_match_text(stripped) in _CHROME_NORM:
            continue
        lines.append(stripped)
    return lines


def _explode(letter: str, body: str) -> list[tuple[str, str]]:
    matches = list(_INLINE_OPTION.finditer(body))
    if not matches:
        text = body.strip()
        return [(letter, text)] if text else []
    parts = [(letter, body[: matches[0].start()].strip())]
    for index, match in enumerate(matches):
        nxt = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        parts.append((match.group(1).upper(), body[match.end() : nxt].strip()))
    return [(item_letter, text) for item_letter, text in parts if text]


def _options_from_lines(lines: list[str]) -> tuple[dict[str, str], int | None]:
    found: dict[str, str] = {}
    first: int | None = None
    last: str | None = None
    for index, line in enumerate(lines):
        match = _LINE_OPTION.match(line)
        if match:
            if first is None:
                first = index
            for letter, body in _explode(match.group(1).upper(), match.group(2)):
                found[letter] = body
                last = letter
            continue
        if found and _STOP_LINE.match(line):
            break
        if last and line and not re.match(r"^\d{1,3}\s*[.、．]", line):
            found[last] = f"{found[last]} {line}".strip()
    return found, first


def _options_inline(text: str) -> tuple[dict[str, str], str]:
    matches = list(_INLINE_OPTION.finditer(text))
    if len(matches) < 2:
        return {}, text
    start = 0
    for index, match in enumerate(matches):
        if match.group(1).upper() == "A":
            start = index
            break
    chosen: list[tuple[str, int, int]] = []
    for match in matches[start:]:
        letter = match.group(1).upper()
        if any(letter == item[0] for item in chosen):
            break
        if chosen and ord(letter) < ord(chosen[-1][0]):
            break
        chosen.append((letter, match.start(), match.end()))
        if len(chosen) == 6:
            break
    if len(chosen) < 2:
        return {}, text
    options: dict[str, str] = {}
    for index, (letter, _start, end) in enumerate(chosen):
        nxt = chosen[index + 1][1] if index + 1 < len(chosen) else len(text)
        body = text[end:nxt].strip(" \t\n")
        if body:
            options[letter] = body
    stem = text[: chosen[0][1]].strip()
    return options, stem


def _judgment_options(lines: list[str]) -> dict[str, str]:
    ordered: list[str] = []
    for line in lines:
        label = _JUDGMENT_WORD.get(normalize_match_text(line))
        if label and label not in ordered:
            ordered.append(label)
    if ordered != ["正确", "错误"] and ordered != ["错误", "正确"]:
        return {}
    return {chr(ord("A") + index): label for index, label in enumerate(ordered)}
