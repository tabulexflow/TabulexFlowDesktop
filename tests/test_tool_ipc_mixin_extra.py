# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""T5 补充：tfp_tool_ipc_mixin.py 更多分支覆盖 — 消息分发/API 代理/权限代理/认证更新

目标：提升 IPC 模块（tfp_tool_ipc_mixin.py）覆盖率至 60% 防倒退线。
覆盖：
- _handle_ipc_message 消息分发（heartbeat_ack / ready / 未知事件）
- _handle_ipc_api_request 缺 path 分支
- _send_ipc_api_response 各分支（工具缺失/无 socket/真实发送）
- _handle_ipc_check_permission 无后端 URL 分支
- _send_auth_update_to_tool（登录/未登录/exe 模式）
- _notify_all_exe_tools_auth_changed
- _on_exe_tool_ready / _on_exe_tool_hidden
"""
import json
import pathlib
import socket
import tempfile
import time

import pytest
from unittest.mock import MagicMock

from build_mode import BACKEND_HOST, BACKEND_PORT

from tfp_mixins.tfp_tool_ipc_mixin import TFP_ToolIPCMixin


class DummyIPC(TFP_ToolIPCMixin):
    def __init__(self):
        self.embedded_tools = {}
        self.backend_url = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
        self.user_setting_dir = pathlib.Path(tempfile.gettempdir())
        self._current_active_tool = None


# ========== 消息分发 ==========

def test_handle_ipc_message_heartbeat_ack():
    host = DummyIPC()
    host.embedded_tools['ToolX'] = {'last_heartbeat': 0}
    host._handle_ipc_message('ToolX', {'type': 'response', 'event': 'heartbeat_ack', 'data': {}})
    assert host.embedded_tools['ToolX']['last_heartbeat'] > 0


def test_handle_ipc_message_ready(mgr, monkeypatch):
    import wx
    host = DummyIPC()
    host.embedded_tools['ToolX'] = {'mode': 'exe', 'is_hidden': True}
    host._on_exe_tool_ready = MagicMock()
    monkeypatch.setattr(wx, 'CallAfter', lambda fn, *a: fn(*a))
    host._handle_ipc_message('ToolX', {'type': 'event', 'event': 'ready', 'data': {}})
    host._on_exe_tool_ready.assert_called_once_with('ToolX')
    assert host.embedded_tools['ToolX']['is_hidden'] is False


def test_handle_ipc_message_unknown_event():
    """未知事件不崩溃"""
    host = DummyIPC()
    host._handle_ipc_message('ToolX', {'type': 'event', 'event': 'unknown_event_xyz', 'data': {}})


def test_handle_ipc_message_closed(mgr, monkeypatch):
    import wx
    host = DummyIPC()
    # closed/hidden 事件仅对已注册工具分发（embedded_tools 守卫），需先注册
    host.embedded_tools['ToolX'] = {'mode': 'exe'}
    host._on_exe_tool_closed = MagicMock()
    monkeypatch.setattr(wx, 'CallAfter', lambda fn, *a: fn(*a))
    host._handle_ipc_message('ToolX', {'type': 'event', 'event': 'closed', 'data': {}})
    host._on_exe_tool_closed.assert_called_once_with('ToolX')


def test_handle_ipc_message_request_login(mgr, monkeypatch):
    import wx
    host = DummyIPC()
    host._on_exe_tool_request_login = MagicMock()
    monkeypatch.setattr(wx, 'CallAfter', lambda fn, *a: fn(*a))
    host._handle_ipc_message('ToolX', {'type': 'event', 'event': 'request_login', 'data': {'feature_key': 'x'}})
    host._on_exe_tool_request_login.assert_called_once_with('ToolX', {'feature_key': 'x'})


# ========== API 代理 ==========

def test_handle_ipc_api_request_missing_path():
    host = DummyIPC()
    sent = []
    host._send_ipc_api_response = lambda t, rid, resp: sent.append(resp)
    host._handle_ipc_api_request('ToolX', {'request_id': 'r1', 'method': 'GET'})
    assert len(sent) == 1
    assert sent[0]['status_code'] == 400


def test_handle_ipc_api_request_no_backend(mgr):
    host = DummyIPC()
    host.backend_url = ''
    sent = []
    host._send_ipc_api_response = lambda t, rid, resp: sent.append(resp)
    host._handle_ipc_api_request('ToolX', {'request_id': 'r1', 'path': '/api/v1/x'})
    time.sleep(0.3)  # 等待后台线程
    assert len(sent) == 1
    assert sent[0]['status_code'] == 503


# ========== API 响应发送 ==========

def test_send_ipc_api_response_tool_missing():
    host = DummyIPC()
    # 工具不在 embedded_tools → 静默返回
    host._send_ipc_api_response('ToolX', 'r1', {'status_code': 200})


def test_send_ipc_api_response_no_socket():
    host = DummyIPC()
    host.embedded_tools['ToolX'] = {}
    host._send_ipc_api_response('ToolX', 'r1', {'status_code': 200})


def test_send_ipc_api_response_sends():
    host = DummyIPC()
    recv_s, send_s = socket.socketpair()
    host.embedded_tools['ToolX'] = {'client_socket': send_s}
    try:
        host._send_ipc_api_response('ToolX', 'r1', {'status_code': 200, 'body': {'ok': True}})
        raw = recv_s.recv(4096).decode('utf-8')
        msg = json.loads(raw)
        assert msg['type'] == 'response'
        assert msg['event'] == 'api_response'
        assert msg['data']['request_id'] == 'r1'
        assert msg['data']['status_code'] == 200
    finally:
        recv_s.close()
        send_s.close()


# ========== 权限检查代理 ==========

def test_check_permission_no_backend_url():
    host = DummyIPC()
    host.backend_url = ''
    sent = []
    host._send_ipc_api_response = lambda t, rid, resp: sent.append(resp)
    host._handle_ipc_check_permission('ToolX', {'request_id': 'r1', 'feature_key': 'compare'})
    time.sleep(0.3)
    assert len(sent) == 1
    assert sent[0]['status_code'] == 503
    assert sent[0]['body']['allowed'] is False


# ========== 认证更新 ==========

def test_send_auth_update_not_logged_in(mgr):
    host = DummyIPC()
    sent = []
    host._send_ipc_to_tool = lambda t, cmd, data: sent.append((t, cmd, data))
    host.embedded_tools['ToolX'] = {'mode': 'exe'}
    host._send_auth_update_to_tool('ToolX')
    assert len(sent) == 1
    assert sent[0][1] == 'auth_update'
    assert sent[0][2]['is_logged_in'] is False


def test_send_auth_update_not_exe_mode():
    host = DummyIPC()
    sent = []
    host._send_ipc_to_tool = lambda t, cmd, data: sent.append(1)
    host.embedded_tools['ToolX'] = {'mode': 'webpage'}
    host._send_auth_update_to_tool('ToolX')
    assert sent == []


def test_send_auth_update_tool_missing():
    host = DummyIPC()
    host._send_auth_update_to_tool('ToolX')  # 不在 embedded_tools → 静默


def test_notify_all_exe_tools_auth_changed(mgr):
    host = DummyIPC()
    sent = []
    host._send_auth_update_to_tool = lambda t: sent.append(t)
    host.embedded_tools = {
        'ToolA': {'mode': 'exe', 'is_hidden': False},
        'ToolB': {'mode': 'exe', 'is_hidden': True},
        'ToolC': {'mode': 'webpage'},
    }
    host._notify_all_exe_tools_auth_changed()
    assert sent == ['ToolA']


# ========== 就绪/隐藏事件 ==========

def test_on_exe_tool_ready(mgr, monkeypatch):
    import wx
    host = DummyIPC()
    host.embedded_tools['ToolX'] = {'mode': 'exe'}
    host._hide_loading_panel = MagicMock()
    host._update_window_menu_for_tool = MagicMock()
    host.unlock_all_tools = MagicMock()
    host._send_auth_update_to_tool = MagicMock()
    monkeypatch.setattr(wx, 'CallAfter', lambda fn: fn())
    host.IsShown = MagicMock(return_value=False)
    host._on_exe_tool_ready('ToolX')
    assert host.embedded_tools['ToolX']['ready_received'] is True
    assert host._current_active_tool == 'ToolX'
    host._send_auth_update_to_tool.assert_called_once_with('ToolX')


def test_on_exe_tool_ready_unknown_tool():
    host = DummyIPC()
    host._on_exe_tool_ready('NotExist')  # 不在 embedded_tools → 静默


def test_on_exe_tool_hidden(mgr, monkeypatch):
    import wx
    host = DummyIPC()
    host.embedded_tools['ToolX'] = {'mode': 'exe', 'main_was_visible': True}
    host.IsShown = MagicMock(return_value=True)
    host.unlock_all_tools = MagicMock()
    host._update_window_menu_for_tool = MagicMock()
    monkeypatch.setattr(wx, 'CallAfter', lambda fn: fn())
    host._on_exe_tool_hidden('ToolX')
    assert host.embedded_tools['ToolX']['is_hidden'] is True


def test_on_exe_tool_hidden_unknown_tool():
    host = DummyIPC()
    host._on_exe_tool_hidden('NotExist')


# ========== IPC 命令发送 ==========

def test_send_ipc_to_tool_missing():
    host = DummyIPC()
    assert host._send_ipc_to_tool('ToolX', 'show') is False


def test_send_ipc_to_tool_no_socket():
    host = DummyIPC()
    host.embedded_tools['ToolX'] = {}
    assert host._send_ipc_to_tool('ToolX', 'show') is False


def test_send_ipc_to_tool_success():
    host = DummyIPC()
    recv_s, send_s = socket.socketpair()
    host.embedded_tools['ToolX'] = {'client_socket': send_s}
    try:
        assert host._send_ipc_to_tool('ToolX', 'show', {'k': 1}) is True
        raw = recv_s.recv(4096).decode('utf-8')
        msg = json.loads(raw)
        assert msg['type'] == 'command'
        assert msg['command'] == 'show'
        assert msg['data'] == {'k': 1}
    finally:
        recv_s.close()
        send_s.close()


def test_get_tool_name_by_ident():
    assert DummyIPC().get_tool_name_by_ident('TabulexBomComparator') == 'TabulexBomComparator'


# ========== 工具关闭 ==========

def test_on_exe_tool_closed_unknown():
    host = DummyIPC()
    host._on_exe_tool_closed('NotExist')


def test_on_exe_tool_closed_full(mgr, monkeypatch):
    import wx
    import time as _time
    monkeypatch.setattr(_time, 'sleep', lambda s: None)
    monkeypatch.setattr(wx, 'CallAfter', lambda fn: fn())
    host = DummyIPC()
    host.IsShown = MagicMock(return_value=True)
    host._hide_loading_panel = MagicMock()

    class FakeProcess:
        def __init__(self):
            self.pid = 12345
            self._rc = 0
        def poll(self):
            return self._rc
        def terminate(self):
            self._rc = 1
        def kill(self):
            self._rc = 1

    ctx = pathlib.Path(tempfile.gettempdir()) / 'tool_context_ToolX_closed.json'
    ctx.write_text('{}', encoding='utf-8')
    host.embedded_tools['ToolX'] = {
        'mode': 'exe', 'main_was_visible': False,
        'process': FakeProcess(),
        'ipc_server': MagicMock(),
        'context_file': str(ctx),
    }
    host._on_exe_tool_closed('ToolX')
    assert 'ToolX' not in host.embedded_tools
    assert not ctx.exists()


def test_on_exe_tool_closed_terminates_process(monkeypatch):
    import wx
    import time as _time
    monkeypatch.setattr(_time, 'sleep', lambda s: None)
    monkeypatch.setattr(wx, 'CallAfter', lambda fn: fn())
    host = DummyIPC()
    host.IsShown = MagicMock(return_value=True)

    class StuckProcess:
        def __init__(self):
            self.pid = 1
            self._rc = None
        def poll(self):
            return self._rc
        def terminate(self):
            self._rc = 2
        def kill(self):
            self._rc = 2

    host.embedded_tools['ToolX'] = {'mode': 'exe', 'process': StuckProcess()}
    host._on_exe_tool_closed('ToolX')
    assert 'ToolX' not in host.embedded_tools


# ========== 状态检查 ==========

def test_check_exe_tool_status_unknown():
    host = DummyIPC()
    host._check_exe_tool_status('NotExist')


def test_check_exe_tool_status_not_exe():
    host = DummyIPC()
    host.embedded_tools['ToolX'] = {'mode': 'webpage'}
    host._check_exe_tool_status('ToolX')


def test_check_exe_tool_status_no_process():
    host = DummyIPC()
    host.embedded_tools['ToolX'] = {'mode': 'exe'}
    host._check_exe_tool_status('ToolX')


def test_check_exe_tool_status_exited(monkeypatch):
    import wx
    monkeypatch.setattr(wx, 'CallAfter', lambda fn: fn())
    host = DummyIPC()
    host.IsShown = MagicMock(return_value=True)

    class ExitedProc:
        def poll(self):
            return 0

    host.embedded_tools['ToolX'] = {'mode': 'exe', 'process': ExitedProc()}
    host._check_exe_tool_status('ToolX')
    assert 'ToolX' not in host.embedded_tools


# ========== 重发 show 命令 ==========

def test_resend_show_unknown():
    host = DummyIPC()
    host._resend_ipc_show_command('NotExist')


def test_resend_show_success(mgr):
    host = DummyIPC()
    host._send_ipc_to_tool = MagicMock(return_value=True)
    host._update_window_menu_for_tool = MagicMock()
    host.IsShown = MagicMock(return_value=False)
    host.embedded_tools['ToolX'] = {'mode': 'exe', 'requires_subscription': False}
    host._resend_ipc_show_command('ToolX')
    assert host.embedded_tools['ToolX']['is_hidden'] is False


def test_resend_show_failure(mgr):
    host = DummyIPC()
    host._send_ipc_to_tool = MagicMock(return_value=False)
    host._on_exe_tool_closed = MagicMock()
    host.embedded_tools['ToolX'] = {'mode': 'exe'}
    host._resend_ipc_show_command('ToolX')
    host._on_exe_tool_closed.assert_called_once_with('ToolX')


# ========== hidden 消息分发 ==========

def test_handle_ipc_message_hidden(mgr, monkeypatch):
    import wx
    host = DummyIPC()
    # closed/hidden 事件仅对已注册工具分发（embedded_tools 守卫），需先注册
    host.embedded_tools['ToolX'] = {'mode': 'exe'}
    host._on_exe_tool_hidden = MagicMock()
    monkeypatch.setattr(wx, 'CallAfter', lambda fn, *a: fn(*a))
    host._handle_ipc_message('ToolX', {'type': 'event', 'event': 'hidden', 'data': {}})
    host._on_exe_tool_hidden.assert_called_once_with('ToolX')


# ========== API 代理转发 ==========

def test_api_request_not_logged_in(mgr, monkeypatch):
    """无 auth_headers → 401 响应"""
    host = DummyIPC()
    host.embedded_tools['ToolX'] = {}
    sent = []
    host._send_ipc_api_response = lambda t, rid, resp: sent.append(resp)
    from tfp_mixins import tfp_tool_ipc_mixin as mod
    monkeypatch.setattr(mod.auth_manager, 'get_auth_headers', lambda: None)
    host._handle_ipc_api_request('ToolX', {'request_id': 'r1', 'method': 'GET', 'path': '/api/v1/x'})
    time.sleep(0.3)
    assert len(sent) == 1
    assert sent[0]['status_code'] == 401


def test_api_request_success_get(mgr, monkeypatch):
    """GET 转发成功"""
    host = DummyIPC()
    host.embedded_tools['ToolX'] = {}
    sent = []
    host._send_ipc_api_response = lambda t, rid, resp: sent.append(resp)
    from tfp_mixins import tfp_tool_ipc_mixin as mod
    monkeypatch.setattr(mod.auth_manager, 'get_auth_headers', lambda: {'Authorization': 'Bearer t'})

    class FakeResp:
        status_code = 200
        text = '{"ok": true}'
        headers = {'Content-Type': 'application/json'}
        def json(self):
            return {'ok': True}

    monkeypatch.setattr(mod.http_requests, 'get', lambda *a, **k: FakeResp())
    host._handle_ipc_api_request('ToolX', {'request_id': 'r1', 'method': 'GET', 'path': '/api/v1/x'})
    time.sleep(0.3)
    assert len(sent) == 1
    assert sent[0]['status_code'] == 200
    assert sent[0]['body'] == {'ok': True}


def test_api_request_unsupported_method(mgr, monkeypatch):
    """不支持的方法 → 400"""
    host = DummyIPC()
    host.embedded_tools['ToolX'] = {}
    sent = []
    host._send_ipc_api_response = lambda t, rid, resp: sent.append(resp)
    from tfp_mixins import tfp_tool_ipc_mixin as mod
    monkeypatch.setattr(mod.auth_manager, 'get_auth_headers', lambda: {'Authorization': 'Bearer t'})
    host._handle_ipc_api_request('ToolX', {'request_id': 'r1', 'method': 'PATCH', 'path': '/api/v1/x'})
    time.sleep(0.3)
    assert len(sent) == 1
    assert sent[0]['status_code'] == 400


def test_api_request_connection_error(mgr, monkeypatch):
    """连接后端失败 → 502"""
    host = DummyIPC()
    host.embedded_tools['ToolX'] = {}
    sent = []
    host._send_ipc_api_response = lambda t, rid, resp: sent.append(resp)
    from tfp_mixins import tfp_tool_ipc_mixin as mod
    monkeypatch.setattr(mod.auth_manager, 'get_auth_headers', lambda: {'Authorization': 'Bearer t'})
    monkeypatch.setattr(mod.http_requests, 'get', MagicMock(side_effect=mod.http_requests.ConnectionError))
    host._handle_ipc_api_request('ToolX', {'request_id': 'r1', 'method': 'GET', 'path': '/api/v1/x'})
    time.sleep(0.3)
    assert len(sent) == 1
    assert sent[0]['status_code'] == 502


def test_check_permission_proxy(mgr, monkeypatch):
    """权限检查转发成功"""
    host = DummyIPC()
    host.embedded_tools['ToolX'] = {}
    sent = []
    host._send_ipc_api_response = lambda t, rid, resp: sent.append(resp)
    from tfp_mixins import tfp_tool_ipc_mixin as mod
    monkeypatch.setattr(mod.auth_manager, 'get_auth_headers', lambda: {'Authorization': 'Bearer t'})

    class FakeResp:
        status_code = 200
        def json(self):
            return {'allowed': True}

    monkeypatch.setattr(mod.http_requests, 'get', lambda *a, **k: FakeResp())
    host._handle_ipc_check_permission('ToolX', {
        'request_id': 'r1', 'tool_ident': 'TabulexBomComparator', 'feature_key': 'compare'
    })
    time.sleep(0.3)
    assert len(sent) == 1
    assert sent[0]['status_code'] == 200
    assert sent[0]['body']['allowed'] is True
