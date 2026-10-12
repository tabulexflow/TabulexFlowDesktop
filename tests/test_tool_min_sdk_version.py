# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""T8.4.1: 工具清单 min_sdk_version 下载门槛（B1）

覆盖：
- try_update_tool 下载前 SDK 比对：本地 tfp_utils.__version__ 低于工具要求阈值时
  拒绝下载（不发起 HTTP 请求）、留存 _last_download_error='SDK_TOO_OLD' 与
  _last_download_sdk_requirement；等于/低于阈值/缺省/非法值 → 正常发起下载
- run_remote_program SDK_TOO_OLD 分支：弹统一升级提示（_prompt_api_deprecated，
  复用 410 提示链路）、不落入启动本地 EXE/源码分支、return False
所有网络请求通过 monkeypatch 模拟，不访问真实后端；弹窗与浏览器跳转全部 mock。
"""
import pathlib

import pytest

from build_mode import BACKEND_HOST, BACKEND_PORT

from tfp_mixins.tfp_tool_ipc_mixin import TFP_ToolIPCMixin
from tfp_mixins.tfp_tool_runner_mixin import TFP_ToolRunnerMixin


@pytest.fixture(autouse=True)
def _reset_deprecated_prompt_flag(monkeypatch):
    """隔离类级防重复弹窗标记（SDK 门槛复用 410 提示链路）"""
    monkeypatch.setattr(TFP_ToolIPCMixin, '_api_deprecated_prompted', False)


class DummyRunner(TFP_ToolRunnerMixin):
    def __init__(self):
        self.backend_url = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
        self.frontend_version = "1.0.0"
        self._last_download_error = None
        self._last_download_deprecated_payload = None
        self._last_download_sdk_requirement = None
        self.embedded_tools = {}


def _run_try_update_tool(monkeypatch, calls, min_sdk_version):
    """驱动一次 try_update_tool；calls 记录 HTTP 请求调用，返回 (ok, runner)"""
    runner = DummyRunner()
    from tfp_mixins import tfp_tool_runner_mixin as rmod
    monkeypatch.setattr(rmod.auth_manager, 'get_auth_headers', lambda: {'Authorization': 'Bearer t'})

    class FakeResp:
        headers = {'Content-Type': 'application/json'}
        status_code = 200

        def json(self):
            return {'status': 'no_update'}

    def fake_get(*args, **kwargs):
        calls.append(args)
        return FakeResp()

    monkeypatch.setattr(rmod.requests, 'get', fake_get)

    tool_info = {'tool_type': 'exe', 'tool_ident': 'ToolX', 'tool_version': '1.0.0'}
    if min_sdk_version is not None:
        tool_info['min_sdk_version'] = min_sdk_version
    ok = runner.try_update_tool(tool_info, pathlib.Path('.'), force_update=False)
    return ok, runner


def test_gate_blocks_lower_sdk(monkeypatch):
    """工具要求 SDK 高于本地 → 拒绝下载：不发起 HTTP 请求，留存错误与阈值"""
    calls = []
    ok, runner = _run_try_update_tool(monkeypatch, calls, '9.9.9')
    assert ok is False
    assert calls == []  # 下载请求未发起
    assert runner._last_download_error == 'SDK_TOO_OLD'
    assert runner._last_download_sdk_requirement == '9.9.9'


@pytest.mark.parametrize('min_sdk', ['1.0.0', '0.9.0', None, 'not-a-version'])
def test_gate_allows_equal_lower_default_or_invalid(monkeypatch, min_sdk):
    """等于/低于阈值、缺省、非法值 → 不限制，正常发起下载（非法值 fail-open）"""
    calls = []
    ok, runner = _run_try_update_tool(monkeypatch, calls, min_sdk)
    assert ok is True
    assert len(calls) == 1
    assert runner._last_download_error is None


def test_run_remote_program_sdk_too_old_prompts_and_refuses(monkeypatch):
    """SDK_TOO_OLD 分支：弹统一升级提示（正文含工具与最低 SDK），不启动本地 EXE"""
    from tfp_mixins import tfp_tool_runner_mixin as rmod
    runner = DummyRunner()
    runner.local_tools_dir = pathlib.Path('.')
    prompts = []
    launched = []

    def fake_try_update(tool_info, local_dir, force_update=False):
        runner._last_download_error = 'SDK_TOO_OLD'
        runner._last_download_sdk_requirement = '9.9.9'
        return False

    monkeypatch.setattr(runner, 'try_update_tool', fake_try_update)
    # 主窗口同时挂载 IPC/Runner 两个 Mixin，_prompt_api_deprecated 定义在 IPC 侧；
    # Dummy 仅继承 Runner，故以 raising=False 注入实例属性
    monkeypatch.setattr(runner, '_prompt_api_deprecated',
                        lambda payload, fallback: prompts.append((payload, fallback)),
                        raising=False)
    monkeypatch.setattr(runner, '_launch_exe_tool', lambda *a, **k: launched.append(a) or True)
    monkeypatch.setattr(runner, '_launch_source_tool', lambda *a, **k: launched.append(a) or True)
    # get_localized_tool_title/_check_tool_login/_show_loading_panel/_hide_loading_panel
    # 同样定义在主窗口类（非本 Mixin），一律以 raising=False 注入
    monkeypatch.setattr(runner, 'get_localized_tool_title', lambda tool_info: 'ToolX', raising=False)
    monkeypatch.setattr(runner, '_check_tool_login', lambda tool_info: True, raising=False)
    monkeypatch.setattr(runner, '_show_loading_panel', lambda tool_name: 'busy', raising=False)
    monkeypatch.setattr(runner, '_hide_loading_panel', lambda panel: None, raising=False)
    monkeypatch.setattr(runner, '_find_main_exe',
                        lambda d, i: pathlib.Path('.') / 'nonexistent.exe')
    monkeypatch.setattr(rmod, 'is_dev_mode', lambda: False)

    ok = runner.run_remote_program({'tool_ident': 'ToolX'})
    assert ok is False
    assert launched == []  # 不得落入启动本地旧 EXE 分支
    assert len(prompts) == 1
    payload, fallback = prompts[0]
    assert payload == {'code': 'SDK_TOO_OLD'}
    assert 'ToolX' in fallback and '9.9.9' in fallback
