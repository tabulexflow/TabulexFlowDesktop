# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import os
import sys
import socket
import threading
import datetime
import logging
import pathlib
import tempfile
import traceback
import secrets
import time
import wx
import requests as http_requests

from tfp_auth import auth_manager, TFP_LoginRegisterDialog
from tfp_utils.tfp_api_paths import API_V1_PREFIX
from tfp_utils.tfp_i18n_manager import translate, i18n
from tfp_utils.tfp_version import version_tuple
from build_mode import IPC_HOST_IP, FRONTEND_DOWNLOAD_PAGE_URL

logger = logging.getLogger(__name__)

IPC_HEARTBEAT_INTERVAL = 30
IPC_HEARTBEAT_TIMEOUT = 10

# T8.5.1（B2）：主程序 IPC 能力表（与 IPC 协议命令/事件列表及能力下限约定同步维护）。
# - commands/events：主程序当前支持下发/接收的命令与事件集（诊断用途；
#   未识别项按 IPC 兼容性契约回发 command_unknown）
# - auth_report_fields：握手认证消息中主程序可识别的子工具上报字段
# - min_sdk_version：能力下限——子工具上报的 sdk_version 低于该值时，在握手阶段
#   给出"工具需更新"诊断（日志 + 弹窗，仅诊断不阻断）。当前所有工具 SDK 均为
#   1.0.0（等于下限，不触发）；未来 IPC 出现旧 SDK 无法兼容的演进时提升该值。
IPC_CAPABILITIES = {
    'commands': ['show', 'hide', 'minimize', 'maximize', 'close', 'heartbeat',
                 'auth_update', 'command_unknown'],
    'events': ['ready', 'closed', 'hidden', 'error', 'menu_click', 'request_login',
               'request_logout', 'api_request', 'check_permission'],
    'auth_report_fields': ['sdk_version', 'frontend_version'],
    'min_sdk_version': '1.0.0',
}


