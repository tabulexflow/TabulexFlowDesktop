# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""WebView 平台分发层（RemoteWebpage 显示引擎选择）。

优先级：
1. wx.html2.WebView —— Windows/macOS 默认路径（原生 WebView）
2. pywebview（独立子进程）—— Linux 无 wx.html2 时的回退引擎，
   基于系统 WebKitGTK（4.1/4.0，通过 PyGObject），不引入 C++ 编译依赖
3. 均不可用 —— 返回 False，由调用方弹出错误提示（保持原有降级行为，不崩溃）

线程模型：pywebview 与 wx 同为 GTK3，进程内混用两个 GTK 主循环有冲突风险，
因此 Linux 回退路径一律通过**独立子进程**运行 WebView（tfp_webview_helper），
父进程在等待期间用 wx.Yield 保持界面响应，等价于原有 ShowModal 的模态语义。
"""

import json
import logging
import os
import pathlib
import re
import subprocess
import sys
import time
from urllib.parse import urlparse

from build_mode import BACKEND_HOST

logger = logging.getLogger(__name__)


def is_url_trusted(url, backend_url=None):
    """M-2 加固：WebView 加载 URL 白名单校验。

    同时校验：① 协议 ∈ http/https；② hostname ∈ {默认可信后端域名 或 当前
    backend_url 域名}。拒绝 file:// 等危险协议与任意外部钓鱼域名（后端被攻破/
    MITM 时将恶意 URL 填入 data['url'] 也无法加载到本地 WebView）。
    """
    if not isinstance(url, str) or not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False
    hostname = (parsed.hostname or '').lower()
    trusted = {str(BACKEND_HOST).lower()}
    if backend_url:
        b = urlparse(backend_url)
        if b.hostname:
            trusted.add(b.hostname.lower())
    trusted.discard('')
    return hostname in trusted


def mask_url_query_token(url):
    """对 URL query 中的一次性 token 脱敏（`?token=xxx` / `&token=xxx` → `token=***`），防止敏感值入日志。"""
    if not url or not isinstance(url, str):
        return url
    return re.sub(r'([?&])token=[^&\s]*', r'\1token=***', url)

# 子进程工作目录：项目根目录（tfp_utils 的上一级），保证 `-m tfp_utils.tfp_webview_helper`
# 在源码模式下不受启动目录影响
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

# 延迟导入（函数内 import），避免本模块在子进程中被 import 时初始化 wx 状态
_wx_html2_module = None


def is_wx_html2_available():
    """检测当前环境是否可导入 wx.html2（True 时优先使用原生 WebView 路径）"""
    global _wx_html2_module
    if _wx_html2_module is None:
        try:
            import wx.html2
            _wx_html2_module = wx.html2
        except ImportError:
            _wx_html2_module = False
    return bool(_wx_html2_module)


def is_pywebview_available():
    """检测 pywebview 是否可导入（Linux 回退引擎）"""
    try:
        import webview  # noqa: F401
        return True
    except ImportError:
        return False


def _launch_helper_process(url, token, title, width, height):
    """启动 WebView 辅助子进程，返回可轮询存活状态的对象。

    H-2 加固：一次性 token 不得出现在子进程命令行参数（/proc/<pid>/cmdline 对本机
    所有用户可读）。源码模式经 **stdin**（JSON）传递；打包模式（multiprocessing spawn）
    经 spawn 管道传递（不落 cmdline）。

    - 源码模式：subprocess.Popen([python, -m, tfp_utils.tfp_webview_helper, --stdin])
    - 打包模式：multiprocessing.get_context('spawn') 子进程（共享同一可执行文件，
      不会像 onefile 下 subprocess sys.executable 那样二次解包）
    """
    frozen = bool(getattr(sys, 'frozen', False))
    if not frozen:
        payload = json.dumps({
            "url": url,
            "token": token,
            "title": title,
            "width": int(width),
            "height": int(height),
        }, ensure_ascii=False)
        proc = subprocess.Popen(
            [sys.executable, '-m', 'tfp_utils.tfp_webview_helper', '--stdin'],
            cwd=str(_PROJECT_ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            proc.stdin.write(payload.encode('utf-8'))
            proc.stdin.close()
        except Exception as e:
            logger.error(f"Failed to pass webview payload to helper process: {e}")
        return proc

    import multiprocessing
    ctx = multiprocessing.get_context('spawn')
    from tfp_utils.tfp_webview_helper import run_webview_window
    proc = ctx.Process(
        target=run_webview_window,
        args=(url, token, title, int(width), int(height)),
        daemon=False,
    )
    proc.start()
    return proc


def _wait_helper_process(proc):
    """阻塞等待辅助子进程退出，返回退出码；失败返回 None 并抛 RuntimeError 描述"""
    import wx

    try:
        has_poll = hasattr(proc, 'poll')
        while True:
            if has_poll:
                code = proc.poll()
                if code is not None:
                    return code
            else:
                proc.join(timeout=0.1)
                if not proc.is_alive():
                    return proc.exitcode
            wx.Yield()
            time.sleep(0.05)
    except Exception as e:
        logger.exception(f"Error while waiting for WebView subprocess: {e}")
        raise RuntimeError(str(e)) from e


def show_webview_dialog_fallback(wx_parent, title, url, width, height, one_time_token=None):
    """Linux 无 wx.html2 时的 RemoteWebpage 显示回退路径。

    Args:
        wx_parent: wx 主窗口（用于模态期间禁用/恢复）
        title: 窗口标题
        url: 页面 URL（仅 http/https，内部再次校验；不含一次 token）
        width/height: 窗口尺寸（已做 DPI 缩放）
        one_time_token: 可选一次性认证 token（H-2 加固：不拼入 URL，经 stdin/spawn 管道
                        传递，由 WebView 以 POST 表单体提交后台兑换 Cookie）

    Returns:
        bool: True 正常显示并关闭；False 环境不支持（pywebview 缺失），
              由调用方弹错误提示。
    """
    if not is_pywebview_available():
        logger.error("pywebview unavailable, cannot open the RemoteWebpage tool")
        return False

    # M-2 加固：URL 白名单 = http/https 协议 + 可信后端域名
    # （默认后端域名 或 当前 backend_url 域名；拒绝任意外部钓鱼域名）
    current_backend = None
    try:
        from tfp_auth import auth_manager as _auth_mgr
        current_backend = getattr(_auth_mgr, 'backend_url', None)
    except Exception:
        current_backend = None
    if not is_url_trusted(url, backend_url=current_backend):
        logger.error(f"Refused to load an untrusted URL: {mask_url_query_token(url)}")
        raise ValueError("URL is not allowed")

    import wx
    logger.info(f"Linux fallback WebView starting: {mask_url_query_token(url)}")

    disabled = False
    if wx_parent is not None and isinstance(wx_parent, wx.Window):
        try:
            wx_parent.Disable()
            disabled = True
        except Exception as e:
            logger.warning(f"Failed to disable the main window: {e}")

    try:
        try:
            proc = _launch_helper_process(url, one_time_token, title, width, height)
        except Exception as e:
            logger.error(f"Failed to start the WebView helper process: {e}")
            raise RuntimeError(str(e)) from e

        try:
            code = _wait_helper_process(proc)
            logger.info(f"WebView helper process exited, exitcode={code}")
            if code not in (0, None):
                return False
            return True
        finally:
            if disabled:
                try:
                    wx_parent.Enable()
                except Exception as e:
                    logger.warning(f"Failed to re-enable the main window: {e}")
    finally:
        if disabled:
            try:
                wx_parent.Enable()
            except Exception as e:
                logger.warning(f"Failed to re-enable the main window: {e}")
