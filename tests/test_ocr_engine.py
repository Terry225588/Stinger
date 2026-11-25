"""对一张本地渲染的中文图做一次真实 OCR。

不断言识别率。只确认引擎能从安装包里的模型读出题干和至少三个选项。
"""

from pathlib import Path

import pytest

FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\msyhbd.ttc"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
    Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
)


def _cjk_font() -> Path | None:
    for path in FONT_CANDIDATES:
        if path.is_file():
            return path
    return None


def test_rapidocr_reads_a_rendered_chinese_question():
    pytest.importorskip("rapidocr_onnxruntime")
    font_path = _cjk_font()
    if font_path is None:
        pytest.skip("没有中文字体（Windows 的 msyh.ttc 或 Linux 的文泉驿/Droid），无法生成测试图")
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np

    from screenmatch.ocr_engine import RapidOcrEngine
    from screenmatch.ocr_text import parse_ocr_text

    font = ImageFont.truetype(str(font_path), 42)
    lines = [
        "传输层负责端到端的可靠传输",
        "A. 流量控制",
        "B. 差错控制",
        "C. 路由选择",
        "D. 调制解调",
    ]
    image = Image.new("RGB", (1100, 420), "white")
    draw = ImageDraw.Draw(image)
    y = 30
    for line in lines:
        draw.text((40, y), line, fill="black", font=font)
        y += 72
    engine = RapidOcrEngine()
    text = engine.recognize(np.array(image))
    parsed = parse_ocr_text(text)
    compact = "".join(text.split())
    assert "传输" in compact or "传输" in parsed.fingerprint
    bodies = "".join(parsed.options.values())
    hits = sum(token in bodies or token in compact for token in ("流量", "差错", "路由", "调制"))
    assert hits >= 3
    assert len(parsed.options) >= 3
