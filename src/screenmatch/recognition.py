"""识别文字是否和上一题实质相同。空白和标点不算变化。"""

from __future__ import annotations

from screenmatch.normalize import normalize_match_text


def recognition_key(text: str) -> str:
    return normalize_match_text(text or "")


def is_same_recognition(previous: str | None, text: str) -> bool:
    key = recognition_key(text)
    return bool(previous) and previous == key
