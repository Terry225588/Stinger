"""快捷键。只用窗口绑定，或 Windows 上登记的热键。不安装键盘钩子。"""

from __future__ import annotations

import re

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001

DEFAULT_FRAME = "Ctrl+Alt+F"
DEFAULT_PAUSE = "Ctrl+Alt+P"

_MOD_NAMES = {
    "ctrl": "Control",
    "control": "Control",
    "alt": "Alt",
    "shift": "Shift",
}
_MOD_BITS = {
    "Control": MOD_CONTROL,
    "Alt": MOD_ALT,
    "Shift": MOD_SHIFT,
}


def parse_accelerator(text: str) -> tuple[str, int, int] | None:
    """返回 Tk 序列、修饰键位、虚拟键码。无法识别时返回 None。"""
    raw = (text or "").strip().replace("＋", "+")
    if not raw:
        return None
    parts = [part.strip() for part in re.split(r"[+\-\s]+", raw) if part.strip()]
    if len(parts) < 2:
        return None
    mods: list[str] = []
    key = parts[-1]
    for part in parts[:-1]:
        name = _MOD_NAMES.get(part.lower())
        if name is None or name in mods:
            return None
        mods.append(name)
    sequence_key, vk = _key_code(key)
    if sequence_key is None or vk is None:
        return None
    bits = MOD_NOREPEAT
    for name in mods:
        bits |= _MOD_BITS[name]
    tk = "<" + "-".join([*mods, sequence_key]) + ">"
    return tk, bits, vk


def _key_code(key: str) -> tuple[str | None, int | None]:
    if re.fullmatch(r"[A-Za-z]", key):
        letter = key.lower()
        return letter, ord(letter.upper())
    match = re.fullmatch(r"[Ff](\d{1,2})", key)
    if match:
        number = int(match.group(1))
        if 1 <= number <= 12:
            return f"F{number}", 0x70 + number - 1
    return None, None


def register_hotkey(user32, hwnd, hotkey_id: int, mods: int, vk: int) -> bool:
    return bool(user32.RegisterHotKey(hwnd, int(hotkey_id), int(mods), int(vk)))


def unregister_hotkey(user32, hwnd, hotkey_id: int) -> None:
    user32.UnregisterHotKey(hwnd, int(hotkey_id))


def poll_hotkey_ids(user32, hwnd) -> list[int]:
    """只取走 WM_HOTKEY。不读取键盘钩子，也不取走其他消息。"""
    found: list[int] = []
    message = user32.MSG()
    while user32.PeekMessageW(message, hwnd, WM_HOTKEY, WM_HOTKEY, PM_REMOVE):
        found.append(int(message.wParam))
    return found
