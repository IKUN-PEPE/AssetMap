from pathlib import Path

from asset_mapping_screenshot_xlsx.gui import (
    GuiLogBuffer,
    QueueLogHandler,
    build_default_form_values,
    coerce_form_values,
    open_path,
)


def test_build_default_form_values_matches_current_defaults():
    values = build_default_form_values()
    assert values["max_items"] == "0"
    assert values["concurrency"] == "5"
    assert values["retry_count"] == "1"


def test_coerce_form_values_converts_strings_to_runtime_types(tmp_path):
    values = coerce_form_values(
        input_path="input.xlsx",
        max_items="10",
        concurrency="3",
        retry_count="1",
        timeout_sec="20",
        wait_after_load="2",
        skip_existing=True,
        headful=False,
        base_dir=tmp_path,
    )
    assert values["input_path"].name == "input.xlsx"
    assert values["max_items"] == 10
    assert values["concurrency"] == 3


def test_gui_log_buffer_collects_formatted_messages():
    buffer = GuiLogBuffer()
    buffer.append("INFO", "hello")
    buffer.append("ERROR", "boom")
    assert buffer.drain() == ["[INFO] hello", "[ERROR] boom"]


def test_queue_log_handler_pushes_records_into_buffer():
    import logging

    buffer = GuiLogBuffer()
    handler = QueueLogHandler(buffer)
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello %s", ("gui",), None)
    handler.emit(record)
    assert buffer.drain() == ["[INFO] hello gui"]


def test_gui_file_contains_direct_script_import_fallback():
    gui_path = Path(__file__).resolve().parent / "gui.py"
    source = gui_path.read_text(encoding="utf-8")
    assert "if __package__ in {None, \"\"}" in source
    assert "sys.path.insert" in source
