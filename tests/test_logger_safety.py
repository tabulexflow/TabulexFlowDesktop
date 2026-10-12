# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""M-4 加固：日志敏感字段脱敏（SafeFormatter）与 0600/0700 权限测试"""
import logging
import stat

from tfp_utils.tfp_logger import SafeFormatter, _chmod_quiet


def _fmt(msg):
    record = logging.LogRecord("test", logging.INFO, __file__, 1, msg, None, None)
    return SafeFormatter("%(message)s").format(record)


# ========== SafeFormatter 敏感字段脱敏 ==========

def test_redact_bearer_authorization():
    out = _fmt("Forwarding request with Authorization: Bearer secret.token.xyz")
    assert "secret.token.xyz" not in out
    assert "Bearer ***" in out


def test_redact_token_kv():
    out = _fmt("exchanging token=abc123 detail")
    assert "abc123" not in out
    assert "token=***" in out


def test_redact_session_token_kv():
    out = _fmt("session token session_token=xyz-end finish")
    assert "xyz-end" not in out
    assert "session_token=***" in out


def test_redact_password_kv():
    out = _fmt("login password=MyP@ss detail")
    assert "MyP@ss" not in out
    assert "password=***" in out


def test_redact_api_key_kv():
    out = _fmt("using api_key=xxxyyy endpoint")
    assert "xxxyyy" not in out
    assert "api_key=***" in out


def test_normal_message_unchanged():
    msg = "Tool TabulexBomComparator downloaded and extracted successfully"
    assert _fmt(msg) == msg


def test_word_boundary_no_false_positive():
    # "webview_token=" 中 token 前是下划线（词字符），不应被 \btoken 误匹配
    out = _fmt("webview_token=abc123")
    assert out == "webview_token=abc123"


# ========== 权限收紧 ==========

def test_chmod_quiet_dir_0700(tmp_path):
    d = tmp_path / "logs"
    d.mkdir()
    _chmod_quiet(d, 0o700)
    assert stat.S_IMODE(d.stat().st_mode) == 0o700


def test_chmod_quiet_file_0600(tmp_path):
    f = tmp_path / "frontend.log"
    f.write_text("x")
    _chmod_quiet(f, 0o600)
    assert stat.S_IMODE(f.stat().st_mode) == 0o600