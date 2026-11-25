import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "screenmatch_locate_entry", ROOT / "packaging" / "locate_entry.py"
)
_module = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_module)
resolve_entry = _module.resolve_entry


def test_spec_entry_is_repository_root_main_py():
    entry = resolve_entry(ROOT / "packaging" / "screenmatch.spec")
    assert entry == ROOT / "main.py"
    assert entry.is_file()
    spec = (ROOT / "packaging" / "screenmatch.spec").read_text(encoding="utf-8")
    assert "resolve_entry" in spec
    assert '["main.py"]' not in spec


def test_build_script_is_powershell_51_safe():
    raw = (ROOT / "scripts" / "build_windows.ps1").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") or all(byte < 128 for byte in raw)
    text = raw.decode("utf-8-sig")
    assert "%d" not in text
    assert "SCREENMATCH_PYTHON" in text
    assert "LASTEXITCODE" in text
    assert "main.py" in text
    assert "ch_PP-OCRv4_det_infer.onnx" in text
