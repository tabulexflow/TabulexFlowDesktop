# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-TabulexFlow-Commercial
#
# Dual License / 双重许可:
#
#   Option 1 - GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later).
#   Applies to the open-source frontend main program and its BuiltinProgram tools.
#   选项 1 - GNU AGPL v3 或更高版本（AGPL-3.0-or-later）。
#   适用于开源前端主程序及其 BuiltinProgram 工具。
#
#   Option 2 - TabulexFlow Commercial License
#   (LicenseRef-TabulexFlow-Commercial).
#   Applies to closed-source commercial tools in the TabulexFlow ecosystem
#   that are authorized to use this file under that license.
#   选项 2 - TabulexFlow 商业许可（LicenseRef-TabulexFlow-Commercial）。
#   适用于已获授权使用该许可的 TabulexFlow 生态内闭源商业工具。
#
# Full terms of both licenses are provided in the LICENSE file in this directory
# (AGPL terms are also in LICENSE.txt at the repository root).
# 两种许可的完整条款见本目录下 LICENSE 文件（AGPL 条款另见仓库根 LICENSE.txt）。
#
# IMPORTANT / 重要（维护者须知）：
# 本文件属双许可 SDK，不得 import 仅以 GPL/AGPL 授权的 copyleft-only 库（如 mutagen、PyMuPDF），
# 否则商业许可选项将失效。详见本目录 LICENSE 文件的 "Maintainer Note / 维护者须知"。
# This file is dual-licensed; do NOT import copyleft-only (GPL/AGPL-exclusive) libraries
# such as mutagen or PyMuPDF, or the commercial license option is invalidated.
# See the Maintainer Note in the LICENSE file in this directory.

"""
TF IPC SDK — RemoteProgram 子工具的高层 IPC 通信库（SDK权威源）

本 SDK 封装了底层 IPC 协议（Socket 连接、Token 认证、心跳、消息序列化），
并提供 API 代理调用接口，使子工具无需直接持有 session_token 或了解后端 API 细节。

使用方式：
    sdk = TFP_IPCSDK()
    sdk.connect(host, port, token)
    sdk.on_command("auth_update", on_auth_update)
    sdk.notify_ready()

    # 通过 IPC 代理调用后端 API（无需 session_token）
    result = sdk.api_request("GET", API_V1_PREFIX + "/remote_program/my_tool/data")
    result = sdk.api_request("POST", API_V1_PREFIX + "/remote_program/my_tool/action", body={"key": "value"})

    # 通过 IPC 代理检查权限
    perm = sdk.check_permission("my_tool", "advanced_feature")

安全说明：
    - SDK 不暴露任何安全敏感信息（无 Salt、无加密参数、无 token 直接访问）
    - 所有后端 API 请求通过前端主程序中转，子工具不直接持有 session_token
    - IPC Token 仅用于 IPC 连接认证，与后端 API 认证无关

注意：此文件是SDK的权威源。TabulexBomComparator等子工具目录下的 tfp_ipc_sdk.py 副本
应删除，改为从此SDK导入。

快速入门示例 — 最小 RemoteProgram 工具：

    import os
    import sys
    import wx
    import json
    from tfp_toolkit.tfp_ipc_sdk import TFP_IPCSDK
    from tfp_toolkit.tfp_dpi import spx_calc

    TOOL_IDENT = "MyRemoteTool"

    class MyRemoteTool:
        def __init__(self):
            self.sdk = TFP_IPCSDK()
            self.sdk.on_command("show", self._on_show)
            self.sdk.on_command("close", self._on_close)
            self.sdk.on_command("auth_update", self._on_auth_update)
            self.frame = None

        def run(self, context_file):
            # 1. 读取上下文文件
            with open(context_file, 'r', encoding='utf-8') as f:
                ctx = json.load(f)

            # 2. 连接 IPC（从上下文自动读取 token 环境变量）
            ipc_config = ctx.get('ipc', {})
            self.sdk.connect_from_context(ipc_config, TOOL_IDENT)

            # 3. 创建窗口
            app = wx.App(False)
            self.frame = wx.Frame(None, title="My Tool",
                                  size=(spx_calc(800), spx_calc(600)))
            self.frame.SetMinSize((spx_calc(600), spx_calc(400)))

            # 4. 窗口关闭 = 隐藏（不退出进程）
            self._closing = False
            self.frame.Bind(wx.EVT_CLOSE, self._on_close_event)

            # 5. 通知主程序就绪
            self.sdk.notify_ready()

            self.frame.Show()
            app.MainLoop()

        def _on_show(self, data):
            if not self._closing and self.frame and not self.frame.IsShown():
                self.frame.Show()
                self.frame.Raise()

        def _on_close(self, data):
            self._closing = True
            if self.sdk.is_connected:
                self.sdk.send_closed()
            if self.frame:
                self.frame.Destroy()

        def _on_auth_update(self, data):
            pass  # 更新本地认证状态

        def _on_close_event(self, event):
            if self._closing:
                return
            event.Veto()
            self.frame.Hide()
            if self.sdk.is_connected:
                self.sdk.send_hidden()

    if __name__ == "__main__":
        # 解析 --context 命令行参数
        context_file = None
        args = sys.argv[1:]
        for i, arg in enumerate(args):
            if arg == '--context' and i + 1 < len(args):
                context_file = args[i + 1]
                break

        if context_file:
            tool = MyRemoteTool()
            tool.run(context_file)
        else:
            print("Usage: python tool_main.py --context <context_file>")
"""

