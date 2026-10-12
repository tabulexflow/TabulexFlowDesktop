# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""F3: TFP_ToolRunnerMixin 工具运行器测试

覆盖：DPI 缩放、Builtin 工具离线宽限期登录检查、工具下载解压安全
（Zip Slip 防护 / SHA-256 校验和 / 无校验和拒绝）、远程网页 URL 获取。
"""
import hashlib
import io
import json
import pathlib
import tempfile
import threading
import zipfile

import pytest
import requests
import wx

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from build_mode import BACKEND_HOST, BACKEND_PORT
import tfp_utils.tfp_tool_signer as tt_signer

from tfp_mixins.tfp_tool_runner_mixin import TFP_ToolRunnerMixin, auth_manager


# ========== H-3：测试签名密钥对（每个导入进程生成一次） ==========
_TEST_SIGN_PRIVATE_KEY = Ed25519PrivateKey.generate()
_TEST_SIGN_PUBLIC_KEY_PEM = _TEST_SIGN_PRIVATE_KEY.public_key().public_bytes(
    Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
).decode("utf-8")

# ========== H-3 根/叶：测试根私钥 + 叶子凭证（根/叶分层，2026-09-07） ==========
_TEST_ROOT_PRIVATE_KEY = Ed25519PrivateKey.generate()
_TEST_ROOT_PUBLIC_KEY_PEM = _TEST_ROOT_PRIVATE_KEY.public_key().public_bytes(
    Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
).decode("utf-8")


def _b64u(data):
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _pub_fingerprint(pub):
    return hashlib.sha256(pub.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)).hexdigest()


def _make_leaf_credential():
    """构造与后端签发脚本一致的叶子凭证（叶子公钥 = 测试签名公钥）"""
    import json
    doc = {
        "schema": "tf-tool-sign-leaf-v1",
        "root_key_id": _pub_fingerprint(_TEST_ROOT_PRIVATE_KEY.public_key()),
        "leaf_key_id": _pub_fingerprint(_TEST_SIGN_PRIVATE_KEY.public_key()),
        "leaf_public_key_pem": _TEST_SIGN_PUBLIC_KEY_PEM,
        "issued_at": "2026-09-07T00:00:00Z",
        "not_after": "2099-12-31T23:59:59Z",
    }
    payload = json.dumps(doc, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    sig = _TEST_ROOT_PRIVATE_KEY.sign(payload)
    return _b64u(payload) + "." + _b64u(sig)


_TEST_LEAF_CREDENTIAL = _make_leaf_credential()


def _sign_checksum(checksum, version="1.0.0"):
    import base64
    sig = _TEST_SIGN_PRIVATE_KEY.sign(f"{checksum}:{version}".encode("utf-8"))
    return base64.b64encode(sig).decode("ascii")


class FakeResponse:
    def __init__(self, payload=None, status_code=200, headers=None, raw=None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self._raw = raw

    def json(self):
        return self.payload

    def iter_content(self, chunk_size=8192):
        yield self._raw


def _signed_response(zip_bytes, tool_version="1.0.0", extra_headers=None):
    """构造带合法发布签名头 + 叶子凭证头的 ZIP 响应（H-3 根/叶）"""
    checksum = hashlib.sha256(zip_bytes).hexdigest()
    headers = {
        "Content-Type": "application/zip",
        "X-Tool-Checksum": checksum,
        "X-Tool-Checksum-Sig": _sign_checksum(checksum, tool_version),
        "X-Tool-Version": tool_version,
        "X-Tool-Sign-Cred": _TEST_LEAF_CREDENTIAL,
    }
    if extra_headers:
        headers.update(extra_headers)
    return FakeResponse(headers=headers, raw=zip_bytes)


class DummyRunner(TFP_ToolRunnerMixin):
    def __init__(self):
        self.TFP_DPI_SCALE_FACTOR = 1.0
        self.backend_url = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
        self.frontend_version = "1.0.0"
        self._last_download_error = None
        self.non_builtin_tools = {}
        self._tools_data_lock = threading.Lock()
        self._tools_with_update = set()
        self.local_tools_dir = pathlib.Path(tempfile.gettempdir())

    def update_local_tool_version(self, tool_ident, tool_type):
        return True

    def get_localized_tool_title(self, tool_info):
        # 真实实现位于工具列表相关 mixin；测试仅需返回稳定名称
        return tool_info.get("tool_ident", "")

    def update_tool_buttons(self):
        pass


def _make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in files:
            z.writestr(name, content)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _silence_wx(monkeypatch):
    """静默 wx 弹窗/异步调度，避免无 GUI 环境问题；并注入测试根公钥（H-3 根/叶）"""
    monkeypatch.setattr(wx, "CallAfter", lambda fn, *a, **k: None)
    monkeypatch.setattr(wx, "MessageBox", lambda *a, **k: 0)
    monkeypatch.setattr(tt_signer, "TOOL_SIGN_ROOT_PUBLIC_KEY_PEM", _TEST_ROOT_PUBLIC_KEY_PEM)


# ========== DPI 缩放 ==========

def test_spx_calc():
    runner = DummyRunner()
    runner.TFP_DPI_SCALE_FACTOR = 1.0
    assert runner._spx_calc(100) == 100
    assert runner._spx_calc(-1) == -1
    runner.TFP_DPI_SCALE_FACTOR = 1.5
    assert runner._spx_calc(100) == 150


# ========== Builtin 工具登录门控 ==========

def test_check_builtin_tool_login_logged_in(mgr):
    mgr._user = object()
    mgr._session_token = "t"
    runner = DummyRunner()
    assert runner._check_builtin_tool_login({"tool_ident": "X"}) is True


def test_check_builtin_tool_login_backend_reachable_requires_login(mgr):
    """后端可达时：未登录必须先登录（不弹离线宽限期，宽限期机制已移除）"""
    mgr._user = None
    mgr._session_token = None
    runner = DummyRunner()
    runner._prompt_login_for_builtin = lambda tool_info: None
    # 后端可达场景：未登录时必须登录
    runner._is_backend_reachable = lambda: True

    # 无保存会话 → 拒绝（要求登录）
    assert runner._check_builtin_tool_login({"tool_ident": "X"}) is False


def test_check_builtin_tool_login_backend_unreachable_allows(mgr):
    """后端不可达时：开源免费工具免登录放行（不检查登录历史，宽限期机制已移除）"""
    mgr._user = None
    mgr._session_token = None
    runner = DummyRunner()
    runner._prompt_login_for_builtin = lambda tool_info: None
    runner._is_backend_reachable = lambda: False

    # 从未登录过 → 放行
    assert runner._check_builtin_tool_login({"tool_ident": "X"}) is True


# ========== 收费工具登录门控与离线运行 ==========

def test_check_tool_login_logged_in(mgr):
    mgr._user = object()
    mgr._session_token = "t"
    runner = DummyRunner()
    assert runner._check_tool_login({"tool_ident": "TestTool", "tool_type": "RemoteProgram"}) is True


def test_check_tool_login_backend_reachable_requires_login(mgr, monkeypatch):
    """后端可达时：未登录必须先登录（提示并弹出登录框）"""
    mgr._user = None
    mgr._session_token = None
    runner = DummyRunner()
    runner._is_backend_reachable = lambda: True

    class _FakeDlg:
        def __init__(self, *a, **k):
            pass

        def ShowModal(self):
            return 0

        def Destroy(self):
            pass

    monkeypatch.setattr(wx, "MessageDialog", _FakeDlg)
    requested = {}
    monkeypatch.setattr(auth_manager, "request_login_via_ipc",
                        lambda message=None: requested.setdefault("called", True))
    assert runner._check_tool_login(
        {"tool_ident": "TestTool", "tool_type": "RemoteProgram", "tool_is_free": False}) is False
    assert requested.get("called") is True


def test_check_tool_login_backend_unreachable_downloaded_allows(mgr, tmp_path):
    """后端不可达+未登录：已下载到本地的 RemoteProgram 放行（离线试用免费功能）"""
    mgr._user = None
    mgr._session_token = None
    runner = DummyRunner()
    runner.local_tools_dir = tmp_path
    runner._is_backend_reachable = lambda: False

    # PyInstaller --onedir 布局：<local_dir>/<tool_ident>/<tool_ident>
    exe = tmp_path / "tools_remote_program" / "TestTool" / "TestTool"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"\x7fELF")
    assert runner._check_tool_login({"tool_ident": "TestTool", "tool_type": "RemoteProgram"}) is True


def test_check_tool_login_backend_unreachable_not_downloaded_prompts_connection(mgr, tmp_path):
    """后端不可达+未登录+未下载：提示需要连接服务器（不弹登录框），阻止打开"""
    mgr._user = None
    mgr._session_token = None
    runner = DummyRunner()
    runner.local_tools_dir = tmp_path
    runner._is_backend_reachable = lambda: False
    prompted = {}
    runner._prompt_offline_connection = lambda tool_name: prompted.setdefault("called", True)
    assert runner._check_tool_login({"tool_ident": "TestTool", "tool_type": "RemoteProgram"}) is False
    assert prompted.get("called") is True


def test_check_tool_login_backend_unreachable_webpage_prompts_connection(mgr, tmp_path):
    """RemoteWebpage 页面由后端提供，离线一律提示需要连接服务器"""
    mgr._user = None
    mgr._session_token = None
    runner = DummyRunner()
    runner.local_tools_dir = tmp_path
    runner._is_backend_reachable = lambda: False
    prompted = {}
    runner._prompt_offline_connection = lambda tool_name: prompted.setdefault("called", True)
    assert runner._check_tool_login({"tool_ident": "TestWeb", "tool_type": "RemoteWebpage"}) is False
    assert prompted.get("called") is True


def test_run_remote_program_offline_runs_local_exe(mgr, tmp_path):
    """后端不可达：本地已有完整性校验通过的 EXE 时，更新失败(NETWORK_ERROR)后离线启动本地 EXE"""
    mgr._user = None
    mgr._session_token = None
    runner = DummyRunner()
    runner.local_tools_dir = tmp_path
    runner.embedded_tools = {}
    runner._is_backend_reachable = lambda: False
    runner._show_loading_panel = lambda tool_name: None
    runner._hide_loading_panel = lambda panel: None
    runner._verify_exe_integrity = lambda tool_ident, exe_file: True

    exe = tmp_path / "tools_remote_program" / "TestTool" / "TestTool"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"\x7fELF")

    def _fake_update(tool_info, local_dir, force_update=False):
        runner._last_download_error = 'NETWORK_ERROR'
        return False

    runner.try_update_tool = _fake_update

    launched = {}

    def _fake_launch(tool_info, exe_file, local_dir, backend_url, loading_panel):
        launched["exe"] = str(exe_file)
        return True

    runner._launch_exe_tool = _fake_launch

    tool_info = {"tool_ident": "TestTool", "tool_type": "RemoteProgram", "tool_version": "1.0.0"}
    assert runner.run_remote_program(tool_info) is True
    assert "exe" in launched


def test_run_remote_program_offline_no_exe_blocks(mgr, tmp_path):
    """后端不可达+已登录但本地无 EXE：NETWORK_ERROR 弹窗提示并阻止"""
    mgr._user = object()
    mgr._session_token = "t"
    runner = DummyRunner()
    runner.local_tools_dir = tmp_path
    runner.embedded_tools = {}
    runner._is_backend_reachable = lambda: False
    runner._show_loading_panel = lambda tool_name: None
    runner._hide_loading_panel = lambda panel: None

    def _fake_update(tool_info, local_dir, force_update=False):
        runner._last_download_error = 'NETWORK_ERROR'
        return False

    runner.try_update_tool = _fake_update

    launched = {}
    runner._launch_exe_tool = lambda *a, **k: launched.setdefault("called", True) or True

    tool_info = {"tool_ident": "TestTool", "tool_type": "RemoteProgram", "tool_version": "1.0.0"}
    assert runner.run_remote_program(tool_info) is False
    assert not launched


# ========== 下载解压安全 ==========

def test_download_and_extract_ok(tmp_path):
    runner = DummyRunner()
    target = tmp_path / "tool"
    zip_bytes = _make_zip([("main.py", "print(1)"), ("data/readme.txt", "hello")])
    resp = _signed_response(zip_bytes)
    tool_info = {"tool_ident": "ToolX", "tool_type": "RemoteProgram"}
    assert runner.download_and_extract_tool_from_response(resp, tool_info, target) is True
    assert (target / "main.py").exists()
    assert (target / "data" / "readme.txt").exists()


def test_download_and_extract_clears_upgrade_tag(tmp_path, monkeypatch):
    """安装成功后立即清除该工具的升级标记并请求刷新卡片（Upgrade 标签残留修复）"""
    refresh_calls = []
    monkeypatch.setattr(wx, "CallAfter", lambda fn, *a, **k: refresh_calls.append(fn))
    runner = DummyRunner()
    runner._tools_with_update = {"ToolX"}
    target = tmp_path / "tool"
    zip_bytes = _make_zip([("main.py", "print(1)")])
    resp = _signed_response(zip_bytes)
    tool_info = {"tool_ident": "ToolX", "tool_type": "RemoteProgram"}
    assert runner.download_and_extract_tool_from_response(resp, tool_info, target) is True
    # 该工具的升级标记已被清除，且通过 wx.CallAfter 请求了卡片刷新
    assert "ToolX" not in runner._tools_with_update
    assert refresh_calls == [runner.update_tool_buttons]


def test_download_and_extract_oversize_rejected(tmp_path, monkeypatch):
    # L-5（2026-09-01）：ZIP 下载大小上限——超限立即中止并清理临时文件（fail-closed）
    from tfp_mixins import tfp_tool_runner_mixin as m

    monkeypatch.setattr(m, "_MAX_TOOL_ZIP_BYTES", 100)  # 注入极小上限
    tmp_src = tmp_path / "zz_zip_tmp"
    monkeypatch.setattr(m.tempfile, "mkdtemp",
                        lambda: tmp_src.mkdir(parents=True, exist_ok=True) or str(tmp_src))

    runner = DummyRunner()
    zip_bytes = _make_zip([("a.txt", "x" * 1000)])  # 远超 100 字节上限
    resp = _signed_response(zip_bytes)
    target = tmp_path / "tool_dir"
    assert runner.download_and_extract_tool_from_response(
        resp, {"tool_ident": "ToolX", "tool_version": "1.0.0", "tool_type": "RemoteProgram"}, target
    ) is False
    # 超限后临时目录（含 ZIP）被 finally 清理
    assert not tmp_src.exists()
    # fail-closed：目标目录不写入任何解压内容
    assert not (target / "a.txt").exists()


def test_download_and_extract_zip_slip_rejected(tmp_path):
    """Zip Slip 路径遍历攻击必须被拒绝"""
    runner = DummyRunner()
    target = tmp_path / "tool"
    zip_bytes = _make_zip([("../evil.py", "import os; os.system('x')")])
    resp = _signed_response(zip_bytes)
    tool_info = {"tool_ident": "ToolX", "tool_type": "RemoteProgram"}
    assert runner.download_and_extract_tool_from_response(resp, tool_info, target) is False
    # 文件不得落在目标目录之外
    assert not (target.parent / "evil.py").exists()


def test_download_and_extract_no_checksum_rejected(tmp_path):
    """服务端未提供校验和时拒绝解压运行（v3.4 安全 F1 回归测试）"""
    runner = DummyRunner()
    target = tmp_path / "tool"
    zip_bytes = _make_zip([("main.py", "x")])
    resp = FakeResponse(
        headers={"Content-Type": "application/zip"},  # 无 X-Tool-Checksum
        raw=zip_bytes,
    )
    tool_info = {"tool_ident": "ToolX", "tool_type": "RemoteProgram"}
    assert runner.download_and_extract_tool_from_response(resp, tool_info, target) is False
    assert not (target / "main.py").exists()


def test_download_and_extract_checksum_mismatch_rejected(tmp_path):
    """验签通过但 ZIP SHA-256 与校验和不一致时拒绝（H-3）"""
    runner = DummyRunner()
    target = tmp_path / "tool"
    zip_bytes = _make_zip([("main.py", "x")])
    bad_checksum = "0" * 64
    resp = FakeResponse(
        headers={
            "Content-Type": "application/zip",
            "X-Tool-Checksum": bad_checksum,
            "X-Tool-Checksum-Sig": _sign_checksum(bad_checksum),
            "X-Tool-Sign-Cred": _TEST_LEAF_CREDENTIAL,
        },
        raw=zip_bytes,
    )
    tool_info = {"tool_ident": "ToolX", "tool_type": "RemoteProgram"}
    assert runner.download_and_extract_tool_from_response(resp, tool_info, target) is False


def test_download_and_extract_signature_missing_rejected(tmp_path):
    """公钥已配置且凭证合法，但响应缺发布签名时拒绝（H-3 新增）"""
    runner = DummyRunner()
    target = tmp_path / "tool"
    zip_bytes = _make_zip([("main.py", "x")])
    checksum = hashlib.sha256(zip_bytes).hexdigest()
    resp = FakeResponse(
        headers={
            "Content-Type": "application/zip",
            "X-Tool-Checksum": checksum,
            "X-Tool-Sign-Cred": _TEST_LEAF_CREDENTIAL,  # 有凭证但无签名头
        },
        raw=zip_bytes,
    )
    tool_info = {"tool_ident": "ToolX", "tool_type": "RemoteProgram"}
    assert runner.download_and_extract_tool_from_response(resp, tool_info, target) is False


def test_download_and_extract_signature_bad_rejected(tmp_path):
    """发布签名验证失败时拒绝（H-3 新增）"""
    runner = DummyRunner()
    target = tmp_path / "tool"
    zip_bytes = _make_zip([("main.py", "x")])
    checksum = hashlib.sha256(zip_bytes).hexdigest()
    resp = FakeResponse(
        headers={
            "Content-Type": "application/zip",
            "X-Tool-Checksum": checksum,
            "X-Tool-Checksum-Sig": _sign_checksum(checksum, version="2.0.0"),  # 版本不符 → 验签失败
            "X-Tool-Sign-Cred": _TEST_LEAF_CREDENTIAL,
        },
        raw=zip_bytes,
    )
    tool_info = {"tool_ident": "ToolX", "tool_type": "RemoteProgram"}
    assert runner.download_and_extract_tool_from_response(resp, tool_info, target) is False


def test_download_and_extract_credential_missing_rejected(tmp_path):
    """根公钥已配置但响应缺叶子凭证头（X-Tool-Sign-Cred）时拒绝（H-3 根/叶新增）"""
    runner = DummyRunner()
    target = tmp_path / "tool"
    zip_bytes = _make_zip([("main.py", "x")])
    checksum = hashlib.sha256(zip_bytes).hexdigest()
    resp = FakeResponse(
        headers={
            "Content-Type": "application/zip",
            "X-Tool-Checksum": checksum,
            "X-Tool-Checksum-Sig": _sign_checksum(checksum),  # 签名合法但无凭证
        },
        raw=zip_bytes,
    )
    tool_info = {"tool_ident": "ToolX", "tool_type": "RemoteProgram"}
    assert runner.download_and_extract_tool_from_response(resp, tool_info, target) is False
    assert not (target / "main.py").exists()


def test_download_and_extract_credential_bad_rejected(tmp_path):
    """叶子凭证非法（篡改 sig）时拒绝（H-3 根/叶新增）"""
    runner = DummyRunner()
    target = tmp_path / "tool"
    zip_bytes = _make_zip([("main.py", "x")])
    checksum = hashlib.sha256(zip_bytes).hexdigest()
    payload_b64, sig_b64 = _TEST_LEAF_CREDENTIAL.split(".")
    sig = __import__("base64").urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
    # 翻转最后一字节（异或 0x01，保证与原签名不同）
    bad_cred = payload_b64 + "." + _b64u(sig[:-1] + bytes([sig[-1] ^ 0x01]))
    resp = FakeResponse(
        headers={
            "Content-Type": "application/zip",
            "X-Tool-Checksum": checksum,
            "X-Tool-Checksum-Sig": _sign_checksum(checksum),
            "X-Tool-Sign-Cred": bad_cred,
        },
        raw=zip_bytes,
    )
    tool_info = {"tool_ident": "ToolX", "tool_type": "RemoteProgram"}
    assert runner.download_and_extract_tool_from_response(resp, tool_info, target) is False
    assert not (target / "main.py").exists()


def test_root_unconfigured_dev_allows(tmp_path, monkeypatch):
    """根公钥未配置 + 源码开发模式 → 放行（本地开发，日志警告）"""
    from tfp_mixins import tfp_tool_runner_mixin as m
    monkeypatch.setattr(tt_signer, "TOOL_SIGN_ROOT_PUBLIC_KEY_PEM", "")
    monkeypatch.setattr(m, "is_dev_mode", lambda: True)
    runner = DummyRunner()
    target = tmp_path / "tool"
    zip_bytes = _make_zip([("main.py", "print(1)")])
    resp = _signed_response(zip_bytes)
    tool_info = {"tool_ident": "ToolX", "tool_type": "RemoteProgram"}
    assert runner.download_and_extract_tool_from_response(resp, tool_info, target) is True
    assert (target / "main.py").exists()


def test_root_unconfigured_production_rejected(tmp_path, monkeypatch):
    """根公钥未配置 + 生产/本地测试构建 → fail-closed 拒绝"""
    from tfp_mixins import tfp_tool_runner_mixin as m
    monkeypatch.setattr(tt_signer, "TOOL_SIGN_ROOT_PUBLIC_KEY_PEM", "")
    monkeypatch.setattr(m, "is_dev_mode", lambda: False)
    runner = DummyRunner()
    target = tmp_path / "tool"
    zip_bytes = _make_zip([("main.py", "print(1)")])
    resp = _signed_response(zip_bytes)
    tool_info = {"tool_ident": "ToolX", "tool_type": "RemoteProgram"}
    assert runner.download_and_extract_tool_from_response(resp, tool_info, target) is False
    assert not (target / "main.py").exists()


def test_download_and_extract_bad_zip_rejected(tmp_path):
    runner = DummyRunner()
    target = tmp_path / "tool"
    resp = FakeResponse(
        headers={"Content-Type": "application/zip", "X-Tool-Checksum": "0" * 64},
        raw=b"not a zip at all",
    )
    tool_info = {"tool_ident": "ToolX", "tool_type": "RemoteProgram"}
    assert runner.download_and_extract_tool_from_response(resp, tool_info, target) is False


def test_download_and_extract_preserves_icon(tmp_path):
    """更新时保留 app_icon.ico（旧版本资源备份恢复）"""
    runner = DummyRunner()
    target = tmp_path / "tool"
    target.mkdir(parents=True)
    (target / "app_icon.ico").write_bytes(b"ICON")
    (target / "old_main.py").write_text("old")
    zip_bytes = _make_zip([("main.py", "new")])
    resp = _signed_response(zip_bytes)
    tool_info = {"tool_ident": "ToolX", "tool_type": "RemoteProgram"}
    assert runner.download_and_extract_tool_from_response(resp, tool_info, target) is True
    assert (target / "main.py").exists()
    assert not (target / "old_main.py").exists()
    assert (target / "app_icon.ico").read_bytes() == b"ICON"


def test_download_and_extract_writes_exe_manifest(tmp_path):
    """含主 EXE 的工具包下载成功后写入完整性清单（0600，H-3 新增）"""
    from tfp_utils.tfp_platform import get_platform_tag as _plat
    exe_name = "ToolX.exe" if _plat() == "windows" else "ToolX"
    runner = DummyRunner()
    runner.local_tools_dir = tmp_path
    target = tmp_path / "tool"
    zip_bytes = _make_zip([(exe_name, b"\x7fELF-binary-content")])
    resp = _signed_response(zip_bytes)
    tool_info = {"tool_ident": "ToolX", "tool_type": "RemoteProgram"}
    assert runner.download_and_extract_tool_from_response(resp, tool_info, target) is True
    manifest_path = tmp_path / ".tfp_manifests" / "ToolX.json"
    assert manifest_path.exists()
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["exe_sha256"] == hashlib.sha256(b"\x7fELF-binary-content").hexdigest()


def test_exe_integrity_manifest_verify_and_tamper(tmp_path):
    """本地 EXE 完整性复验：正常通过 / 篡改拒绝 / 清单缺失拒绝（H-3 新增）"""
    from tfp_utils.tfp_platform import get_platform_tag as _plat
    exe_name = "ToolX.exe" if _plat() == "windows" else "ToolX"
    runner = DummyRunner()
    runner.local_tools_dir = tmp_path
    tool_dir = tmp_path / "tool"
    tool_dir.mkdir()
    exe_path = tool_dir / exe_name
    exe_path.write_bytes(b"\x7fELF-original")

    # 无清单 → 拒绝
    assert runner._verify_exe_integrity("ToolX", exe_path) is False

    assert runner._write_tool_manifest("ToolX", "RemoteProgram", "1.0.0", tool_dir) is True
    assert runner._verify_exe_integrity("ToolX", exe_path) is True

    # 篡改磁盘 EXE → 拒绝（fail-closed）
    exe_path.write_bytes(b"\x7fELF-TAMPERED")
    assert runner._verify_exe_integrity("ToolX", exe_path) is False


# ========== 远程网页 URL ==========

def test_try_get_remote_webpage_url_success(monkeypatch):
    runner = DummyRunner()
    monkeypatch.setattr(
        requests, "get",
        lambda *a, **k: FakeResponse({"status": "success", "url": "https://tool.example.com", "webview_token": "abc"}),
    )
    url, token, reason = runner.try_get_remote_webpage_url({"tool_ident": "P", "tool_version": "1.0"})
    assert url == "https://tool.example.com"
    assert token == "abc"
    assert reason is None
    # H-2 加固：一次性 token 不得拼入 URL
    assert "token=" not in url


def test_try_get_remote_webpage_url_network_error(monkeypatch):
    runner = DummyRunner()
    def _raise(*a, **k):
        raise requests.exceptions.ConnectionError()
    monkeypatch.setattr(requests, "get", _raise)
    assert runner.try_get_remote_webpage_url({"tool_ident": "P"}) == (None, None, 'network_error')
