# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""T8.5.1: IPC 能力表与握手能力下限诊断（B2）

覆盖（真实 socket 握手，弹窗 mock、wx.CallAfter 同步化）：
- 子工具上报 sdk_version 低于能力下限 → 弹"工具需更新"诊断（仅诊断不阻断：
  认证成功、连接保持）
- sdk_version 等于下限 / 缺省（旧子工具）/ unknown（SDK 防御回退值）→ 不弹
- 每工具每次启动周期仅弹一次（同 token 重连不重复弹）
- IPC_CAPABILITIES 能力表结构完整性（与 IPC 协议命令/事件列表同步维护）
"""
import json
import socket
import time

import pytest
import wx

from build_mode import IPC_HOST_IP

import tfp_mixins.tfp_tool_ipc_mixin as ipc_mod
from tfp_mixins.tfp_tool_ipc_mixin import TFP_ToolIPCMixin


@pytest.fixture(autouse=True)
def _reset_sdk_floor_warned(monkeypatch):
    """隔离类级"已提示工具"集合（每用例独立）"""
    monkeypatch.setattr(TFP_ToolIPCMixin, '_sdk_floor_warned_tools', set())


@pytest.fixture()
def _raise_floor(monkeypatch):
    """临时抬高能力下限至 9.0.0（默认 1.0.0 等于现网 SDK 版本，不会触发）；
    非 autouse——能力表结构测试需要原始值"""
    caps = dict(ipc_mod.IPC_CAPABILITIES)
    caps['min_sdk_version'] = '9.0.0'
    monkeypatch.setattr(ipc_mod, 'IPC_CAPABILITIES', caps)


@pytest.fixture(autouse=True)
def _sync_callafter(monkeypatch):
    """wx.CallAfter 同步执行，便于在真实 socket 线程回调中直接断言"""
    monkeypatch.setattr(wx, 'CallAfter', lambda fn, *a: fn(*a))


class DummyIPC(TFP_ToolIPCMixin):
    def __init__(self):
        self.embedded_tools = {}


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((IPC_HOST_IP, 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _connect_and_auth(port, token, auth_extra):
    c = socket.create_connection((IPC_HOST_IP, port), timeout=3)
    msg = {"type": "auth", "token": token}
    msg.update(auth_extra)
    c.sendall((json.dumps(msg) + "\n").encode("utf-8"))
    return c


def _wait_auth(host, tool, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if host.embedded_tools[tool].get('client_socket') is not None:
            return True
        time.sleep(0.02)
    return False


def test_handshake_below_floor_warns_and_not_blocking(monkeypatch, _raise_floor):
    """sdk_version 低于下限：弹诊断，且认证成功（仅诊断不阻断）"""
    host = DummyIPC()
    host.embedded_tools["ToolX"] = {}
    prompts = []
    monkeypatch.setattr(host, '_prompt_tool_sdk_below_floor',
                        lambda t, sdk, floor: prompts.append((t, sdk, floor)))
    port = _free_port()
    server_sock, token, _ = host._start_ipc_server("ToolX", port)
    try:
        c = _connect_and_auth(port, token, {"sdk_version": "8.9.9"})
        assert _wait_auth(host, "ToolX")  # 认证成功 = 不阻断
        assert prompts == [("ToolX", "8.9.9", "9.0.0")]
        c.close()
    finally:
        server_sock.close()


def test_handshake_equal_floor_no_warn(monkeypatch, _raise_floor):
    """sdk_version 等于下限：不弹（仅低于才诊断）"""
    host = DummyIPC()
    host.embedded_tools["ToolX"] = {}
    prompts = []
    monkeypatch.setattr(host, '_prompt_tool_sdk_below_floor',
                        lambda t, sdk, floor: prompts.append((t, sdk, floor)))
    port = _free_port()
    server_sock, token, _ = host._start_ipc_server("ToolX", port)
    try:
        c = _connect_and_auth(port, token, {"sdk_version": "9.0.0"})
        assert _wait_auth(host, "ToolX")
        assert prompts == []
        c.close()
    finally:
        server_sock.close()


@pytest.mark.parametrize('auth_extra', [{}, {"sdk_version": "unknown"}])
def test_handshake_missing_or_unknown_sdk_no_warn(monkeypatch, _raise_floor, auth_extra):
    """旧子工具缺省字段（T3 兼容）与 SDK 防御回退值 unknown：均不弹"""
    host = DummyIPC()
    host.embedded_tools["ToolX"] = {}
    prompts = []
    monkeypatch.setattr(host, '_prompt_tool_sdk_below_floor',
                        lambda t, sdk, floor: prompts.append((t, sdk, floor)))
    port = _free_port()
    server_sock, token, _ = host._start_ipc_server("ToolX", port)
    try:
        c = _connect_and_auth(port, token, auth_extra)
        assert _wait_auth(host, "ToolX")
        assert prompts == []
        c.close()
    finally:
        server_sock.close()


def test_handshake_warn_once_per_tool_per_run(monkeypatch, _raise_floor):
    """同工具重连（同 token）：仅首次弹，重连不重复弹（走真实去重逻辑）"""
    boxes = []
    # 不 mock _prompt_tool_sdk_below_floor（保留其去重逻辑），仅静默 wx.MessageBox
    monkeypatch.setattr(wx, 'MessageBox', lambda msg, title, style=0: boxes.append((msg, title)))
    host = DummyIPC()
    host.embedded_tools["ToolX"] = {}
    port = _free_port()
    server_sock, token, _ = host._start_ipc_server("ToolX", port)
    try:
        c1 = _connect_and_auth(port, token, {"sdk_version": "8.9.9"})
        assert _wait_auth(host, "ToolX")
        time.sleep(0.3)  # 等首次诊断弹窗（CallAfter 已同步化）
        assert len(boxes) == 1
        c1.close()
        time.sleep(0.2)  # 等服务端回收 c1
        c2 = _connect_and_auth(port, token, {"sdk_version": "8.9.9"})
        time.sleep(0.3)  # 等第二次握手诊断触发（应被去重）
        assert len(boxes) == 1
        c2.close()
    finally:
        server_sock.close()


def test_ipc_capabilities_structure():
    """能力表结构完整性：命令/事件/上报字段与 IPC 协议命令/事件列表一致"""
    caps = ipc_mod.IPC_CAPABILITIES
    assert caps['min_sdk_version'] == '1.0.0'
    # 主程序可下发的命令（前端→子工具）
    assert set(caps['commands']) == {'show', 'hide', 'minimize', 'maximize', 'close',
                                     'heartbeat', 'auth_update', 'command_unknown'}
    # 主程序可接收的子工具事件（子工具→前端）
    assert set(caps['events']) == {'ready', 'closed', 'hidden', 'error', 'menu_click',
                                   'request_login', 'request_logout', 'api_request',
                                   'check_permission'}
    # 握手认证消息可识别的上报字段（T3）
    assert set(caps['auth_report_fields']) == {'sdk_version', 'frontend_version'}