import json
import socket
import threading
import time
import uuid
import logging
import traceback
from typing import Optional, Dict, Any, Callable

# 平台后端 API 版本前缀（SDK 侧唯一定义处；主程序侧见 tfp_utils.tfp_api_paths，
# 后端侧见 be_utils.be_api_version。URL 前缀当前统一为 /api/v1。
# 第三方子工具构造 API 路径时应使用本常量，禁止硬编码版本前缀）
API_V1_PREFIX = '/api/v1'

# SDK 版本标识：从包定义处读取（tfp_toolkit/__init__.py 为唯一定义源）。
# 随 IPC 认证消息上报给主程序，用于诊断用户机器上 EXE 内嵌的 SDK 版本。
try:
    from tfp_toolkit import __version__ as _SDK_VERSION
except ImportError:  # pragma: no cover - SDK 文件被脱离包结构单独复制时的防御回退
    _SDK_VERSION = "unknown"

logger = logging.getLogger('TFP_IPC_SDK')

# SDK 异常消息 i18n：优先使用共享 SDK 的 translate（主程序/子工具各自加载其 locales）；
# SDK脱离 i18n 环境使用时回退到英文硬编码（开发者终端可读，终端用户正常情况下不会见到）。
try:
    from tfp_toolkit.tfp_i18n_manager import translate as _i18n_translate
except Exception:  # pragma: no cover - 脱离包结构单独复制时的防御回退
    _i18n_translate = None

_IPC_MESSAGE_EN_FALLBACK = {
    "ipc_error_not_connected": "IPC is not connected; cannot send API requests",
    "ipc_error_send_failed": "Failed to send API request; the IPC connection may be broken",
    "ipc_error_request_timeout": "API request timed out ({timeout}s): {method} {path}",
}


def _ipc_message(key, en_fallback, **kwargs):
    """按当前语言翻译 SDK 异常消息；键不可用时回退英文"""
    if _i18n_translate is not None:
        try:
            text = _i18n_translate(key, **kwargs)
            if text and text != key:
                return text
        except Exception:  # pragma: no cover - i18n 异常不阻断 SDK 主流程
            pass
    if kwargs:
        try:
            return en_fallback.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass
    return en_fallback


class TFP_IPCAPIError(Exception):
    """IPC API 代理调用异常"""
    def __init__(self, status_code: int, message: str, body: Any = None):
        self.status_code = status_code
        self.message = message
        self.body = body
        super().__init__(f"API proxy error {status_code}: {message}")


# IPC 回环绑定地址（仅本机进程通信），安全
IPC_HOST_IP = "127.0.0.1"


