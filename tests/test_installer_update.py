# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""T8.6 验证：前端安装包后台静默下载 + 就绪引导（A4 调整版基础层）。

覆盖：_start_installer_download 资格判定（缺本平台条目/生产无根公钥 fail-closed/
sig 验签失败 fail-closed/dev 模式跳过验签/缓存命中跳过下载/缓存失配重新下载）/
_download_installer_worker（下载→sha256 比对→缓存保留→就绪提示、哈希不符拒收
清理、大小超限中止、HTTP 失败回退方案 1a 提示）。
"""

import hashlib

import pytest

import tfp_mixins.tfp_tool_runner_mixin as runner_module
from tfp_mixins.tfp_tool_runner_mixin import TFP_ToolRunnerMixin
from tfp_utils.tfp_platform import get_platform_tag

_PLAT = get_platform_tag()
# 非本机平台条目键（用于验证"缺本平台条目"分支；与 _PLAT 必不相同）
_OTHER_PLAT = 'windows' if _PLAT != 'windows' else 'linux-deb'
_URL = 'https://dl.example.com/TabulexFlow-1.2.0.exe'
_BODY = b'installer-bytes'


class DummyRunner(TFP_ToolRunnerMixin):
    """最小宿主：继承 mixin 以解析其方法；仅提供所需属性与可记录提示（不依赖真实 wx UI）。"""

    frontend_version = '1.0.0'
    backend_url = 'https://backend.example.com'

    def __init__(self, tmp_path):
        self._runtime_base_dir = tmp_path
        self.ready_prompts = []
        self.update_prompts = []

    def _prompt_installer_ready(self, installer_path, version):
        self.ready_prompts.append((installer_path, version))

    def _prompt_frontend_update(self, latest_version, changelog, download_url):
        self.update_prompts.append((latest_version, changelog, download_url))


class _InlineThread:
    """同步执行 target 的假线程（替代真实 daemon 线程，保证测试确定性）。"""

    def __init__(self, target=None, args=(), name=None, daemon=False):
        self._target, self._args = target, args

    def start(self):
        self._target(*self._args)


class _FakeStreamResponse:
    def __init__(self, chunks, status=200):
        self._chunks, self.status_code = chunks, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'http {self.status_code}')

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_content(self, chunk_size=65536):
        yield from self._chunks


@pytest.fixture
def runner(tmp_path, monkeypatch):
    """生产路径验签放行 + wx.CallAfter 同步执行 + 线程同步执行。

    两段验签的密码学实现已由工具分发链路测试覆盖，此处聚焦下载编排与完整性比对。
    """
    r = DummyRunner(tmp_path)
    monkeypatch.setattr(runner_module, 'is_public_key_configured', lambda: True)
    monkeypatch.setattr(runner_module, 'verify_leaf_credential', lambda cred: 'LEAF_PEM')
    monkeypatch.setattr(runner_module, 'verify_tool_signature',
                        lambda sha, ver, sig, pem: True)
    monkeypatch.setattr(runner_module.wx, 'CallAfter', lambda fn, *a: fn(*a))
    monkeypatch.setattr(runner_module.threading, 'Thread', _InlineThread)
    return r


def _info(sha=None, url=_URL, version='1.2.0', **overrides):
    info = {
        'version': version,
        'changelog': 'changelog-text',
        'download_url': 'https://tabulexflow.com/web/download',
        'sign_cred': 'cred',
        'installers': {
            _PLAT: {'url': url, 'sha256': sha or hashlib.sha256(_BODY).hexdigest(),
                    'sig': 'sig'},
            _OTHER_PLAT: {'url': url, 'sha256': sha or hashlib.sha256(_BODY).hexdigest(),
                          'sig': 'sig'},
        },
    }
    info.update(overrides)
    return info


def _serve(monkeypatch, chunks, status=200):
    seen = []
    monkeypatch.setattr(runner_module.requests, 'get',
                        lambda url, **kw: (seen.append(url),
                                           _FakeStreamResponse(chunks, status))[1])
    return seen


def test_start_downloads_verifies_and_prompts_ready(runner, monkeypatch):
    """完整链路：启动下载 → 写缓存 → sha256 匹配 → 就绪提示（不弹下载页提示）。"""
    seen = _serve(monkeypatch, [_BODY])
    assert runner._start_installer_download(_info()) is True
    assert seen == [_URL]
    final_path = runner._get_installer_cache_dir() / 'TabulexFlow-1.2.0.exe'
    assert final_path.read_bytes() == _BODY
    assert runner.ready_prompts == [(final_path, '1.2.0')]
    assert runner.update_prompts == []


def test_start_fails_when_platform_entry_missing(runner, monkeypatch):
    """installers 缺本平台条目 → 返回 False，不发起下载、不弹任何窗。"""
    info = _info()
    info['installers'] = {_OTHER_PLAT: info['installers'][_OTHER_PLAT]}
    assert runner._start_installer_download(info) is False
    assert runner.ready_prompts == [] and runner.update_prompts == []


def test_start_fails_without_root_key_in_production(runner, monkeypatch):
    """生产环境（非 dev）未配置根公钥 → fail-closed 返回 False。"""
    monkeypatch.setattr(runner_module, 'is_public_key_configured', lambda: False)
    monkeypatch.setattr(runner_module, 'is_dev_mode', lambda: False)
    assert runner._start_installer_download(_info()) is False
    assert runner.ready_prompts == [] and runner.update_prompts == []


def test_dev_mode_without_root_key_skips_verify_but_still_checks_hash(
        runner, monkeypatch):
    """dev 模式未配根公钥：跳过验签（同工具分发规则），但仍校验文件 sha256。"""
    monkeypatch.setattr(runner_module, 'is_public_key_configured', lambda: False)
    monkeypatch.setattr(runner_module, 'is_dev_mode', lambda: True)
    verify_calls = []
    monkeypatch.setattr(runner_module, 'verify_leaf_credential',
                        lambda cred: verify_calls.append(cred))
    _serve(monkeypatch, [_BODY])
    assert runner._start_installer_download(_info()) is True
    assert verify_calls == []  # 验签被跳过
    assert len(runner.ready_prompts) == 1  # 哈希匹配 → 就绪


def test_start_fails_when_sig_verification_fails(runner, monkeypatch):
    """生产环境 sig 验签失败 → fail-closed 返回 False，不下载。"""
    monkeypatch.setattr(runner_module, 'verify_tool_signature',
                        lambda sha, ver, sig, pem: False)
    seen = _serve(monkeypatch, [_BODY])
    assert runner._start_installer_download(_info()) is False
    assert seen == []  # 未发起 HTTP
    assert runner.ready_prompts == [] and runner.update_prompts == []


def test_cache_hit_skips_download_and_prompts_ready(runner, monkeypatch):
    """缓存命中（sha256 匹配）→ 跳过下载直接就绪提示（"NO→下次启动再提示"）。"""
    final_path = runner._get_installer_cache_dir() / 'TabulexFlow-1.2.0.exe'
    final_path.parent.mkdir(parents=True)
    final_path.write_bytes(_BODY)
    seen = _serve(monkeypatch, [_BODY])
    assert runner._start_installer_download(_info()) is True
    assert seen == []  # 未发起 HTTP
    assert runner.ready_prompts == [(final_path, '1.2.0')]


def test_stale_cache_is_redownloaded_and_replaced(runner, monkeypatch):
    """缓存文件内容与期望 sha256 不符（旧版残留/损坏）→ 重新下载覆盖。"""
    final_path = runner._get_installer_cache_dir() / 'TabulexFlow-1.2.0.exe'
    final_path.parent.mkdir(parents=True)
    final_path.write_bytes(b'stale-old-content')
    _serve(monkeypatch, [_BODY])
    assert runner._start_installer_download(_info()) is True
    assert final_path.read_bytes() == _BODY
    assert len(runner.ready_prompts) == 1


def test_worker_sha_mismatch_rejects_cleans_and_falls_back(runner, monkeypatch):
    """实际内容哈希与验签过的期望值不符 → 拒收（不留成品、无 .part 残留）、回退提示。"""
    _serve(monkeypatch, [b'corrupted-content'])
    runner._download_installer_worker(_info())
    cache_dir = runner._get_installer_cache_dir()
    assert list(cache_dir.glob('*')) == []  # 成品与临时文件均不存在
    assert runner.ready_prompts == []
    assert len(runner.update_prompts) == 1  # 回退方案 1a
    assert runner.update_prompts[0][0] == '1.2.0'
    assert runner.update_prompts[0][2] == 'https://tabulexflow.com/web/download'


def test_worker_size_limit_aborts(runner, monkeypatch):
    """超过大小上限（本测压至 8 字节）→ 中止下载、清理临时文件、回退提示。"""
    monkeypatch.setattr(runner_module, '_MAX_TOOL_ZIP_BYTES', 8)
    _serve(monkeypatch, [b'x' * 20])
    runner._download_installer_worker(_info())
    assert list(runner._get_installer_cache_dir().glob('*')) == []
    assert runner.ready_prompts == []
    assert len(runner.update_prompts) == 1


def test_worker_http_error_falls_back(runner, monkeypatch):
    """HTTP 500 → 下载失败回退方案 1a 提示，不留任何文件。"""
    _serve(monkeypatch, [_BODY], status=500)
    runner._download_installer_worker(_info())
    assert list(runner._get_installer_cache_dir().glob('*')) == []
    assert len(runner.update_prompts) == 1
