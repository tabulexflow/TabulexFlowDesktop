# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""pywebview 独立 WebView 辅助进程（Linux RemoteWebpage 回退引擎）。

背景：Linux 上 Debian/Ubuntu 的 python3-wxgtk4.0 无 wx.html2 子模块，
且 Ubuntu 24.04 已移除 webkit2gtk-4.0（wxPython html2 依赖的 API），
因此 Linux 打包的前端无法用 wx.html2.WebView 显示 RemoteWebpage 工具。

本模块提供与 wx.html2 无关的 WebView 实现：基于 pywebview（GTK WebKit2 4.1/4.0，
通过 PyGObject 调用系统 WebKitGTK），由主程序以独立子进程方式启动，
避免与 wx 主进程的 GTK 主循环冲突。

本模块刻意不 import wx：可作为 ``python -m tfp_utils.tfp_webview_helper <url> <title> [w] [h]``
运行，也可作为 multiprocessing 子进程的目标函数运行（打包产物模式）。
"""

import html
import http.server
import json
import sys
import threading
import traceback
from urllib.parse import urlparse

SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 1
PYWEBVIEW_MISSING_EXIT_CODE = 2
WEBVIEW_ERROR_EXIT_CODE = 3

_DEFAULT_WIDTH = 800
_DEFAULT_HEIGHT = 600

# M-2 加固：默认可信后端域名（与 build_mode 同源——生产为 tabulexflow.com，
# 开发/本地测试构建为 127.0.0.1）。WebView 只允许加载该域名下的 http/https 页面，
# 防止本地任意进程把 helper 当作"无地址栏钓鱼窗口"使用。
try:
    from build_mode import BACKEND_HOST
    _TRUSTED_HOSTS = {str(BACKEND_HOST)}
except Exception:
    _TRUSTED_HOSTS = set()


def is_url_allowed(url):
    """URL 白名单校验（M-2 加固）。

    同时校验：① 协议 ∈ http/https；② hostname ∈ {默认可信后端域名}。
    拒绝 file:// 等危险协议与任意外部钓鱼域名。
    """
    if not isinstance(url, str) or not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False
    hostname = (parsed.hostname or '').lower()
    return hostname in _TRUSTED_HOSTS


def build_post_form_html(action_url, token):
    """构造一次性 token 的 POST 表单交换页（H-2 加固）。

    WebView 以本地 HTML 自动提交 POST（token 在表单体，不落 URL/命令行/日志），
    后端兑换成功后 302 到页面并写入 HttpOnly Cookie。
    """
    action = html.escape(action_url, quote=True)
    token_esc = html.escape(token or '', quote=True)
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<style>html,body{margin:0;padding:0;height:100%;display:flex;'
        'align-items:center;justify-content:center;background:#f5f6f8;'
        'font-family:sans-serif;color:#666;}p{margin:0;}</style>'
        '</head><body><p>正在加载页面… Please wait</p>'
        f'<form id="f" method="POST" action="{action}">'
        f'<input type="hidden" name="token" value="{token_esc}">'
        '</form>'
        '<script>document.getElementById("f").submit();</script>'
        '</body></html>'
    )


class _LocalFormServer:
    """本地回环一次性表单服务（127.0.0.1 随机端口，承载 token 兑换 POST 表单页）。

    背景：pywebview 以 load_html 加载表单页时，页面来源为不透明 origin
    （about:blank），WebKitGTK 将其对后端的表单 POST 视为跨站导航，并拒存
    跨站响应中的 SameSite Cookie（曾用 Strict 直接导致兑换成功但 302 后
    GET 无 Cookie → 页面渲染 401 JSON）。改由本地 HTTP 服务承载表单页：
    SameSite 的 site 比较忽略端口，127.0.0.1:<随机端口> 与本地后端
    （127.0.0.1:8080）同 site，表单 POST 为同站点导航，Set-Cookie 可正常存储。
    后端为远程域名（生产 https://tabulexflow.com）时仍属跨站，由后端将兑换
    Cookie 放宽为 samesite='Lax' 兜底。

    安全边界：仅绑定 127.0.0.1；token 为一次性、60 秒 TTL；表单页含 token，
    响应不写任何访问日志。
    """

    def __init__(self, action_url, token):
        form_html = build_post_form_html(action_url, token)

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = form_html.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass  # 静默：表单页内嵌一次性 token，不写入任何日志

        self._httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def form_url(self):
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}/"

    def start(self):
        self._thread.start()

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()


def run_webview_window(url, token, title, width=_DEFAULT_WIDTH, height=_DEFAULT_HEIGHT):
    """启动 pywebview 窗口并阻塞直到窗口关闭（多进程目标函数 / 命令行共用）。

    Args:
        url: 页面 URL 或（token 存在时）POST 表单提交目标（仅允许 http/https）
        token: 可选一次性认证 token（H-2 加固：经 POST 表单体提交，不拼 URL）
        title: 窗口标题
        width: 窗口宽度（默认 800）
        height: 窗口高度（默认 600）

    Returns:
        int 退出码：0 正常退出；2 pywebview 不可用；3 加载/运行时错误
    """
    if not is_url_allowed(url):
        print(f"REFUSED_URL: {url}", file=sys.stderr)
        return WEBVIEW_ERROR_EXIT_CODE

    try:
        import webview
    except ImportError as e:
        print(f"PYWEBVIEW_MISSING: {e}", file=sys.stderr)
        return PYWEBVIEW_MISSING_EXIT_CODE

    try:
        if token:
            # H-2 加固：token 经 POST 表单体提交（不拼 URL/命令行/日志）。
            # 表单页由本地同站点服务承载（直接 load_html 的表单页来自不透明 origin，
            # WebKitGTK 拒存跨站响应的 SameSite Cookie，见 _LocalFormServer 类注释）。
            form_server = _LocalFormServer(url, token)
            form_server.start()
            try:
                webview.create_window(title, form_server.form_url,
                                      width=int(width), height=int(height), resizable=True)
                webview.start()
            finally:
                form_server.stop()
        else:
            webview.create_window(title, url, width=int(width), height=int(height), resizable=True)
            webview.start()
        return SUCCESS_EXIT_CODE
    except Exception as e:
        print(f"WEBVIEW_ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return WEBVIEW_ERROR_EXIT_CODE


def main(argv=None):
    """命令行入口。

    M-2 加固：只接受 --stdin（JSON {"url","token","title","width","height"}），
    **不再支持位置参数** `<url> <title> ...`——防止本地任意进程把本入口当作
    "自定义标题 + 无地址栏" 的任意网页展示窗口（钓鱼）。URL 域名另受
    `is_url_allowed()` 白名单限制（仅可信后端域名）。
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] != '--stdin':
        print("usage: tfp_webview_helper --stdin  (URL can only be passed via stdin JSON)", file=sys.stderr)
        return USAGE_EXIT_CODE
    try:
        payload = json.load(sys.stdin)
    except Exception as e:
        print(f"STDIN_JSON_ERROR: {e}", file=sys.stderr)
        return USAGE_EXIT_CODE
    url = payload.get('url') or ''
    token = payload.get('token') or None
    title = payload.get('title') or ''
    width = int(payload.get('width') or _DEFAULT_WIDTH)
    height = int(payload.get('height') or _DEFAULT_HEIGHT)
    return run_webview_window(url, token, title, width, height)


if __name__ == '__main__':
    sys.exit(main())