class TFP_ToolIPCMixin:

    # T7.2：410 弃用契约升级提示，同启动周期仅弹一次（IPC 代理与工具下载
    # 共用本标记——两个 Mixin 挂在同一主窗口实例上）
    _api_deprecated_prompted = False

    # T8.5.1：已弹出过"工具需更新"诊断的 tool_ident 集合（每工具每次启动周期
    # 仅弹一次；子工具重连同一 token 时不重复弹）。去重在 UI 线程内完成
    _sdk_floor_warned_tools = set()

    def _start_ipc_server(self, tool_ident, port=0):
        """启动 IPC 服务器（port=0 时由操作系统动态分配空闲端口）。
        返回 (server_socket, ipc_token, actual_port)。"""
        import socket
        import threading
        
        ipc_token = secrets.token_urlsafe(32)
        ipc_token_expiry = time.time() + 3600
        if tool_ident in self.embedded_tools:
            self.embedded_tools[tool_ident]['ipc_token'] = ipc_token
            self.embedded_tools[tool_ident]['ipc_token_expiry'] = ipc_token_expiry
        
        def handle_client(client_socket, addr):
            logger.info(f"IPC client connected: {addr}")
            authenticated = False
            buffer = ""
            try:
                while True:
                    data = client_socket.recv(4096)
                    if not data:
                        break
                    buffer += data.decode('utf-8')
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if line.strip():
                            try:
                                import json
                                message = json.loads(line)
                                if not authenticated:
                                    token_expired = False
                                    if tool_ident in self.embedded_tools:
                                        expiry = self.embedded_tools[tool_ident].get('ipc_token_expiry', 0)
                                        if time.time() > expiry:
                                            token_expired = True
                                    if not token_expired and message.get('type') == 'auth' and message.get('token') == ipc_token:
                                        authenticated = True
                                        if tool_ident in self.embedded_tools:
                                            self.embedded_tools[tool_ident]['client_socket'] = client_socket
                                            self.embedded_tools[tool_ident]['last_heartbeat'] = time.time()
                                        logger.info(f"IPC client authenticated: {addr}")
                                        # 版本上报仅诊断用途（T3.3）：记录子工具 EXE
                                        # 内嵌 SDK 版本与其读到的前端版本；旧 EXE 不发送这些字段
                                        # 时静默跳过，不影响既有流程（追加字段不改语义）
                                        _sdk_ver = message.get('sdk_version')
                                        _fe_ver = message.get('frontend_version')
                                        if _sdk_ver or _fe_ver:
                                            logger.info(
                                                "IPC tool version report: tool=%s, sdk_version=%s, frontend_version=%s",
                                                tool_ident, _sdk_ver, _fe_ver)
                                        # T8.5.1（B2）能力下限握手诊断：子工具上报 sdk_version
                                        # 低于主程序能力下限时，在握手阶段明确诊断（日志 + 弹
                                        # "工具需更新"），而非运行期逐命令失败。仅诊断不阻断
                                        # （用户决策 2026-09-10）；旧子工具无该字段或值为 unknown
                                        # 时静默跳过（T3 兼容约定），非法值按 (0,0,0) fail-open
                                        _ipc_floor = IPC_CAPABILITIES.get('min_sdk_version')
                                        if _sdk_ver and _sdk_ver != 'unknown' and _ipc_floor \
                                                and version_tuple(_sdk_ver) < version_tuple(_ipc_floor):
                                            logger.warning(
                                                "IPC tool %s sdk_version=%s below capability floor %s; "
                                                "tool update recommended (diagnostic only, not blocking)",
                                                tool_ident, _sdk_ver, _ipc_floor)
                                            wx.CallAfter(self._prompt_tool_sdk_below_floor,
                                                         tool_ident, _sdk_ver, _ipc_floor)
                                        heartbeat_thread = threading.Thread(
                                            target=self._heartbeat_monitor,
                                            args=(tool_ident, client_socket),
                                            daemon=True
                                        )
                                        heartbeat_thread.start()
                                    else:
                                        if token_expired:
                                            logger.error(f"IPC client auth failed: token expired {addr}")
                                        else:
                                            logger.error(f"IPC client authentication failed: {addr}")
                                        client_socket.close()
                                        return
                                    continue
                                self._handle_ipc_message(tool_ident, message)
                            except json.JSONDecodeError:
                                logger.warning(f"Invalid IPC message: {line}")
            except Exception as e:
                logger.error(f"IPC client error: {e}")
            finally:
                if tool_ident in self.embedded_tools and self.embedded_tools[tool_ident].get('client_socket') is client_socket:
                    self.embedded_tools[tool_ident]['client_socket'] = None
                client_socket.close()
                logger.info(f"IPC client disconnected: {addr}")
        
        def server_thread(server_socket):
            server_socket.settimeout(1.0)
            while True:
                try:
                    client, addr = server_socket.accept()
                    thread = threading.Thread(target=handle_client, args=(client, addr), daemon=True)
                    thread.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"IPC server error: {e}")
                    break
        
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((IPC_HOST_IP, port))
            server_socket.listen(1)
            # 动态端口：bind(0) 后由操作系统分配实际空闲端口
            actual_port = server_socket.getsockname()[1] if port == 0 else port
            logger.info(f"IPC server started, listening on port: {actual_port}")
            
            thread = threading.Thread(target=server_thread, args=(server_socket,), daemon=True)
            thread.start()
            
            return (server_socket, ipc_token, actual_port)
        except Exception as e:
            logger.error(f"Failed to start IPC server: {e}")
            return (None, None, 0)

    def _handle_ipc_message(self, tool_ident, message):
        msg_type = message.get('type')
        event = message.get('event')
        data = message.get('data', {})
        
        if msg_type == 'response' and event == 'heartbeat_ack':
            if tool_ident in self.embedded_tools:
                self.embedded_tools[tool_ident]['last_heartbeat'] = time.time()
            return

        if msg_type == 'response' and event == 'command_unknown':
            # 子工具回报不认识的命令——仅诊断日志，不回发，防循环
            unknown_cmd = (data or {}).get('command', '?')
            logger.warning(f"Tool {tool_ident} does not support command: {unknown_cmd}")
            return

        logger.info(f"Received IPC message [{tool_ident}]: type={msg_type}, event={event}")
        
        if event == 'ready':
            logger.info(f"Tool {tool_ident} is ready")
            if tool_ident in self.embedded_tools and self.embedded_tools[tool_ident].get('mode') == 'exe':
                self.embedded_tools[tool_ident]['is_hidden'] = False
                wx.CallAfter(self._on_exe_tool_ready, tool_ident)
        elif event == 'hidden':
            logger.info(f"Tool {tool_ident} sent hide event")
            if tool_ident in self.embedded_tools:
                # _on_exe_tool_hidden 内部会执行 wx 控件操作（unlock_all_tools/更新菜单），
                # 必须在主线程执行，否则与主线程事件循环并发操作 wx 会导致崩溃
                wx.CallAfter(self._on_exe_tool_hidden, tool_ident)
        elif event == 'closed':
            logger.info(f"Tool {tool_ident} sent close event")
            if tool_ident in self.embedded_tools:
                # _on_exe_tool_closed 内部会执行 wx 控件操作（Show/Layout/关闭IPC服务器等），
                # 且主线程 close_embedded_tool 也会调用它，必须回到主线程串行执行，
                # 避免两个线程同时操作 wx 内部对象导致堆破坏（malloc corruption / SIGFPE）
                wx.CallAfter(self._on_exe_tool_closed, tool_ident)
        elif event == 'request_login':
            logger.info(f"Tool {tool_ident} requested login")
            wx.CallAfter(self._on_exe_tool_request_login, tool_ident, data)
        elif event == 'request_logout':
            logger.info(f"Tool {tool_ident} requested logout")
            wx.CallAfter(self._on_exe_tool_request_logout, tool_ident)
        elif event == 'api_request':
            logger.info(f"Tool {tool_ident} requested API proxy call")
            self._handle_ipc_api_request(tool_ident, data)
        elif event == 'check_permission':
            logger.info(f"Tool {tool_ident} requested permission check proxy")
            self._handle_ipc_check_permission(tool_ident, data)
        elif event == 'window_menu_action':
            action = data.get('action')
            logger.info(f"Tool {tool_ident} requested Window menu action: {action}")
            self._handle_window_menu_action(tool_ident, action, data)
        elif msg_type == 'event':
            # 兼容性契约（IPC 规则2/3）：未知事件必须回发可识别的 command_unknown
            # 命令（而非断连/静默），使子工具可诊断主程序不支持该事件。该回应仅用于诊断，
            # 子工具不得依赖其存在性实现业务流程。限定 msg_type=='event'，避免 menu_action
            # 等其他消息类型误触发回发。
            logger.warning(f"Unknown IPC event from tool {tool_ident}, replying command_unknown: {event}")
            self._send_ipc_to_tool(tool_ident, 'command_unknown', {'event': event})

    def _on_exe_tool_ready(self, tool_ident):
        if tool_ident not in self.embedded_tools:
            return
        tool_data = self.embedded_tools[tool_ident]
        tool_data['ready_received'] = True
        loading_panel = tool_data.get('loading_panel')
        if loading_panel:
            self._hide_loading_panel(loading_panel)
            tool_data['loading_panel'] = None
        self._current_active_tool = tool_ident
        self._update_window_menu_for_tool(tool_ident)
        self.unlock_all_tools()
        self._send_auth_update_to_tool(tool_ident)
        if self.IsShown():
            logger.info(f"[Standalone Process Mode] Tool {tool_ident} is ready, hiding main window")
            self.Hide()

    def _on_exe_tool_hidden(self, tool_ident):
        if tool_ident not in self.embedded_tools:
            return
        tool_data = self.embedded_tools[tool_ident]
        tool_data['is_hidden'] = True

        # 收费工具隐藏时释放企业席位
        if tool_data.get('requires_subscription', False):
            try:
                from tfp_auth import auth_manager
                auth_manager.release_seat(tool_ident)
            except Exception as e:
                logger.warning(f"Failed to release seat when hiding tool: {e}")

        main_was_visible = tool_data.get('main_was_visible', True)
        if main_was_visible and not self.IsShown():
            logger.info(f"[IPC] Restoring main window")
            wx.CallAfter(self.Show)
        if hasattr(self, '_current_active_tool') and self._current_active_tool == tool_ident:
            self._current_active_tool = None
            self._update_window_menu_for_tool(None)
        self.unlock_all_tools()

    def _on_exe_tool_request_login(self, tool_ident, data):
        feature_key = data.get('feature_key', '')
        message = data.get('message', '')
        logger.info(f"[IPC] Tool {tool_ident} requested login, feature_key={feature_key}, message={message}")
        
        self._show_login_dialog_for_tool(tool_ident)
    
    def _show_login_dialog_for_tool(self, tool_ident):
        """显示登录对话框（带防重复保护）

        同一时刻只允许弹出一个登录对话框：主程序 IPC 代理在会话刷新失败时会
        触发一次（_handle_ipc_api_request），同时子工具收到 401 后也会通过
        request_login 再请求一次，若不防重会连续弹出两个"User Login"窗口。
        若已有登录框正在显示/排队，则本次请求直接忽略。
        """
        if getattr(self, '_tool_login_dialog_active', False):
            logger.info(f"[IPC] Login dialog already visible, ignoring duplicate login request (tool={tool_ident})")
            return
        self._tool_login_dialog_active = True

        def on_login_ok():
            self._tool_login_dialog_active = False
            self._send_auth_update_to_tool(tool_ident)

        # 使用 self（主窗口）作为 parent，确保登录对话框继承正确的 DPI 缩放因子
        dlg = TFP_LoginRegisterDialog(self, on_login_ok)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()
            self._tool_login_dialog_active = False

    def _force_clear_tool_session(self, tool_ident):
        """后端校验会话失效（401刷新token失败）时，强制将主程序状态置为未登录，
        并同步各子工具认证状态，使主平台及已打开子工具的 Account 主菜单
        第一项自动从 "Logout (USERNAME)" 切回 "Login"。
        """
        try:
            if auth_manager.is_user_logged_in():
                auth_manager.force_logout_local()
            self._send_auth_update_to_tool(tool_ident)
        except Exception as e:
            logger.error(f"[IPC Proxy] Failed to force clear session: {e}")

    def _on_exe_tool_request_logout(self, tool_ident):
        """子工具请求退出登录：由主程序发起登出请求并完成登出。

        主程序执行登出后会触发 _notify_auth_change 刷新主平台 Account 菜单，
        并通过 _notify_all_exe_tools_auth_changed 向所有已打开子工具广播
        未登录状态，使其 Account 菜单从 "Logout (USERNAME)" 切换为 "Login"。
        """
        logger.info(f"[IPC] Tool {tool_ident} requested logout, performing logout")
        try:
            auth_manager.logout_user()
            self._notify_all_exe_tools_auth_changed()
        except Exception as e:
            logger.error(f"[IPC] Sub-tool logout request failed: {e}")
    
    # ========== IPC 代理服务：为 RemoteProgram 子工具中转后端 API 请求 ==========

    def _is_allowed_ipc_api_path(self, path):
        """M-1 加固：IPC API 代理路径白名单（宽松策略）。

        仅允许以 /api/ 开头的后端 API 路径；拒绝反斜杠、@、控制字符、
        双斜杠等可能导致协议/路径绕过的构造。调用方在 403 分支 fail-closed。
        """
        if not isinstance(path, str):
            return False
        if not path.startswith('/api/'):
            return False
        if '\\' in path or '@' in path or '\x00' in path or '//' in path:
            return False
        return True

    def _handle_ipc_api_request(self, tool_ident, data):
        """处理子工具通过IPC发送的API代理请求
        
        子工具不再直接持有session_token，所有后端API请求通过此方法中转。
        主程序自动附加Authorization头，转发请求到后端，将响应原样返回。
        
        data字段格式:
        {
            "request_id": "唯一请求ID，用于匹配响应",
            "method": "GET|POST|PUT|DELETE",
            "path": "/api/v1/remote_program/{tool_ident}/xxx",
            "body": {},
            "extra_headers": {}
        }
        """
        request_id = data.get('request_id', '')
        method = data.get('method', 'GET').upper()
        path = data.get('path', '').strip()
        body = data.get('body')
        
        # M-1 加固：path 白名单（宽松）——仅允许以 /api/ 开头的后端 API 路径，
        # 拒绝其余路径与可能造成协议/路径绕过的极端构造（子工具经此代理的
        # 实际调用面为 /api/v1/remote_program/{tool_ident}/... 及固定平台级端点）。
        if not path:
            self._send_ipc_api_response(tool_ident, request_id, {
                "status_code": 400,
                "body": {"success": False, "message": "Missing path in api_request"},
                "headers": {}
            })
            return
        if not self._is_allowed_ipc_api_path(path):
            logger.warning(f"[IPC Proxy] Rejected api_request path (not allowed): {path!r}")
            self._send_ipc_api_response(tool_ident, request_id, {
                "status_code": 403,
                "body": {"success": False, "message": "Path not allowed"},
                "headers": {}
            })
            return
        
        # 在后台线程中执行HTTP请求，避免阻塞IPC消息处理
        def _do_api_request():
            try:
                backend_url = getattr(self, 'backend_url', '')
                if not backend_url:
                    self._send_ipc_api_response(tool_ident, request_id, {
                        "status_code": 503,
                        "body": {"success": False, "message": "Backend URL not configured"},
                        "headers": {}
                    })
                    return
                
                url = f"{backend_url}{path}"
                
                # 构造请求头：仅由主程序附加 Content-Type 与当前用户的 Authorization。
                # M-1 加固：忽略子工具传入的 extra_headers，防止以用户身份注入任意自定义请求头。
                headers = {'Content-Type': 'application/json'}
                
                auth_headers = auth_manager.get_auth_headers()
                if auth_headers:
                    headers.update(auth_headers)
                else:
                    # 未登录，返回401让子工具处理
                    self._send_ipc_api_response(tool_ident, request_id, {
                        "status_code": 401,
                        "body": {"success": False, "message": "Not logged in"},
                        "headers": {}
                    })
                    return
                
                logger.info(f"[IPC Proxy] Forwarding API request: {method} {url}")
                
                # 执行HTTP请求
                response = None
                if method == 'GET':
                    response = http_requests.get(url, headers=headers, timeout=30)
                elif method == 'POST':
                    response = http_requests.post(url, headers=headers, json=body, timeout=30)
                elif method == 'PUT':
                    response = http_requests.put(url, headers=headers, json=body, timeout=30)
                elif method == 'DELETE':
                    response = http_requests.delete(url, headers=headers, timeout=30)
                else:
                    self._send_ipc_api_response(tool_ident, request_id, {
                        "status_code": 400,
                        "body": {"success": False, "message": f"Unsupported method: {method}"},
                        "headers": {}
                    })
                    return
                
                # 若后端返回401，尝试刷新token后重试一次
                if response.status_code == 401:
                    logger.info(f"[IPC Proxy] Backend returned 401, retrying after refreshing token")
                    try:
                        refresh_result = auth_manager.refresh_session()
                        if refresh_result.get('success'):
                            # 刷新成功，用新token重试
                            new_auth_headers = auth_manager.get_auth_headers()
                            headers.update(new_auth_headers)
                            if method == 'GET':
                                response = http_requests.get(url, headers=headers, timeout=30)
                            elif method == 'POST':
                                response = http_requests.post(url, headers=headers, json=body, timeout=30)
                            elif method == 'PUT':
                                response = http_requests.put(url, headers=headers, json=body, timeout=30)
                            elif method == 'DELETE':
                                response = http_requests.delete(url, headers=headers, timeout=30)
                        else:
                            # 刷新失败，触发登录流程
                            logger.warning(f"[IPC Proxy] Token refresh failed, triggering login flow")
                            self._force_clear_tool_session(tool_ident)
                            wx.CallAfter(self._show_login_dialog_for_tool, tool_ident)
                    except Exception as refresh_err:
                        logger.error(f"[IPC Proxy] Token refresh error: {refresh_err}")
                        self._force_clear_tool_session(tool_ident)
                        wx.CallAfter(self._show_login_dialog_for_tool, tool_ident)
                
                # 解析响应
                resp_body = None
                try:
                    resp_body = response.json()
                except Exception:
                    resp_body = response.text
                
                # 提取安全响应头（仅转发必要的头信息，不暴露敏感头）
                resp_headers = {}
                for key in ('Content-Type', 'X-Total-Count'):
                    val = response.headers.get(key)
                    if val:
                        resp_headers[key] = val

                # T7.2 弃用契约识别：410 + API_DEPRECATED → 弹统一升级提示
                # （同启动周期仅一次，wx.CallAfter 回 UI 线程）。410 响应原样透传
                # 给子工具：旧子工具按非 200 通用错误处理（与 404/500 同路径，
                # 无需适配），新子工具可读 body 中 code=API_DEPRECATED 精确识别。
                if response.status_code == 410 and isinstance(resp_body, dict) \
                        and resp_body.get('code') == 'API_DEPRECATED':
                    wx.CallAfter(self._prompt_api_deprecated, resp_body)

                self._send_ipc_api_response(tool_ident, request_id, {
                    "status_code": response.status_code,
                    "body": resp_body,
                    "headers": resp_headers
                })
                
            except http_requests.Timeout:
                logger.error(f"[IPC Proxy] API request timed out: {method} {path}")
                self._send_ipc_api_response(tool_ident, request_id, {
                    "status_code": 504,
                    "body": {"success": False, "message": "Backend request timeout"},
                    "headers": {}
                })
            except http_requests.ConnectionError:
                logger.error(f"[IPC Proxy] Cannot connect to backend: {method} {path}")
                self._send_ipc_api_response(tool_ident, request_id, {
                    "status_code": 502,
                    "body": {"success": False, "message": "Backend connection error"},
                    "headers": {}
                })
            except Exception as e:
                logger.error(f"[IPC Proxy] API request error: {e}")
                self._send_ipc_api_response(tool_ident, request_id, {
                    "status_code": 500,
                    "body": {"success": False, "message": f"Proxy error: {str(e)}"},
                    "headers": {}
                })
        
        thread = threading.Thread(target=_do_api_request, daemon=True)
        thread.start()

    def _resolve_api_deprecated_text(self, payload, fallback_text):
        """410 弹窗正文解析：优先后端 message（按界面语言取，en 兜底，再取任意可用项），
        缺省回退前端 i18n 文案（T7.2 约定）。"""
        message = payload.get('message') if isinstance(payload, dict) else None
        if isinstance(message, dict):
            candidates = [i18n.get_language_code(), 'en']
            for lang in candidates:
                text = str(message.get(lang) or '').strip()
                if text:
                    return text
            for value in message.values():
                text = str(value or '').strip()
                if text:
                    return text
        return fallback_text

    def _prompt_api_deprecated(self, payload, fallback_text=None):
        """410 弃用契约统一升级提示（UI 线程，经 wx.CallAfter 调入；T7.2）。

        同启动周期仅弹一次（IPC 代理/工具下载/会话三处共用本标记与文案逻辑，
        会话侧经 TFP_AuthManager 找到主窗口后调用本方法）；OK 后打开前端下载页。
        正文优先取后端 message（按界面语言），缺省回退 fallback_text（前端 i18n）。

        Args:
            payload: 后端 410 响应 body（{code, message?, min_frontend_version?}）
            fallback_text: 后端未提供 message 时的弹窗正文（i18n 文案，含工具上下文等）
        """
        if self._api_deprecated_prompted:
            logger.info("API deprecated upgrade prompt suppressed (already shown this run)")
            return
        self._api_deprecated_prompted = True
        min_required = str((payload or {}).get('min_frontend_version') or '').strip()
        text = self._resolve_api_deprecated_text(
            payload, fallback_text or translate("api_deprecated_upgrade_text"))
        if min_required:
            text += "\n\n" + translate("api_deprecated_upgrade_min_suffix").format(min_required=min_required)
        dialog = wx.MessageDialog(
            self, text,
            translate("api_deprecated_upgrade_title"),
            wx.OK | wx.ICON_WARNING
        )
        dialog.ShowModal()
        dialog.Destroy()
        logger.info("Opening frontend download page (API deprecated): %s", FRONTEND_DOWNLOAD_PAGE_URL)
        wx.LaunchDefaultBrowser(FRONTEND_DOWNLOAD_PAGE_URL)

    def _prompt_tool_sdk_below_floor(self, tool_ident, sdk_version, min_sdk_version):
        """握手能力下限诊断弹窗（UI 线程，经 wx.CallAfter 调入；T8.5.1）。

        子工具内嵌 SDK 低于主程序能力下限时告知用户"该工具需更新"——仅诊断，
        不阻断工具运行（协议向后兼容由 IPC 兼容性契约保障）。
        每工具每次启动周期仅弹一次（重连不重复弹），去重在本方法（UI 线程）内完成。
        注意与 410 弃用提示（_prompt_api_deprecated，引导升级客户端）方向相反：
        本弹窗不跳转下载页，工具更新由既有 try_update_tool 流程承担。

        Args:
            tool_ident: 子工具标识
            sdk_version: 子工具上报的内嵌 SDK 版本
            min_sdk_version: 主程序 IPC 能力下限（IPC_CAPABILITIES['min_sdk_version']）
        """
        if tool_ident in self._sdk_floor_warned_tools:
            logger.info(f"Tool {tool_ident} SDK floor warning suppressed (already shown this run)")
            return
        self._sdk_floor_warned_tools.add(tool_ident)
        wx.MessageBox(
            translate("ipc_tool_sdk_too_old_text").format(
                tool_ident=tool_ident, sdk_version=sdk_version,
                min_sdk_version=min_sdk_version),
            translate("ipc_tool_sdk_too_old_title"),
            wx.OK | wx.ICON_WARNING
        )

    def _handle_ipc_check_permission(self, tool_ident, data):
        """处理子工具通过IPC发送的权限检查请求
        
        data字段格式:
        {
            "request_id": "唯一请求ID",
            "tool_ident": "xxx",
            "feature_key": "xxx"
        }
        """
        request_id = data.get('request_id', '')
        target_tool = data.get('tool_ident', tool_ident)
        feature_key = data.get('feature_key', '')
        
        def _do_check_permission():
            try:
                backend_url = getattr(self, 'backend_url', '')
                if not backend_url:
                    self._send_ipc_api_response(tool_ident, request_id, {
                        "status_code": 503,
                        "body": {"allowed": False, "reason": "Backend URL not configured"},
                        "headers": {}
                    })
                    return
                
                auth_headers = auth_manager.get_auth_headers()
                if not auth_headers:
                    self._send_ipc_api_response(tool_ident, request_id, {
                        "status_code": 200,
                        "body": {"allowed": False, "reason": "not_logged_in"},
                        "headers": {}
                    })
                    return
                
                url = f"{backend_url}{API_V1_PREFIX}/permissions/feature/{target_tool}/{feature_key}"
                logger.info(f"[IPC Proxy] Forwarding permission check: {url}")
                
                response = http_requests.get(url, headers=auth_headers, timeout=15)
                
                resp_body = None
                try:
                    resp_body = response.json()
                except Exception:
                    resp_body = {"allowed": False, "reason": "invalid_response"}
                
                self._send_ipc_api_response(tool_ident, request_id, {
                    "status_code": response.status_code,
                    "body": resp_body,
                    "headers": {}
                })
                
            except Exception as e:
                logger.error(f"[IPC Proxy] Permission check error: {e}")
                # Fail-Closed原则：异常时默认拒绝
                self._send_ipc_api_response(tool_ident, request_id, {
                    "status_code": 200,
                    "body": {"allowed": False, "reason": "proxy_error"},
                    "headers": {}
                })
        
        thread = threading.Thread(target=_do_check_permission, daemon=True)
        thread.start()
    
    def _send_ipc_api_response(self, tool_ident, request_id, response_data):
        """向子工具发送API代理响应
        
        通过IPC将后端API的响应返回给子工具。
        响应格式:
        {
            "type": "response",
            "event": "api_response",
            "data": {
                "request_id": "xxx",
                "status_code": 200,
                "body": { ... },
                "headers": { ... }
            }
        }
        """
        if tool_ident not in self.embedded_tools:
            logger.warning(f"[IPC Proxy] Tool {tool_ident} is not in embedded_tools, cannot send API response")
            return
        
        client_socket = self.embedded_tools[tool_ident].get('client_socket')
        if not client_socket:
            logger.warning(f"[IPC Proxy] Tool {tool_ident} has no available client socket, cannot send API response")
            return
        
        try:
            response_data['request_id'] = request_id
            message = json.dumps({
                "type": "response",
                "event": "api_response",
                "data": response_data,
                "timestamp": datetime.datetime.now().isoformat()
            })
            client_socket.sendall((message + "\n").encode('utf-8'))
            logger.info(f"[IPC Proxy] API response sent to {tool_ident}, request_id={request_id}, status={response_data.get('status_code')}")
        except Exception as e:
            logger.error(f"[IPC Proxy] Failed to send API response: {e}")
    
    # ========== 原有IPC方法 ==========
    
    def _send_auth_update_to_tool(self, tool_ident):
        if tool_ident not in self.embedded_tools:
            return
        tool_data = self.embedded_tools[tool_ident]
        if tool_data.get('mode') != 'exe':
            return
        
        auth_data = {}
        if auth_manager.is_user_logged_in():
            user = auth_manager.get_current_user()
            auth_data = {
                "user_id": user.id if user else 0,
                "username": user.username if user else "",
                "user_type": auth_manager.get_user_type(),
                "is_logged_in": True,
                "can_request_api": True
            }
            token_expiry = getattr(auth_manager, '_token_expiry', None)
            if token_expiry:
                auth_data["expires_at"] = token_expiry.isoformat()
        else:
            auth_data = {
                "user_id": 0,
                "username": "",
                "user_type": "free",
                "is_logged_in": False,
                "can_request_api": False
            }
        
        self._send_ipc_to_tool(tool_ident, "auth_update", auth_data)
    
    def _notify_all_exe_tools_auth_changed(self):
        for tool_ident, tool_data in list(self.embedded_tools.items()):
            if tool_data.get('mode') == 'exe' and not tool_data.get('is_hidden', False):
                self._send_auth_update_to_tool(tool_ident)

    def _handle_window_menu_action(self, tool_ident, action, data):
        logger.info(f"[IPC] Processing window menu action: {action}")
        
        if action == 'show_home':
            wx.CallAfter(self.show_home_panel)
            
        elif action == 'switch_to_tool':
            target_tool = data.get('tool_ident')
            if target_tool:
                wx.CallAfter(lambda: self.on_window_menu_click(target_tool))
            
        elif action == 'get_window_menu_items':
            menu_items = []
            
            menu_items.append({
                'id': 'home',
                'label': translate('menu_home'),
                'type': 'item'
            })
            
            menu_items.append({
                'type': 'separator'
            })
            
            for tid, tool_data in self.embedded_tools.items():
                if tool_data.get('mode') == 'exe' and tid != tool_ident:
                    tool_name = self.get_tool_name_by_ident(tid)
                    menu_items.append({
                        'id': tid,
                        'label': tool_name,
                        'type': 'item'
                    })
            
            if tool_ident in self.embedded_tools:
                client_socket = self.embedded_tools[tool_ident].get('client_socket')
                if client_socket:
                    response = {
                        'type': 'response',
                        'event': 'window_menu_items',
                        'data': {
                            'items': menu_items
                        }
                    }
                    self._send_ipc_response(client_socket, response)
        
        else:
            logger.info(f"[IPC] Unknown window menu action: {action}")
    
    def _send_ipc_response(self, ipc_server, response):
        try:
            if ipc_server and hasattr(ipc_server, 'sendall'):
                message = json.dumps(response) + "\n"
                ipc_server.sendall(message.encode('utf-8'))
                logger.info(f"[IPC] Response sent: {response}")
            else:
                logger.warning(f"[IPC] Invalid server connection, cannot send response")
        except Exception as e:
            logger.error(f"[IPC] Failed to send response: {e}")
    
    def _send_ipc_to_tool(self, tool_ident, command, data=None):
        if tool_ident not in self.embedded_tools:
            logger.info(f"[IPC] Tool {tool_ident} is not in embedded_tools, cannot send command")
            return False
        
        client_socket = self.embedded_tools[tool_ident].get('client_socket')
        if not client_socket:
            logger.info(f"[IPC] Tool {tool_ident} has no available client socket, cannot send command")
            return False
        
        try:
            message = json.dumps({
                "type": "command",
                "command": command,
                "data": data or {},
                "timestamp": datetime.datetime.now().isoformat()
            })
            client_socket.sendall((message + "\n").encode('utf-8'))
            logger.info(f"[IPC] Command sent to tool {tool_ident}: {command}")
            return True
        except Exception as e:
            logger.error(f"[IPC] Failed to send command to tool {tool_ident}: {e}")
            return False
    
    def _heartbeat_monitor(self, tool_ident, client_socket):
        while True:
            time.sleep(IPC_HEARTBEAT_INTERVAL)
            
            if tool_ident not in self.embedded_tools:
                break
            
            tool_data = self.embedded_tools[tool_ident]
            if tool_data.get('client_socket') is not client_socket:
                break
            
            process = tool_data.get('process')
            if process and process.poll() is not None:
                logger.info(f"[IPC Heartbeat] Tool {tool_ident} process exited")
                wx.CallAfter(self._on_exe_tool_closed, tool_ident)
                break
            
            try:
                heartbeat_msg = json.dumps({
                    "type": "command",
                    "command": "heartbeat",
                    "data": {},
                    "timestamp": datetime.datetime.now().isoformat()
                })
                client_socket.sendall((heartbeat_msg + "\n").encode('utf-8'))
            except Exception as e:
                logger.error(f"[IPC Heartbeat] Failed to send heartbeat to tool {tool_ident}: {e}")
                if tool_ident in self.embedded_tools:
                    wx.CallAfter(self._on_exe_tool_closed, tool_ident)
                break
            
            last_hb = tool_data.get('last_heartbeat', time.time())
            if time.time() - last_hb > IPC_HEARTBEAT_INTERVAL + IPC_HEARTBEAT_TIMEOUT:
                logger.warning(f"[IPC Heartbeat] Tool {tool_ident} heartbeat timed out")
                if tool_ident in self.embedded_tools:
                    wx.CallAfter(self._on_exe_tool_closed, tool_ident)
                break
    
    def _resend_ipc_show_command(self, tool_ident):
        if tool_ident not in self.embedded_tools:
            return
        
        sent = self._send_ipc_to_tool(tool_ident, "show")
        if sent:
            self.embedded_tools[tool_ident]['is_hidden'] = False
            self._current_active_tool = tool_ident
            self._update_window_menu_for_tool(tool_ident)

            # 收费工具重新显示时重新占用席位
            tool_data = self.embedded_tools[tool_ident]
            if tool_data.get('requires_subscription', False):
                try:
                    from tfp_auth import auth_manager
                    auth_manager.occupy_seat(tool_ident)
                except Exception as e:
                    logger.warning(f"Failed to occupy seat when re-showing tool: {e}")

            if self.IsShown():
                logger.info(f"[Standalone Process Mode] Re-showing tool {tool_ident}, hiding main window")
                self.Hide()
        else:
            logger.error(f"[Standalone Process Mode] Failed to send show command, attempting to restart tool")
            self._on_exe_tool_closed(tool_ident)

    def get_tool_name_by_ident(self, tool_ident):
        return tool_ident

    def _prepare_tool_context(self, tool_info, tool_dir, backend_url=None, ipc_token=None, socket_port=0):
        import uuid
        from datetime import datetime
        
        tool_ident = tool_info['tool_ident']
        
        # 纵深防御：tool_ident 格式校验（入口已校验，此处断言确保不被绕过）
        from tfp_toolkit.tfp_constants import validate_tool_ident_format
        if not validate_tool_ident_format(tool_ident):
            raise ValueError(f"Invalid tool_ident format: {repr(tool_ident)}")
        
        try:
            auth_data = {}
            if auth_manager.is_user_logged_in():
                user = auth_manager.get_current_user()
                auth_data = {
                    "user_id": user.id if user else 0,
                    "username": user.username if user else "",
                    "user_type": auth_manager.get_user_type(),
                    "is_logged_in": True,
                    "can_request_api": True
                }
                token_expiry = getattr(auth_manager, '_token_expiry', None)
                if token_expiry:
                    auth_data["expires_at"] = token_expiry.isoformat()
            else:
                auth_data = {
                    "user_id": 0,
                    "username": "",
                    "user_type": "free",
                    "is_logged_in": False,
                    "can_request_api": False
                }
            
            settings_data = {
                "language": i18n.get_language_code(),
                "backend_url": backend_url or self.backend_url,
                "user_setting_base_dir": str(self.user_setting_dir) if hasattr(self, 'user_setting_dir') else "",
                "dpi_scale_factor": getattr(self, 'TFP_DPI_SCALE_FACTOR', 1.0)
            }
            logger.info(f"[DPI_DIAG] _prepare_tool_context: dpi_scale_factor={settings_data['dpi_scale_factor']}, self.TFP_DPI_SCALE_FACTOR={getattr(self, 'TFP_DPI_SCALE_FACTOR', 'NOT_FOUND')}")
            
            # socket_port 由调用方传入（EXE 流程为 _start_ipc_server 返回的实际动态端口）
            
            ipc_config = {
                "socket_host": IPC_HOST_IP,
                "socket_port": socket_port
            }
            # ipc_token 不写入上下文文件，通过环境变量传递给子进程
            ipc_token_env_var = None
            if ipc_token:
                ipc_token_env_var = f"TFP_IPC_TOKEN_{tool_ident}"
                ipc_config["token_env"] = ipc_token_env_var
            
            context = {
                "version": "1.0.0",
                "timestamp": datetime.now().isoformat(),
                "tool_ident": tool_ident,
                "auth": auth_data,
                "settings": settings_data,
                "ipc": ipc_config
            }
            
            temp_dir = pathlib.Path(tempfile.gettempdir())
            context_file = temp_dir / f"tool_context_{tool_ident}_{secrets.token_hex(8)}.json"
            
            with open(context_file, 'w', encoding='utf-8') as f:
                json.dump(context, f, ensure_ascii=False, indent=2)
            
            try:
                if sys.platform == 'win32':
                    import subprocess
                    username = os.environ.get('USERNAME', '')
                    if username:
                        subprocess.run(
                            ['icacls', str(context_file), '/inheritance:r', '/grant', f'{username}:R'],
                            capture_output=True, timeout=5
                        )
                else:
                    os.chmod(context_file, 0o600)
            except Exception:
                logger.warning("Failed to set context file permissions, file permissions may be too broad")
            
            logger.info(f"Context file created: {context_file}")
            return context_file, ipc_token_env_var, ipc_token
            
        except Exception as e:
            logger.error(f"Failed to create context file: {e}")
            traceback.print_exc()
            return None, None, None

    def _cleanup_stale_context_files(self):
        temp_dir = pathlib.Path(tempfile.gettempdir())
        for context_file in temp_dir.glob("tool_context_*.json"):
            try:
                st = context_file.stat()
                # L-6 加固（2026-09-01）：仅清理本机当前用户属主的文件，
                # 原实现 glob 全量匹配会误删其他用户/其他实例的临时文件（低危 DoS）。
                # Windows 无 os.getuid（temp 目录通常按用户隔离 + icacls 已限当前用户读），跳过 uid 判断
                if sys.platform != 'win32' and hasattr(os, 'getuid') and st.st_uid != os.getuid():
                    continue
                if time.time() - st.st_mtime > 3600:
                    context_file.unlink()
                    logger.info(f"[IPC] Cleaning up stale context files: {context_file}")
            except Exception as e:
                logger.error(f"[IPC] Failed to clean up context files: {e}")

    def _on_exe_tool_closed(self, tool_ident):
        logger.info(f"\n[IPC] Processing tool {tool_ident} close event")
        
        if tool_ident not in self.embedded_tools:
            logger.info(f"[IPC] Tool {tool_ident} is not in embedded_tools, may have been cleaned up")
            return
        
        tool_data = self.embedded_tools[tool_ident]
        # 防重入：主线程 close_embedded_tool 与 IPC 'closed' 事件都可能触发关闭处理，
        # 均已通过 wx.CallAfter 归一到主线程，这里再加标志位兜底，防止任何残留的重复调用
        # 导致对同一 wx 控件/进程/IPC 服务器的并发清理
        if tool_data.get('_closing'):
            logger.info(f"[IPC] Tool {tool_ident} is closing, skipping duplicate processing")
            return
        tool_data['_closing'] = True

        # 收费工具释放企业席位
        if tool_data.get('requires_subscription', False):
            try:
                from tfp_auth import auth_manager
                auth_manager.release_seat(tool_ident)
            except Exception as e:
                logger.warning(f"Failed to release seat: {e}")

        loading_panel = tool_data.get('loading_panel')
        if loading_panel:
            self._hide_loading_panel(loading_panel)
            tool_data['loading_panel'] = None
        
        main_was_visible = tool_data.get('main_was_visible', True)
        if main_was_visible and not self.IsShown():
            logger.info(f"[IPC] Restoring main window")
            wx.CallAfter(self.Show)
        
        process = tool_data.get('process')
        if process:
            try:
                import time
                start_time = time.time()
                while process.poll() is None and (time.time() - start_time) < 3.0:
                    time.sleep(0.1)
                
                if process.poll() is None:
                    logger.warning(f"[IPC] Process still running, force terminating PID: {process.pid}")
                    process.terminate()
                    time.sleep(0.5)
                    if process.poll() is None:
                        process.kill()
                
                logger.info(f"[IPC] Process terminated, return code: {process.poll()}")
            except Exception as e:
                logger.error(f"[IPC] Failed to clean up process: {e}")
        
        ipc_server = tool_data.get('ipc_server')
        if ipc_server:
            try:
                ipc_server.close()
                logger.info(f"IPC server closed")
            except Exception as e:
                logger.error(f"Failed to close IPC server: {e}")
        
        context_file = tool_data.get('context_file')
        if context_file and pathlib.Path(context_file).exists():
            try:
                pathlib.Path(context_file).unlink()
                logger.info(f"Context file cleaned up: {context_file}")
            except Exception as e:
                logger.error(f"Failed to clean up context file: {e}")
        
        if tool_ident in self.embedded_tools:
            del self.embedded_tools[tool_ident]
        
        if hasattr(self, 'home_panel'):
            self.home_panel.Show()
            if hasattr(self, 'content_sizer'):
                self.content_sizer.Show(self.home_panel)
                self.content_sizer.Layout()
        
        logger.info(f"[IPC] Tool {tool_ident} close handling complete, main window restored\n")

    def _check_exe_tool_status(self, tool_ident):
        if tool_ident not in self.embedded_tools:
            return
        
        tool_data = self.embedded_tools[tool_ident]
        
        if tool_data.get('mode') != 'exe':
            return
        
        process = tool_data.get('process')
        if not process:
            return
        
        return_code = process.poll()
        
        if return_code is not None:
            logger.info(f"Tool {tool_ident} process exited, return code: {return_code}")
            
            main_was_visible = tool_data.get('main_was_visible', True)
            if main_was_visible and not self.IsShown():
                wx.CallAfter(self.Show)
            
            ipc_server = tool_data.get('ipc_server')
            if ipc_server:
                try:
                    ipc_server.close()
                    logger.info(f"IPC server closed")
                except Exception as e:
                    logger.error(f"Failed to close IPC server: {e}")
            
            context_file = tool_data.get('context_file')
            if context_file and pathlib.Path(context_file).exists():
                try:
                    pathlib.Path(context_file).unlink()
                    logger.info(f"Context file cleaned up: {context_file}")
                except Exception as e:
                    logger.error(f"Failed to clean up context file: {e}")
            
            if tool_ident in self.embedded_tools:
                del self.embedded_tools[tool_ident]
            
            if hasattr(self, '_allocated_ports') and tool_ident in self._allocated_ports:
                del self._allocated_ports[tool_ident]
