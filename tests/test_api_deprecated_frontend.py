# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""T7.2: 前端识别 410 API_DEPRECATED → 升级提示（三处收口）

覆盖：
- IPC 代理（tfp_tool_ipc_mixin）：410+API_DEPRECATED 触发升级提示且 410 原样透传；
  非契约 410 / 非 410 错误不触发提示
- _prompt_api_deprecated：同启动周期防重复、后端 message 优先、
  min_frontend_version 附加、OK 后跳转下载页
- 工具下载（tfp_tool_runner_mixin.try_update_tool）：410+API_DEPRECATED →
  _last_download_error='API_DEPRECATED' + 载荷留存；非契约 410 仍为 HTTP_410
- 会话（tfp_auth_manager._validate_session）：410+API_DEPRECATED 不静默清会话
  并提示升级；非契约 410 走既有刷新/清会话路径；_prompt_api_deprecated_upgrade
  主窗口查找与复用
所有网络请求通过 monkeypatch 模拟，不访问真实后端；弹窗与浏览器跳转全部 mock。
"""
import pathlib
import time

import pytest
import requests
import wx

from build_mode import BACKEND_HOST, BACKEND_PORT, FRONTEND_DOWNLOAD_PAGE_URL

from tfp_mixins.tfp_tool_ipc_mixin import TFP_ToolIPCMixin
from tfp_mixins.tfp_tool_runner_mixin import TFP_ToolRunnerMixin


# ========== 公共夹具 ==========

@pytest.fixture(autouse=True)
def _reset_deprecated_prompt_flag(monkeypatch):
    """隔离类级防重复弹窗标记（"同启动周期"语义在单测中逐用例重置）"""
    monkeypatch.setattr(TFP_ToolIPCMixin, '_api_deprecated_prompted', False)


@pytest.fixture()
def wx_calls(monkeypatch):
    """静默弹窗/浏览器跳转，记录调用供断言"""
    calls = {'dialogs': [], 'browser': []}

    class FakeDialog:
        def __init__(self, parent, text, title, style):
            calls['dialogs'].append({'text': text, 'title': title, 'style': style})

        def ShowModal(self):
            return wx.OK

        def Destroy(self):
            pass

    monkeypatch.setattr(wx, 'MessageDialog', FakeDialog)
    monkeypatch.setattr(wx, 'LaunchDefaultBrowser', lambda url: calls['browser'].append(url))
    return calls


def _deprecated_body(**overrides):
    """构造后端 410 响应 body（T7.1 契约）"""
    body = {'status': 'error', 'code': 'API_DEPRECATED'}
    body.update(overrides)
    return body


# ========== IPC 代理（tfp_tool_ipc_mixin） ==========

class DummyIPC(TFP_ToolIPCMixin):
    def __init__(self):
        self.embedded_tools = {}
        self.backend_url = f"http://{BACKEND_HOST}:{BACKEND_PORT}"


def _run_ipc_proxy(monkeypatch, status_code, body):
    """驱动一次 IPC 代理请求，返回 (发给子工具的响应列表, host)"""
    host = DummyIPC()
    sent = []
    host._send_ipc_api_response = lambda t, rid, resp: sent.append(resp)
    from tfp_mixins import tfp_tool_ipc_mixin as mod

    monkeypatch.setattr(mod.auth_manager, 'get_auth_headers', lambda: {'Authorization': 'Bearer t'})

    class FakeResp:
        headers = {'Content-Type': 'application/json'}

        def __init__(self):
            self.status_code = status_code

        def json(self):
            return body

    monkeypatch.setattr(mod.http_requests, 'get', lambda *a, **k: FakeResp())
    monkeypatch.setattr(wx, 'CallAfter', lambda fn, *a: fn(*a))  # 同步触发便于断言
    host._handle_ipc_api_request('ToolX', {'request_id': 'r1', 'method': 'GET', 'path': '/api/v1/x'})
    time.sleep(0.3)  # 等待后台线程
    return sent, host


def test_ipc_proxy_410_deprecated_prompts_and_passthrough(mgr, monkeypatch, wx_calls):
    """410+API_DEPRECATED：触发升级提示，且 410 响应原样透传给子工具"""
    body = _deprecated_body(message={'en': 'Please upgrade.', 'zh': '请升级客户端。'},
                            min_frontend_version='2.0.0')
    sent, host = _run_ipc_proxy(monkeypatch, 410, body)
    assert len(sent) == 1
    assert sent[0]['status_code'] == 410
    assert sent[0]['body'] == body  # 原样透传：旧子工具按非 200 处理，新子工具可读 code
    assert host._api_deprecated_prompted is True
    assert len(wx_calls['browser']) == 1
    assert wx_calls['browser'][0] == FRONTEND_DOWNLOAD_PAGE_URL


def test_ipc_proxy_410_without_contract_no_prompt(mgr, monkeypatch, wx_calls):
    """410 但无 API_DEPRECATED 契约体：不弹提示，仍原样透传"""
    sent, host = _run_ipc_proxy(monkeypatch, 410, {'foo': 'bar'})
    assert len(sent) == 1 and sent[0]['status_code'] == 410
    assert host._api_deprecated_prompted is False
    assert wx_calls['browser'] == []


def test_ipc_proxy_500_no_prompt(mgr, monkeypatch, wx_calls):
    """非 410 错误：不触发升级提示"""
    sent, host = _run_ipc_proxy(monkeypatch, 500, {'status': 'error'})
    assert sent[0]['status_code'] == 500
    assert host._api_deprecated_prompted is False
    assert wx_calls['browser'] == []


# ========== 统一升级提示（_prompt_api_deprecated） ==========

def test_prompt_api_deprecated_dedup_per_run(mgr, monkeypatch, wx_calls):
    """同启动周期仅弹一次：第二次调用被抑制"""
    host = DummyIPC()
    host._prompt_api_deprecated(_deprecated_body())
    host._prompt_api_deprecated(_deprecated_body())
    assert len(wx_calls['dialogs']) == 1
    assert len(wx_calls['browser']) == 1
    assert host._api_deprecated_prompted is True


def test_prompt_api_deprecated_uses_backend_message_by_language(mgr, monkeypatch, wx_calls):
    """后端 message 按界面语言优先：当前语言命中 → 用后端文案而非 fallback"""
    from tfp_mixins import tfp_tool_ipc_mixin as mod
    monkeypatch.setattr(mod.i18n, 'get_language_code', lambda: 'zh')
    host = DummyIPC()
    host._prompt_api_deprecated(
        _deprecated_body(message={'en': 'Backend EN', 'zh': '后端文案'}), fallback_text='FB')
    assert wx_calls['dialogs'][0]['text'] == '后端文案'


def test_prompt_api_deprecated_message_en_fallback_then_any(mgr, monkeypatch, wx_calls):
    """后端 message 无当前语言 → 回退 en → 再取任意可用项"""
    from tfp_mixins import tfp_tool_ipc_mixin as mod
    host = DummyIPC()
    monkeypatch.setattr(mod.i18n, 'get_language_code', lambda: 'fr')
    host._prompt_api_deprecated(_deprecated_body(message={'en': 'Backend EN', 'de': 'Backend DE'}), 'FB')
    assert wx_calls['dialogs'][0]['text'] == 'Backend EN'
    monkeypatch.setattr(TFP_ToolIPCMixin, '_api_deprecated_prompted', False)
    host2 = DummyIPC()
    host2._prompt_api_deprecated(_deprecated_body(message={'de': 'Backend DE'}), 'FB')
    assert wx_calls['dialogs'][1]['text'] == 'Backend DE'


def test_prompt_api_deprecated_fallback_i18n_and_min_suffix(mgr, monkeypatch, wx_calls):
    """后端无 message → 回退 fallback 文案；带 min_frontend_version 时附加最低版本行"""
    host = DummyIPC()
    host._prompt_api_deprecated(_deprecated_body(min_frontend_version='2.0.0'), fallback_text='FB')
    text = wx_calls['dialogs'][0]['text']
    assert text.startswith('FB')
    assert '2.0.0' in text  # 最低版本后缀已格式化

    # 无 min_frontend_version：不附加后缀行
    monkeypatch.setattr(TFP_ToolIPCMixin, '_api_deprecated_prompted', False)
    host2 = DummyIPC()
    host2._prompt_api_deprecated(_deprecated_body(), fallback_text='FB2')
    assert wx_calls['dialogs'][1]['text'] == 'FB2'


# ========== 工具下载（tfp_tool_runner_mixin.try_update_tool） ==========

class DummyRunner(TFP_ToolRunnerMixin):
    def __init__(self):
        self.backend_url = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
        self.frontend_version = "1.0.0"
        self._last_download_error = None
        self._last_download_deprecated_payload = None


def _run_try_update_tool(monkeypatch, status_code, body):
    runner = DummyRunner()
    from tfp_mixins import tfp_tool_runner_mixin as rmod
    monkeypatch.setattr(rmod.auth_manager, 'get_auth_headers', lambda: {'Authorization': 'Bearer t'})

    class FakeResp:
        headers = {'Content-Type': 'application/json'}

        def __init__(self):
            self.status_code = status_code

        def json(self):
            return body

    monkeypatch.setattr(rmod.requests, 'get', lambda *a, **k: FakeResp())
    ok = runner.try_update_tool(
        {'tool_type': 'exe', 'tool_ident': 'ToolX', 'tool_version': '1.0.0'},
        pathlib.Path('.'), force_update=False)
    return ok, runner


def test_try_update_tool_410_deprecated(mgr, monkeypatch):
    """410+API_DEPRECATED → _last_download_error='API_DEPRECATED' + 载荷留存"""
    body = _deprecated_body(min_frontend_version='2.0.0')
    ok, runner = _run_try_update_tool(monkeypatch, 410, body)
    assert ok is False
    assert runner._last_download_error == 'API_DEPRECATED'
    assert runner._last_download_deprecated_payload == body


def test_try_update_tool_410_without_contract(mgr, monkeypatch):
    """非契约 410 → 保持既有 HTTP_410 语义，不留存载荷"""
    ok, runner = _run_try_update_tool(monkeypatch, 410, {'code': 'OTHER'})
    assert ok is False
    assert runner._last_download_error == 'HTTP_410'
    assert runner._last_download_deprecated_payload is None


# ========== 会话（tfp_auth_manager._validate_session） ==========

class _AuthFakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


def test_validate_session_410_deprecated_keeps_session(mgr, monkeypatch):
    """410+API_DEPRECATED：不静默清会话，返回 False 并触发升级提示，不走 refresh"""
    mgr._session_token = 'st'
    mgr._refresh_token = 'rt'
    prompted = []
    monkeypatch.setattr(mgr, '_prompt_api_deprecated_upgrade', lambda p: prompted.append(p))

    def _unexpected_refresh(*a, **k):
        raise AssertionError("refresh_session must not be called on contract 410")

    monkeypatch.setattr(mgr, 'refresh_session', _unexpected_refresh)
    monkeypatch.setattr(requests, 'get',
                        lambda *a, **k: _AuthFakeResp(410, _deprecated_body(min_frontend_version='2.0.0')))
    ok = mgr._validate_session()
    assert ok is False
    assert mgr._session_token == 'st'  # 会话保留，避免"莫名被登出"
    assert mgr._refresh_token == 'rt'
    assert len(prompted) == 1 and prompted[0]['code'] == 'API_DEPRECATED'


def test_validate_session_410_without_contract_clears(mgr, monkeypatch):
    """非契约 410：保持既有行为（刷新失败 → 清会话）"""
    mgr._session_token = 'st'
    mgr._refresh_token = 'rt'
    monkeypatch.setattr(requests, 'get', lambda *a, **k: _AuthFakeResp(410, {'foo': 1}))
    monkeypatch.setattr(requests, 'post',
                        lambda *a, **k: _AuthFakeResp(200, {'success': False, 'message': 'x'}))
    ok = mgr._validate_session()
    assert ok is False
    assert mgr._session_token is None


def test_prompt_api_deprecated_upgrade_reuses_main_frame(mgr, monkeypatch):
    """_prompt_api_deprecated_upgrade：经 wx.CallAfter 调度，找到主窗口后复用其统一提示"""
    scheduled = []
    monkeypatch.setattr(wx, 'CallAfter', lambda fn, *a: scheduled.append(fn))
    payload = _deprecated_body(min_frontend_version='2.0.0')
    mgr._prompt_api_deprecated_upgrade(payload)
    assert len(scheduled) == 1

    class TFP_MainFrame:
        def __init__(self):
            self.prompts = []

        def _prompt_api_deprecated(self, p, fallback_text=None):
            self.prompts.append(p)

    frame = TFP_MainFrame()
    monkeypatch.setattr(wx, 'GetTopLevelWindows', lambda: [frame])
    scheduled[0]()
    assert frame.prompts == [payload]


def test_prompt_api_deprecated_upgrade_without_main_frame(mgr, monkeypatch):
    """找不到主窗口（异常场景）：不崩溃，仅静默记日志"""
    scheduled = []
    monkeypatch.setattr(wx, 'CallAfter', lambda fn, *a: scheduled.append(fn))
    monkeypatch.setattr(wx, 'GetTopLevelWindows', lambda: [])
    mgr._prompt_api_deprecated_upgrade(_deprecated_body())
    scheduled[0]()  # 不抛异常即通过
