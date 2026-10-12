# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""F1: TFP_AuthManager 认证管理器测试

覆盖：登录/登出/Token刷新/会话恢复/权限检查（Fail-Closed）/订阅匹配/显示等级派生。
所有网络请求通过 monkeypatch requests 模拟，不访问真实后端。
"""
import requests
import pytest
from datetime import datetime, timedelta

from build_mode import BACKEND_HOST, BACKEND_PORT, LOCAL_HOST_IP, LOCAL_HOST_NAME

from tfp_auth.tfp_auth_manager import (
    TFP_AuthManager,
    TFP_UserInfo,
    TFP_LicenseInfo,
    TFP_CompanyInfo,
    _is_dev_host,
    _is_local_url,
    _derive_display_tier_local,
    _toolkit_contains_tool,
)


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


def _login_payload():
    return {
        "success": True,
        "data": {
            "user": {"id": 7, "username": "alice", "user_type": "individual"},
            "session_token": "session-abc",
            "refresh_token": "refresh-def",
            "expires_at": (datetime.now() + timedelta(hours=1)).isoformat(),
            "tool_subscriptions": [],
            "display_tier": {"display_tier": "free", "display_tier_color": "gray"},
        },
    }


def test_singleton(mgr):
    assert TFP_AuthManager() is mgr


# ========== 后端 URL 安全 ==========

def test_set_backend_url_local_http_allowed(mgr):
    assert mgr.set_backend_url(f"http://{BACKEND_HOST}:{BACKEND_PORT}") is True
    assert mgr.backend_url == f"http://{BACKEND_HOST}:{BACKEND_PORT}"


def test_set_backend_url_private_http_allowed(mgr):
    assert mgr.set_backend_url("http://192.168.1.5:8080") is True


def test_set_backend_url_public_http_rejected(mgr):
    # 生产环境禁止向公网 HTTP 地址发送 Token
    assert mgr.set_backend_url("http://8.8.8.8:8080") is False
    assert mgr.backend_url != "http://8.8.8.8:8080"


def test_set_backend_url_https_allowed(mgr):
    assert mgr.set_backend_url("https://tabulexflow.com") is True


def test_set_backend_url_production_rejects_local(mgr, monkeypatch):
    # 生产模式（IS_PRODUCTION_BUILD=True, IS_LOCAL_TEST_BUILD=False）：拒绝所有本地地址（回环 + 内网IP）
    monkeypatch.setattr("tfp_auth.tfp_auth_manager.IS_PRODUCTION_BUILD", True)
    monkeypatch.setattr("tfp_auth.tfp_auth_manager.IS_LOCAL_TEST_BUILD", False)
    monkeypatch.setattr("tfp_auth.tfp_auth_manager._TRUSTED_BACKEND_HOST", "tabulexflow.com")
    assert mgr.set_backend_url(f"http://{BACKEND_HOST}:{BACKEND_PORT}") is False
    assert mgr.set_backend_url("http://192.168.1.5:8080") is False
    assert mgr.set_backend_url("https://tabulexflow.com") is True


def test_set_backend_url_production_rejects_untrusted_https(mgr, monkeypatch):
    # L-3（2026-09-01）：生产模式仅允许唯一可信后端域名，拒绝任意其他 HTTPS 主机
    monkeypatch.setattr("tfp_auth.tfp_auth_manager.IS_PRODUCTION_BUILD", True)
    monkeypatch.setattr("tfp_auth.tfp_auth_manager.IS_LOCAL_TEST_BUILD", False)
    monkeypatch.setattr("tfp_auth.tfp_auth_manager._TRUSTED_BACKEND_HOST", "tabulexflow.com")
    assert mgr.set_backend_url("https://evil.example.com") is False
    assert mgr.backend_url != "https://evil.example.com"
    assert mgr.set_backend_url("https://tabulexflow.com:8443") is True  # 可信域名任意端口允许
    assert mgr.set_backend_url("https://tabulexflow.com") is True


def test_is_trusted_host(monkeypatch):
    monkeypatch.setattr("tfp_auth.tfp_auth_manager._TRUSTED_BACKEND_HOST", "backend.example.com")
    from tfp_auth.tfp_auth_manager import TFP_AuthManager
    assert TFP_AuthManager._is_trusted_host("https://backend.example.com") is True
    assert TFP_AuthManager._is_trusted_host("https://backend.example.com:8443") is True
    assert TFP_AuthManager._is_trusted_host("https://evil.example.com") is False


def test_set_backend_url_localtest_allows_local(mgr, monkeypatch):
    # 本地测试构建（IS_PRODUCTION_BUILD=True, IS_LOCAL_TEST_BUILD=True）：允许本地地址
    monkeypatch.setattr("tfp_auth.tfp_auth_manager.IS_PRODUCTION_BUILD", True)
    monkeypatch.setattr("tfp_auth.tfp_auth_manager.IS_LOCAL_TEST_BUILD", True)
    assert mgr.set_backend_url(f"http://{BACKEND_HOST}:{BACKEND_PORT}") is True
    assert mgr.set_backend_url("http://192.168.1.5:8080") is True
    assert mgr.set_backend_url("https://tabulexflow.com") is True


def test_is_local_url():
    assert _is_local_url(f"http://{LOCAL_HOST_NAME}:{BACKEND_PORT}") is True
    assert _is_local_url(f"http://{LOCAL_HOST_IP}:{BACKEND_PORT}") is True
    assert _is_local_url("http://192.168.1.1") is True
    assert _is_local_url("http://10.0.0.1") is True
    assert _is_local_url("http://8.8.8.8") is False


def test_is_dev_host():
    assert _is_dev_host(LOCAL_HOST_NAME) is True
    assert _is_dev_host(LOCAL_HOST_IP) is True
    assert _is_dev_host("::1") is True
    assert _is_dev_host("192.168.1.1") is True
    assert _is_dev_host("www.example.com") is False


# ========== 登录 / 登出 ==========

def test_login_success(mgr, monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(_login_payload()))
    result = mgr.login_user("alice", "pw")
    assert result["success"] is True
    assert mgr.get_session_token() == "session-abc"
    assert mgr.get_current_user() is not None
    assert mgr.get_current_user().id == 7
    assert mgr.is_user_logged_in() is True


def test_login_failure(mgr, monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse({"success": False, "message": "密码错误"}))
    result = mgr.login_user("alice", "wrong")
    assert result["success"] is False
    assert mgr.is_user_logged_in() is False


def test_login_network_error(mgr, monkeypatch):
    def _raise(*a, **k):
        raise requests.exceptions.ConnectionError()
    monkeypatch.setattr(requests, "post", _raise)
    result = mgr.login_user("alice", "pw")
    assert result["success"] is False


def test_logout(mgr, monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse({}))
    mgr._session_token = "session-abc"
    mgr._user = TFP_UserInfo(id=7, username="alice")
    assert mgr.logout_user() is True
    assert mgr.is_user_logged_in() is False


def test_is_user_logged_in_requires_token_and_user(mgr):
    assert mgr.is_user_logged_in() is False
    mgr._session_token = "t"
    mgr._user = TFP_UserInfo(id=1, username="u")
    assert mgr.is_user_logged_in() is True


def test_is_user_logged_in_expired_clears(mgr):
    mgr._session_token = "t"
    mgr._user = TFP_UserInfo(id=1, username="u")
    mgr._token_expiry = datetime.now() - timedelta(minutes=1)
    assert mgr.is_user_logged_in() is False
    assert mgr._session_token is None  # 过期即清除


# ========== Token 刷新 ==========

def test_refresh_session_no_token(mgr):
    mgr._refresh_token = None
    result = mgr.refresh_session()
    assert result["success"] is False


def test_refresh_session_success(mgr, monkeypatch):
    payload = _login_payload()
    payload["data"]["session_token"] = "new-session"
    payload["data"]["refresh_token"] = "new-refresh"
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(payload))
    mgr._refresh_token = "refresh-def"
    result = mgr.refresh_session()
    assert result["success"] is True
    assert mgr.get_session_token() == "new-session"


def test_refresh_session_failure_clears_token(mgr, monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse({"success": False, "message": "无效"}))
    mgr._refresh_token = "refresh-def"
    result = mgr.refresh_session()
    assert result["success"] is False
    assert mgr._refresh_token is None


def test_ensure_token_valid_near_expiry_refreshes(mgr, monkeypatch):
    # 距过期 <5 分钟阈值，应触发自动刷新
    payload = _login_payload()
    payload["data"]["session_token"] = "refreshed-session"
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(payload))
    mgr._session_token = "old"
    mgr._refresh_token = "refresh-def"
    mgr._token_expiry = datetime.now() + timedelta(minutes=3)
    mgr._ensure_token_valid()
    assert mgr.get_session_token() == "refreshed-session"


def test_ensure_token_valid_expired_no_refresh_clears(mgr, monkeypatch):
    mgr._session_token = "old"
    mgr._refresh_token = None
    mgr._token_expiry = datetime.now() - timedelta(minutes=1)
    mgr._ensure_token_valid()
    assert mgr._session_token is None


# ========== 权限检查 Fail-Closed ==========

def test_check_tool_access_allowed(mgr, monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse({"allowed": True}))
    result = mgr.check_tool_access("TabulexBomComparator")
    assert result["allowed"] is True


def test_check_tool_access_denied(mgr, monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse({"allowed": False, "reason": "x"}))
    result = mgr.check_tool_access("TabulexBomComparator")
    assert result["allowed"] is False


def test_check_tool_access_connection_error_fail_closed(mgr, monkeypatch):
    def _raise(*a, **k):
        raise requests.exceptions.ConnectionError()
    monkeypatch.setattr(requests, "get", _raise)
    result = mgr.check_tool_access("TabulexBomComparator")
    assert result["allowed"] is False
    assert result["reason"] == "backend_unavailable"


def test_check_tool_access_timeout_fail_closed(mgr, monkeypatch):
    def _raise(*a, **k):
        raise requests.exceptions.Timeout()
    monkeypatch.setattr(requests, "get", _raise)
    result = mgr.check_tool_access("TabulexBomComparator")
    assert result["allowed"] is False
    assert result["reason"] == "backend_timeout"


def test_check_tool_access_unknown_error_fail_closed(mgr, monkeypatch):
    def _raise(*a, **k):
        raise ValueError("boom")
    monkeypatch.setattr(requests, "get", _raise)
    result = mgr.check_tool_access("TabulexBomComparator")
    assert result["allowed"] is False
    assert result["reason"] == "backend_error"


def test_check_tool_access_unexpected_response_fail_closed(mgr, monkeypatch):
    # 后端返回非字典/缺 allowed 字段 → 必须拒绝
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(["not", "dict"]))
    result = mgr.check_tool_access("TabulexBomComparator")
    assert result["allowed"] is False
    assert result["reason"] == "unexpected_response"


def test_check_feature_access_fail_closed(mgr, monkeypatch):
    def _raise(*a, **k):
        raise requests.exceptions.ConnectionError()
    monkeypatch.setattr(requests, "get", _raise)
    result = mgr.check_feature_access("TabulexBomComparator", "export")
    assert result["allowed"] is False
    assert result["reason"] == "backend_unavailable"


# ========== 订阅匹配 ==========

def test_toolkit_contains_tool():
    assert _toolkit_contains_tool("TFP_CORE", "TabulexBomComparator") is True
    assert _toolkit_contains_tool("TFP_CORE", "PalletLayout") is True
    assert _toolkit_contains_tool("TFP_CORE", "Unknown") is False
    assert _toolkit_contains_tool(None, "TabulexBomComparator") is False


def test_has_tool_subscription_single_tool(mgr):
    mgr._user = TFP_UserInfo(
        user_type="individual",
        tool_subscriptions=[{"subscription_type": "single_tool", "tool_ident": "TabulexBomComparator"}],
    )
    assert mgr.has_tool_subscription("TabulexBomComparator") is True
    assert mgr.has_tool_subscription("PalletLayout") is False


def test_has_tool_subscription_toolkit(mgr):
    mgr._user = TFP_UserInfo(
        user_type="individual",
        tool_subscriptions=[{"subscription_type": "toolkit", "toolkit_id": "TFP_CORE"}],
    )
    assert mgr.has_tool_subscription("TabulexBomComparator") is True


def test_has_tool_subscription_enterprise_gift(mgr):
    mgr._user = TFP_UserInfo(
        user_type="enterprise",
        tool_subscriptions=[{"subscription_type": "enterprise"}],
    )
    assert mgr.has_tool_subscription("PalletLayout") is True


def test_has_tool_subscription_platform_always(mgr):
    mgr._user = TFP_UserInfo(user_type="platform")
    assert mgr.has_tool_subscription("Anything") is True


def test_has_tool_subscription_no_user(mgr):
    mgr._user = None
    assert mgr.has_tool_subscription("TabulexBomComparator") is False


# ========== 显示等级派生 ==========

def test_derive_display_tier_local():
    assert _derive_display_tier_local("platform", False) == ("platform", "red")
    assert _derive_display_tier_local("enterprise", False, "admin") == ("enterprise_admin", "blue")
    assert _derive_display_tier_local("enterprise", False, "member") == ("enterprise", "blue")
    assert _derive_display_tier_local("individual", True) == ("premium", "gold")
    assert _derive_display_tier_local("individual", False) == ("free", "gray")


def test_userinfo_from_dict_legacy_user_type():
    u = TFP_UserInfo.from_dict({"user_type": "admin"})
    assert u.user_type == "platform"
    u2 = TFP_UserInfo.from_dict({"user_type": "free"})
    assert u2.user_type == "individual"
    u3 = TFP_UserInfo.from_dict({"user_type": "premium"})
    assert u3.user_type == "individual"


def test_userinfo_display_tier_derived():
    u = TFP_UserInfo.from_dict({"user_type": "individual", "tool_subscriptions": [{"x": 1}]})
    assert u.display_tier == "premium"
    u2 = TFP_UserInfo.from_dict({"user_type": "enterprise", "company_role": "admin"})
    assert u2.display_tier == "enterprise_admin"


# ========== 数据模型 ==========

def test_user_info_methods():
    u = TFP_UserInfo(user_type="individual", company_role=None, display_tier="free")
    assert u.is_individual() is True
    assert u.is_platform() is False
    assert u.is_company_admin() is False
    u2 = TFP_UserInfo(user_type="enterprise", company_role="admin")
    assert u2.is_company_admin() is True
    u3 = TFP_UserInfo(user_type="platform")
    assert u3.is_platform() is True


def test_license_info():
    lic = TFP_LicenseInfo(license_type="premium", features=["export"])
    assert lic.is_premium() is True
    assert lic.has_feature("export") is True
    assert lic.has_feature("nope") is False
    unlimited = TFP_LicenseInfo(features=["unlimited"])
    assert unlimited.has_feature("anything") is True
    free = TFP_LicenseInfo(license_type="free")
    assert free.is_premium() is False


def test_company_info():
    c = TFP_CompanyInfo(license_count=5, used_license_count=3)
    assert c.has_available_license() is True
    assert c.available_licenses() == 2
    c2 = TFP_CompanyInfo(license_count=2, used_license_count=5)
    assert c2.available_licenses() == 0


def test_get_auth_headers(mgr):
    assert mgr.get_auth_headers() == {}
    mgr._session_token = "tok"
    mgr._user = TFP_UserInfo(id=9, username="u")
    headers = mgr.get_auth_headers()
    assert headers["Authorization"] == "Bearer tok"
    assert headers["X-User-ID"] == "9"


def test_auth_change_callback(mgr):
    calls = []
    mgr.add_auth_change_callback(lambda: calls.append(1))
    mgr.add_auth_change_callback(lambda: calls.append(1))
    mgr._notify_auth_change()
    assert len(calls) == 2
    mgr.remove_auth_change_callback(lambda: None)  # 不存在的回调应静默
    assert len(calls) == 2
