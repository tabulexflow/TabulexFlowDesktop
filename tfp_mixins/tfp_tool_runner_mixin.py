# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import sys
import json
import logging
import pathlib
import time
import shutil
import zipfile
import tempfile
import traceback
import hashlib
import threading
import requests
import importlib
from urllib.parse import urlparse
import wx
try:
    import wx.html2
except ImportError:
    wx.html2 = None

logger = logging.getLogger(__name__)

from tfp_utils.tfp_api_paths import API_V1_PREFIX
from tfp_utils.tfp_main_utils import get_resource_path
from tfp_utils.tfp_i18n_manager import translate, i18n
from tfp_utils.tfp_version import version_tuple
# 本地内嵌 SDK 版本（与 tfp_toolkit 权威源保持一致，测试守护）。
# 用于 T8.4.1 工具清单 min_sdk_version 下载门槛比对
from tfp_utils import __version__ as _LOCAL_SDK_VERSION
from tfp_utils.tfp_webview_fallback import show_webview_dialog_fallback, mask_url_query_token, is_url_trusted
from tfp_utils.tfp_webview_helper import build_post_form_html
from tfp_utils.tfp_platform import get_platform_tag
from tfp_utils.tfp_tool_signer import (
    is_public_key_configured,
    verify_leaf_credential,
    verify_tool_signature,
)
from tfp_auth import auth_manager
from build_mode import is_dev_mode


# L-5 加固（2026-09-01）：单个子工具包 ZIP 下载大小上限（500MB）。
# 超限立即中止并删除临时文件（finally 清理），防止恶意/异常响应写满磁盘（DA3 资源耗尽）
_MAX_TOOL_ZIP_BYTES = 500 * 1024 * 1024

# T8.6.1（A4 调整版）：前端安装包后台静默下载缓存目录名
# （<runtime_base>/update_cache，与 tools_fe/user_setting 平级，runtime_base 为可写目录）
_INSTALLER_CACHE_DIRNAME = 'update_cache'


def _sha256_of_file(path):
    """流式计算文件 SHA-256（十六进制小写），供安装包完整性比对。"""
    sha = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha.update(chunk)
    return sha.hexdigest()


def _occupy_seat_safe(auth_mgr, tool_ident: str):
    """安全占用收费工具席位，失败不阻塞工具启动"""
    try:
        result = auth_mgr.occupy_seat(tool_ident)
        if not result.get('success') and result.get('concurrent_limit_reached'):
            wx.CallAfter(
                wx.MessageBox,
                result.get('message', '企业收费工具在线人数已达上限'),
                "席位限制",
                wx.OK | wx.ICON_WARNING
            )
    except Exception as e:
        logger.warning(f"Seat occupation request failed: {e}")


def _release_seat_safe(auth_mgr, tool_ident: str):
    """安全释放收费工具席位"""
    try:
        auth_mgr.release_seat(tool_ident)
    except Exception as e:
        logger.warning(f"Seat release request failed: {e}")


