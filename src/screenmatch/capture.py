"""普通屏幕截图。坐标使用系统给的像素，不做焦点伪装。"""

from __future__ import annotations

import hashlib

import numpy as np


def normalize_region(region: dict) -> dict:
    try:
        top = int(region["top"])
        left = int(region["left"])
        width = int(region["width"])
        height = int(region["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("截图区域无效") from exc
    if width < 20 or height < 20:
        raise ValueError("区域太小")
    return {"top": top, "left": left, "width": width, "height": height}


def top_band(image: np.ndarray, fraction: float = 0.45) -> np.ndarray:
    """先看画面上半截，题干通常在选项上面。不够再识别整张。"""
    arr = np.asarray(image)
    if arr.ndim < 2:
        return arr
    height = int(arr.shape[0])
    if height < 2:
        return arr
    cut = max(1, min(height, int(height * fraction)))
    return arr[:cut]


def image_signature(image: np.ndarray) -> str:
    """把画面收成粗颗粒指纹。同一档亮度里的细小闪烁不会变成新题目。"""
    arr = np.asarray(image)
    if arr.size == 0:
        return "empty"
    if arr.ndim == 3:
        gray = arr[..., :3].astype(np.float32).mean(axis=2)
    elif arr.ndim == 2:
        gray = arr.astype(np.float32)
    else:
        return "empty"
    height, width = gray.shape[:2]
    if height < 1 or width < 1:
        return "empty"
    ys = np.clip((np.arange(32) * (height / 32)).astype(int), 0, height - 1)
    xs = np.clip((np.arange(32) * (width / 32)).astype(int), 0, width - 1)
    small = gray[ys][:, xs]
    quant = np.clip(small // 16, 0, 15).astype(np.uint8)
    return hashlib.sha256(quant.tobytes()).hexdigest()


def bgra_to_bgr(image: np.ndarray) -> np.ndarray:
    arr = np.asarray(image)
    if arr.ndim == 3 and arr.shape[2] == 4:
        return arr[:, :, :3]
    return arr


class MssGrabber:
    """mss 的普通区域截图。调用方只在监听线程里使用它。"""

    def __init__(self) -> None:
        import mss

        self._sct = mss.mss()

    def grab(self, region: dict) -> np.ndarray:
        shot = self._sct.grab(normalize_region(region))
        return np.asarray(shot)

    def close(self) -> None:
        close = getattr(self._sct, "close", None)
        if close:
            close()
