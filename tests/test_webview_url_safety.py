# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""M-2 加固：WebView URL 域名白名单 / helper stdin-only 入口测试

覆盖：tfp_utils/tfp_webview_helper.py 的 is_url_allowed（协议+域名白名单）与
main()（仅 --stdin）；tfp_utils/tfp_webview_fallback.py 的 is_url_trusted
（协议+可信后端域名/当前 backend_url 域名）。
"""
import pytest

from build_mode import BACKEND_HOST

from tfp_utils import tfp_webview_helper as helper
from tfp_utils import tfp_webview_fallback as fallback

_DEV_HOST = str(BACKEND_HOST)  # 测试环境（源码运行）为 127.0.0.1


# ========== helper.is_url_allowed（协议 + 域名白名单） ==========

def test_helper_is_url_allowed_trusted_backend():
    assert helper.is_url_allowed(f"http://{_DEV_HOST}:8080/webpage/remote/X") is True
    assert helper.is_url_allowed(f"https://{_DEV_HOST}/webpage/remote/X") is True


def test_helper_is_url_allowed_phishing_domain_rejected():
    """M-2：非可信后端域名（钓鱼站）必须被拒绝"""
    assert helper.is_url_allowed("https://evil.example.com/login") is False
    assert helper.is_url_allowed("https://www.google.com/") is False


def test_helper_is_url_allowed_bad_protocol_rejected():
    assert helper.is_url_allowed("file:///etc/passwd") is False
    assert helper.is_url_allowed("javascript:alert(1)") is False
    assert helper.is_url_allowed("") is False
    assert helper.is_url_allowed(None) is False


# ========== helper.main（仅 --stdin，位置参数被拒） ==========

def test_helper_main_positional_args_rejected():
    """M-2：位置参数模式必须被拒绝（本地进程无法再用它开任意网页窗口）"""
    assert helper.main(["http://evil.example.com/x", "Phishing"]) == helper.USAGE_EXIT_CODE
    assert helper.main([]) == helper.USAGE_EXIT_CODE


def test_helper_main_stdin_only_rejects_non_json():
    # 无有效 stdin（pytest 下 stdin 为空）：json 解析失败 → usage 错误
    assert helper.main(["--stdin"]) == helper.USAGE_EXIT_CODE


# ========== helper.run_webview_window（恶意 URL 直接拒绝，不进 webview） ==========

def test_helper_run_webview_window_phishing_rejected():
    """恶意域名 URL 在 import webview 之前即拒绝（fail-closed）"""
    code = helper.run_webview_window("https://evil.example.com/login", None, "t")
    assert code == helper.WEBVIEW_ERROR_EXIT_CODE


# ========== fallback.is_url_trusted（协议 + 可信后端域名/当前 backend_url） ==========

def test_fallback_is_url_trusted_backend_consistent():
    # 与 BOTH build_mode 默认域名一致 → 允许
    assert fallback.is_url_trusted(f"https://{_DEV_HOST}/a") is True


def test_fallback_is_url_trusted_current_backend_url_merged():
    # 即使默认域名不同，当前 backend_url 域名也允许（set_backend_url 场景）
    url = "https://tabulexflow.com/webpage/remote/X"
    backend_url = "https://tabulexflow.com:443"
    assert fallback.is_url_trusted(url, backend_url=backend_url) is True


def test_fallback_is_url_trusted_phishing_rejected():
    assert fallback.is_url_trusted("https://evil.example.com/login") is False
    assert fallback.is_url_trusted("https://evil.example.com/login",
                                    backend_url=f"http://{_DEV_HOST}:8080") is False
    assert fallback.is_url_trusted("file:///etc/passwd") is False
    assert fallback.is_url_trusted("") is False
    assert fallback.is_url_trusted(None) is False