class TFP_ToolRunnerMixin:

    def _spx_calc(self, value):
        """Scale pixels by TFP_DPI_SCALE_FACTOR. 对固定像素值进行DPI缩放。"""
        if value == -1:
            return -1
        scale_factor = getattr(self, 'TFP_DPI_SCALE_FACTOR', 1.0)
        return int(value * scale_factor)

    def _check_tool_login(self, tool_info) -> bool:
        """检查收费工具（RemoteProgram/RemoteWebpage）打开时的登录要求

        登录门控规则：
        - 已登录：放行（下载/更新与收费功能仍由后端校验订阅权限，Fail-Closed）
        - 未登录且后端可达：必须登录才能打开（提示并弹出登录框）
        - 未登录且后端不可达：无法登录，不强制要求登录，按工具形态分流——
          RemoteProgram 已下载到本地则放行（离线试用工具内免费功能，收费功能
          仍需后端不可用）；未下载或 RemoteWebpage（页面由后端提供）则提示
          需要连接服务器

        Returns:
            True 表示允许使用，False 表示阻止使用
        """
        if auth_manager.is_user_logged_in():
            return True

        tool_name = self.get_localized_tool_title(tool_info)
        is_free = tool_info.get('tool_is_free', False)

        # 后端不可达：登录必然失败，不强制要求登录，按"能否离线使用"分流
        if not self._is_backend_reachable():
            tool_ident = tool_info.get('tool_ident', '')
            if tool_info.get('tool_type') == 'RemoteProgram':
                local_dir = self.local_tools_dir / "tools_remote_program" / tool_ident
                exe_file = self._find_main_exe(local_dir, tool_ident)
                if exe_file is not None and exe_file.exists():
                    logger.info(f"Backend unreachable, locally downloaded paid tool allowed for offline use: {tool_ident}")
                    return True
            # 未下载或 RemoteWebpage：离线无法获取/运行，提示需要连接服务器（不弹登录框）
            logger.info(f"Backend unreachable and tool not locally available; connection required: {tool_ident}")
            self._prompt_offline_connection(tool_name)
            return False

        if is_free:
            message = translate("message_login_required_free", tool_name=tool_name)
        else:
            message = translate("message_login_required_paid", tool_name=tool_name)

        dlg = wx.MessageDialog(
            self,
            message,
            translate("dialog_title_login_required"),
            wx.OK | wx.ICON_INFORMATION
        )
        dlg.ShowModal()
        dlg.Destroy()

        # 弹出登录对话框
        auth_manager.request_login_via_ipc(message=translate("message_login_prompt", tool_name=tool_name))
        return False

    def _prompt_offline_connection(self, tool_name):
        """后端不可达且工具无法离线使用时，提示需要连接服务器（不弹登录框）"""
        dlg = wx.MessageDialog(
            self,
            translate("message_need_server_connection", tool_name=tool_name),
            translate("dialog_title_network_error"),
            wx.OK | wx.ICON_INFORMATION
        )
        dlg.ShowModal()
        dlg.Destroy()

    def _is_backend_reachable(self) -> bool:
        """后端是否可达（复用启动健康检查结果，用于登录门控）"""
        try:
            from tfp_utils.tfp_backend_config import get_backend_manager
            return get_backend_manager().is_backend_reachable()
        except Exception as e:
            logger.warning(f"Failed to determine backend reachability: {e}")
            return False

    def _check_builtin_tool_login(self, tool_info) -> bool:
        """检查Builtin工具的登录要求

        登录门控规则（仅非OSS版；OSS社区版后端恒不可达，天然走放行分支）：
        - 后端可达时：必须登录才能打开（包括开源免费子工具）
        - 后端不可达时：不强制要求用户登录，开源免费子工具免登录放行
          （开源免费，本地运行无法限制；无论是否曾经登录过均不设离线宽限期阻断）

        Returns:
            True 表示允许使用，False 表示阻止使用
        """
        # 已登录用户直接放行
        if auth_manager.is_user_logged_in():
            return True

        # 后端可达：未登录必须先登录才能打开（包括开源免费子工具）
        if self._is_backend_reachable():
            logger.info("Backend reachable, Builtin free tool requires login to open")
            self._prompt_login_for_builtin(tool_info)
            return False

        # 后端不可达：不强制要求用户登录，免登录放行
        logger.info("Backend unreachable; open-source free tool allowed without login")
        return True

    def _prompt_login_for_builtin(self, tool_info):
        """提示用户登录以使用Builtin工具"""
        tool_name = self.get_localized_tool_title(tool_info)

        message = translate("message_login_required_free", tool_name=tool_name)
        
        dlg = wx.MessageDialog(
            self,
            message,
            translate("dialog_title_login_required"),
            wx.OK | wx.ICON_INFORMATION
        )
        dlg.ShowModal()
        dlg.Destroy()
        
        # 弹出登录对话框
        auth_manager.request_login_via_ipc(message=translate("message_login_prompt", tool_name=tool_name))

    def run_builtin_program(self, tool_info) -> bool:
        tool_ident = tool_info['tool_ident']
        tool_name = self.get_localized_tool_title(tool_info)
        logger.info(f"Attempting to run built-in program tool: {tool_ident}")
        
        # tool_ident 格式校验（防止路径穿越/注入）
        from tfp_toolkit.tfp_constants import validate_tool_ident_format
        if not validate_tool_ident_format(tool_ident):
            logger.error(f"Invalid tool_ident format, refusing to run: {repr(tool_ident)}")
            wx.MessageBox(
                f"Invalid tool identifier: {tool_ident}",
                translate("dialog_title_error"),
                wx.OK | wx.ICON_ERROR
            )
            return False
        
        # Builtin工具登录检查：后端可达时必须登录（含开源免费子工具）；后端不可达时免登录放行（无离线宽限期）
        if not self._check_builtin_tool_login(tool_info):
            return False
        
        if tool_ident in self.embedded_tools:
            tool_data = self.embedded_tools[tool_ident]
            if tool_data.get('mode') == 'exe':
                if tool_data.get('is_hidden'):
                    self._resend_ipc_show_command(tool_ident)
                else:
                    logger.info(f"Tool {tool_ident} is already running")
                return True
            else:
                self.show_tool_panel(tool_ident)
                return True
        tool_dir = get_resource_path(f"tools_fe/tools_builtin_program/{tool_ident}")
        main_file = tool_dir / "tool_main.py"
        if not main_file.exists():
            wx.MessageBox(translate("message_tool_main_file_not_found").format(path=main_file), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
            return False
        self.clear_tool_module_cache(tool_dir)
        
        tool_panel = None
        try:
            tool_dir_str = str(tool_dir)
            if tool_dir_str not in sys.path:
                sys.path.insert(0, tool_dir_str)
            
            timestamp = int(time.time() * 1000)
            module_name = f"builtin_{tool_ident}_{timestamp}"
            spec = importlib.util.spec_from_file_location(module_name, main_file)
            module = importlib.util.module_from_spec(spec)
            if is_dev_mode():
                module.DEVELOPMENT_MODE = True
            spec.loader.exec_module(module)
            
            if hasattr(module, 'i18n') and hasattr(module.i18n, 'set_language'):
                current_lang = i18n.get_language_code()
                module.i18n.set_language(current_lang)
                logger.info(f"Set language of built-in tool {tool_ident} to: {current_lang}")
            
            user_setting_base_dir = str(self.user_setting_dir)
            tool_instance = module.create_tool(self, user_setting_base_dir=user_setting_base_dir)
            tool_instance.name = self.get_localized_tool_title(tool_info)
            tool_panel = wx.Panel(self.content_container)
            tool_panel_sizer = wx.BoxSizer(wx.VERTICAL)
            tool_panel.SetSizer(tool_panel_sizer)
            if hasattr(tool_instance, 'create_embedded_interface'):
                tool_instance.create_embedded_interface(tool_panel, tool_panel_sizer)
            else:
                static_text = wx.StaticText(tool_panel, label=translate("message_tool_not_support_embedded").format(tool_name=self.get_localized_tool_title(tool_info)))
                tool_panel_sizer.Add(static_text, 1, wx.ALIGN_CENTER)
            self.content_sizer.Add(tool_panel, 1, wx.EXPAND)
            self.embedded_tools[tool_ident] = {
                'panel': tool_panel,
                'instance': tool_instance,
                'mode': 'embedded',
                'requires_subscription': tool_info.get('requires_subscription', False),
            }
            self.add_tool_to_window_menu(tool_ident, self.get_localized_tool_title(tool_info))
            
            saved_tool_size = self.window_sizes.get(tool_ident)
            if saved_tool_size:
                logger.info(f"Detected previously saved window size for tool {tool_ident}: {saved_tool_size[0]}x{saved_tool_size[1]}")
            else:
                tool_window_width = tool_info.get('tool_window_width', 800)
                tool_window_height = tool_info.get('tool_window_height', 600)
                height_offset = -10
                adjusted_tool_height = max(tool_window_height - height_offset, 300)
                frame_extra_width = 16
                total_width = self._spx_calc(tool_window_width + frame_extra_width)
                total_height = self._spx_calc(adjusted_tool_height)
                self.window_sizes[tool_ident] = (total_width, total_height)
                logger.info(f"Tool {tool_ident} first launch, saving default window size: {total_width}x{total_height}")

            self.show_tool_panel(tool_ident)
            logger.info(f"Tool {tool_ident} loaded successfully (embedded)")
            return True
        except Exception as e:
            import traceback as tb
            error_msg = f"加载工具 {tool_ident} 时出错: {str(e)}"
            logger.error(error_msg)
            tb.print_exc()
            try:
                if tool_panel:
                    self.content_sizer.Detach(tool_panel)
                    tool_panel.Destroy()
            except Exception:
                pass
            wx.MessageBox(error_msg, "错误", wx.OK | wx.ICON_ERROR)
            return False

    def _launch_source_tool(self, tool_info, main_file, tool_dir, backend_url=None, loading_panel=None) -> bool:
        """开发模式下以Python源码方式启动RemoteProgram工具"""
        tool_ident = tool_info['tool_ident']
        tool_name = self.get_localized_tool_title(tool_info)
        
        try:
            logger.info(f"[Source Mode] Launching tool: {tool_ident}")
            logger.info(f"Main file path: {main_file}")
            
            ipc_server, ipc_token, socket_port = self._start_ipc_server(tool_ident, 0)
            
            if not ipc_server:
                if loading_panel:
                    loading_panel = self._hide_loading_panel(loading_panel)
                wx.MessageBox(
                    f"无法启动IPC服务器",
                    "错误",
                    wx.OK | wx.ICON_ERROR
                )
                return False
            
            context_file, ipc_token_env_var, ipc_token_value = self._prepare_tool_context(tool_info, tool_dir, backend_url, ipc_token=ipc_token, socket_port=socket_port)
            if not context_file:
                if loading_panel:
                    loading_panel = self._hide_loading_panel(loading_panel)
                wx.MessageBox(
                    f"无法创建工具上下文文件",
                    "错误",
                    wx.OK | wx.ICON_ERROR
                )
                return False
            
            self._cleanup_stale_context_files()
            
            import subprocess
            cmd = [sys.executable, str(main_file), '--context', str(context_file)]
            env = os.environ.copy()
            if ipc_token_env_var and ipc_token_value:
                env[ipc_token_env_var] = ipc_token_value
            # 将SDK根目录（TabulexFlowDesktop根目录，含tfp_toolkit）通过PYTHONPATH注入子进程，
            # 使子工具可直接 `from tfp_toolkit.xxx import ...`
            from tfp_utils.tfp_main_utils import get_base_path
            _sdk_root = str(get_base_path())
            _env_pythonpath = env.get('PYTHONPATH', '')
            if _sdk_root and _sdk_root not in _env_pythonpath.split(os.pathsep):
                env['PYTHONPATH'] = _sdk_root + (os.pathsep + _env_pythonpath if _env_pythonpath else '')
            process = subprocess.Popen(cmd, cwd=str(tool_dir), env=env)
            
            self.embedded_tools[tool_ident] = {
                'mode': 'exe',
                'process': process,
                'ipc_server': ipc_server,
                'ipc_token': ipc_token,
                'ipc_token_expiry': time.time() + 3600,
                'context_file': context_file,
                'loading_panel': loading_panel,
                'main_was_visible': self.IsShown(),
                'is_hidden': False,
                'client_socket': None,
                'ready_received': False,
                'requires_subscription': tool_info.get('requires_subscription', False),
            }
            
            self.add_tool_to_window_menu(tool_ident, tool_name)
            
            def check_process():
                if process.poll() is not None:
                    wx.CallAfter(self._on_exe_tool_closed, tool_ident)
                else:
                    wx.CallLater(1000, check_process)
            
            wx.CallLater(1000, check_process)
            
            def ipc_ready_timeout():
                if tool_ident not in self.embedded_tools:
                    return
                tool_data = self.embedded_tools[tool_ident]
                if tool_data.get('ready_received'):
                    return
                logger.warning(f"[Source Mode] Tool {tool_ident} IPC ready timeout, forcibly hiding main window")
                lp = tool_data.get('loading_panel')
                if lp:
                    tool_data['loading_panel'] = self._hide_loading_panel(lp)
                self.unlock_all_tools()
                if self.IsShown():
                    self.Hide()
            
            wx.CallLater(10000, ipc_ready_timeout)
            
            logger.info(f"Tool {tool_ident} source process started (PID: {process.pid})")
            if tool_info.get('requires_subscription', False):
                _occupy_seat_safe(auth_manager, tool_ident)
            return True
            
        except Exception as e:
            logger.error(f"Failed to launch source tool: {e}")
            traceback.print_exc()
            if loading_panel:
                loading_panel = self._hide_loading_panel(loading_panel)
            wx.MessageBox(f"启动工具失败: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
            return False

    def _launch_exe_tool(self, tool_info, exe_file, tool_dir, backend_url=None, loading_panel=None) -> bool:
        tool_ident = tool_info['tool_ident']
        tool_name = self.get_localized_tool_title(tool_info)
        
        try:
            # H-3 加固：每次启动本地 EXE 前复验 SHA-256 与清单一致
            # （防止磁盘上的 EXE 被同用户进程篡改后，主程序成为任意代码执行载体）
            if not self._verify_exe_integrity(tool_ident, exe_file):
                logger.error(f"Tool {tool_ident} EXE integrity verification failed, refusing to launch")
                if loading_panel:
                    loading_panel = self._hide_loading_panel(loading_panel)
                wx.MessageBox(
                    f"工具 {tool_ident} 文件完整性校验失败，已拒绝启动。\n"
                    "本地文件可能被篡改，请删除后重新下载该工具。",
                    "安全警告",
                    wx.OK | wx.ICON_ERROR
                )
                return False

            logger.info(f"[Standalone Process Mode] Launching tool: {tool_ident}")
            logger.info(f"EXE path: {exe_file}")
            
            # 动态端口（port=0 由系统分配空闲端口），避免固定端口被占用
            ipc_server, ipc_token, socket_port = self._start_ipc_server(tool_ident, 0)
            
            if not ipc_server:
                if loading_panel:
                    loading_panel = self._hide_loading_panel(loading_panel)
                wx.MessageBox(
                    f"无法启动IPC服务器",
                    "错误",
                    wx.OK | wx.ICON_ERROR
                )
                return False
            
            context_file, ipc_token_env_var, ipc_token_value = self._prepare_tool_context(tool_info, tool_dir, backend_url, ipc_token=ipc_token, socket_port=socket_port)
            if not context_file:
                if loading_panel:
                    loading_panel = self._hide_loading_panel(loading_panel)
                wx.MessageBox(
                    f"无法创建工具上下文文件",
                    "错误",
                    wx.OK | wx.ICON_ERROR
                )
                return False
            
            self._cleanup_stale_context_files()
            
            import subprocess
            # Linux/macOS：解压 ZIP 后文件可能丢失可执行位，Popen 前确保 0o755
            # （run_remote_program 中的 chmod 发生在下载解压前，首次打开时文件尚不存在，
            #   此处再次确保以覆盖解压后的文件）
            if os.name != 'nt' and exe_file.exists():
                try:
                    os.chmod(exe_file, 0o755)
                except OSError:
                    logger.warning(f"Failed to set executable permission: {exe_file}")
            cmd = [str(exe_file), '--context', str(context_file)]
            # 通过环境变量传递 ipc_token
            env = os.environ.copy()
            if ipc_token_env_var and ipc_token_value:
                env[ipc_token_env_var] = ipc_token_value
            # Nuitka --standalone: cwd 需设为 exe 所在目录（.dist/），以便 DLL 解析
            # PyInstaller --onedir: cwd 需设为 exe 所在目录（{tool_ident}/），以便 DLL 解析
            # PyInstaller onefile: cwd 设为工具目录即可
            exe_parent_name = exe_file.parent.name
            exe_cwd = str(exe_file.parent) if exe_parent_name.endswith('.dist') or exe_parent_name == tool_ident else str(tool_dir)
            process = subprocess.Popen(cmd, cwd=exe_cwd, env=env)
            
            self.embedded_tools[tool_ident] = {
                'mode': 'exe',
                'process': process,
                'ipc_server': ipc_server,
                'ipc_token': ipc_token,
                'ipc_token_expiry': time.time() + 3600,
                'context_file': context_file,
                'loading_panel': loading_panel,
                'main_was_visible': self.IsShown(),
                'is_hidden': False,
                'client_socket': None,
                'ready_received': False,
                'requires_subscription': tool_info.get('requires_subscription', False),
            }
            
            self.add_tool_to_window_menu(tool_ident, tool_name)
            
            def check_process():
                if process.poll() is not None:
                    wx.CallAfter(self._on_exe_tool_closed, tool_ident)
                else:
                    wx.CallLater(1000, check_process)
            
            wx.CallLater(1000, check_process)
            
            def ipc_ready_timeout():
                if tool_ident not in self.embedded_tools:
                    return
                tool_data = self.embedded_tools[tool_ident]
                if tool_data.get('ready_received'):
                    return
                logger.warning(f"[Standalone Process Mode] Tool {tool_ident} IPC ready timeout, forcibly hiding main window")
                lp = tool_data.get('loading_panel')
                if lp:
                    tool_data['loading_panel'] = self._hide_loading_panel(lp)
                self.unlock_all_tools()
                if self.IsShown():
                    self.Hide()
            
            wx.CallLater(10000, ipc_ready_timeout)
            
            logger.info(f"Tool {tool_ident} EXE process started (PID: {process.pid})")
            # 收费工具占用企业席位
            if tool_info.get('requires_subscription', False):
                _occupy_seat_safe(auth_manager, tool_ident)
            return True
            
        except Exception as e:
            logger.error(f"Failed to launch EXE tool: {e}")
            traceback.print_exc()
            if loading_panel:
                loading_panel = self._hide_loading_panel(loading_panel)
            wx.MessageBox(f"启动工具失败: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
            return False

    def run_remote_program(self, tool_info) -> bool:
        tool_ident = tool_info['tool_ident']
        tool_name = self.get_localized_tool_title(tool_info)
        tool_deploy_mode = tool_info.get('tool_deploy_mode', 'platform')
        self._last_download_error = None
        self._last_download_deprecated_payload = None
        
        # tool_ident 格式校验（防止路径穿越/子进程注入）
        from tfp_toolkit.tfp_constants import validate_tool_ident_format
        if not validate_tool_ident_format(tool_ident):
            logger.error(f"Invalid tool_ident format, refusing to run: {repr(tool_ident)}")
            wx.MessageBox(
                f"Invalid tool identifier: {tool_ident}",
                translate("dialog_title_error"),
                wx.OK | wx.ICON_ERROR
            )
            return False
        
        # 所有工具打开时都要求已登录
        if not self._check_tool_login(tool_info):
            return False
        
        if tool_ident in self.embedded_tools:
            tool_data = self.embedded_tools[tool_ident]
            if tool_data.get('mode') == 'exe':
                if tool_data.get('is_hidden'):
                    self._resend_ipc_show_command(tool_ident)
                else:
                    logger.info(f"Tool {tool_ident} is already running")
                return True
            else:
                self.show_tool_panel(tool_ident)
                return True
        
        loading_panel = self._show_loading_panel(tool_name)
        
        local_dir = self.local_tools_dir / "tools_remote_program" / tool_ident
        main_file = local_dir / "tool_main.py"
        # 平台感知的可执行文件查找（TASK-4，H-3 后统一由 _find_main_exe 负责）：
        # - Windows：主程序名为 {tool_ident}.exe（Nuitka/PyInstaller/onefile）
        # - Linux/macOS：主程序名为 {tool_ident}（无扩展名），Nuitka/PyInstaller 均如此
        # Nuitka --standalone: exe 在 local_dir/{tool_ident}.dist/
        # PyInstaller --onedir: exe 在 local_dir/{tool_ident}/
        # PyInstaller onefile: exe 在 local_dir/ 下
        exe_file = self._find_main_exe(local_dir, tool_ident)
        # Linux/macOS：解压 ZIP 后文件可能丢失可执行位，启动前确保 0o755
        if exe_file is not None and exe_file.exists() and os.name != 'nt':
            try:
                os.chmod(exe_file, 0o755)
            except OSError:
                logger.warning(f"Failed to set executable permission: {exe_file}")
        
        logger.info("=" * 50)
        logger.info(f"Running remote program tool: {tool_ident}")
        logger.info(f"Tool display name: {tool_name}")
        logger.info(f"Deploy mode: {tool_deploy_mode}")
        logger.info(f"Local tool directory: {local_dir}")
        logger.info(f"Main file path: {main_file}")
        logger.info(f"EXE file path: {exe_file}")
        logger.info(f"Local directory exists: {local_dir.exists()}")
        logger.info(f"Main file exists: {main_file.exists()}")
        logger.info(f"EXE file exists: {exe_file.exists()}")
        if getattr(sys, 'frozen', False):
            logger.info(f"Packaged environment: sys._MEIPASS = {getattr(sys, '_MEIPASS', 'Not found')}")
            logger.info(f"EXE directory: {pathlib.Path(sys.executable).parent}")
            logger.info(f"Current working directory: {os.getcwd()}")
        if local_dir.exists():
            logger.info(f"Directory contents: {list(local_dir.iterdir())}")
        logger.info("=" * 50)
        
        # H-3 加固：本地 EXE 完整性已知性检查。清单缺失或哈希不匹配时
        # 强制重新下载（带签名验证），避免"本地 EXE 被篡改后 no_update 直接执行"。
        force_update = False
        if exe_file.exists() and local_dir.exists():
            if not self._verify_exe_integrity(tool_ident, exe_file):
                force_update = True
                logger.warning(
                    f"Tool {tool_ident} local EXE integrity unknown or mismatched, forcing re-download"
                )

        update_success = self.try_update_tool(tool_info, local_dir, force_update=force_update)
        last_error = getattr(self, '_last_download_error', None)
        is_dev = is_dev_mode()
        if not update_success:
            if last_error == 'NETWORK_ERROR' and not force_update and exe_file.exists():
                # 后端不可达：本地已存在且完整性校验通过（force_update=False）的 EXE，
                # 允许离线运行已下载的收费工具（离线试用工具内免费功能；收费功能仍需
                # 后端，Fail-Closed），落入下方本地启动分支
                # 方案A：保持 BusyInfo 不放，直到子工具就绪/超时（下方启动流程负责）
                logger.info(f"Backend unreachable; running locally downloaded tool offline: {tool_ident}")
            elif last_error in ('PACKAGE_NOT_FOUND', 'NETWORK_ERROR', 'API_DEPRECATED', 'SDK_TOO_OLD'):
                loading_panel = self._hide_loading_panel(loading_panel)
                if last_error == 'PACKAGE_NOT_FOUND':
                    wx.MessageBox(
                        translate("message_tool_package_not_found").format(tool_ident=tool_ident),
                        translate("dialog_title_error"),
                        wx.OK | wx.ICON_ERROR
                    )
                elif last_error == 'NETWORK_ERROR':
                    # NETWORK_ERROR 但无本地可用 EXE（未下载，或 force_update=True 表示
                    # 完整性未知/不匹配，不得离线运行未校验的 EXE）
                    wx.MessageBox(
                        translate("message_server_unavailable").format(tool_ident=tool_ident),
                        translate("dialog_title_network_error"),
                        wx.OK | wx.ICON_ERROR
                    )
                elif last_error == 'SDK_TOO_OLD':
                    # T8.4.1：工具要求更高 SDK（随前端主程序分发）——需升级客户端，
                    # 复用统一升级提示链路，同样不得落入"静默启动本地旧 EXE"分支
                    self._prompt_api_deprecated(
                        {'code': 'SDK_TOO_OLD'},
                        translate("tool_sdk_too_old_text").format(
                            tool_ident=tool_ident,
                            min_sdk=getattr(self, '_last_download_sdk_requirement', '') or ''),
                    )
                else:
                    # T7.2：下载端点被弃用（410 API_DEPRECATED）——需要新版客户端。
                    # 弹统一升级提示（OK 后跳转下载页），不再落入"静默启动本地旧 EXE"分支
                    self._prompt_api_deprecated(
                        getattr(self, '_last_download_deprecated_payload', None) or {},
                        translate("tool_api_deprecated_text").format(tool_ident=tool_ident),
                    )
                return False
            # 方案A：不再提前释放 BusyInfo，将其传入启动流程——由 _on_exe_tool_ready（就绪）
            # 或 ipc_ready_timeout（超时）或 _launch_*_tool 的错误分支负责隐藏，使
            # "正在加载/打开工具"提示覆盖子工具启动全过程，避免用户误以为程序卡死。
            # 开发模式始终走源码启动；生产模式使用 EXE 模式
            if is_dev and main_file.exists():
                return self._launch_source_tool(tool_info, main_file, local_dir, self.backend_url, loading_panel)
            elif exe_file.exists():
                return self._launch_exe_tool(tool_info, exe_file, local_dir, self.backend_url, loading_panel)
            else:
                loading_panel = self._hide_loading_panel(loading_panel)
                wx.MessageBox(
                    translate("message_first_run_need_download").format(tool_ident=tool_ident),
                    translate("dialog_title_need_download"),
                    wx.OK | wx.ICON_ERROR
                )
                return False
        else:
            # 方案A：同上，保持 BusyInfo 直到子工具就绪/超时/失败
            # 开发模式始终走源码启动；生产模式使用 EXE 模式
            if is_dev_mode() and main_file.exists():
                return self._launch_source_tool(tool_info, main_file, local_dir, self.backend_url, loading_panel)
            elif exe_file.exists():
                return self._launch_exe_tool(tool_info, exe_file, local_dir, self.backend_url, loading_panel)
            else:
                loading_panel = self._hide_loading_panel(loading_panel)
                error_msg = f"工具 {tool_ident} 下载成功但文件缺失，无法运行。"
                logger.error(error_msg)
                wx.MessageBox(error_msg, "错误", wx.OK | wx.ICON_ERROR)
                return False

    def _show_loading_panel(self, tool_name):
        wx.Yield()
        return wx.BusyInfo(translate("busy_loading_tool", tool_name=tool_name), self)
    
    def _hide_loading_panel(self, loading_panel):
        # 调用者必须用 loading_panel = self._hide_loading_panel(loading_panel) 重新赋值
        # 以释放BusyInfo对象的引用，使其被GC回收并消失
        return None

    def run_remote_webpage(self, tool_info) -> bool:
        tool_ident = tool_info['tool_ident']
        tool_name = self.get_localized_tool_title(tool_info)
        # RemoteWebpage 独立 WebView 窗口标题与主窗口工具标题格式保持一致
        # （同 main.py SetTitle 的 "<品牌标题> - <工具名>"，品牌标题随语言本地化）；
        # 延迟导入避免循环依赖（main.py 顶层导入本 mixin，运行期 main 已加载完成）
        from main import get_app_base_title
        window_title = f"{get_app_base_title()} - {tool_name}"
        
        # tool_ident 格式校验（防止路径穿越）
        from tfp_toolkit.tfp_constants import validate_tool_ident_format
        if not validate_tool_ident_format(tool_ident):
            logger.error(f"Invalid tool_ident format, refusing to run: {repr(tool_ident)}")
            wx.MessageBox(
                f"Invalid tool identifier: {tool_ident}",
                translate("dialog_title_error"),
                wx.OK | wx.ICON_ERROR
            )
            return False
        
        # 所有工具打开时都要求已登录
        if not self._check_tool_login(tool_info):
            return False
        
        url, token, reason = self.try_get_remote_webpage_url(tool_info)
        if url:
            self.show_webview_dialog(window_title, url, True, one_time_token=token)
            # RemoteWebpage 使用 ShowModal 阻塞对话框，关闭后回到主界面，
            # 不走 show_tool_panel/show_home_panel 流程（这两个方法内部会调用 unlock_all_tools），
            # 因此必须在此处显式解锁工具卡片，否则关闭 WebView 对话框后主界面的工具卡片将无法点击
            self.unlock_all_tools()
            return True
        elif reason == 'login_required':
            # 已弹出登录框；登录成功后需用户重新点击工具打开
            logger.warning(f"Tool {tool_ident} requires login; please reopen after logging in")
            wx.MessageBox(
                translate("message_remote_webpage_login_required"),
                translate("dialog_title_login_required"),
                wx.OK | wx.ICON_INFORMATION
            )
            return False
        else:
            # 网络错误、版本过低等其他原因
            wx.MessageBox(
                translate("message_remote_webpage_offline_error"),
                translate("dialog_title_network_error"),
                wx.OK | wx.ICON_ERROR
            )
            return False

    def _get_installer_cache_dir(self):
        """T8.6.1 安装包缓存目录（<runtime_base>/update_cache，可写目录）。"""
        return pathlib.Path(getattr(self, '_runtime_base_dir', '')) / _INSTALLER_CACHE_DIRNAME

    def _start_installer_download(self, latest_info):
        """T8.6.1 发现新版本后启动后台静默下载安装包（不阻塞版本检查线程）。

        资格判定：installers 含本平台条目（url/sha256/sig 齐全）且验签前置满足
        （生产环境须根公钥已配置且两段验签通过——根验叶凭证 → 叶验 sig；
        dev 模式未配公钥按工具分发同规则跳过验签）。缓存已命中（sha256 匹配）
        时跳过下载直接弹"更新包已就绪"（实现"NO → 下次启动再提示"）。
        返回 True=已启动（或缓存命中已提示）；False=不具备后台下载条件，
        调用方回退方案 1a"提示 + 跳转下载页"。

        T8.6.3（增强层预留，本期不实现）：未来在"安装器带有效 OS 签名证书 +
        用户配置开关启用"两条件同时满足时，才允许切换为自动调起安装器路径；
        无证书环境自动安装会被 Windows SmartScreen/AV 拦截，故本期一律引导
        手动安装（_prompt_installer_ready，见 main.py）。
        """
        try:
            entry = (latest_info.get('installers') or {}).get(get_platform_tag()) or {}
            url = str(entry.get('url', '')).strip()
            expected_sha = str(entry.get('sha256', '')).strip().lower()
            sig = str(entry.get('sig', '')).strip()
            cred = str(latest_info.get('sign_cred', '') or '').strip()
            version = str(latest_info.get('version', '')).strip()
            if not (url and expected_sha and sig and version):
                return False
            if not is_public_key_configured() and not is_dev_mode():
                # 生产环境未配置根公钥：无法验签，fail-closed 回退提示模式
                logger.warning("Installer download skipped: root public key not configured")
                return False
            if not is_dev_mode():
                # 两段验签（元数据层，下载前 fail-fast）：根验叶凭证 → 叶验 sig
                leaf_pem = verify_leaf_credential(cred)
                if not leaf_pem:
                    logger.error("Installer leaf credential verification failed; "
                                 "falling back to download-page prompt")
                    return False
                if not verify_tool_signature(expected_sha, version, sig, leaf_pem):
                    logger.error("Installer sig verification failed; "
                                 "falling back to download-page prompt")
                    return False
            final_path = self._get_installer_cache_dir() / self._installer_filename(url, version)
            # 缓存命中：实际文件 sha256 与验签过的期望值一致 → 直接就绪提示
            if final_path.exists() and _sha256_of_file(final_path) == expected_sha:
                logger.info("Installer cache hit: %s", final_path)
                wx.CallAfter(self._prompt_installer_ready, final_path, version)
                return True
            threading.Thread(
                target=self._download_installer_worker,
                args=(latest_info,),
                name=f"installer-download-{version}",
                daemon=True,
            ).start()
            return True
        except Exception as e:
            logger.error("Installer download scheduling failed: %s", e)
            return False

    @staticmethod
    def _installer_filename(url, version):
        """从安装包直链取文件名（无文件名时回退带版本号的默认名）。"""
        return os.path.basename(urlparse(url).path) or f"tabulexflow-installer-{version}"

    def _download_installer_worker(self, latest_info):
        """T8.6.1 daemon 线程：流式下载安装包 → sha256 比对 → 缓存保留 → 就绪提示。

        元数据验签已在 _start_installer_download 完成（sig 验证 expected_sha 真实性）；
        此处将实际文件哈希与之比对（fail-closed，内容层校验）。任一环节失败：
        清理临时文件并回退方案 1a"提示 + 跳转下载页"（与旧版用户可见行为一致）。
        """
        entry = (latest_info.get('installers') or {}).get(get_platform_tag()) or {}
        url = str(entry.get('url', '')).strip()
        expected_sha = str(entry.get('sha256', '')).strip().lower()
        version = str(latest_info.get('version', '')).strip()
        cache_dir = self._get_installer_cache_dir()
        final_path = cache_dir / self._installer_filename(url, version)
        tmp_path = None
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            # 先写临时文件再原子改名（同工具分发 L-7 精神），半成品不冒充完整安装包
            with tempfile.NamedTemporaryFile(
                    dir=str(cache_dir), prefix='.tfp_installer_', suffix='.part',
                    delete=False) as tmp_file:
                tmp_path = pathlib.Path(tmp_file.name)
                downloaded = 0
                with requests.get(url, stream=True, timeout=(10, 30)) as response:
                    response.raise_for_status()
                    for chunk in response.iter_content(chunk_size=65536):
                        if not chunk:
                            continue
                        tmp_file.write(chunk)
                        downloaded += len(chunk)
                        if downloaded > _MAX_TOOL_ZIP_BYTES:
                            # 复用工具包 500MB 上限，防恶意/异常响应写满磁盘（DA3）
                            raise ValueError(
                                f"Installer exceeds size limit {_MAX_TOOL_ZIP_BYTES} bytes")
            if _sha256_of_file(tmp_path) != expected_sha:
                raise ValueError("Installer sha256 mismatch (integrity check failed)")
            os.replace(str(tmp_path), str(final_path))
            tmp_path = None
            logger.info("Installer downloaded and verified: %s (%d bytes)",
                        final_path, downloaded)
            wx.CallAfter(self._prompt_installer_ready, final_path, version)
        except Exception as e:
            logger.error("Installer download failed (non-blocking): %s", e)
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass  # 临时文件清理失败可容忍（缓存目录残留 .part 文件无害）
            # 回退方案 1a：提示 + 跳转下载页（_prompt_frontend_update 内部二次确认版本）
            wx.CallAfter(self._prompt_frontend_update,
                         version,
                         str(latest_info.get('changelog', '') or ''),
                         str(latest_info.get('download_url', '') or ''))

    def try_update_tool(self, tool_info, local_dir, force_update=False):
        try:
            # T8.4.1（B1）：工具清单声明 min_sdk_version 时，下载前先比对本地 SDK 版本
            # （tfp_utils.__version__）。低于阈值拒绝下载并留存载荷供 run_remote_program
            # 弹统一升级提示（复用 410 提示链路）；缺省/非法值=不限制（fail-open）。
            # 注意 SDK 版本与前端主程序版本是独立语义，弹窗正文需带 SDK 语境
            _min_sdk = str(tool_info.get('min_sdk_version') or '').strip()
            if _min_sdk and version_tuple(_min_sdk) > version_tuple(_LOCAL_SDK_VERSION):
                self._last_download_error = 'SDK_TOO_OLD'
                self._last_download_sdk_requirement = _min_sdk
                logger.error(
                    f"Tool {tool_info['tool_ident']} requires SDK >= {_min_sdk}, "
                    f"local SDK is {_LOCAL_SDK_VERSION}; refusing download")
                return False
            _auth_headers = auth_manager.get_auth_headers()
            # H-3 加固：force_update 时版本号压低为 0.0.0，使后端绕过 no_update 判断重新下发 ZIP
            request_tool_version = '0.0.0' if force_update else tool_info.get('tool_version', '0.0.0')
            response = requests.get(
                f"{self.backend_url}{API_V1_PREFIX}/download_tool/{tool_info['tool_type']}/{tool_info['tool_ident']}",
                params={
                    'tool_version': request_tool_version,
                    'frontend_version': self.frontend_version,
                    'os': get_platform_tag(),  # TASK-3/4：告知后端客户端平台，以便下发对应平台 ZIP
                },
                headers=_auth_headers,
                timeout=10,
                stream=True
            )
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    try:
                        data = response.json()
                        if data.get('status') == 'no_update':
                            logger.info(f"Tool {tool_info['tool_ident']} is already the latest version")
                            return True
                        else:
                            logger.info(f"Unknown JSON response: {data}")
                            return False
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON parse error: {e}")
                        return False
                elif 'application/zip' in content_type or 'application/octet-stream' in content_type or 'application/x-zip-compressed' in content_type:
                    logger.info(f"Starting to download tool {tool_info['tool_ident']}...")
                    return self.download_and_extract_tool_from_response(response, tool_info, local_dir)
                else:
                    logger.info(f"Unknown response type: {content_type}")
                    return False
            else:
                error_msg = f"Server returned error: {response.status_code}"
                try:
                    error_data = response.json()
                    error_code = error_data.get('code', '')
                    if error_code == 'PACKAGE_NOT_FOUND':
                        self._last_download_error = 'PACKAGE_NOT_FOUND'
                        error_msg = translate("message_tool_package_not_found").format(tool_ident=tool_info['tool_ident'])
                    elif response.status_code == 410 and error_code == 'API_DEPRECATED':
                        # T7.2：后端弃用契约——下载端点已弃用，需新版客户端
                        # （载荷留给 run_remote_program 弹窗取后端文案/最低版本）
                        self._last_download_error = 'API_DEPRECATED'
                        self._last_download_deprecated_payload = error_data
                        error_msg = f"Tool download API deprecated: {response.status_code} (code=API_DEPRECATED)"
                    else:
                        self._last_download_error = f"HTTP_{response.status_code}"
                except Exception:
                    self._last_download_error = f"HTTP_{response.status_code}"
                logger.error(error_msg)
                return False
        except Exception as e:
            logger.error(f"Failed to update tool: {e}")
            self._last_download_error = 'NETWORK_ERROR'
            return False

    def download_and_extract_tool_from_response(self, response, tool_info, target_dir):
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            logger.info("=" * 50)
            logger.info(f"Downloading tool file: {tool_info['tool_ident']}")
            logger.info(f"Target directory: {target_dir}")
            logger.info(f"Target directory absolute path: {target_dir.absolute()}")
            logger.info(f"Target directory parent: {target_dir.parent}")
            logger.info(f"Target directory parent exists: {target_dir.parent.exists()}")
            try:
                # L-7 加固（2026-09-01）：改为 NamedTemporaryFile
                # （不可预测随机名 + O_EXCL 创建 + delete=True 自动清理），
                # 避免可预测文件名 test_write.txt 被本地攻击者预置 symlink 造成覆写
                with tempfile.NamedTemporaryFile(dir=str(target_dir), prefix=".tfp_wt_", delete=True) as tf:
                    tf.write(b"test")
                logger.info("Target directory writable: yes")
            except Exception as e:
                logger.info(f"Target directory writable: no - {e}")
                wx.MessageBox(
                    translate("message_cannot_write_tool_dir").format(dir=target_dir),
                    translate("dialog_title_permission_error"),
                    wx.OK | wx.ICON_ERROR
                )
                return False
            logger.info("=" * 50)
            temp_dir = pathlib.Path(tempfile.mkdtemp())
            temp_zip_path = temp_dir / f"{tool_info['tool_ident']}.zip"
            logger.info(f"Temporary directory: {temp_dir}")
            logger.info(f"Temporary ZIP file: {temp_zip_path}")
            try:
                logger.info("Starting to download ZIP file...")
                total_size = 0
                with open(temp_zip_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            total_size += len(chunk)
                            if total_size % (8192 * 100) == 0:
                                logger.info(f"Downloaded: {total_size} bytes")
                            # L-5 加固（2026-09-01）：ZIP 大小上限，超限立即中止（finally 清理临时文件），
                            # 防止恶意/异常响应写满磁盘（fail-closed：不会进入解压/校验流程）
                            if total_size > _MAX_TOOL_ZIP_BYTES:
                                raise ValueError(
                                    f"Tool package exceeds size limit ({_MAX_TOOL_ZIP_BYTES} bytes), "
                                    f"download aborted: {tool_info['tool_ident']}"
                                )
                logger.info(f"Download complete, ZIP file size: {temp_zip_path.stat().st_size} bytes")
                if not zipfile.is_zipfile(temp_zip_path):
                    raise zipfile.BadZipFile("Downloaded file is not a valid ZIP file")
                logger.info("ZIP file verified successfully")
                
                expected_checksum = response.headers.get('X-Tool-Checksum')
                signature = response.headers.get('X-Tool-Checksum-Sig', '')
                tool_version = response.headers.get('X-Tool-Version', tool_info.get('tool_version', ''))
                if not expected_checksum:
                    # 无校验和时拒绝运行
                    logger.error("No checksum in response, refusing to extract and run")
                    wx.CallAfter(
                        wx.MessageBox,
                        translate("message_no_checksum").format(tool_ident=tool_info['tool_ident']),
                        translate("dialog_title_security_warning"),
                        wx.OK | wx.ICON_ERROR
                    )
                    raise ValueError("Server did not provide a file checksum; integrity verification is not possible")

                # H-3 加固：发布方签名验证（独立信任锚，根/叶分层）。
                # 根公钥内置于打包产物；先用根验证"叶子凭证"（X-Tool-Sign-Cred）得到叶子公钥，
                # 再用叶子公钥验签。攻击者可篡改 ZIP 与响应头，但无私钥无法伪造签名/凭证。
                if is_public_key_configured():
                    # 1) 验证叶子凭证（X-Tool-Sign-Cred）→ 得到叶子公钥
                    cred = response.headers.get('X-Tool-Sign-Cred', '')
                    leaf_pem = verify_leaf_credential(cred)
                    if not leaf_pem:
                        logger.error(
                            f"Tool signing credential verification FAILED: {tool_info['tool_ident']}"
                        )
                        wx.CallAfter(
                            wx.MessageBox,
                            f"工具 {tool_info['tool_ident']} 无法验证发布方签名凭证，已拒绝下载。",
                            translate("dialog_title_security_warning"),
                            wx.OK | wx.ICON_ERROR
                        )
                        raise ValueError("Tool package signing credential verification failed; the file may have been tampered with")
                    # 2) 必须带工具包签名
                    if not signature:
                        logger.error(f"No tool signature in response, refusing to extract and run: {tool_info['tool_ident']}")
                        wx.CallAfter(
                            wx.MessageBox,
                            translate("message_no_publisher_signature").format(tool_ident=tool_info['tool_ident']),
                            translate("dialog_title_security_warning"),
                            wx.OK | wx.ICON_ERROR
                        )
                        raise ValueError("Server did not provide a tool package signature; cannot verify the publisher")
                    # 3) 用凭证解析出的叶子公钥验签
                    if not verify_tool_signature(expected_checksum, tool_version, signature, leaf_pem):
                        logger.error(
                            f"Tool signature verification FAILED: {tool_info['tool_ident']} "
                            f"(checksum={expected_checksum}, version={tool_version})"
                        )
                        wx.CallAfter(
                            wx.MessageBox,
                            translate("message_publisher_signature_failed").format(tool_ident=tool_info['tool_ident']),
                            translate("dialog_title_security_warning"),
                            wx.OK | wx.ICON_ERROR
                        )
                        raise ValueError("Tool package signature verification failed; the file may have been tampered with")
                    logger.info(f"Tool signature verification passed: {tool_info['tool_ident']}")
                elif is_dev_mode():
                    # 源码开发模式且未配置公钥：放行（本地开发环境，信任本地后端）
                    logger.warning(
                        "Tool signing public key not configured; dev mode skips signature "
                        f"verification (H-3): {tool_info['tool_ident']}"
                    )
                else:
                    # 生产 / 本地测试构建且未配置公钥：fail-closed
                    logger.error(
                        f"Tool signing public key not configured, refusing unsigned tool package: {tool_info['tool_ident']}"
                    )
                    wx.CallAfter(
                        wx.MessageBox,
                        f"工具 {tool_info['tool_ident']} 无法验证发布方签名（未配置公钥），已拒绝下载。",
                        translate("dialog_title_security_warning"),
                        wx.OK | wx.ICON_ERROR
                    )
                    raise ValueError("Tool publisher signing public key is not configured; refusing to run an unverified tool package")

                # 比对 ZIP SHA-256（验签通过后，确认 ZIP 内容与签名载荷中的校验和一致）
                sha256 = hashlib.sha256()
                with open(temp_zip_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(8192), b''):
                        sha256.update(chunk)
                actual_checksum = sha256.hexdigest()
                if actual_checksum != expected_checksum:
                    logger.error(f"Checksum mismatch! Expected: {expected_checksum}, actual: {actual_checksum}")
                    wx.CallAfter(
                        wx.MessageBox,
                        translate("message_checksum_mismatch").format(tool_ident=tool_info['tool_ident']),
                        translate("dialog_title_security_warning"),
                        wx.OK | wx.ICON_ERROR
                    )
                    raise ValueError("Downloaded file checksum mismatch; the file may be corrupted or tampered with")
                logger.info(f"Checksum verification passed: {actual_checksum}")
                
                if target_dir.exists():
                    logger.info("Clearing target directory...")
                    deleted_count = 0
                    icon_backup = {}
                    for item in target_dir.iterdir():
                        try:
                            if item.is_file() and item.name != "app_icon.ico":
                                item.unlink()
                                deleted_count += 1
                            elif item.is_file() and item.name == "app_icon.ico":
                                icon_backup['icon'] = item.read_bytes()
                            elif item.is_dir():
                                icon_path = item / "app_icon.ico"
                                if icon_path.exists():
                                    icon_backup['icon'] = icon_path.read_bytes()
                                shutil.rmtree(item)
                                deleted_count += 1
                        except Exception as e:
                            logger.info(f"Error deleting {item}: {e}")
                    logger.info(f"Deleted {deleted_count} files/directories")
                logger.info("Starting to extract ZIP file...")
                with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                    file_list = zip_ref.namelist()
                    logger.info(f"ZIP file contains {len(file_list)} files:")
                    for file in file_list:
                        logger.info(f"  - {file}")
                    # 路径遍历防护
                    target_dir_real = os.path.realpath(str(target_dir))
                    for member in file_list:
                        member_path = os.path.realpath(os.path.join(str(target_dir), member))
                        if not member_path.startswith(target_dir_real + os.sep):
                            logger.error(f"Illegal path detected: {member}")
                            raise ValueError(f"Illegal ZIP file path: {member}")
                    zip_ref.extractall(target_dir)
                    logger.info("Extraction complete")
                    if icon_backup.get('icon'):
                        icon_dest = target_dir / "app_icon.ico"
                        if not icon_dest.exists():
                            try:
                                icon_dest.write_bytes(icon_backup['icon'])
                                logger.info(f"Icon restored: {icon_dest}")
                            except Exception as e:
                                logger.error(f"Failed to restore icon: {e}")
                logger.info("Directory contents after extraction:")
                if target_dir.exists():
                    for item in target_dir.iterdir():
                        if item.is_file():
                            logger.info(f"  File: {item.name} ({item.stat().st_size} bytes)")
                        elif item.is_dir():
                            sub_items = list(item.iterdir())
                            logger.info(f"  Directory: {item.name} ({len(sub_items)} items)")
                zip_file_in_target = target_dir / f"{tool_info['tool_ident']}.zip"
                if zip_file_in_target.exists():
                    try:
                        zip_file_in_target.unlink()
                        logger.info(f"Deleted extracted ZIP file: {zip_file_in_target}")
                    except Exception as e:
                        logger.error(f"Failed to delete ZIP file: {e}")
                logger.info(f"Tool {tool_info['tool_ident']} downloaded and extracted successfully")
                # H-3 加固：解压成功后写入本地完整性清单（每次启动时复验 EXE 哈希）
                if not self._write_tool_manifest(
                    tool_info['tool_ident'], tool_info['tool_type'], tool_version, target_dir
                ):
                    raise ValueError("Failed to write the local integrity manifest; refusing to run")
                self.update_local_tool_version(tool_info['tool_ident'], tool_info['tool_type'])
                # 安装成功后立即清除该工具的升级标记并刷新卡片，避免标签残留到下次重启前端
                # （原先仅在点击 Upgrade 标签 on_tool_upgrade_click 时清除）
                with self._tools_data_lock:
                    self._tools_with_update.discard(tool_info['tool_ident'])
                wx.CallAfter(self.update_tool_buttons)
                return True
            except (zipfile.BadZipFile, ValueError) as e:
                logger.error(f"Downloaded file corrupted or checksum verification failed: {str(e)}")
                return False
            finally:
                try:
                    if temp_zip_path.exists():
                        temp_zip_path.unlink()
                        logger.info("Temporary ZIP file deleted")
                    if temp_dir.exists():
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        logger.info("Temporary directory deleted")
                except Exception as e:
                    logger.info(f"Error cleaning up temporary files: {e}")
        except Exception as e:
            logger.info(f"Error downloading tool file: {str(e)}")
            traceback.print_exc()
            return False

    # ========== H-3 加固：EXE 查找 / 本地完整性清单 ==========

    def _find_main_exe(self, local_dir, tool_ident, use_fallback=True):
        """平台感知的可执行文件查找。

        - Windows：主程序名 {tool_ident}.exe；Linux/macOS：{tool_ident}（无扩展名）
        - 候选位置依次为 Nuitka --standalone（{ident}.dist/）、
          PyInstaller --onedir（{ident}/）、PyInstaller onefile（目录根）
        - use_fallback=True 时（与旧行为一致）找不到也返回 Nuitka 默认路径（可能不存在）；
          use_fallback=False 时找不到返回 None（用于解压后定位真实 EXE）
        """
        exe_name = f"{tool_ident}.exe" if get_platform_tag() == 'windows' else tool_ident
        candidates = [
            local_dir / f"{tool_ident}.dist" / exe_name,   # Nuitka
            local_dir / tool_ident / exe_name,             # PyInstaller --onedir
            local_dir / exe_name,                          # PyInstaller onefile
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        if use_fallback:
            return candidates[0]
        return None

    def _tool_manifest_path(self, tool_ident):
        """本地 EXE 完整性清单路径（工具目录之外，避免更新清目录时被清除）"""
        return self.local_tools_dir / '.tfp_manifests' / f"{tool_ident}.json"

    def _write_file_0600(self, path, data):
        """原子创建文件并收紧 0600（避免"先写后 chmod"竞态）"""
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
        except BaseException:
            raise
        try:
            os.chmod(str(path), 0o600)
        except OSError:
            pass

    def _write_tool_manifest(self, tool_ident, tool_type, tool_version, local_dir):
        """下载解压成功后，将主 EXE 的 SHA-256 写入本地完整性清单（0600）。

        包内没有主 EXE 时（例如纯源码 ZIP）跳过写入并返回 True；
        写入失败返回 False（调用方 fail-closed）。
        """
        exe_file = self._find_main_exe(local_dir, tool_ident, use_fallback=False)
        if exe_file is None or not exe_file.exists():
            logger.info(f"Tool {tool_ident}: no main EXE found in package, skip integrity manifest")
            return True
        sha256 = hashlib.sha256()
        with open(exe_file, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        manifest = {
            'tool_ident': tool_ident,
            'tool_type': tool_type,
            'tool_version': tool_version,
            'exe_sha256': sha256.hexdigest(),
        }
        try:
            manifest_path = self._tool_manifest_path(tool_ident)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_file_0600(
                manifest_path,
                json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'),
            )
            logger.info(f"Tool {tool_ident} integrity manifest written: {manifest_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to write integrity manifest for {tool_ident}: {e}")
            return False

    def _verify_exe_integrity(self, tool_ident, exe_file) -> bool:
        """复验本地 EXE 的 SHA-256 与完整性清单一致（H-3 加固）。

        清单缺失、EXE 缺失或哈希不匹配均返回 False（fail-closed）。
        """
        try:
            manifest_path = self._tool_manifest_path(tool_ident)
            if not manifest_path.exists():
                logger.warning(f"Tool {tool_ident} integrity manifest missing: {manifest_path}")
                return False
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            expected_sha256 = manifest.get('exe_sha256', '')
            if not expected_sha256:
                return False
            if not exe_file.exists():
                return False
            sha256 = hashlib.sha256()
            with open(exe_file, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256.update(chunk)
            actual_sha256 = sha256.hexdigest()
            if actual_sha256 != expected_sha256:
                logger.error(
                    f"Tool {tool_ident} EXE integrity check FAILED: "
                    f"expected {expected_sha256}, actual {actual_sha256}"
                )
                return False
            return True
        except Exception as e:
            logger.error(f"Tool {tool_ident} EXE integrity check error: {e}")
            return False

    def update_local_tool_version(self, tool_ident, tool_type):
        try:
            backend_version = self.get_tool_version_from_backend_cache(tool_ident, tool_type)
            if not backend_version:
                if self.fetch_backend_tools_cache():
                    backend_version = self.get_tool_version_from_backend_cache(tool_ident, tool_type)
            if backend_version:
                with self._tools_data_lock:
                    for category, tools in self.non_builtin_tools.items():
                        for tool in tools:
                            if tool['tool_ident'] == tool_ident and tool['tool_type'] == tool_type:
                                tool['tool_version'] = backend_version
                                logger.info(f"Updated tool {tool_ident} version to {backend_version}")
                                self.save_local_non_builtin_tools()
                                return True
                logger.info(f"Tool {tool_ident} not found in local tool list")
                return False
            else:
                logger.info(f"Failed to get version number of tool {tool_ident} from backend")
                return False
        except Exception as e:
            logger.error(f"Failed to update tool version number: {e}")
            return False

    def fetch_backend_tools_cache(self):
        try:
            response = requests.get(
                f"{self.backend_url}{API_V1_PREFIX}/tool_list",
                params={'last_modified': '1970-01-01T00:00:00Z', 'frontend_version': self.frontend_version},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'updated':
                    self.backend_tools_cache = data.get('tools', {})
                    logger.info("Backend tool list cache fetched")
                    return True
            return False
        except Exception as e:
            logger.error(f"Failed to fetch backend tool list cache: {e}")
            return False

    def get_tool_version_from_backend_cache(self, tool_ident, tool_type):
        if not self.backend_tools_cache:
            return None
        category_map = {
            'RemoteProgram': 'tools_remote_program',
            'RemoteWebpage': 'tools_remote_webpage'
        }
        category = category_map.get(tool_type)
        if not category or category not in self.backend_tools_cache:
            return None
        for tool in self.backend_tools_cache[category]:
            if tool.get('tool_ident') == tool_ident:
                return tool.get('tool_version', '1.0.0')
        return None

    def try_get_remote_webpage_url(self, tool_info):
        """获取 RemoteWebpage 页面 URL 与一次性认证 token，返回 (url, token, reason)。

        H-2 加固：token 不再拼入 URL（避免命令行/日志暴露），改为随返回的
        (url, token) 由 WebView 以 POST 表单体提交后台兑换 HttpOnly Cookie。

        Returns:
            tuple[str|None, str|None, str|None]:
            - 成功: (页面URL(不含token), 一次性token, None)
            - 401 未登录: (None, None, 'login_required')（已触发登录弹窗）
            - 403 权限不足: (None, None, 'permission_denied')（已弹出权限不足对话框）
            - 400 前端版本过低: (None, None, 'version_too_low')
            - 其他/网络错误: (None, None, 'network_error')
        """
        try:
            tool_ident = tool_info['tool_ident']
            tool_version = tool_info.get('tool_version', '0.0.0')
            frontend_version = self.frontend_version
            _auth_headers = auth_manager.get_auth_headers()
            response = requests.get(
                f"{self.backend_url}{API_V1_PREFIX}/download_tool/RemoteWebpage/{tool_ident}",
                params={
                    "tool_version": tool_version,
                    "frontend_version": frontend_version
                },
                headers=_auth_headers,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success' and data.get('url'):
                    url = data['url']
                    webview_token = data.get('webview_token')
                    return url, webview_token or None, None
                elif data.get('status') == 'no_update':
                    return f"{self.backend_url}/webpage/remote/{tool_ident}", None, None
                else:
                    logger.error(f"Failed to get remote webpage URL: {data.get('error', 'unknown error')}")
                    return None, None, 'error'
            elif response.status_code == 400:
                data = response.json()
                logger.error(f"Frontend version too low to use this tool: {data.get('error', '')}")
                return None, None, 'version_too_low'
            elif response.status_code == 401:
                # 未登录：触发登录流程
                logger.warning(f"Login required to get remote webpage URL: {tool_ident}")
                auth_manager.request_login_via_ipc(message=translate("message_login_prompt_generic"))
                return None, None, 'login_required'
            elif response.status_code == 403:
                # 权限不足：弹出权限不足提示对话框
                error_data = response.json()
                logger.warning(f"Insufficient permissions for remote webpage tool: {tool_ident}, reason={error_data.get('reason')}")
                from tfp_auth.tfp_login_dialog import TFP_PermissionRequiredDialog
                dlg = TFP_PermissionRequiredDialog(
                    self,
                    message=error_data.get('error', '权限不足'),
                    required_type=error_data.get('reason', 'subscription_required'),
                    current_type=error_data.get('current_type', 'free')
                )
                dlg.ShowModal()
                dlg.Destroy()
                return None, None, 'permission_denied'
            else:
                logger.error(f"Failed to get remote webpage URL: HTTP {response.status_code}")
                return None, None, 'network_error'
        except Exception as e:
            logger.error(f"Failed to get remote webpage URL: {e}")
            return None, None, 'network_error'

    def show_webview_dialog(self, title, url, is_remote=False, one_time_token=None):
        if wx.html2 is None:
            # Linux 回退：wx.html2 缺失时使用 pywebview 独立子进程（WebKitGTK 4.1/4.0）
            try:
                shown = show_webview_dialog_fallback(
                    self, title, url,
                    self._spx_calc(800), self._spx_calc(600),
                    one_time_token=one_time_token
                )
            except Exception as e:
                logger.error(f"WebView fallback path failed: {e}")
                wx.MessageBox(
                    translate("message_page_load_failed").format(error=str(e)),
                    translate("dialog_title_load_error"),
                    wx.OK | wx.ICON_ERROR
                )
                return
            if not shown:
                wx.MessageBox(
                    "WebView is not available on this platform (wx.html2 missing).",
                    translate("dialog_title_error"),
                    wx.OK | wx.ICON_ERROR
                )
            return
        dialog = wx.Dialog(self, title=title, size=(self._spx_calc(800), self._spx_calc(600)))
        panel = wx.Panel(dialog)
        sizer = wx.BoxSizer(wx.VERTICAL)
        browser = wx.html2.WebView.New(panel)
        try:
            if hasattr(browser, 'EnableContextMenu'):
                browser.EnableContextMenu(True)
            if hasattr(browser, 'EnableAccessToDevTools'):
                browser.EnableAccessToDevTools(is_dev_mode())
        except Exception:
            pass
        # H-2 加固：日志对 URL query 中的一次性 token 脱敏（?token=***）
        if one_time_token:
            logger.info(f"Attempting POST token exchange to load URL: {mask_url_query_token(url)}")
        else:
            logger.info(f"Attempting to load URL: {mask_url_query_token(url)}")

        # M-2 加固：URL 白名单 = http/https 协议 + 可信后端域名（默认后端域名 或 当前 backend_url 域名）
        if not is_url_trusted(url, backend_url=self.backend_url):
            logger.error(f"Refusing to load untrusted URL: {mask_url_query_token(url)}")
            wx.MessageBox(
                translate("message_page_load_failed").format(error="URL不被允许"),
                translate("dialog_title_load_error"), wx.OK | wx.ICON_ERROR
            )
            dialog.Destroy()
            return

        def on_loaded(event):
            logger.info("WebView loaded successfully")
            dialog_status.SetLabel(translate("label_page_loaded"))

        def on_error(event):
            error_msg = translate("message_page_load_failed").format(error=event.GetString())
            logger.error(error_msg)
            dialog_status.SetLabel(translate("label_page_load_failed"))
            wx.MessageBox(error_msg, translate("dialog_title_load_error"), wx.OK | wx.ICON_ERROR)
        browser.Bind(wx.html2.EVT_WEBVIEW_LOADED, on_loaded)
        browser.Bind(wx.html2.EVT_WEBVIEW_ERROR, on_error)
        # H-2 加固：一次性 token 经 POST 表单体提交后台兑换 HttpOnly Cookie（不拼入 URL/命令行/日志）
        if one_time_token:
            browser.SetPage(build_post_form_html(url, one_time_token), url)
        else:
            browser.LoadURL(url)
        sizer.Add(browser, 1, wx.EXPAND | wx.ALL, self._spx_calc(10))
        dialog_status = wx.StaticText(panel, label=translate("label_loading_page"))
        sizer.Add(dialog_status, 0, wx.ALIGN_LEFT | wx.ALL, self._spx_calc(10))
        if is_remote:
            api_status = wx.StaticText(panel, label=translate("label_connected_to_backend"))
            sizer.Add(api_status, 0, wx.ALIGN_LEFT | wx.ALL, self._spx_calc(10))
        btn_close = wx.Button(panel, label=translate("button_close"))
        sizer.Add(btn_close, 0, wx.ALIGN_CENTER | wx.ALL, self._spx_calc(10))
        btn_close.Bind(wx.EVT_BUTTON, lambda e: dialog.EndModal(wx.ID_OK))
        panel.SetSizer(sizer)
        dialog.ShowModal()
        dialog.Destroy()