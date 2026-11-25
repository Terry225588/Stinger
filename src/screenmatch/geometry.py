"""屏幕矩形是否重叠。用来提醒答案面板不要盖住识别区域。"""

from __future__ import annotations


def rectangles_overlap(first: dict, second: dict) -> bool:
    first_right = int(first["left"]) + int(first["width"])
    first_bottom = int(first["top"]) + int(first["height"])
    second_right = int(second["left"]) + int(second["width"])
    second_bottom = int(second["top"]) + int(second["height"])
    separated = (
        first_right <= int(second["left"])
        or second_right <= int(first["left"])
        or first_bottom <= int(second["top"])
        or second_bottom <= int(first["top"])
    )
    return not separated
