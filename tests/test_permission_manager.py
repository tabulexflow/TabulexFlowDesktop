# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""TFP_PermissionManager 权限管理测试

覆盖：权限定义加载、本地功能权限检查各分支（未定义/无需订购/企业级/平台/已订购/未订购）、
未登录返回 login_required、缓存清理。
"""
import pytest

from tfp_auth.tfp_auth_manager import TFP_UserInfo
from tfp_auth.tfp_permission_manager import TFP_PermissionManager

_TOOLS_DATA = {
    "tools_remote_program": [
        {
            "tool_ident": "TabulexBomComparator",
            "feature_permissions": [
                {"feature_key": "export", "requires_subscription": True},
                {"feature_key": "compare", "requires_subscription": False},
                {"feature_key": "enterprise_only", "requires_subscription": True,
                 "requires_enterprise_subscription": True},
                {"feature_key": "free_limited", "requires_subscription": True,
                 "free_usage_limit": 3},
            ],
        }
    ],
    "tools_remote_webpage": [],
}


@pytest.fixture()
def pm():
    TFP_PermissionManager._instance = None
    obj = TFP_PermissionManager()
    yield obj
    TFP_PermissionManager._instance = None


# ========== 权限定义加载 ==========

def test_load_feature_permissions(pm):
    pm.load_feature_permissions_from_tools(_TOOLS_DATA)
    feature = pm.get_feature_permission_local("TabulexBomComparator", "export")
    assert feature is not None
    assert feature["feature_key"] == "export"
    assert pm.get_feature_permission_local("TabulexBomComparator", "missing") is None


def test_load_feature_permissions_from_json(pm, tmp_path):
    import json as _json
    path = tmp_path / "tools.json"
    path.write_text(_json.dumps(_TOOLS_DATA), encoding="utf-8")
    pm.load_feature_permissions_from_json(str(path))
    assert pm.get_feature_permission_local("TabulexBomComparator", "export") is not None


def test_clear_cache(pm):
    pm.load_feature_permissions_from_tools(_TOOLS_DATA)
    pm.clear_cache()
    assert pm._permission_cache == {}
    assert pm._feature_cache == {}


# ========== 本地功能权限检查 ==========

def test_check_no_permission_defined(pm, mgr):
    mgr._user = TFP_UserInfo(user_type="individual")
    result = pm.check_feature_permission_local("TabulexBomComparator", "not_defined", "individual")
    assert result["allowed"] is True
    assert result["reason"] == "no_permission_defined"


def test_check_no_subscription_required(pm, mgr):
    pm.load_feature_permissions_from_tools(_TOOLS_DATA)
    mgr._user = TFP_UserInfo(user_type="individual")
    result = pm.check_feature_permission_local("TabulexBomComparator", "compare", "individual")
    assert result["allowed"] is True


def test_check_subscription_required_denied(pm, mgr):
    pm.load_feature_permissions_from_tools(_TOOLS_DATA)
    mgr._user = TFP_UserInfo(user_type="individual", tool_subscriptions=[])
    result = pm.check_feature_permission_local("TabulexBomComparator", "export", "individual")
    assert result["allowed"] is False
    assert result["reason"] == "subscription_required"
    assert result["required_type"] == "toolkit"


def test_check_subscription_required_allowed(pm, mgr):
    pm.load_feature_permissions_from_tools(_TOOLS_DATA)
    mgr._user = TFP_UserInfo(
        user_type="individual",
        tool_subscriptions=[{"subscription_type": "single_tool", "tool_ident": "TabulexBomComparator"}],
    )
    result = pm.check_feature_permission_local("TabulexBomComparator", "export", "individual")
    assert result["allowed"] is True


def test_check_platform_always_allowed(pm, mgr):
    pm.load_feature_permissions_from_tools(_TOOLS_DATA)
    mgr._user = TFP_UserInfo(user_type="platform")
    result = pm.check_feature_permission_local("TabulexBomComparator", "export", "platform")
    assert result["allowed"] is True


def test_check_enterprise_feature_enterprise_user(pm, mgr):
    pm.load_feature_permissions_from_tools(_TOOLS_DATA)
    # 企业成员（非管理员）→ display_tier=enterprise → 允许企业功能
    mgr._user = TFP_UserInfo(user_type="enterprise", company_role="member", display_tier="enterprise")
    result = pm.check_feature_permission_local("TabulexBomComparator", "enterprise_only", "enterprise")
    assert result["allowed"] is True


def test_check_enterprise_feature_individual_denied(pm, mgr):
    pm.load_feature_permissions_from_tools(_TOOLS_DATA)
    mgr._user = TFP_UserInfo(user_type="individual")
    result = pm.check_feature_permission_local("TabulexBomComparator", "enterprise_only", "individual")
    assert result["allowed"] is False
    assert result["reason"] == "enterprise_required"


def test_check_legacy_min_user_type(pm, mgr):
    # 兼容旧配置：min_user_type 非空且非 free 视为 requires_subscription
    data = {
        "tools_remote_program": [
            {"tool_ident": "T", "feature_permissions": [
                {"feature_key": "f", "min_user_type": "premium"}]}
        ],
        "tools_remote_webpage": [],
    }
    pm.load_feature_permissions_from_tools(data)
    mgr._user = TFP_UserInfo(user_type="individual", tool_subscriptions=[])
    result = pm.check_feature_permission_local("T", "f", "individual")
    assert result["allowed"] is False


# ========== 入口方法 ==========

def test_check_feature_permission_not_logged_in(pm, mgr):
    mgr._user = None
    mgr._session_token = None
    result = pm.check_feature_permission("TabulexBomComparator", "export", show_dialog=False)
    assert result["allowed"] is False
    assert result["reason"] == "login_required"


def test_check_tool_permission_delegates(mgr, monkeypatch):
    pm = TFP_PermissionManager()
    monkeypatch.setattr(mgr, "check_tool_access", lambda tool: {"allowed": True, "reason": "ok"})
    result = pm.check_tool_permission("TabulexBomComparator", show_dialog=False)
    assert result["allowed"] is True


def test_is_feature_accessible(mgr, monkeypatch):
    pm = TFP_PermissionManager()
    monkeypatch.setattr(mgr, "check_feature_access", lambda t, f: {"allowed": True})
    assert pm.is_feature_accessible("TabulexBomComparator", "export") is True