class TFP_IPCSDK:
    """RemoteProgram 子工具的 IPC 通信 SDK

    封装 IPC Socket 连接、认证、心跳、命令处理和 API 代理调用。
    子工具开发者只需使用本类提供的高层方法，无需了解底层 IPC 协议细节。
    """

    def __init__(self):
        self._host: str = IPC_HOST_IP
        self._port: int = 0
        self._token: Optional[str] = None
        self._socket: Optional[socket.socket] = None
        self._connected: bool = False
        self._authenticated: bool = False
        self._listener_thread: Optional[threading.Thread] = None
        self._stop_listener: bool = False
        self._command_handlers: Dict[str, Callable] = {}
        self._pending_requests: Dict[str, dict] = {}  # request_id -> {event, result, error}
        self._pending_lock = threading.Lock()
        self._reconnect_enabled: bool = True
        self._reconnect_interval: float = 3.0
        self._max_reconnect_attempts: int = 5

    # ========== 连接与认证 ==========

    def connect(self, host: str, port: int, token: Optional[str] = None,
                frontend_version: Optional[str] = None) -> bool:
        """连接 IPC 服务器

        Args:
            host: IPC 服务器地址（通常为 IPC_HOST_IP）
            port: IPC 服务器端口
            token: IPC 认证 Token（从环境变量获取）
            frontend_version: 前端主程序版本（从上下文 JSON 的 version 字段读取），
                随认证消息上报供主程序诊断；不传则消息中省略该字段（向后兼容）

        Returns:
            True 表示连接并认证成功
        """
        self._host = host
        self._port = port
        self._token = token

        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(5)
            self._socket.connect((self._host, self._port))
            self._connected = True
            logger.info(f"IPC connected: {host}:{port}")

            # 发送认证消息（版本字段仅诊断用途，主程序只记日志；旧主程序忽略未知字段）
            if token:
                auth_payload = {
                    "type": "auth",
                    "token": token,
                    "sdk_version": _SDK_VERSION,
                }
                if frontend_version:
                    auth_payload["frontend_version"] = frontend_version
                auth_msg = json.dumps(auth_payload)
                self._socket.sendall((auth_msg + "\n").encode('utf-8'))
                self._authenticated = True
                logger.info("IPC auth message sent")

            # 启动监听线程
            self._start_listener()
            return True

        except Exception as e:
            logger.error(f"IPC connection failed: {e}")
            self._connected = False
            return False

    def connect_from_context(self, ipc_config: dict, tool_ident: str,
                             frontend_version: Optional[str] = None) -> bool:
        """从上下文文件的 ipc 配置连接 IPC 服务器

        Args:
            ipc_config: 上下文文件中的 ipc 字段，格式：
                {
                    "socket_host": IPC_HOST_IP,
                    "socket_port": 0,
                    "token_env": "TFP_IPC_TOKEN_TabulexBomComparator"
                }
            tool_ident: 工具标识，用于从环境变量获取 IPC Token
            frontend_version: 前端主程序版本（上下文 JSON 顶层 version 字段），
                转发给 connect() 随认证消息上报

        Returns:
            True 表示连接并认证成功
        """
        host = ipc_config.get("socket_host", IPC_HOST_IP)
        port = ipc_config.get("socket_port", 0)

        # IPC Token 从环境变量获取（不写入上下文文件）
        token = None
        token_env = ipc_config.get("token_env")
        if token_env:
            import os
            token = os.environ.get(token_env)
            if not token:
                logger.warning(f"IPC Token not found in environment variable {token_env}")
        else:
            # 直接从环境变量按 tool_ident 查找
            import os
            token = os.environ.get(f"TFP_IPC_TOKEN_{tool_ident}")

        return self.connect(host, port, token, frontend_version=frontend_version)

    def disconnect(self):
        """断开 IPC 连接"""
        self._stop_listener = True
        self._connected = False
        self._authenticated = False
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
        self._socket = None
        logger.info("IPC disconnected")

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected and self._socket is not None

    # ========== 事件通知 ==========

    def notify_ready(self) -> bool:
        """通知主程序：子工具已就绪"""
        return self._send_event("ready", {})

    def send_hidden(self) -> bool:
        """通知主程序：子工具窗口已隐藏"""
        return self._send_event("hidden", {})

    def send_closed(self) -> bool:
        """通知主程序：子工具已关闭"""
        result = self._send_event("closed", {})
        self.disconnect()
        return result

    def request_login(self, message: str = "", feature_key: str = "") -> bool:
        """请求主程序弹出登录对话框

        Args:
            message: 登录提示信息
            feature_key: 触发登录的功能键
        """
        return self._send_event("request_login", {
            "message": message,
            "feature_key": feature_key
        })

    def request_logout(self) -> bool:
        """请求主程序执行退出登录操作

        子工具不持有 session_token，无法自行登出。
        通过 IPC 通知主程序发起登出请求并完成登出，登出后主程序会
        同步 auth_update 给各子工具，使 Account 菜单刷新。
        """
        return self._send_event("request_logout", {})

    # ========== API 代理调用 ==========

    def api_request(self, method: str, path: str, body: Any = None,
                    extra_headers: Optional[Dict[str, str]] = None,
                    timeout: float = 30.0) -> Dict[str, Any]:
        """通过 IPC 代理调用后端 API

        子工具不再直接持有 session_token，所有后端 API 请求通过此方法中转。
        主程序自动附加 Authorization 头，转发请求到后端并返回响应。

        Args:
            method: HTTP 方法（GET/POST/PUT/DELETE）
            path: API 路径（以 API_V1_PREFIX 开头，如 API_V1_PREFIX + "/remote_program/my_tool/data"）
            body: 请求体（POST/PUT 时使用）
            extra_headers: 额外请求头（M-1 加固：主程序 IPC 代理会忽略该参数，
                            仅附加 Content-Type 与 Authorization，勿依赖其生效）
            timeout: 等待响应的超时时间（秒）

        Returns:
            响应字典，格式：
            {
                "status_code": 200,
                "body": { ... },
                "headers": { ... }
            }

        Raises:
            TFP_IPCAPIError: API 代理调用失败
            ConnectionError: IPC 未连接
            TimeoutError: 等待响应超时
        """
        if not self.is_connected:
            raise ConnectionError(_ipc_message(
                "ipc_error_not_connected", _IPC_MESSAGE_EN_FALLBACK["ipc_error_not_connected"]))

        request_id = str(uuid.uuid4())
        data = {
            "request_id": request_id,
            "method": method.upper(),
            "path": path,
            "body": body,
            "extra_headers": extra_headers or {}
        }

        # 注册待处理请求
        with self._pending_lock:
            self._pending_requests[request_id] = {
                "event": threading.Event(),
                "result": None
            }

        try:
            # 发送 api_request 事件
            sent = self._send_event("api_request", data)
            if not sent:
                raise ConnectionError(_ipc_message(
                    "ipc_error_send_failed", _IPC_MESSAGE_EN_FALLBACK["ipc_error_send_failed"]))

            # 等待响应
            pending = self._pending_requests[request_id]
            if not pending["event"].wait(timeout=timeout):
                raise TimeoutError(_ipc_message(
                    "ipc_error_request_timeout", _IPC_MESSAGE_EN_FALLBACK["ipc_error_request_timeout"],
                    timeout=timeout, method=method, path=path))

            result = pending["result"]
            if result is None:
                raise TFP_IPCAPIError(500, "Empty response from IPC proxy")

            return result

        finally:
            with self._pending_lock:
                self._pending_requests.pop(request_id, None)

    def api_get(self, path: str, timeout: float = 30.0) -> Dict[str, Any]:
        """通过 IPC 代理发送 GET 请求（便捷方法）"""
        return self.api_request("GET", path, timeout=timeout)

    def api_post(self, path: str, body: Any = None, timeout: float = 30.0) -> Dict[str, Any]:
        """通过 IPC 代理发送 POST 请求（便捷方法）"""
        return self.api_request("POST", path, body=body, timeout=timeout)

    def api_put(self, path: str, body: Any = None, timeout: float = 30.0) -> Dict[str, Any]:
        """通过 IPC 代理发送 PUT 请求（便捷方法）"""
        return self.api_request("PUT", path, body=body, timeout=timeout)

    def api_delete(self, path: str, timeout: float = 30.0) -> Dict[str, Any]:
        """通过 IPC 代理发送 DELETE 请求（便捷方法）"""
        return self.api_request("DELETE", path, timeout=timeout)

    def check_permission(self, tool_ident: str, feature_key: str,
                         timeout: float = 15.0) -> Dict[str, Any]:
        """通过 IPC 代理检查权限

        Args:
            tool_ident: 工具标识
            feature_key: 功能键

        Returns:
            权限检查结果，格式：
            {
                "status_code": 200,
                "body": {"allowed": True/False, "reason": "...", ...},
                "headers": {}
            }
        """
        if not self.is_connected:
            return {
                "status_code": 200,
                "body": {"allowed": False, "reason": "ipc_not_connected"},
                "headers": {}
            }

        request_id = str(uuid.uuid4())
        data = {
            "request_id": request_id,
            "tool_ident": tool_ident,
            "feature_key": feature_key
        }

        with self._pending_lock:
            self._pending_requests[request_id] = {
                "event": threading.Event(),
                "result": None
            }

        try:
            sent = self._send_event("check_permission", data)
            if not sent:
                return {
                    "status_code": 200,
                    "body": {"allowed": False, "reason": "ipc_send_failed"},
                    "headers": {}
                }

            pending = self._pending_requests[request_id]
            if not pending["event"].wait(timeout=timeout):
                return {
                    "status_code": 200,
                    "body": {"allowed": False, "reason": "ipc_timeout"},
                    "headers": {}
                }

            result = pending["result"]
            if result is None:
                return {
                    "status_code": 200,
                    "body": {"allowed": False, "reason": "ipc_empty_response"},
                    "headers": {}
                }

            return result

        finally:
            with self._pending_lock:
                self._pending_requests.pop(request_id, None)

    # ========== 命令处理器注册 ==========

    def on_command(self, command: str, handler: Callable):
        """注册命令处理器

        当主程序通过 IPC 发送命令时，调用对应的 handler。
        handler 会在 wx.CallAfter 中被调用（如果 wx 可用），否则在监听线程中调用。

        Args:
            command: 命令名称（如 "auth_update"、"show"、"close"）
            handler: 处理函数，签名为 handler(data: dict)
        """
        self._command_handlers[command] = handler

    # ========== 内部方法 ==========

    def _start_listener(self):
        """启动 IPC 消息监听线程"""
        self._stop_listener = False
        if self._socket:
            self._socket.settimeout(1.0)
        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()
        logger.info("IPC listener thread started")

    def _listen_loop(self):
        """IPC 消息监听循环"""
        buffer = ""
        while not self._stop_listener and self._connected:
            try:
                if not self._socket:
                    break
                data = self._socket.recv(4096)
                if not data:
                    logger.info("IPC connection closed (server shut down)")
                    self._connected = False
                    break
                buffer += data.decode('utf-8')
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        try:
                            message = json.loads(line)
                            self._handle_message(message)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse IPC message: {e}")
            except socket.timeout:
                continue
            except Exception as e:
                if not self._stop_listener:
                    logger.error(f"IPC listener error: {e}")
                break

        logger.info("IPC listener thread exited")

    def _handle_message(self, message: dict):
        """处理收到的 IPC 消息"""
        msg_type = message.get('type')
        event = message.get('event')
        command = message.get('command')
        data = message.get('data', {})

        # 处理心跳命令
        if msg_type == 'command' and command == 'heartbeat':
            self._send_response('heartbeat_ack', {})
            return

        # 处理 API 代理响应
        if msg_type == 'response' and event == 'api_response':
            request_id = data.get('request_id')
            if request_id:
                with self._pending_lock:
                    pending = self._pending_requests.get(request_id)
                    if pending:
                        pending["result"] = data
                        pending["event"].set()
            return

        # 处理命令
        if msg_type == 'command' and command:
            handler = self._command_handlers.get(command)
            if handler:
                try:
                    import wx
                    wx.CallAfter(handler, data)
                except ImportError:
                    # 无 wx 环境，直接在监听线程中调用
                    try:
                        handler(data)
                    except Exception as e:
                        logger.error(f"Failed to execute command handler {command}: {e}")
            elif command == 'command_unknown':
                # 主程序对我方先前发送的未知 event 的诊断回应（IPC 兼容性契约）。
                # 特判仅记日志、不再回发，避免"未知命令→回发→再触发未知命令"的往返循环。
                logger.warning("Main program does not recognize an event we sent (command_unknown echo)")
            else:
                # 兼容性契约（IPC 规则2/3）：未注册命令必须回发可识别的
                # command_unknown 响应（而非断连/静默），使主程序可诊断子工具不支持该命令。
                # 该响应仅用于诊断，主程序不得依赖其存在性实现业务流程。
                logger.warning(f"Unregistered command, replying command_unknown: {command}")
                self._send_response('command_unknown', {"command": command})

        # 处理其他响应（如 heartbeat_ack）
        if msg_type == 'response' and event == 'heartbeat_ack':
            # 心跳确认，无需处理
            return

    def _send_event(self, event_type: str, data: Any) -> bool:
        """发送 IPC 事件消息

        Args:
            event_type: 事件类型
            data: 事件数据

        Returns:
            True 表示发送成功
        """
        if not self._connected or not self._socket:
            logger.error(f"IPC not connected, cannot send event: {event_type}")
            return False

        try:
            message = json.dumps({
                "type": "event",
                "event": event_type,
                "data": data,
                "timestamp": __import__('datetime').datetime.now().isoformat()
            })
            self._socket.sendall((message + "\n").encode('utf-8'))
            return True
        except Exception as e:
            logger.error(f"Failed to send IPC event: {e}")
            self._connected = False
            return False

    def _send_response(self, event: str, data: Any) -> bool:
        """发送 IPC 响应消息

        Args:
            event: 响应事件名
            data: 响应数据

        Returns:
            True 表示发送成功
        """
        if not self._connected or not self._socket:
            return False

        try:
            message = json.dumps({
                "type": "response",
                "event": event,
                "data": data,
                "timestamp": __import__('datetime').datetime.now().isoformat()
            })
            self._socket.sendall((message + "\n").encode('utf-8'))
            return True
        except Exception as e:
            logger.error(f"Failed to send IPC response: {e}")
            return False
