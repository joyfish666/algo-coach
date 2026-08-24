import logging
import logging.handlers

import lc.logutil as logutil


def test_redact_headers_masks_sensitive():
    redacted = logutil.redact_headers(
        {"Cookie": "a=b", "x-csrftoken": "tok", "User-Agent": "UA", "Referer": "R"}
    )
    assert redacted["Cookie"] == "<redacted>"
    assert redacted["x-csrftoken"] == "<redacted>"
    assert redacted["User-Agent"] == "UA"
    assert redacted["Referer"] == "R"


def test_redact_headers_handles_none():
    assert logutil.redact_headers(None) == {}


def test_redact_mapping():
    payload = {"cookie": "secret", "llm_api_key": "sk-1", "model": "m"}
    redacted = logutil.redact_mapping(payload)
    assert redacted["cookie"] == "<redacted>"
    assert redacted["llm_api_key"] == "<redacted>"
    assert redacted["model"] == "m"


def test_setup_logging_debug_and_file(tmp_path):
    log_file = tmp_path / "coach.log"
    logutil.setup_logging(debug=True, log_file=log_file)
    assert logutil.logger.level == logging.DEBUG
    logutil.logger.info("hello-file")
    for handler in logutil.logger.handlers:
        handler.flush()
    assert "hello-file" in log_file.read_text(encoding="utf-8")


def test_setup_logging_info_hides_debug(tmp_path):
    logutil.setup_logging(debug=False)
    assert logutil.logger.level == logging.INFO


def test_setup_logging_replaces_handlers(tmp_path):
    logutil.setup_logging(debug=True)
    count_first = len(logutil.logger.handlers)
    logutil.setup_logging(debug=True)
    assert len(logutil.logger.handlers) == count_first


def test_setup_logging_uses_rotating_file_handler(tmp_path):
    log_file = tmp_path / "coach.log"
    logutil.setup_logging(debug=False, log_file=log_file)
    file_handlers = [
        h
        for h in logutil.logger.handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert len(file_handlers) == 1
    handler = file_handlers[0]
    assert handler.maxBytes == logutil.LOG_MAX_BYTES
    assert handler.backupCount == logutil.LOG_BACKUP_COUNT
