# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""前端核心测试 fixtures"""
import sys
import os
import types

# 确保前端工程根目录在 sys.path 中
_fe_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _fe_root not in sys.path:
    sys.path.insert(0, _fe_root)

from build_mode import BACKEND_HOST, BACKEND_PORT, IPC_HOST_IP

# 注入 fake main 模块：tfp_auth_manager.py / tfp_base_tool.py 顶层会 `import main`
# 副作用（DPI 设置、日志初始化、资源检查、GUI 构建），测试环境不应执行。
if 'main' not in sys.modules:
    _fake_main = types.ModuleType('main')
    _fake_main.BACKEND_HOST = BACKEND_HOST
    _fake_main.BACKEND_PORT = BACKEND_PORT
    _fake_main.IPC_HOST = IPC_HOST_IP
    _fake_main.IPC_PORT_BASE = 0
    sys.modules['main'] = _fake_main

import pytest


@pytest.fixture(autouse=True)
def _reset_auth_manager(monkeypatch):
    """每个测试前重置 TFP_AuthManager 单例状态，禁止真实网络/keyring 访问

    注意：不重置 _instance（否则 tfp_permission_manager / tfp_tool_ipc_mixin 等
    模块绑定的 auth_manager 引用会与 fixture 返回的新实例分裂），只清空运行时状态。
    """
    from tfp_auth.tfp_auth_manager import TFP_AuthManager

    # 禁止后台会话验证线程发出真实网络请求
    monkeypatch.setattr(TFP_AuthManager, '_validate_session_async', lambda self: None)

    mgr = TFP_AuthManager()
    mgr._secure_storage = None
    mgr._user = None
    mgr._license = None
    mgr._session_token = None
    mgr._refresh_token = None
    mgr._token_expiry = None
    mgr._auth_change_callbacks = []
    yield mgr
    mgr._user = None
    mgr._license = None
    mgr._session_token = None
    mgr._refresh_token = None
    mgr._token_expiry = None


@pytest.fixture()
def mgr(_reset_auth_manager):
    """返回已重置状态的 TFP_AuthManager 单例"""
    return _reset_auth_manager
