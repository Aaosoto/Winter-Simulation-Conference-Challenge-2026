"""
Unit tests for the LogUtils module in o2des.utils.

This module verifies the functionality of logging utilities, including:
- Singleton logger behavior and reset
- Log message transformation
- Console and file handler setup
- Context binding and record mode
- Logging with keyword arguments
- Formatter classes
- Logging at all levels
- Option settings (depth, colors, exception handling)

Uses pytest for assertions and test parametrization.
"""

import time
from pathlib import Path

import pytest

from o2des.utils import LogUtils


def test_singleton_and_reset() -> None:
    LogUtils.reset_logger()
    logger1 = LogUtils.get_logger("test_app")
    logger2 = LogUtils.get_logger("another_app")
    assert logger1 is logger2
    assert logger1.name == "test_app"
    LogUtils.reset_logger()
    logger3 = LogUtils.get_logger("new_app")
    assert logger3 is not logger1
    assert logger3.name == "new_app"

def test_transform_log_message() -> None:
    msg = "{[[user]]} at {[function]} - {status}"
    transformed = LogUtils.transform_log_message(msg)
    assert transformed == "{record[extra][user]} at {record[function]} - {status}"
    msg2 = "{[time]:%H:%M:%S} - {[[value]]:.2f} - {count}"
    transformed2 = LogUtils.transform_log_message(msg2)
    assert transformed2 == "{record[time]:%H:%M:%S} - {record[extra][value]:.2f} - {count}"
    msg3 = "User {user} with status {status}"
    assert LogUtils.transform_log_message(msg3) == msg3

def test_console_handler_and_basic_logging(capsys: pytest.CaptureFixture) -> None:
    LogUtils.reset_logger()
    logger = LogUtils.get_logger("console_test")
    logger.add_console_handler(level="DEBUG", formatter=LogUtils.SimpleFormatter())
    logger.debug("Debug message {x}", x=123)
    logger.info("Info message {y}", y="abc")
    time.sleep(0.1)  # Ensure logs are flushed
    out = capsys.readouterr().out
    assert "Debug message 123" in out
    assert "Info message abc" in out

def test_context_binding_and_record_mode(capsys: pytest.CaptureFixture) -> None:
    LogUtils.reset_logger()
    logger = LogUtils.get_logger("bind_test")
    logger.add_console_handler(level="INFO")
    bound_logger = logger.opt(record=True).bind(user="alice", session="xyz")
    bound_logger.info("{[[user]]} started session {[[session]]}")
    time.sleep(0.1)  # Ensure logs are flushed
    out = capsys.readouterr().out
    assert "alice started session xyz" in out

def test_logging_with_kwargs(capsys: pytest.CaptureFixture) -> None:
    LogUtils.reset_logger()
    logger = LogUtils.get_logger("kwargs_test")
    logger.add_console_handler(level="INFO")
    logger.info("User {user} logged in", user="bob")
    time.sleep(0.1)  # Ensure logs are flushed
    out = capsys.readouterr().out
    assert "User bob logged in" in out

def test_formatter_classes() -> None:
    default = LogUtils.DefaultFormatter()
    simple = LogUtils.SimpleFormatter()
    detailed = LogUtils.DetailedFormatter()
    assert "{message}" in default.get_format()
    assert "{message}" in simple.get_format()
    assert "{message}" in detailed.get_format()
    assert "process" in detailed.get_format()
    assert "thread" in detailed.get_format()

def test_file_handler_creates_log_file(tmp_path: Path) -> None:
    LogUtils.reset_logger()
    logger = LogUtils.get_logger("file_test")
    log_dir = tmp_path / "logs"
    logger.add_file_handler(str(log_dir), level="INFO", formatter=LogUtils.SimpleFormatter(), rotation="1 day")
    logger.info("File log test {val}", val=42)
    files = list(log_dir.iterdir())
    assert any(f.suffix == ".log" for f in files)

def test_log_method(capsys: pytest.CaptureFixture) -> None:
    LogUtils.reset_logger()
    logger = LogUtils.get_logger("log_test")
    logger.add_console_handler(level="INFO")
    logger.log("info", "Log method {x}", x=100)
    logger.log("warning", "Warning log {y}", y="test")
    time.sleep(0.1)  # Ensure logs are flushed
    out = capsys.readouterr().out
    assert "Log method 100" in out
    assert "Warning log test" in out

@pytest.mark.parametrize("level,method", [
    ("trace", "trace"),
    ("debug", "debug"),
    ("info", "info"),
    ("success", "success"),
    ("warning", "warning"),
    ("error", "error"),
    ("critical", "critical"),
])
def test_all_log_levels(capsys: pytest.CaptureFixture, level: str, method: str) -> None:
    LogUtils.reset_logger()
    logger = LogUtils.get_logger("levels_test")
    logger.add_console_handler(level="TRACE")
    getattr(logger, method)("Test {level} log", level=level)
    time.sleep(0.1)  # Ensure logs are flushed
    out = capsys.readouterr().out
    assert f"Test {level} log" in out

def test_opt_depth_and_colors(capsys: pytest.CaptureFixture) -> None:
    LogUtils.reset_logger()
    logger = LogUtils.get_logger("opt_test")
    logger.add_console_handler(level="INFO")
    logger.opt(colors=True).info("<red>Colored {user_msg}</red>", user_msg="output")
    time.sleep(0.1)  # Ensure logs are flushed
    out = capsys.readouterr().out
    assert "Colored output" in out

def test_opt_exception(capsys: pytest.CaptureFixture) -> None:
    LogUtils.reset_logger()
    logger = LogUtils.get_logger("exc_test")
    logger.add_console_handler(
        level="ERROR",
        formatter=LogUtils.DefaultFormatter(include_exception=True)
    )
    try:
        raise ValueError("fail!")
    except Exception as e:
        logger.opt(exception=e).error("Caught exception")
    time.sleep(0.1)  # Ensure logs are flushed
    out = capsys.readouterr().out
    assert "Caught exception" in out
    assert "ValueError" in out
