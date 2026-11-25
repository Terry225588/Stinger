"""本地 RapidOCR。模型来自安装包里的 onnx 文件，这里不调用云端接口。"""

from __future__ import annotations

from pathlib import Path

from screenmatch.capture import bgra_to_bgr
from screenmatch.ocr_text import join_ocr_lines

MODEL_FILES = (
    "ch_PP-OCRv4_det_infer.onnx",
    "ch_PP-OCRv4_rec_infer.onnx",
    "ch_ppocr_mobile_v2.0_cls_infer.onnx",
)


class OcrNotAvailable(RuntimeError):
    pass


def bundled_model_report() -> tuple[Path | None, list[str]]:
    """检查安装包内的模型文件。不下载，也不访问识别接口。"""
    try:
        import rapidocr_onnxruntime
    except Exception as exc:
        return None, [f"没有安装 rapidocr-onnxruntime：{exc}"]
    root = Path(rapidocr_onnxruntime.__file__).resolve().parent / "models"
    missing = [name for name in MODEL_FILES if not (root / name).is_file()]
    return root, missing


class RapidOcrEngine:
    def __init__(self) -> None:
        self._engine = None

    def recognize(self, image) -> str:
        engine = self._ensure()
        prepared = bgra_to_bgr(image)
        result, _elapse = engine(prepared)
        if not result:
            return ""
        return join_ocr_lines(result)

    def _ensure(self):
        if self._engine is not None:
            return self._engine
        _root, missing = bundled_model_report()
        if missing and _root is not None:
            raise OcrNotAvailable(
                "安装目录里缺少本地 OCR 模型："
                + "、".join(missing)
                + "。这些文件应随 rapidocr-onnxruntime 安装包提供，程序不会改为云端识别。"
            )
        try:
            from rapidocr_onnxruntime import RapidOCR
        except Exception as exc:
            raise OcrNotAvailable(
                "没有安装本地 OCR 组件 rapidocr-onnxruntime。"
                "安装依赖时需要联网下载安装包；安装包里带有中文识别模型。"
                "装好之后，识别使用这些本地模型，本程序不会把题目发到云端。"
            ) from exc
        try:
            self._engine = RapidOCR()
        except Exception as exc:
            raise OcrNotAvailable(f"本地 OCR 初始化失败：{exc}") from exc
        return self._engine
