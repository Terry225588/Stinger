import tkinter as tk

import pytest

from screenmatch.bank import load_bank
from screenmatch.template_bank import (
    EXAMPLE_ROWS,
    TEMPLATE_HEADERS,
    bundled_template_path,
    export_template,
    write_template,
)


def test_bundled_template_matches_importer_and_is_only_samples():
    path = bundled_template_path()
    assert path is not None
    assert path.name == "stinger-question-template.xlsx"
    bank, report = load_bank(path)
    assert report.rejected == []
    assert report.valid_count == 3
    assert [question.qtype for question in bank.questions] == ["single", "multi", "judgment"]
    assert bank.questions[0].answer == "A"
    assert bank.questions[1].answer == "ABC"
    assert bank.questions[2].answer == "B"
    assert bank.questions[2].options["A"] == "正确"
    assert bank.questions[2].options["B"] == "错误"
    assert all("示例" in question.stem for question in bank.questions)
    assert len(bank.questions) != 1080


def test_template_headers_are_the_supported_columns():
    assert TEMPLATE_HEADERS == [
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
    assert len(EXAMPLE_ROWS) == 3
    assert {row[0] for row in EXAMPLE_ROWS} == {"单选题", "多选题", "判断题"}


def test_export_writes_a_workbook_the_importer_accepts(tmp_path):
    saved = export_template(tmp_path / "导出的模板")
    assert saved.suffix == ".xlsx"
    assert saved.is_file()
    bank, report = load_bank(saved)
    assert report.rejected == []
    assert report.valid_count == 3
    fresh = write_template(tmp_path / "现写.xlsx")
    fresh_bank, fresh_report = load_bank(fresh)
    assert fresh_report.rejected == []
    assert [question.stem for question in fresh_bank.questions] == [
        question.stem for question in bank.questions
    ]


def test_export_action_reports_success_in_chinese(tmp_path):
    from screenmatch.app import App

    try:
        probe = tk.Tk()
        probe.withdraw()
        probe.update()
        probe.destroy()
    except tk.TclError as exc:
        pytest.skip(f"没有可用的图形界面：{exc}")

    app = App(data_dir=tmp_path / "data")
    app.withdraw()
    try:
        found = _button_texts(app)
        assert "导出模板" in found
        saved = app.write_exported_template(str(tmp_path / "从按钮导出.xlsx"))
        assert "已导出模板" in app.status.get()
        shown = app.result.get("1.0", "end")
        assert "题型" in shown
        assert "【示例】" in shown
        bank, report = load_bank(saved)
        assert report.valid_count == 3
    finally:
        app.destroy()


def _button_texts(widget) -> set[str]:
    found: set[str] = set()
    try:
        text = widget.cget("text")
    except tk.TclError:
        text = ""
    if text:
        found.add(str(text))
    for child in widget.winfo_children():
        found.update(_button_texts(child))
    return found


def test_packaged_spec_ships_the_template():
    from pathlib import Path

    spec = (Path(__file__).resolve().parents[1] / "packaging" / "screenmatch.spec").read_text(encoding="utf-8")
    assert "stinger-question-template.xlsx" in spec
