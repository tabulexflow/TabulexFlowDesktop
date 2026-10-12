# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""TFP_ToolIPCMixin IPC 机制测试

覆盖：IPC 服务器启动与 Token 认证（真实 socket）、上下文文件生成（Token 不落盘）、
过期上下文文件清理、端口分配、API 代理请求的同步校验分支。
"""
import json
import os
import pathlib
import socket
import time
import tempfile

import pytest

from build_mode import BACKEND_HOST, BACKEND_PORT, IPC_HOST_IP

from tfp_mixins.tfp_tool_ipc_mixin import TFP_ToolIPCMixin, tempfile as ipc_tempfile


class DummyIPC(TFP_ToolIPCMixin):
    def __init__(self):
        self.embedded_tools = {}
        self.backend_url = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
        self.user_setting_dir = pathlib.Path(tempfile.gettempdir())


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((IPC_HOST_IP, 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ========== 端口分配 ==========

def test_start_ipc_server_dynamic_port():
    """动态端口——port=0 由系统分配空闲端口，不同工具获得不同端口"""
    host = DummyIPC()
    host.embedded_tools["ToolA"] = {}
    host.embedded_tools["ToolB"] = {}
    sock1, token1, port1 = host._start_ipc_server("ToolA", 0)
    sock2, token2, port2 = host._start_ipc_server("ToolB", 0)
    try:
        assert port1 > 0 and port2 > 0
        assert port1 != port2
        assert token1 and len(token1) >= 32
        assert token2 and len(token2) >= 32
    finally:
        sock1.close()
        sock2.close()


# ========== 上下文文件 ==========

def test_prepare_tool_context_not_logged_in(mgr, tmp_path):
    host = DummyIPC()
    host.user_setting_dir = tmp_path
    tool_info = {"tool_ident": "TabulexBomComparator"}
    context_file, env_var, token = host._prepare_tool_context(
        tool_info, tmp_path, f"http://{BACKEND_HOST}:{BACKEND_PORT}", ipc_token="tok-secret-123", socket_port=12345
    )
    assert context_file is not None and pathlib.Path(context_file).exists()
    assert env_var == "TFP_IPC_TOKEN_TabulexBomComparator"
    assert token == "tok-secret-123"

    data = json.loads(pathlib.Path(context_file).read_text(encoding="utf-8"))
    assert data["tool_ident"] == "TabulexBomComparator"
    assert data["ipc"]["socket_host"] == IPC_HOST_IP
    assert data["ipc"]["socket_port"] == 12345
    assert data["ipc"]["token_env"] == "TFP_IPC_TOKEN_TabulexBomComparator"
    assert data["auth"]["can_request_api"] is False  # 未登录
    # ipc_token 不写入上下文文件
    assert "tok-secret-123" not in pathlib.Path(context_file).read_text(encoding="utf-8")
    pathlib.Path(context_file).unlink()


def test_prepare_tool_context_logged_in(mgr, tmp_path):
    from tfp_auth.tfp_auth_manager import TFP_UserInfo
    mgr._user = TFP_UserInfo(id=42, username="bob")
    mgr._session_token = "session-t"
    host = DummyIPC()
    host.user_setting_dir = tmp_path
    context_file, _, _ = host._prepare_tool_context(
        {"tool_ident": "ToolX"}, tmp_path, f"http://{BACKEND_HOST}:{BACKEND_PORT}", ipc_token="t", socket_port=54321
    )
    data = json.loads(pathlib.Path(context_file).read_text(encoding="utf-8"))
    assert data["auth"]["can_request_api"] is True
    assert data["auth"]["user_id"] == 42
    assert data["auth"]["username"] == "bob"
    pathlib.Path(context_file).unlink()


# ========== 过期上下文文件清理 ==========

def test_cleanup_stale_context_files(tmp_path, monkeypatch):
    monkeypatch.setattr(ipc_tempfile, "gettempdir", lambda: str(tmp_path))
    host = DummyIPC()

    stale = tmp_path / "tool_context_ToolA_old.json"
    stale.write_text("{}", encoding="utf-8")
    # 修改 mtime 为 2 小时前（超过 1 小时阈值）
    old = time.time() - 7200
    os.utime(stale, (old, old))

    fresh = tmp_path / "tool_context_ToolB_new.json"
    fresh.write_text("{}", encoding="utf-8")

    host._cleanup_stale_context_files()

    assert not stale.exists()
    assert fresh.exists()
    fresh.unlink()


def test_cleanup_stale_context_files_skips_other_uid(tmp_path, monkeypatch):
    # L-6（2026-09-01）：仅清理本机当前用户属主的文件，
    # 其他 uid 属主的临时文件不得被删除（原实现 glob 会误删其他用户/实例的文件）
    monkeypatch.setattr(ipc_tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr("tfp_mixins.tfp_tool_ipc_mixin.os.getuid", lambda: 65534)  # 模拟"其他用户"视角
    host = DummyIPC()

    other_uid_file = tmp_path / "tool_context_OtherUser_old.json"
    other_uid_file.write_text("{}", encoding="utf-8")
    old = time.time() - 7200  # 2 小时前（超过 1 小时阈值）
    os.utime(other_uid_file, (old, old))

    host._cleanup_stale_context_files()

    assert other_uid_file.exists()  # 非本 uid 属主 → 不清理
    other_uid_file.unlink()


# ========== IPC 服务器与 Token 认证（真实 socket） ==========

def test_start_ipc_server_auth_flow(mgr):
    host = DummyIPC()
    host.embedded_tools["ToolX"] = {}  # 模拟 _launch_exe_tool 中已插入的工具条目
    port = _free_port()
    server_sock, token, actual_port = host._start_ipc_server("ToolX", port)
    assert server_sock is not None
    assert token and len(token) >= 32
    assert actual_port == port

    try:
        # 1. 错误 Token → 服务器关闭连接
        bad = socket.create_connection((IPC_HOST_IP, port), timeout=3)
        bad.sendall((json.dumps({"type": "auth", "token": "wrong"}) + "\n").encode("utf-8"))
        bad.settimeout(2)
        assert bad.recv(1024) == b""
        bad.close()

        # 2. 正确 Token → 认证成功，记录 client_socket
        good = socket.create_connection((IPC_HOST_IP, port), timeout=3)
        good.sendall((json.dumps({"type": "auth", "token": token}) + "\n").encode("utf-8"))
        time.sleep(0.3)
        assert host.embedded_tools["ToolX"].get("client_socket") is not None
        assert host.embedded_tools["ToolX"].get("ipc_token") == token
        good.close()
    finally:
        server_sock.close()


def test_start_ipc_server_invalid_json_ignored(mgr):
    host = DummyIPC()
    host.embedded_tools["ToolY"] = {}
    port = _free_port()
    server_sock, token, _actual_port = host._start_ipc_server("ToolY", port)
    assert server_sock is not None
    try:
        c = socket.create_connection((IPC_HOST_IP, port), timeout=3)
        c.sendall(b"not-json\n")
        time.sleep(0.2)
        # 无效 JSON 被忽略，连接仍存活（未认证也不关闭）
        c.sendall((json.dumps({"type": "auth", "token": token}) + "\n").encode("utf-8"))
        time.sleep(0.3)
        assert host.embedded_tools["ToolY"].get("client_socket") is not None
        c.close()
    finally:
        server_sock.close()


# ========== API 代理请求（同步分支） ==========

def test_handle_ipc_api_request_missing_path():
    host = DummyIPC()
    host.embedded_tools["T"] = {}
    calls = []
    host._send_ipc_api_response = lambda tid, rid, rd: calls.append((tid, rid, rd))
    host._handle_ipc_api_request("T", {"request_id": "r1", "method": "GET"})
    assert len(calls) == 1
    assert calls[0][2]["status_code"] == 400


def test_send_ipc_api_response_no_socket():
    host = DummyIPC()
    host.embedded_tools["T"] = {}  # 无 client_socket
    # 不应抛异常，仅记录 warning
    host._send_ipc_api_response("T", "r1", {"status_code": 200, "body": {}})


# ========== M-1 加固：IPC API 代理 path 白名单 / extra_headers 忽略 ==========

def test_is_allowed_ipc_api_path():
    host = DummyIPC()
    # 允许：/api/ 前缀的正常后端 API 路径（子工具实际调用面）
    assert host._is_allowed_ipc_api_path("/api/v1/remote_program/TabulexBomComparator/compare-async-v2")
    assert host._is_allowed_ipc_api_path("/api/v1/auth/me")
    assert host._is_allowed_ipc_api_path("/api/v1/services/active?tool_ident=TabulexBomComparator")
    assert host._is_allowed_ipc_api_path("/api/v1/user_tool_setting/TabulexBomComparator")
    # 拒绝：空/非 /api/ 前缀/协议穿越/路径走私构造/非字符串
    assert host._is_allowed_ipc_api_path("") is False
    assert host._is_allowed_ipc_api_path("not/api/x") is False
    assert host._is_allowed_ipc_api_path("http://evil.com/api/x") is False
    assert host._is_allowed_ipc_api_path("/api/v1//evil") is False
    assert host._is_allowed_ipc_api_path("/api\\evil") is False
    assert host._is_allowed_ipc_api_path("/api/v1/x@evil") is False
    assert host._is_allowed_ipc_api_path(None) is False
    assert host._is_allowed_ipc_api_path(123) is False


def test_handle_ipc_api_request_path_not_allowed():
    """M-1：非白名单 path 一律 403（fail-closed）"""
    host = DummyIPC()
    host.embedded_tools["T"] = {}
    calls = []
    host._send_ipc_api_response = lambda tid, rid, rd: calls.append((tid, rid, rd))
    for bad in ("http://evil.com/x", "not-an-api", "/api/v1//evil", "static/foo"):
        calls.clear()
        host._handle_ipc_api_request("T", {"request_id": "r", "method": "GET", "path": bad})
        assert len(calls) == 1
        assert calls[0][2]["status_code"] == 403


def test_handle_ipc_api_request_extra_headers_ignored(mgr, monkeypatch):
    """M-1：extra_headers 被忽略，仅附加 Content-Type + Authorization（真实 token 覆盖注入）"""
    import time as _time
    import tfp_mixins.tfp_tool_ipc_mixin as ipc_mod
    from tfp_auth.tfp_auth_manager import TFP_UserInfo

    mgr._user = TFP_UserInfo(id=7, username="alice")
    mgr._session_token = "sess-token-abc"

    captured = {}

    def fake_get(url, headers=None, timeout=30):
        captured["url"] = url
        captured["headers"] = headers or {}
        return type("R", (), {"status_code": 200})()

    monkeypatch.setattr(ipc_mod.http_requests, "get", fake_get)

    host = DummyIPC()
    host.embedded_tools["T"] = {}
    host._handle_ipc_api_request("T", {
        "request_id": "r1",
        "method": "GET",
        "path": "/api/v1/auth/me",
        "extra_headers": {"X-Injected": "evil", "Authorization": "Bearer injected"},
    })

    # 后台线程执行，等待 HTTP 调用被捕获
    for _ in range(50):
        if captured:
            break
        _time.sleep(0.02)
    assert captured.get("url", "").endswith("/api/v1/auth/me")
    hdrs = captured.get("headers", {})
    assert "X-Injected" not in hdrs
    assert hdrs.get("Content-Type") == "application/json"
    assert hdrs.get("Authorization") == "Bearer sess-token-abc"
