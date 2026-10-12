# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import sys
import re
import logging
import ctypes

def _set_dpi_awareness():
    # 显式 Windows 分支——ctypes.windll 等 Win32
    # API 在 Linux/macOS 不存在，直接以平台判断代替两层"静默 except"，消除
    # "看起来像漏洞"的可读性债务；Linux 未设置 DPI 感知（wxGTK 自行处理缩放）
    if sys.platform != 'win32':
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

_set_dpi_awareness()

from tfp_utils.tfp_logger import setup_main_logger, get_log_dir
from tfp_utils.tfp_api_paths import API_V1_PREFIX
from tfp_utils.tfp_version import version_tuple
logger = setup_main_logger()

# ============================================
# 多入口配置：打包时根据此配置生成不同的exe
# DEFAULT_TOOL: 默认打开的工具，空值或"main"表示主页，其他值为builtin工具名如"TabulexFileOperator"
# DEFAULT_LANG: 默认语言，可选值: en, zh, fr, ru, es, ar
# ============================================
DEFAULT_TOOL = ""
DEFAULT_LANG = "en"
# ============================================

# ============================================
# 后端服务配置：唯一来源为 build_mode.py
# BACKEND_HOST / BACKEND_PORT 在此仅作再导出，供 tfp_backend_config.py /
# tfp_auth_manager.py 等以 `main.BACKEND_HOST` 方式读取
# 生产/开发模式判断统一由 build_mode 提供
# ============================================
from build_mode import (
    IS_PRODUCTION_BUILD,
    IS_LOCAL_TEST_BUILD,
    IS_OSS_COMMUNITY_BUILD,
    is_dev_mode,
    BACKEND_HOST,
    BACKEND_PORT,
    BACKEND_BASE_URL,
    FRONTEND_DOWNLOAD_PAGE_URL,
)


# ============================================
# 可写运行时根目录（工具目录/用户配置/配置目录的上级）统一由
# tfp_utils.tfp_main_utils.get_runtime_base_dir() 提供，主程序与菜单处理器共用同一来源：
# - 开发（源码运行）：前端工程根目录
# - 打包：可执行文件所在目录（可写时，便于便携）
# - 只读挂载（AppImage/.deb 系统目录）：回退每用户数据目录 <XDG_DATA_HOME>/TabulexFlow
# ============================================

# 使用绝对路径，导入调试工具
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tfp_utils.tfp_main_utils import setup_debug, get_base_path, get_resource_path, get_runtime_base_dir
from tfp_utils.tfp_main_utils import output_system_info, check_resource_structure

# 设置调试环境
DEVELOPMENT_MODE = is_dev_mode()
if DEVELOPMENT_MODE: setup_debug()
logger.info(f"Dev mode status: DEVELOPMENT_MODE={DEVELOPMENT_MODE}")
# 检查资源结构
output_system_info()
check_resource_structure()

# 然后继续原有的导入
import gc
import io
import struct
import time, datetime
import json
import shutil
import requests
import importlib
import zipfile
import traceback
import threading
import subprocess
import wx
import wx.grid
import wx.adv
from tfp_utils.tfp_i18n_manager import translate, i18n
try:
    import wx.html2
except ImportError:
    wx.html2 = None
from tfp_utils.tfp_backend_config import get_backend_manager

from tfp_auth import auth_manager, permission_manager
from tfp_auth import TFP_LoginRegisterDialog, TFP_LoginRequiredDialog, TFP_PermissionRequiredDialog
from tfp_auth.tfp_auth_manager import mask_display_name
from tfp_mixins import TFP_ToolIPCMixin, TFP_ToolRunnerMixin
logger.info("All modules imported successfully")

_APP_BASE_TITLE = "TabulexFlow"  # 品牌名兜底值（翻译缺失时使用）

def get_app_base_title():
    """获取本地化后的品牌标题（随界面语言变化，如中文为"灵表矩阵"）"""
    title = translate("app_title")
    # translate 在缺失键时返回键名本身，此时回退到品牌英文名兜底
    return title if title and title != "app_title" else _APP_BASE_TITLE

def get_app_title():
    """获取应用标题，本地测试构建（IS_LOCAL_TEST_BUILD）时追加 [DEV MODE]"""
    base_title = get_app_base_title() if (not DEFAULT_TOOL or DEFAULT_TOOL == "main") else DEFAULT_TOOL
    if IS_LOCAL_TEST_BUILD:
        base_title += " [DEV MODE]"
    return base_title

class TFP_PlatformApp(wx.App):
    def OnInit(self):
        try:
            # 屏蔽 wxWidgets 的 Debug 级日志（如 GTK 文本控件焦点提示），
            # 避免开源后这些噪音让贡献者困惑；不影响应用自身的 logging 日志。
            wx.Log.SetLogLevel(wx.LOG_Warning)
            app_title = get_app_title()
            self.frame = TFP_MainFrame(None, title=app_title)
            self.frame.Show()
            # 本地测试构建：仅在日志中标记（明文 http://127.0.0.1:8080，仅限内部开发环境，
            # 防误部署/误发给终端用户）；不弹窗——窗口标题已含 [DEV MODE] 标记
            if IS_LOCAL_TEST_BUILD:
                logger.warning("LOCAL TEST BUILD detected: backend at http://127.0.0.1:8080, not for end users")
            return True
        except Exception:
            import io, os, datetime
            _msg = "".join(__import__('traceback').format_exc())
            try:
                print("=" * 60, file=sys.stderr)
                print("TFP_MainFrame initialization failed (exception caught in OnInit):", file=sys.stderr)
                print(_msg, file=sys.stderr)
                print("=" * 60, file=sys.stderr)
                _err = os.path.join(str(self.base_path), "frontend_oninit_error.log") if hasattr(self, 'base_path') else os.path.join(os.getcwd(), "frontend_oninit_error.log")
                with open(_err, 'a', encoding='utf-8') as _f:
                    _f.write("[" + datetime.datetime.now().isoformat() + "]\n" + _msg + "\n")
            except Exception:
                pass
            return False

    def OnExceptionInMainLoop(self):
        import traceback
        logger.error("Uncaught wxPython main-loop exception:\n%s", traceback.format_exc())
        try:
            import wx
            wx.MessageBox(
                "程序发生了一个意外错误，请查看日志获取详细信息。\n如问题持续，请联系技术支持。",
                "程序错误",
                wx.OK | wx.ICON_ERROR
            )
        except Exception:
            pass
        return True

def _load_ico_bitmap(icon_path):
    """加载 .ico 图标，优先提取最大尺寸的 PNG 帧解码。

    Linux python3-wxgtk4.0(wxPython 4.2.1 gtk3) 的 wx.Bitmap(path, BITMAP_TYPE_ICO)
    对 ICO 内 16~96px 的 BMP 32bpp(带alpha) 帧解码错误（顶半部被错误解码为透明/黑，
    导致主界面子工具卡片图标显示为"上侧空白、下侧噪点"）；而 128/256px 的 PNG 帧解码正确。
    因此这里手动解析 ICO 目录，提取最大 PNG 帧用 wx.Image 从内存流加载；
    若 ICO 无 PNG 帧，则回退到 wx 默认 ICO 解码。
    """
    try:
        with open(str(icon_path), "rb") as f:
            data = f.read()
        if len(data) < 6:
            return None
        reserved, typ, count = struct.unpack("<HHH", data[:6])
        if typ != 1 or count <= 0:
            return None
        best = None  # (size, img_off, width, height)
        for i in range(count):
            off = 6 + i * 16
            if off + 16 > len(data):
                break
            w, h, colors, res, planes, bpp, size, img_off = struct.unpack("<BBBBHHII", data[off:off + 16])
            w = 256 if w == 0 else w
            h = 256 if h == 0 else h
            if img_off + 8 > len(data):
                continue
            if data[img_off:img_off + 8] == b"\x89PNG\r\n\x1a\n":
                if best is None or (w * h) > (best[2] * best[3]):
                    best = (size, img_off, w, h)
        if best is not None:
            size, img_off, w, h = best
            png_bytes = data[img_off:img_off + size]
            image = wx.Image(io.BytesIO(png_bytes), wx.BITMAP_TYPE_PNG)
            if image.IsOk():
                return wx.Bitmap(image)
    except Exception as e:
        logger.warning("Failed to parse ICO icon %s: %s", icon_path, e)
    # 回退：wx 默认 ICO 解码
    try:
        bitmap = wx.Bitmap(str(icon_path), wx.BITMAP_TYPE_ICO)
        if bitmap.IsOk():
            return bitmap
    except Exception:
        pass
    return None


class TFP_MainFrame(TFP_ToolRunnerMixin, TFP_ToolIPCMixin, wx.Frame):
    ID_SEARCH_FOCUS = wx.NewIdRef()

    def __init__(self, parent, title):
        self.default_tool = DEFAULT_TOOL
        self.default_lang = DEFAULT_LANG
        self.base_path = get_base_path()
        display = wx.Display(0)
        dpi = display.GetPPI()
        if sys.platform == 'win32':
            # Windows（per-monitor DPI aware，见模块顶部 _set_dpi_awareness）：
            # wx 使用物理像素，需按 PPI/96 手动缩放。
            self.TFP_DPI_SCALE_FACTOR = dpi.x / 96.0
        else:
            # Linux(wxGTK)/macOS(Cocoa)：工具包已按系统 DPI 自动缩放，wx 坐标为逻辑像素；
            # 若再用 GetPPI()/96 缩放会造成双重放大——高分屏下主窗口占满整屏、
            # 字体过大导致工具卡片换行与宽度错乱。
            self.TFP_DPI_SCALE_FACTOR = 1.0
        if self.TFP_DPI_SCALE_FACTOR < 1.0:
            self.TFP_DPI_SCALE_FACTOR = 1.0
        logger.info("DPI scale factor: %.2f (%ddpi)", self.TFP_DPI_SCALE_FACTOR, dpi.x)
        logger.info(f"[DPI_DIAG] Main: TFP_DPI_SCALE_FACTOR={self.TFP_DPI_SCALE_FACTOR}, wx.Display.GetPPI()={dpi.x}")
        super(TFP_MainFrame, self).__init__(parent, title=title, size=(self.spx_calc(720), self.spx_calc(450)))
        self.SetTitle(title)
        # 设置程序图标
        self.setup_icon()
        self.frontend_version = self._read_frontend_version_from_file()
        if IS_OSS_COMMUNITY_BUILD:
            # 社区发布版（OSS）不启用后端：不发起后端探测、不启用登录/远程功能
            self.backend_url = ""
            logger.info("OSS Community Edition startup mode: no backend connection, only built-in (BuiltinProgram) tools provided")
        else:
            # 使用BackendConfigManager获取后端URL（支持多URL自动检测）
            backend_manager = get_backend_manager()
            self.backend_url = backend_manager.get_available_url()
            logger.info("Backend service URL: %s", self.backend_url)

            if not auth_manager.set_backend_url(self.backend_url):
                logger.error("Backend URL rejected by security policy; falling back to default URL: %s", BACKEND_BASE_URL)
                self.backend_url = BACKEND_BASE_URL
                if not auth_manager.set_backend_url(self.backend_url):
                    logger.critical("Unable to set any valid backend URL; the application may not work properly")
                    # 后端不可达时（如开源预览阶段未部署后端），不弹窗——这是正常状态
                    try:
                        _backend_ok = get_backend_manager().is_backend_reachable()
                    except Exception:
                        _backend_ok = False
                    if _backend_ok:
                        wx.MessageBox(
                            "无法连接到后端服务，请检查网络连接或联系管理员。",
                            "连接失败",
                            wx.OK | wx.ICON_ERROR
                        )
            auth_manager.add_auth_change_callback(self._on_auth_state_changed)
        
        self.builtin_tools = {}
        self.non_builtin_tools = {}
        self.last_modified = "1970-01-01T00:00:00Z"
        self.backend_tools_cache = {}
        self._tools_data_lock = threading.Lock()
        # 有版本更新的工具ident集合（用于在工具卡片上显示升级标签）
        self._tools_with_update = set()
        self.open_tool_windows = {}
        # 嵌入式工具管理：{tool_ident: {'panel': panel, 'instance': tool_instance}}
        self.embedded_tools = {}
        # 窗口尺寸状态管理：记录每个工具的窗口大小
        self.window_sizes = {}  # {tool_ident: (width, height)}
        # 窗口菜单相关
        self.window_menu = None
        self.window_menu_tools = {}
        # 工具方块锁定标志，防止重复点击
        self.tools_locked = False
        # 正在打开/加载中的工具标识（用于状态栏/卡片提示，就绪或失败后清除）
        self._launching_tool_ident = None
        # 保存所有工具方块的引用，用于锁定/解锁
        self.tool_panels = []
        # 修正路径获取 - 使用可写运行时根目录下的 tools_fe 子目录
        # （AppImage 仅读挂载 / 系统目录安装时，会自动退回用户数据目录，见 get_runtime_base_dir）
        self._runtime_base_dir = get_runtime_base_dir()
        self.local_tools_dir = self._runtime_base_dir / "tools_fe"
        # 确保 tools_fe 目录存在且有读写权限
        try:
            self.local_tools_dir.mkdir(parents=True, exist_ok=True)
            # 测试写入权限
            test_file = self.local_tools_dir / "test_write.tmp"
            test_file.write_text("test")
            test_file.unlink()
            logger.info("Tools directory created successfully: %s", self.local_tools_dir)
        except Exception as e:
            error_msg = f"无法创建或写入工具目录: {self.local_tools_dir}\n错误: {str(e)}\n\n请确保程序有足够的权限，或移动程序到有读写权限的目录。"
            logger.error(error_msg)
            wx.MessageBox(error_msg, "权限错误", wx.OK | wx.ICON_ERROR)
            # 如果无法创建目录，可能无法正常使用下载工具的功能
        # 用户配置目录（与 tools_fe 平级）
        self.user_setting_dir = self._runtime_base_dir / "user_setting"
        self.user_setting_dir.mkdir(parents=True, exist_ok=True)
        # 配置目录也使用相同逻辑
        self.config_dir = self._runtime_base_dir / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        logger.info("=" * 60 + "TabulexFlow path info" + "=" * 60)
        logger.info("Base path (resource path): %s", self.base_path)
        logger.info("Tools dir (tool directory): %s", self.local_tools_dir)
        logger.info("Config dir (config directory): %s", self.config_dir)
        # 版本矩阵（T3.1）：前端版本 + tfp_utils 侧 SDK 派生版本。
        # frontend_version 当前仍由下方 __init__ 硬编码（T1 将改为 config/version.txt 单一来源）；
        # 子工具 EXE 内嵌的 tfp_toolkit SDK 版本在其 IPC 认证时上报（见 tfp_tool_ipc_mixin）。
        try:
            from tfp_utils import __version__ as _tfp_utils_sdk_version
        except ImportError:  # pragma: no cover - tfp_utils 缺失属装配错误，不应静默失败
            _tfp_utils_sdk_version = "unknown"
        logger.info("Version matrix: frontend_version=%s, tfp_utils_sdk_version=%s",
                    self.frontend_version, _tfp_utils_sdk_version)
        logger.debug("Tools dir exists: %s", self.local_tools_dir.exists())
        logger.debug("Config dir exists: %s", self.config_dir.exists())
        tool_categories = ["tools_remote_program" ]
        for category in tool_categories:
            category_dir = self.local_tools_dir / category
            logger.debug("%s directory: %s", category, category_dir)
            logger.debug("%s exists: %s", category, category_dir.exists())
            if category_dir.exists():
                tools = [item.name for item in category_dir.iterdir() if item.is_dir()]
                logger.debug("%s contains tools: %s", category, tools)
        logger.info("=" * 60)
        # 绑定窗口事件
        self.Bind(wx.EVT_ICONIZE, self.on_minimize)
        self.Bind(wx.EVT_CLOSE, self.on_exit)
        self.Bind(wx.EVT_ACTIVATE, self._on_window_activate)
        self.init_ui()
        wx.CallAfter(self.load_all_tools)

    def spx_calc(self, value):
        """Scale pixels by TFP_DPI_SCALE_FACTOR. 对固定像素值进行DPI缩放。"""
        if value == -1:
            return -1
        return int(value * self.TFP_DPI_SCALE_FACTOR)

    """初始化用户界面"""
    def init_ui(self):
        panel = wx.Panel(self)
        self.main_panel = panel
        # 根据DPI调整字体大小
        self.adjust_fonts_for_hidpi()
        # 加载语言设置
        self.load_language_setting()
        # 语言设置加载后，按用户选择的语言刷新窗口标题
        # （OnInit 阶段 i18n 可能尚未读取运行时 config 目录中的语言设置）
        self.SetTitle(get_app_title())
        # 创建菜单栏
        self.create_menu_bar()
        # 创建主布局
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        # 创建主内容区域容器（用于切换主页和工具）
        self.content_container = wx.Panel(panel)
        self.content_sizer = wx.BoxSizer(wx.VERTICAL)
        self.content_container.SetSizer(self.content_sizer)
        self.main_sizer.Add(self.content_container, 1, wx.EXPAND)
        # 创建主页面板
        self.home_panel = wx.Panel(self.content_container)
        self.home_sizer = wx.BoxSizer(wx.VERTICAL)
        self.home_panel.SetSizer(self.home_sizer)
        # ===== 顶部搜索栏行：收藏按钮 + 搜索框 + 搜索按钮 + 排序下拉 =====
        # 统一行高 = 单行文本控件自然高度 × 1.5（文字大小保持不变）。实现约束：
        # (a) 原生单行 wx.TextCtrl 被拉高后文字会顶对齐（非垂直居中），故搜索框采用
        #     “无边框文本框 + 垂直居中于带边框面板”（内层用水平 BoxSizer 的
        #     ALIGN_CENTER_VERTICAL 才能在其高度内上下居中）；
        # (b) 原生 wx.Choice 高度无法被 SetMinSize 拉高，故排序下拉改用“按钮 + 弹出菜单”
        #     （与收藏按钮一致），从而可与其它控件统一高度。
        search_bar_panel = wx.Panel(self.home_panel)
        search_bar_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 统一行高 = 标准单行控件（带边框文本框）在当前字体下的自然高度 × 1.5（文字大小不变）。
        # 注意：(1) 不能用下面无边框的 search_ctrl 求基准（无边框自然高度偏小）；
        #       (2) 原生 wx.TextCtrl.GetBestSize() 的高度依赖平台主题——GTK(Linux) 会给输入框
        #           附加远大于 Windows 的额外内边距，使该自然高度明显偏大，×1.5 后工具栏在
        #           Linux 上比 Windows 高约 1.5 倍。故以与平台无关的字体文本高度推算基准高度
        #           并与原生值取较小者：Windows 保持原有表现，Linux 被压回一致的行高。
        _ctrl_vpad = self.spx_calc(8)  # 单行控件垂直内边距（边框 + 内部留白）的估算值
        _ref_ctrl = wx.TextCtrl(search_bar_panel, value="", style=wx.TE_PROCESS_ENTER)
        _font_base_h = _ref_ctrl.GetTextExtent("Ag")[1] + _ctrl_vpad
        row_h = int(min(_ref_ctrl.GetBestSize().height, _font_base_h) * 1.5)
        _ref_ctrl.Destroy()

        # 收藏下拉按钮（文字 + 右侧下拉箭头）
        self.fav_button = wx.Button(search_bar_panel, label=translate("label_favorite_tools") + " \u25BC", size=(self.spx_calc(110), row_h))
        self.fav_button.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        self.fav_button.Bind(wx.EVT_BUTTON, self.on_fav_button_click)

        # 搜索框：无边框 wx.TextCtrl 垂直居中于带边框面板
        self.search_box_panel = wx.Panel(search_bar_panel, style=wx.BORDER_SIMPLE)
        self.search_box_panel.SetBackgroundColour(wx.WHITE)
        _sbox_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.search_ctrl = wx.TextCtrl(self.search_box_panel, value="", style=wx.TE_PROCESS_ENTER | wx.BORDER_NONE)
        self.search_ctrl.SetHint(translate("hint_search_tools"))
        self.search_ctrl.Bind(wx.EVT_TEXT, self.on_search_text_changed)
        self.search_ctrl.Bind(wx.EVT_KEY_DOWN, self.on_search_key_down)
        _sbox_sizer.Add(self.search_ctrl, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(4))
        self.search_box_panel.SetSizer(_sbox_sizer)
        # 点击文本框上下留白处也聚焦到搜索框
        self.search_box_panel.Bind(wx.EVT_LEFT_DOWN, lambda e: self.search_ctrl.SetFocus())

        # 搜索按钮：使用系统标准搜索图标
        # （原 emoji "\U0001F50D" 在 wx.Button 的字体下无法渲染，显示为空白按钮）
        _search_bmp = wx.ArtProvider.GetBitmap(wx.ART_FIND, wx.ART_BUTTON, wx.Size(self.spx_calc(16), self.spx_calc(16)))
        self.search_icon_btn = wx.BitmapButton(search_bar_panel, bitmap=_search_bmp, size=(row_h, row_h))
        self.search_icon_btn.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        self.search_icon_btn.SetToolTip(translate("hint_search_tools"))

        # 排序下拉：按钮 + 弹出菜单（默认/最近使用/最多人用(OSS隐藏)/名称/类型分组/免费本地优先）
        self._sort_mode_list = []
        def _add_sort_item(mode, key):
            self._sort_mode_list.append(mode)
            return translate(key)
        self._sort_labels = [_add_sort_item('default', 'label_sort_default'),
                             _add_sort_item('recent', 'label_sort_recent')]
        if not IS_OSS_COMMUNITY_BUILD:
            self._sort_labels.append(_add_sort_item('popular', 'label_sort_popular'))
        self._sort_labels += [_add_sort_item('name', 'label_sort_name'),
                              _add_sort_item('type', 'label_sort_type'),
                              _add_sort_item('free_local', 'label_sort_free_local')]
        self._sort_index = 0
        _sort_w = max(self.GetTextExtent(lbl + " \u25BC")[0] for lbl in self._sort_labels) + self.spx_calc(20)
        self.sort_button = wx.Button(search_bar_panel, label=self._sort_labels[0] + " \u25BC", size=(_sort_w, row_h))
        self.sort_button.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        self.sort_button.SetToolTip(translate("hint_sort_tools"))
        self.sort_button.Bind(wx.EVT_BUTTON, self.on_sort_button_click)

        # 按显示顺序加入布局
        search_bar_sizer.Add(self.fav_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(8))
        self.search_box_panel.SetMinSize((self.spx_calc(300), row_h))
        search_bar_sizer.Add(self.search_box_panel, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(4))
        search_bar_sizer.Add(self.search_icon_btn, 0, wx.ALIGN_CENTER_VERTICAL)
        search_bar_sizer.Add(self.sort_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(6))
        search_bar_panel.SetSizer(search_bar_sizer)
        self.home_sizer.Add(search_bar_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, self.spx_calc(10))
        # ===== 全部工具Grid区域 =====
        self.tools_scroll = wx.ScrolledWindow(self.home_panel, style=wx.VSCROLL)
        self.tools_scroll.SetScrollRate(0, self.spx_calc(10))
        # 显式 flags=0：禁用 wx.WrapSizer 默认的 EXTEND_LAST_ON_EACH_LINE
        # （WRAPSIZER_DEFAULT_FLAGS 含该位），否则每行最后一张卡片会被拉伸填满
        # 剩余宽度，导致卡片宽度不一致、单独成行的卡片占满整行。
        # 规范要求卡片固定为 154×121（逻辑像素），故保持固定宽度。
        self.tools_grid_sizer = wx.WrapSizer(orient=wx.HORIZONTAL, flags=0)
        tools_inner_panel = wx.Panel(self.tools_scroll)
        tools_inner_panel.SetSizer(self.tools_grid_sizer)
        scroll_sizer = wx.BoxSizer(wx.VERTICAL)
        scroll_sizer.Add(tools_inner_panel, 1, wx.EXPAND)
        self.tools_scroll.SetSizer(scroll_sizer)
        self.tools_inner_panel = tools_inner_panel
        # 空状态面板（搜索无结果时显示）
        self.empty_state_panel = wx.Panel(self.tools_scroll)
        self.empty_state_panel.SetBackgroundColour(wx.WHITE)
        empty_sizer = wx.BoxSizer(wx.VERTICAL)
        empty_icon = wx.StaticText(self.empty_state_panel, label="\U0001F50D", style=wx.ALIGN_CENTER)
        empty_icon.SetFont(wx.Font(self.spx_calc(32), wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        empty_sizer.Add(empty_icon, 0, wx.ALIGN_CENTER | wx.TOP, self.spx_calc(30))
        empty_text = wx.StaticText(self.empty_state_panel, label=translate("label_no_search_results"), style=wx.ALIGN_CENTER)
        empty_text.SetFont(wx.Font(self.spx_calc(10), wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        empty_text.SetForegroundColour(wx.Colour(150, 150, 150))
        empty_sizer.Add(empty_text, 0, wx.ALIGN_CENTER | wx.TOP, self.spx_calc(8))
        empty_hint = wx.StaticText(self.empty_state_panel, label=translate("label_try_other_keywords"), style=wx.ALIGN_CENTER)
        empty_hint.SetFont(wx.Font(self.spx_calc(9), wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        empty_hint.SetForegroundColour(wx.Colour(180, 180, 180))
        empty_sizer.Add(empty_hint, 0, wx.ALIGN_CENTER | wx.TOP, self.spx_calc(4))
        self.empty_state_panel.SetSizer(empty_sizer)
        self.empty_state_panel.Hide()
        scroll_sizer.Add(self.empty_state_panel, 1, wx.EXPAND)
        self.home_sizer.AddSpacer(self.spx_calc(12))
        self.home_sizer.Add(self.tools_scroll, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self.spx_calc(5))
        # 将主页面板添加到内容容器
        self.content_sizer.Add(self.home_panel, 1, wx.EXPAND)
        # 状态栏
        self.status_bar = self.CreateStatusBar(2)
        self.status_bar.SetStatusText(translate("status_ready"), 0)
        self.status_bar.SetStatusText(translate("status_initializing"), 1)
        panel.SetSizer(self.main_sizer)
        # 加载收藏数据（OSS 社区版离线可用：未登录时读本地匿名收藏文件；
        # 已登录用户随后经 _on_auth_changed_sync_favorites 从后端下载覆盖）
        self.favorites = self._load_favorites()
        self._fav_dirty = False  # 标记是否有未同步到后端的收藏变更
        # 置顶工具（ident 有序列表，前面为更晚置顶的工具），本地持久化、无需登录即可使用
        self.pinned = self._load_pinned()
        # 工具卡片排序模式('default'/'recent'/'popular'/'name'/'type'/'free_local')，默认=按tool_sort_order升序
        self.sort_mode = 'default'
        # 最近使用时间记录（ident -> ISO时间戳），本地持久化
        self.recent_usage = self._load_recent_usage()
        # 后端全局工具热度缓存（ident -> 使用次数），仅在线版使用
        self.popularity_cache = {}
        # 当前被聚焦（键盘焦点）的工具卡片，None表示没有卡片获得焦点
        self._focused_panel = None
        # 顶部固定控件获得焦点时，清除卡片聚焦状态，避免回车误触发打开工具
        self.fav_button.Bind(wx.EVT_SET_FOCUS, self._on_home_control_focus)
        self.search_ctrl.Bind(wx.EVT_SET_FOCUS, self._on_home_control_focus)
        self.search_icon_btn.Bind(wx.EVT_SET_FOCUS, self._on_home_control_focus)
        self.sort_button.Bind(wx.EVT_SET_FOCUS, self._on_home_control_focus)
        # 按钮上直接处理Tab，确保焦点导航在不同平台都可靠生效
        self.fav_button.Bind(wx.EVT_KEY_DOWN, self._on_control_key_down)
        self.search_icon_btn.Bind(wx.EVT_KEY_DOWN, self._on_control_key_down)
        self.sort_button.Bind(wx.EVT_KEY_DOWN, self._on_control_key_down)
        self._update_fav_button_state()
        # 启动时如果已登录，主动同步收藏（auth回调在init_ui之前已触发，此时UI控件还未创建）
        if auth_manager.is_user_logged_in():
            self._on_auth_changed_sync_favorites()
        self.Centre()
        self.Layout()
        # 主界面启动后不聚焦任何控件（焦点置于窗口本身，避免搜索框默认被激活），
        # 需等工具列表加载完成后设置，见 load_all_tools() 中调用的 _clear_home_default_focus()

    """创建菜单栏"""
    def create_menu_bar(self):
        menubar = wx.MenuBar()
        # 文件菜单
        file_menu = wx.Menu()
        self._main_refresh_item = file_menu.Append(wx.ID_ANY, translate("menu_refresh_tools") + "\tF5", translate("menu_refresh_tools_tip"))
        self._main_clear_cache_item = file_menu.Append(wx.ID_ANY, translate("menu_clear_cache"), translate("menu_clear_cache_tip"))
        self._main_close_tools_item = file_menu.Append(wx.ID_ANY, translate("menu_close_all_tools"), translate("menu_close_all_tools_tip"))
        file_menu.AppendSeparator()
        self._main_check_update_item = file_menu.Append(wx.ID_ANY, translate("menu_check_update"), translate("menu_check_update_tip"))
        file_menu.AppendSeparator()
        self._main_exit_item = file_menu.Append(wx.ID_EXIT, translate("menu_exit") + "\tCtrl+Q", translate("menu_exit_tip"))
        
        self.user_menu = wx.Menu()
        self.login_item = self.user_menu.Append(wx.ID_ANY, translate("menu_login"), translate("menu_login_tip"))
        self.user_menu.AppendSeparator()
        self.user_info_item = self.user_menu.Append(wx.ID_ANY, translate("menu_user_info"), translate("menu_user_info_tip"))
        self.user_info_item.Enable(False)
        self.join_company_item = self.user_menu.Append(wx.ID_ANY, translate("menu_join_company"), translate("menu_join_company_tip"))
        self.order_tools_item = self.user_menu.Append(wx.ID_ANY, translate("menu_order_tools"), translate("menu_order_tools_tip"))
        self.feedback_item = self.user_menu.Append(wx.ID_ANY, translate("menu_feedback"), translate("menu_feedback_tip"))
        
        self.window_menu = wx.Menu()
        self.home_menu_item = self.window_menu.Append(wx.ID_ANY, translate("menu_home") + "\tCtrl+H", translate("menu_home_tip"))
        self.window_menu.AppendSeparator()
        
        settings_menu = wx.Menu()
        language_menu = wx.Menu()
        self.language_items = {}
        languages = [
            ('en', "English"),
            ('zh', "中文"),
            ('fr', "Français"),
            ('ru', "Русский"),
            ('es', "Español"),
            ('ar', "العربية")
        ]
        for lang_code, lang_name in languages:
            item = language_menu.Append(wx.ID_ANY, lang_name, translate("menu_switch_language").format(lang_name=lang_name), kind=wx.ITEM_RADIO)
            self.language_items[lang_code] = item
            self.Bind(wx.EVT_MENU, lambda event, code=lang_code: self.on_language_change(code), item)
        settings_menu.AppendSubMenu(language_menu, translate("menu_language"), translate("menu_language_tip"))
        
        help_menu = wx.Menu()
        self._main_about_item = help_menu.Append(wx.ID_ABOUT, translate("menu_about") + "\tF1", translate("menu_about_tip"))
        menubar.Append(file_menu, translate("menu_file"))
        menubar.Append(self.window_menu, translate("menu_window"))
        menubar.Append(settings_menu, translate("menu_settings"))
        # 社区发布版（OSS）不含登录/后端功能，隐藏"账户"菜单以避免误导用户
        if not IS_OSS_COMMUNITY_BUILD:
            menubar.Append(self.user_menu, translate("menu_account"))
        menubar.Append(help_menu, translate("menu_help"))
        self.SetMenuBar(menubar)
        self._main_menubar = menubar
        
        self._bind_main_menu_events()
        
        self.update_language_selection()
        self._update_user_menu_state()
        
        accel_tbl = wx.AcceleratorTable([
            (wx.ACCEL_NORMAL, wx.WXK_F5, self._main_refresh_item.GetId()),
            (wx.ACCEL_CTRL, ord('Q'), self._main_exit_item.GetId()),
            (wx.ACCEL_CTRL, ord('H'), self.home_menu_item.GetId()),
            (wx.ACCEL_NORMAL, wx.WXK_F1, self._main_about_item.GetId()),
            (wx.ACCEL_CTRL, ord('F'), self.ID_SEARCH_FOCUS)
        ])
        self.SetAcceleratorTable(accel_tbl)

    def _bind_main_menu_events(self):
        self.Bind(wx.EVT_MENU, self.on_refresh_tool_list, self._main_refresh_item)
        self.Bind(wx.EVT_MENU, self.on_clear_cache, self._main_clear_cache_item)
        self.Bind(wx.EVT_MENU, self.on_close_all_tools, self._main_close_tools_item)
        self.Bind(wx.EVT_MENU, self.on_check_update, self._main_check_update_item)
        self.Bind(wx.EVT_MENU, self.on_exit_menu, self._main_exit_item)
        self.Bind(wx.EVT_MENU, self._on_user_menu_click, self.login_item)
        self.Bind(wx.EVT_MENU, self._on_user_info_click, self.user_info_item)
        self.Bind(wx.EVT_MENU, self._on_join_company_click, self.join_company_item)
        self.Bind(wx.EVT_MENU, self._on_order_tools_click, self.order_tools_item)
        self.Bind(wx.EVT_MENU, self._on_feedback_click, self.feedback_item)
        self.Bind(wx.EVT_MENU, self.on_show_home, self.home_menu_item)
        self.Bind(wx.EVT_MENU, self.on_about, self._main_about_item)
        # Ctrl+F 聚焦搜索框
        self.Bind(wx.EVT_MENU, self.on_search_focus, self.ID_SEARCH_FOCUS)
        # 额外通过EVT_CHAR_HOOK确保Ctrl+F在任何焦点状态下都能生效
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

    """更新语言选择状态"""
    def update_language_selection(self):
        current_lang = i18n.get_language_code()
        if current_lang in self.language_items:
            self.language_items[current_lang].Check(True)

    """按当前语言刷新窗口标题（主页显示品牌名，工具页显示"品牌名 - 工具名"）"""
    def refresh_window_title(self):
        active_tool = getattr(self, '_current_active_tool', None)
        if active_tool:
            tool_instance = self.embedded_tools.get(active_tool, {}).get('instance')
            tool_name = getattr(tool_instance, 'name', active_tool)
            self.SetTitle(f"{get_app_base_title()} - {tool_name}" + (" [DEV MODE]" if IS_LOCAL_TEST_BUILD else ""))
        else:
            self.SetTitle(get_app_title())

    """语言切换事件处理"""
    def on_language_change(self, lang_code):
        if i18n.set_language(lang_code):
            logger.info("Language switched to: %s", lang_code)
            # 保存语言设置
            self.save_language_setting(lang_code)
            # 立即按新语言刷新窗口标题，其余界面在下次启动时生效
            self.refresh_window_title()
            # 提示用户需要重启
            wx.MessageBox(
                translate("message_language_changed"),
                translate("dialog_title_language_settings"),
                wx.OK | wx.ICON_INFORMATION
            )
        else:
            wx.MessageBox(translate("message_unsupported_language").format(lang_code=lang_code), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)

    """保存语言设置到配置文件"""
    def save_language_setting(self, lang_code):
        try:
            # 使用可写运行时配置目录（AppImage/只读安装时自动退回 ~/.local/share/TabulexFlow/config），
            # 不能用 get_config_path()——打包产物中它指向可执行文件旁的只读挂载目录，写入会失败/丢失
            config_file = self.config_dir / "language_settings.json"
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config = {}
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            config['language'] = lang_code
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            logger.info("Language setting saved: %s", lang_code)
            logger.debug("Config file path: %s", config_file)
        except Exception as e:
            logger.error("Failed to save language setting: %s", e)

    """加载语言设置"""
    def load_language_setting(self):
        try:
            # 与 save_language_setting 使用同一可写运行时配置目录，保证跨启动持久化
            config_file = self.config_dir / "language_settings.json"
            config = {}
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            if 'language' not in config:
                config['language'] = self.default_lang
                config_file.parent.mkdir(parents=True, exist_ok=True)
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
                logger.info("Default language setting written: %s", self.default_lang)
            lang_code = config.get('language', self.default_lang)
            i18n.set_language(lang_code)
            logger.info("Language setting loaded: %s", lang_code)
            logger.debug("Config file path: %s", config_file)
        except Exception as e:
            logger.error("Failed to load language setting: %s", e)
            i18n.set_language(self.default_lang)

    """设置程序图标"""
    def setup_icon(self):
        try:
            icon_path = get_resource_path("app_icon.ico")
            if icon_path.exists():
                # 用 IconBundle 载入 ICO 内全部尺寸并 SetIcons：wxGTK 下 SetIcon 只向窗口管理器
                # 写入单一尺寸的 _NET_WM_ICON，Linux 任务栏（如 Cinnamon）取不到合适尺寸导致图标显示异常
                self.SetIcons(wx.IconBundle(str(icon_path), wx.BITMAP_TYPE_ICO))
                if sys.platform == 'win32':
                    # 开发模式下python.exe没有自定义图标，Windows任务栏会先缓存python.exe的默认图标
                    # 需要在窗口完全显示后通过Win32 API强制设置任务栏图标
                    # 使用多次延迟设置来克服Windows Shell的图标缓存时序问题
                    wx.CallAfter(self._set_taskbar_icon_winapi, str(icon_path))
                    # 保险：窗口完全显示后再次设置，解决CallAfter时窗口尚未被Shell关联的竞争问题
                    wx.CallLater(500, self._set_taskbar_icon_winapi, str(icon_path))
            else:
                logger.warning("Icon not found at: %s", icon_path)
        except Exception as e:
            logger.error("Failed to set icon: %s", e)

    def _set_taskbar_icon_winapi(self, icon_path_str):
        try:
            hwnd = self.GetHandle()
            if not hwnd:
                return

            user32 = ctypes.windll.user32

            WM_SETICON = 0x0080
            ICON_SMALL = 0
            ICON_BIG = 1
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x00000010
            LR_DEFAULTSIZE = 0x00000040

            user32.LoadImageW.restype = ctypes.c_void_p
            user32.LoadImageW.argtypes = [
                ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
                ctypes.c_int, ctypes.c_int, ctypes.c_uint
            ]

            hicon_small = user32.LoadImageW(
                None, icon_path_str, IMAGE_ICON, 16, 16, LR_LOADFROMFILE
            )
            hicon_large = user32.LoadImageW(
                None, icon_path_str, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
            )

            if not hicon_small and not hicon_large:
                hicon_small = user32.LoadImageW(
                    None, icon_path_str, IMAGE_ICON, 32, 32, LR_LOADFROMFILE
                )
                hicon_large = user32.LoadImageW(
                    None, icon_path_str, IMAGE_ICON, 48, 48, LR_LOADFROMFILE
                )

            if not hicon_small and not hicon_large and getattr(sys, 'frozen', False):
                shell32 = ctypes.windll.shell32
                shell32.ExtractIconW.restype = ctypes.c_void_p
                shell32.ExtractIconW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
                hicon = shell32.ExtractIconW(0, sys.executable, 0)
                if hicon:
                    hicon_small = hicon
                    hicon_large = hicon

            if hicon_small:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)

            if hicon_large:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_large)

            if not hicon_small and not hicon_large:
                logger.error("Failed to load taskbar icon from: %s", icon_path_str)
                return

            try:
                GCL_HICON = -14
                GCL_HICONSM = -34
                if sys.maxsize > 2 ** 32:
                    set_class_fn = user32.SetClassLongPtrW
                else:
                    set_class_fn = user32.SetClassLongW

                if hicon_large:
                    set_class_fn(hwnd, GCL_HICON, hicon_large)
                if hicon_small:
                    set_class_fn(hwnd, GCL_HICONSM, hicon_small)
            except Exception:
                pass
        except Exception as e:
            logger.error("Failed to set taskbar icon: %s", e)

    """显示主页面板"""
    def on_show_home(self, event):
        # 检查是否已经在主页
        if hasattr(self, '_current_active_tool') and self._current_active_tool is None:
            # 已经在主页，不做任何尺寸调整
            logger.debug("Clicked current home page, keeping current window size")
            return
        else:
            # 不在主页，切换到主页
            self.show_home_panel()

    """显示主页面板"""
    def show_home_panel(self):
        logger.info("[HOVER_DIAG] show_home_panel: starting to show home panel")
        if hasattr(self, '_current_active_tool') and self._current_active_tool:
            self.save_current_window_size(self._current_active_tool)
            logger.debug("Saving tool %s window size before switching", self._current_active_tool)
        
        # 清理旧工具的菜单扩展（如子工具添加的"编辑"菜单）
        if hasattr(self, '_current_active_tool') and self._current_active_tool:
            old_tool_ident = self._current_active_tool
            if old_tool_ident in self.embedded_tools:
                old_tool_instance = self.embedded_tools[old_tool_ident].get('instance')
                if old_tool_instance and hasattr(old_tool_instance, 'unbind_menu_events'):
                    old_tool_instance.unbind_menu_events(self)
                # 源码模式收费工具切换回主页时释放席位（EXE模式由_on_exe_tool_hidden处理）
                old_tool_data = self.embedded_tools[old_tool_ident]
                if old_tool_data.get('mode') != 'exe' and old_tool_data.get('requires_subscription', False):
                    try:
                        from tfp_auth import auth_manager
                        auth_manager.release_seat(old_tool_ident)
                    except Exception as e:
                        logger.warning(f"Failed to release seat when switching back to home: {e}")
        
        for tool_ident, tool_data in self.embedded_tools.items():
            if tool_data.get('panel'):
                tool_data['panel'].Hide()
        self.home_panel.Show()
        self.status_bar.Show()
        
        if hasattr(self, '_main_menubar'):
            self.SetMenuBar(self._main_menubar)
            self._bind_main_menu_events()
            accel_tbl = wx.AcceleratorTable([
                (wx.ACCEL_NORMAL, wx.WXK_F5, self._main_refresh_item.GetId()),
                (wx.ACCEL_CTRL, ord('Q'), self._main_exit_item.GetId()),
                (wx.ACCEL_CTRL, ord('H'), self.home_menu_item.GetId()),
                (wx.ACCEL_NORMAL, wx.WXK_F1, self._main_about_item.GetId())
            ])
            self.SetAcceleratorTable(accel_tbl)
            # 启用平台级菜单项（仅在主页时可用）
            self._enable_platform_menu_items(True)
        
        if not self.IsShown():
            self.Show()
        
        self.set_default_main_window_size()
        
        self.SendSizeEvent()
        self.status_bar.SetStatusText(translate("status_ready"), 0)
        self._update_status_bar_auth()
        
        self._current_active_tool = None
        
        self.SetTitle(get_app_title())
        
        self._update_window_menu_for_tool(None)
        
        self.unlock_all_tools()

    def show_tool_panel(self, tool_ident):
        if tool_ident not in self.embedded_tools:
            return
        
        # 清理旧工具的菜单扩展（如子工具添加的"编辑"菜单）
        if hasattr(self, '_current_active_tool') and self._current_active_tool and self._current_active_tool != tool_ident:
            old_tool_ident = self._current_active_tool
            if old_tool_ident in self.embedded_tools:
                old_tool_instance = self.embedded_tools[old_tool_ident].get('instance')
                if old_tool_instance and hasattr(old_tool_instance, 'unbind_menu_events'):
                    old_tool_instance.unbind_menu_events(self)
                # 源码模式收费工具切换到其他工具时释放席位（EXE模式由_on_exe_tool_hidden处理）
                old_tool_data = self.embedded_tools[old_tool_ident]
                if old_tool_data.get('mode') != 'exe' and old_tool_data.get('requires_subscription', False):
                    try:
                        from tfp_auth import auth_manager
                        auth_manager.release_seat(old_tool_ident)
                    except Exception as e:
                        logger.warning(f"Failed to release seat when switching tools: {e}")
            self.save_current_window_size(self._current_active_tool)
            logger.debug("Saving tool %s window size before switching", self._current_active_tool)
        
        self.home_panel.Hide()
        for tid, tool_data in self.embedded_tools.items():
            if tid != tool_ident and tool_data.get('panel'):
                tool_data['panel'].Hide()
        if self.embedded_tools[tool_ident].get('panel'):
            self.embedded_tools[tool_ident]['panel'].Show()
        
        # 源码模式收费工具切换回来时重新占用席位（EXE模式由_resend_ipc_show_command处理）
        new_tool_data = self.embedded_tools[tool_ident]
        if new_tool_data.get('mode') != 'exe' and new_tool_data.get('requires_subscription', False):
            try:
                from tfp_auth import auth_manager
                auth_manager.occupy_seat(tool_ident)
            except Exception as e:
                logger.warning(f"Failed to occupy seat when switching to paid tool: {e}")
        
        tool_name = self.embedded_tools[tool_ident]['instance'].name if hasattr(self.embedded_tools[tool_ident]['instance'], 'name') else tool_ident
        self.status_bar.SetStatusText(translate("status_current_tool").format(tool_name=tool_name), 0)
        self.status_bar.Hide()
        
        tool_instance = self.embedded_tools[tool_ident].get('instance')
        if tool_instance and hasattr(tool_instance, 'get_menu_bar'):
            tool_menubar = tool_instance.get_menu_bar()
            if tool_menubar:
                self.SetMenuBar(tool_menubar)
                if hasattr(tool_instance, 'bind_menu_events'):
                    tool_instance.bind_menu_events(self)
                self.SetAcceleratorTable(wx.AcceleratorTable())
            else:
                # get_menu_bar() 返回 None：保留主框架菜单栏，但可能需要插入子工具的菜单扩展
                if hasattr(self, '_main_menubar'):
                    self.SetMenuBar(self._main_menubar)
                    self._bind_main_menu_events()
                    # 禁用平台级菜单项（仅在主页时可用）
                    self._enable_platform_menu_items(False)
                if hasattr(tool_instance, 'bind_menu_events'):
                    tool_instance.bind_menu_events(self)
        else:
            if hasattr(self, '_main_menubar'):
                self.SetMenuBar(self._main_menubar)
                self._bind_main_menu_events()
                # 禁用平台级菜单项（仅在主页时可用）
                self._enable_platform_menu_items(False)
        
        self.restore_tool_window_size(tool_ident)
        
        self.content_container.Layout()
        self.main_panel.Layout()
        self.Layout()
        
        self._current_active_tool = tool_ident
        
        self.SetTitle(f"{get_app_base_title()} - {tool_name}" + (" [DEV MODE]" if IS_LOCAL_TEST_BUILD else ""))
        
        self._update_window_menu_for_tool(tool_ident)
        
        self.unlock_all_tools()

    """设置主页默认窗口大小"""
    def set_default_main_window_size(self):
        default_width = self.spx_calc(720)
        default_height = self.spx_calc(450)
        self.SetSize(default_width, default_height)
        self.Centre()
        logger.debug("Setting default home-panel window size: %dx%d", default_width, default_height)

    """保存工具窗口尺寸"""
    def save_current_window_size(self, tool_ident):
        current_size = self.GetSize()
        self.window_sizes[tool_ident] = (current_size.width, current_size.height)
        logger.debug("Saving tool %s window size: %dx%d", tool_ident, current_size.width, current_size.height)

    """恢复工具窗口尺寸"""
    def restore_tool_window_size(self, tool_ident):
        saved_size = self.window_sizes.get(tool_ident)
        if saved_size:
            width, height = saved_size
            self.SetSize(int(width), int(height))
            self.Centre()
            logger.debug("Restoring tool %s window size: %dx%d", tool_ident, width, height)
        else:
            logger.debug("Tool %s has no saved window size; using current size", tool_ident)
    
    """添加工具到窗口菜单"""
    def add_tool_to_window_menu(self, tool_ident, tool_name):
        if tool_ident in self.window_menu_tools:
            return
        menu_item = self.window_menu.Append(wx.ID_ANY, tool_name, translate("menu_switch_to_tool").format(tool_name=tool_name))
        self.window_menu_tools[tool_ident] = menu_item
        self.Bind(wx.EVT_MENU, lambda e, tid=tool_ident: self.on_window_menu_click(tid), menu_item)
    
    """更新Window菜单项的启用/禁用状态"""
    def _update_window_menu_for_tool(self, active_tool_ident):
        for tid, menu_item in self.window_menu_tools.items():
            menu_item.Enable(tid != active_tool_ident)
    
    """启用/禁用平台级菜单项
    
    这些菜单项仅在平台主页时可用，在子工具中应禁用：
    - 刷新工具列表 (F5)
    - 清除缓存
    - 关闭所有工具
    
    Args:
        enabled: True=启用, False=禁用
    """
    def _enable_platform_menu_items(self, enabled: bool):
        if hasattr(self, '_main_refresh_item') and self._main_refresh_item:
            self._main_refresh_item.Enable(enabled)
        if hasattr(self, '_main_clear_cache_item') and self._main_clear_cache_item:
            self._main_clear_cache_item.Enable(enabled)
        if hasattr(self, '_main_close_tools_item') and self._main_close_tools_item:
            self._main_close_tools_item.Enable(enabled)

    """窗口菜单点击事件处理"""
    def on_window_menu_click(self, tool_ident):
        if hasattr(self, '_current_active_tool') and self._current_active_tool == tool_ident:
            logger.debug("Clicked on currently active tool %s; keeping current window size", tool_ident)
            return
        elif hasattr(self, '_current_active_tool') and self._current_active_tool is None and tool_ident == 'home':
            logger.debug("Clicked current home page, keeping current window size")
            return
        else:
            if tool_ident in self.embedded_tools and self.embedded_tools[tool_ident].get('mode') == 'exe':
                tool_data = self.embedded_tools[tool_ident]
                if tool_data.get('is_hidden'):
                    self._resend_ipc_show_command(tool_ident)
                else:
                    logger.debug("Tool %s is already running", tool_ident)
            else:
                self.show_tool_panel(tool_ident)
    
    """从窗口菜单移除工具"""
    def remove_tool_from_window_menu(self, tool_ident):
        if tool_ident in self.window_menu_tools:
            self.window_menu.Delete(self.window_menu_tools[tool_ident].GetId())
            del self.window_menu_tools[tool_ident]

    """通过发送大小事件强制重新布局，用于解决主窗口初始元素堆叠的问题"""
    def force_layout_by_resize(self):
        self.tools_grid_sizer.Layout()
        self.tools_inner_panel.Layout()
        self.tools_scroll.Layout()
        self.home_panel.Layout()
        self.content_container.Layout()
        self.main_panel.Layout()
        self.SendSizeEvent()
        self.Layout()
        self.Refresh()
        self.Update()
        logger.debug("Forced window relayout")

    """根据DPI调整字体大小"""
    def adjust_fonts_for_hidpi(self):
        # 实测在高分屏的Win11系统里对冰凌输入法无效
        try:
            # 获取系统默认字体
            default_font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
            # 使用已计算的TFP_DPI_SCALE_FACTOR调整字体大小
            if self.TFP_DPI_SCALE_FACTOR > 1.0:
                new_size = int(default_font.GetPointSize() * self.TFP_DPI_SCALE_FACTOR)
                default_font.SetPointSize(new_size)
                # 设置全局字体
                wx.SystemSettings.SetFont(wx.SYS_DEFAULT_GUI_FONT, default_font)
                logger.info("HiDPI detected: font enlarged to %dpt (scale factor %.2f)", new_size, self.TFP_DPI_SCALE_FACTOR)
        except Exception as e:
            logger.error("Failed to adjust font: %s", e)

    """关闭所有工具"""
    def on_close_all_tools(self, event):
        open_tool_count = len(self.embedded_tools)
        if open_tool_count > 0:
            dialog = wx.MessageDialog(
                self,
                translate("dialog_text_confirm_close_tools", count=open_tool_count),
                translate("dialog_title_confirm_close_tools"),
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION
            )
            if dialog.ShowModal() == wx.ID_YES:
                dialog.Destroy()
                self.lock_all_tools()
                busy_info = wx.BusyInfo(translate("busy_closing_tools"), self)
                wx.Yield()
                self.close_all_embedded_tools()
                closed_count = open_tool_count
                busy_info = None
                wx.Yield()
                wx.MessageBox(
                    translate("message_closed_tools_result", count=closed_count),
                    translate("dialog_title_info"),
                    wx.OK | wx.ICON_INFORMATION
                )
                self.unlock_all_tools()
            else:
                dialog.Destroy()
        else:
            wx.MessageBox(translate("message_no_open_tools"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)

    """关闭所有嵌入式工具"""
    def close_all_embedded_tools(self):
        tools_to_close = list(self.embedded_tools.keys())
        for tool_ident in tools_to_close:
            self.close_embedded_tool(tool_ident)
        # 双重保险：关闭所有工具后再次释放所有席位，防止个别释放失败导致席位泄漏
        try:
            from tfp_auth import auth_manager
            auth_manager.release_all_seats()
        except Exception as e:
            logger.warning(f"Failed to release all seats after closing all tools: {e}")
        if not any(td.get('mode') == 'exe' for td in self.embedded_tools.values()):
            self.show_home_panel()

    """关闭单个嵌入式工具"""
    def close_embedded_tool(self, tool_ident):
        if tool_ident in self.embedded_tools:
            tool_data = self.embedded_tools[tool_ident]
            # 收费工具释放企业席位
            if tool_data.get('requires_subscription', False):
                try:
                    auth_manager.release_seat(tool_ident)
                except Exception as e:
                    logger.warning(f"Failed to release seat: {e}")
            if tool_data.get('mode') == 'exe':
                self._send_ipc_to_tool(tool_ident, "close")
                tool_data['main_was_visible'] = False
                self._on_exe_tool_closed(tool_ident)
            else:
                tool_instance = tool_data.get('instance')
                if tool_instance:
                    if hasattr(tool_instance, '_main_panel') and tool_instance._main_panel:
                        try:
                            # 直接调用_on_close进行清理，不再预先设置_is_closing
                            # _on_close会自己设置_is_closing并执行清理
                            if hasattr(tool_instance._main_panel, '_on_close'):
                                tool_instance._main_panel._on_close()
                            elif hasattr(tool_instance._main_panel, 'cleanup'):
                                tool_instance._main_panel.cleanup()
                        except Exception as e:
                            logger.error("Error cleaning up tool %s instance: %s", tool_ident, e)
                try:
                    tool_data['panel'].Destroy()
                except Exception as e:
                    logger.error("Error closing tool %s: %s", tool_ident, e)
                del self.embedded_tools[tool_ident]
                self.remove_tool_from_window_menu(tool_ident)

    """清除所有工具目录下模块的缓存"""
    def clear_tool_module_cache(self, tool_dir):
        try:
            tool_dir_path = os.path.normpath(str(tool_dir)).lower()
            if not tool_dir_path:
                return
            tool_dir_path_with_sep = tool_dir_path + os.sep
            logger.info("Preparing to clear tool directory cache: %s", tool_dir_path)
            modules_to_remove = set()
            for module_name, module in list(sys.modules.items()):
                try:
                    module_file = None
                    if hasattr(module, '__file__') and module.__file__:
                        module_file = module.__file__
                    elif hasattr(module, '__spec__') and module.__spec__ and hasattr(module.__spec__, 'origin') and module.__spec__.origin:
                        module_file = module.__spec__.origin
                    if module_file:
                        norm_file = os.path.normpath(module_file).lower()
                        if norm_file == tool_dir_path or norm_file.startswith(tool_dir_path_with_sep):
                            modules_to_remove.add(module_name)
                    if hasattr(module, '__path__'):
                        try:
                            for mp in module.__path__:
                                norm_mp = os.path.normpath(str(mp)).lower()
                                if norm_mp == tool_dir_path or norm_mp.startswith(tool_dir_path_with_sep):
                                    modules_to_remove.add(module_name)
                                    break
                        except (TypeError, AttributeError):
                            pass
                except (AttributeError, TypeError):
                    continue
            sorted_modules = sorted(modules_to_remove, key=len, reverse=True)
            removed_count = 0
            for module_name in sorted_modules:
                try:
                    if module_name in sys.modules:
                        parent_name = module_name.rsplit('.', 1)[0]
                        if '.' in module_name and parent_name in sys.modules:
                            child_attr = module_name.rsplit('.', 1)[1]
                            try:
                                delattr(sys.modules[parent_name], child_attr)
                            except (AttributeError, TypeError):
                                pass
                        del sys.modules[module_name]
                        removed_count += 1
                except Exception as e:
                    logger.warning("Failed to clear module %s: %s", module_name, e)
            sys.path = [p for p in sys.path if os.path.normpath(p).lower() != tool_dir_path]
            logger.info("Removed tool directory from sys.path: %s", tool_dir_path)
            logger.info("Cleared %d module caches in total", removed_count)
            gc.collect()
        except Exception as e:
            logger.error("Error clearing module cache: %s", e)

    def _is_backend_reachable(self) -> bool:
        # 社区发布版（OSS）无后端，直接判定为不可达，避免发起后端探测
        if IS_OSS_COMMUNITY_BUILD:
            return False
        """后端是否可达（复用启动健康检查结果，用于UI反馈）"""
        try:
            from tfp_utils.tfp_backend_config import get_backend_manager
            return get_backend_manager().is_backend_reachable()
        except Exception as e:
            logger.warning(f"Failed to determine backend reachability: {e}")
            return False

    def _backend_status_text(self, key):
        """生成底部状态栏"服务器连接状态"文本：在状态文案后附上后端地址。

        - 连接成功 → 显示实际连接的后端地址；
        - 连接失败 → 显示最终尝试失败的同一后端地址（当前后端地址唯一）。
        key 取 status_server_connected / status_server_disconnected / status_offline_mode。
        """
        url = getattr(self, 'backend_url', '') or BACKEND_BASE_URL
        return f"{translate(key)} · {url}"

    def _on_auth_state_changed(self):
        """认证状态变化回调"""
        wx.CallAfter(self._update_user_menu_state)
        wx.CallAfter(self._update_status_bar_auth)
        wx.CallAfter(self._on_auth_changed_sync_favorites)

    def _update_user_menu_state(self):
        """更新用户菜单状态"""
        if not hasattr(self, 'user_menu'):
            return
        
        is_logged_in = auth_manager.is_user_logged_in()
        backend_ok = self._is_backend_reachable()
        
        if is_logged_in:
            user = auth_manager.get_current_user()
            display_name = user.display_name if user else translate("menu_user_info")
            user_type = user.user_type.upper() if user else "FREE"
            
            self.login_item.SetItemLabel(translate("menu_logout", name=display_name))
            self.login_item.SetHelp(translate("menu_logout_tip"))
            self.user_info_item.SetItemLabel(f"{display_name} ({user_type})")
            self.user_info_item.Enable(True)
            # 个人用户且未加入企业时，启用"加入企业"菜单项
            is_individual_no_company = (user and user.user_type == 'individual' and not user.company_id)
            self.join_company_item.Enable(is_individual_no_company)
        else:
            self.login_item.SetItemLabel(translate("menu_login"))
            self.login_item.SetHelp(translate("menu_login_tip"))
            self.user_info_item.SetItemLabel(translate("menu_not_logged_in"))
            self.user_info_item.Enable(False)
            self.join_company_item.Enable(False)
        
        # 后端不可达时禁用依赖后端的菜单项（点击时也会弹窗提示，禁用是视觉反馈）
        # 已登录时"登出"不需要后端，始终启用；未登录时"登录"需要后端
        self.login_item.Enable(is_logged_in or backend_ok)
        self.order_tools_item.Enable(backend_ok)
        self.feedback_item.Enable(backend_ok)

    def _update_status_bar_auth(self):
        """更新状态栏认证信息"""
        # 社区发布版（OSS）无登录功能，不展示"未登录"误导信息
        if IS_OSS_COMMUNITY_BUILD:
            return
        if not hasattr(self, 'status_bar'):
            return
        
        is_logged_in = auth_manager.is_user_logged_in()
        
        if is_logged_in:
            user = auth_manager.get_current_user()
            display_name = user.display_name if user else translate("menu_user_info")
            user_type = user.user_type.upper() if user else "FREE"
            # 平台用户在状态栏打码显示名称（仅状态栏，菜单/对话框等不受影响）
            if user and user.is_platform() and display_name:
                display_name = mask_display_name(display_name)
            self.status_bar.SetStatusText(f"{display_name} ({user_type})", 1)
        else:
            self.status_bar.SetStatusText(translate("menu_not_logged_in"), 1)

    def _on_user_menu_click(self, event):
        """用户菜单点击事件"""
        if auth_manager.is_user_logged_in():
            result = wx.MessageBox(
                translate("message_confirm_logout"),
                translate("dialog_title_confirm_logout"),
                wx.YES_NO | wx.ICON_QUESTION
            )
            if result == wx.YES:
                auth_manager.logout_user()
                self._notify_all_exe_tools_auth_changed()
        else:
            if not self._is_backend_reachable():
                wx.MessageBox(translate("message_offline_login_unavailable"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
                return
            self._show_login_dialog()
    
    def _on_user_info_click(self, event):
        """用户信息菜单点击事件"""
        if not auth_manager.is_user_logged_in():
            self._show_login_dialog()
            return
        
        from tfp_auth.tfp_login_dialog import TFP_UserProfileDialog
        dlg = TFP_UserProfileDialog(self, self._on_profile_update_success)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_join_company_click(self, event):
        """加入企业菜单点击事件 - 显示加入企业对话框"""
        if not auth_manager.is_user_logged_in():
            self._show_login_dialog()
            return
        
        from tfp_auth.tfp_enterprise_dialog import TFP_QuickJoinCompanyDialog
        
        def on_join_success():
            self._update_user_menu_state()
            self._update_status_bar_auth()
        
        dlg = TFP_QuickJoinCompanyDialog(self, on_success=on_join_success)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_order_tools_click(self, event):
        """订购工具菜单点击事件 - 在默认浏览器中打开订购中心"""
        if not self._is_backend_reachable():
            wx.MessageBox(translate("message_offline_order_unavailable"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        import webbrowser
        order_url = f"{self.backend_url}/web/order"
        try:
            webbrowser.open(order_url)
            logger.info("Opened ordering center: %s", order_url)
        except Exception as e:
            logger.error("Failed to open ordering center: %s", e)
            wx.MessageBox(
                translate("message_open_order_center_failed").format(url=order_url),
                translate("dialog_title_error"),
                wx.OK | wx.ICON_ERROR
            )

    def _on_feedback_click(self, event):
        """问题反馈菜单点击事件 - 在默认浏览器中打开问题反馈页面"""
        if not self._is_backend_reachable():
            wx.MessageBox(translate("message_offline_feedback_unavailable"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        import webbrowser
        feedback_url = f"{self.backend_url}/web/support"
        try:
            webbrowser.open(feedback_url)
            logger.info("Opened feedback: %s", feedback_url)
        except Exception as e:
            logger.error("Failed to open feedback: %s", e)
            wx.MessageBox(
                translate("message_open_feedback_failed").format(url=feedback_url),
                translate("dialog_title_error"),
                wx.OK | wx.ICON_ERROR
            )

    def _show_login_dialog(self):
        """显示登录对话框"""
        dlg = TFP_LoginRegisterDialog(self, self._on_login_success)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_login_success(self):
        """登录成功回调"""
        logger.info("User logged in successfully")
        self._update_user_menu_state()
        self._update_status_bar_auth()
        self._notify_all_exe_tools_auth_changed()
    
    def _on_profile_update_success(self):
        """用户资料更新成功回调"""
        logger.info("User profile updated successfully")
        self._update_user_menu_state()
        self._update_status_bar_auth()
    
    def _on_login_success_for_tool(self):
        """工具登录成功回调 - 登录后重新打开工具"""
        logger.info("Tool login succeeded; re-checking permissions")
        self._update_user_menu_state()
        self._update_status_bar_auth()

    """处理主程序最小化事件 - 简化修复版本"""
    def on_minimize(self, event):
        # 让系统处理最小化逻辑，我们只确保工具窗口不受影响
        event.Skip()

    """处理窗口激活事件：清理残留的hover状态"""
    def _on_window_activate(self, event):
        if event.GetActive():
            logger.info("[HOVER_DIAG] _on_window_activate: window activated")
            # 窗口激活时，检查鼠标实际位置，清理不在鼠标下的卡片的hover状态
            mouse_pos = wx.GetMousePosition()
            for panel in self.tool_panels:
                if panel and hasattr(panel, '_hover') and panel._hover:
                    screen_rect = panel.GetScreenRect()
                    tool_name = getattr(panel, '_tool_name', '?')
                    if not screen_rect.Contains(mouse_pos):
                        logger.info("[HOVER_DIAG] _on_window_activate: clearing leftover hover state of card %s", tool_name)
                        panel._hover = False
                        panel.Refresh()
                    else:
                        logger.info("[HOVER_DIAG] _on_window_activate: card %s is under the mouse; keeping hover state", tool_name)
        else:
            logger.info("[HOVER_DIAG] _on_window_activate: window lost activation")
        event.Skip()

    """Exit菜单/Ctrl+Q事件处理：菜单事件的Skip()不会关闭窗口，
    必须通过Close()触发EVT_CLOSE走统一的关闭流程(on_exit)"""
    def on_exit_menu(self, event):
        self.Close()

    """处理主程序关闭事件 - 嵌入式工具版本，支持从工具界面返回主页"""
    def on_exit(self, event):
        if hasattr(self, '_current_active_tool') and self._current_active_tool is not None:
            if self.default_tool and self.default_tool != "main":
                dlg = wx.Dialog(self, title=translate("dialog_title_exit_options"), size=(self.spx_calc(350), self.spx_calc(150)))
                dlg.SetWindowStyle(wx.CAPTION | wx.CLOSE_BOX)
                panel = wx.Panel(dlg)
                sizer = wx.BoxSizer(wx.VERTICAL)
                label = wx.StaticText(panel, label=translate("dialog_text_exit_options"))
                label.Wrap(self.spx_calc(300))
                sizer.Add(label, 0, wx.ALL | wx.ALIGN_CENTER, self.spx_calc(15))
                btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
                show_all_btn = wx.Button(panel, wx.ID_YES, translate("btn_show_all_tools"))
                exit_btn = wx.Button(panel, wx.ID_NO, translate("btn_exit_directly"))
                btn_sizer.Add(show_all_btn, 0, wx.ALL, self.spx_calc(5))
                btn_sizer.Add(exit_btn, 0, wx.ALL, self.spx_calc(5))
                sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.BOTTOM, self.spx_calc(10))
                panel.SetSizer(sizer)
                show_all_btn.SetDefault()
                show_all_btn.SetFocus()
                def on_show_all(e):
                    dlg.EndModal(wx.ID_YES)
                def on_exit_directly(e):
                    dlg.EndModal(wx.ID_NO)
                show_all_btn.Bind(wx.EVT_BUTTON, on_show_all)
                exit_btn.Bind(wx.EVT_BUTTON, on_exit_directly)
                result = dlg.ShowModal()
                dlg.Destroy()
                if result == wx.ID_YES:
                    self.show_home_panel()
                else:
                    self.close_all_embedded_tools()
                    event.Skip()
            else:
                self.show_home_panel()
        else:
            self.close_all_embedded_tools()
            event.Skip()

    """加载所有工具列表 - 异步版本"""
    def load_all_tools(self):
        self.load_builtin_tools()
        # 社区发布版（OSS）不含后端/远程工具，仅加载并展示内置(BuiltinProgram)工具
        if not IS_OSS_COMMUNITY_BUILD:
            self.load_local_non_builtin_tools()
        self.update_tool_buttons()
        self.status_bar.SetStatusText(translate("status_local_tools_loaded"), 1)
        wx.CallAfter(self.force_layout_by_resize)
        # 主界面启动后不聚焦任何控件（焦点置于窗口本身，避免搜索框默认被激活）
        wx.CallAfter(self._clear_home_default_focus)
        if not IS_OSS_COMMUNITY_BUILD:
            wx.CallAfter(self.async_update_non_builtin_tools)
        # 前端自更新检查（T1.2）：工具列表检查后异步发起，失败静默
        wx.CallAfter(self._start_frontend_update_check)
        if self.default_tool and self.default_tool != "main":
            wx.CallAfter(self.auto_open_default_tool)

    """自动打开默认工具"""
    def auto_open_default_tool(self):
        tool_ident = self.default_tool
        builtin_tools = self.builtin_tools.get("tools_builtin_program", [])
        for tool_info in builtin_tools:
            if tool_info.get("tool_ident") == tool_ident:
                logger.info("Auto-opening default tool: %s", tool_ident)
                self.run_builtin_program(tool_info)
                return
        logger.warning("Default tool not found: %s", tool_ident)

    """异步从后端更新非内置工具列表 - 普通更新版本"""
    def async_update_non_builtin_tools(self):
        # 社区发布版（OSS）不连接后端，直接返回，避免展示失效的登录/远程功能
        if IS_OSS_COMMUNITY_BUILD:
            return
        def update_thread():
            try:
                with self._tools_data_lock:
                    last_modified_snapshot = self.last_modified
                self.status_bar.SetStatusText(translate("status_updating_from_backend"), 1)
                response = requests.get(
                    f"{self.backend_url}{API_V1_PREFIX}/tool_list",
                    params={
                        'last_modified': last_modified_snapshot,
                        'frontend_version': self.frontend_version
                    },
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == 'no_change':
                        wx.CallAfter(self.status_bar.SetStatusText, self._backend_status_text("status_server_connected"), 1)
                        return
                    elif data.get('status') == 'updated':
                        backend_tools = data.get('tools', {})
                        wx.CallAfter(self.handle_backend_tools_update, backend_tools, data.get('last_modified', self.last_modified))
                        return
                # 后端可达但响应异常：显示错误提示
                wx.CallAfter(self.status_bar.SetStatusText, self._backend_status_text("status_server_disconnected"), 1)
            except requests.exceptions.ConnectionError:
                # 后端不可达时显示"离线模式"，而非"服务器: 未连接"
                if self._is_backend_reachable():
                    wx.CallAfter(self.status_bar.SetStatusText, self._backend_status_text("status_server_disconnected"), 1)
                else:
                    wx.CallAfter(self.status_bar.SetStatusText, self._backend_status_text("status_offline_mode"), 1)
            except requests.exceptions.Timeout:
                if self._is_backend_reachable():
                    wx.CallAfter(self.status_bar.SetStatusText, self._backend_status_text("status_server_disconnected"), 1)
                else:
                    wx.CallAfter(self.status_bar.SetStatusText, self._backend_status_text("status_offline_mode"), 1)
            except Exception as e:
                if self._is_backend_reachable():
                    wx.CallAfter(self.status_bar.SetStatusText, self._backend_status_text("status_server_disconnected"), 1)
                else:
                    wx.CallAfter(self.status_bar.SetStatusText, self._backend_status_text("status_offline_mode"), 1)
        # 启动后台线程
        thread = threading.Thread(target=update_thread)
        thread.daemon = True
        thread.start()

    """下载工具图标"""
    def download_tool_icon(self, tool_info):
        try:
            tool_ident = tool_info['tool_ident']
            tool_type = tool_info['tool_type']
            
            category_map = {
                'RemoteProgram': 'tools_remote_program',
                'RemoteWebpage': 'tools_remote_webpage'
            }
            
            category = category_map.get(tool_type)
            if not category:
                return False
            
            tool_dir = self.local_tools_dir / category / tool_ident
            tool_dir.mkdir(parents=True, exist_ok=True)
            icon_path = tool_dir / "app_icon.ico"
            
            if icon_path.exists():
                return True
            
            icon_url = f"{self.backend_url}/tool_icon/{tool_type}/{tool_ident}"
            logger.debug("Downloading tool icon: %s", icon_url)
            
            response = requests.get(icon_url, timeout=10)
            if response.status_code == 200:
                with open(icon_path, 'wb') as f:
                    f.write(response.content)
                logger.debug("Tool icon downloaded successfully: %s", icon_path)
                return True
            else:
                logger.warning("Tool icon download failed, status code: %d", response.status_code)
                return False
        except Exception as e:
            logger.error("Error downloading tool icon: %s", e)
            return False

    """处理后端工具列表更新"""
    def handle_backend_tools_update(self, backend_tools, new_last_modified):
        try:
            with self._tools_data_lock:
                # 差异检测：新增/删除/更新的工具
                local_idents = set()
                for category, tools in self.non_builtin_tools.items():
                    if isinstance(tools, list):
                        for tool in tools:
                            if isinstance(tool, dict):
                                local_idents.add(tool.get('tool_ident'))

                backend_idents = set()
                for category, tools in backend_tools.items():
                    if isinstance(tools, list):
                        for tool in tools:
                            if isinstance(tool, dict):
                                backend_idents.add(tool.get('tool_ident'))

                added = backend_idents - local_idents
                removed = local_idents - backend_idents
                updated = set()
                for category, tools in backend_tools.items():
                    if isinstance(tools, list):
                        for tool in tools:
                            if isinstance(tool, dict):
                                ident = tool.get('tool_ident')
                                if ident in local_idents:
                                    local_tool = self._find_tool_by_ident(ident)
                                    if local_tool and local_tool.get('tool_version') != tool.get('tool_version'):
                                        updated.add(ident)

                self.backend_tools_cache = backend_tools.copy()
                self.merge_tool_lists(backend_tools)
                self.last_modified = new_last_modified
                self.save_local_non_builtin_tools()

                if added or removed or updated:
                    logger.info("Tools synced: added=%s, removed=%s, updated=%s", added, removed, updated)
                    # 记录有版本更新的工具
                    self._tools_with_update = updated
                else:
                    logger.debug("Tools synced: no changes")

            for category, tools in backend_tools.items():
                if category in ('last_modified', 'version') or not isinstance(tools, list):
                    continue
                for tool_info in tools:
                    if isinstance(tool_info, dict) and tool_info.get('tool_type') in ('RemoteProgram', 'RemoteWebpage'):
                        try:
                            self.download_tool_icon(tool_info)
                        except Exception:
                            logger.debug("Failed to download tool icon: %s", tool_info.get('tool_ident', 'unknown'))
            self.update_tool_buttons()
            self.status_bar.SetStatusText(self._backend_status_text("status_server_connected"), 1)
        except Exception as e:
            if self._is_backend_reachable():
                self.status_bar.SetStatusText(self._backend_status_text("status_server_disconnected"), 1)
            else:
                self.status_bar.SetStatusText(self._backend_status_text("status_offline_mode"), 1)

    def _find_tool_by_ident(self, ident):
        """在本地缓存的非内置工具中按ident查找工具"""
        for category, tools in self.non_builtin_tools.items():
            if isinstance(tools, list):
                for tool in tools:
                    if isinstance(tool, dict) and tool.get('tool_ident') == ident:
                        return tool
        return None

    """从文件加载内置工具列表 - 增强版本（扫描tool_manifest.json）"""
    def load_builtin_tools(self):
        builtin_dir = get_resource_path("tools_fe/tools_builtin_program")
        self.builtin_tools = {"last_modified": "2024-01-01T00:00:00Z", "tools_builtin_program": []}

        # 优先扫描目录下的tool_manifest.json
        if builtin_dir and builtin_dir.exists():
            logger.info("Scanning builtin tools from: %s", builtin_dir)
            found_count = 0
            for tool_dir in builtin_dir.iterdir():
                if not tool_dir.is_dir():
                    continue
                manifest_path = tool_dir / "tool_manifest.json"
                if not manifest_path.exists():
                    continue
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        tool_info = json.load(f)
                    # 验证必要字段
                    if tool_info.get('tool_ident') and tool_info.get('tool_type') == 'BuiltinProgram':
                        self.builtin_tools["tools_builtin_program"].append(tool_info)
                        found_count += 1
                        logger.info("Found builtin tool: %s", tool_info.get('tool_ident'))
                    else:
                        logger.warning("Invalid manifest %s: missing tool_ident or wrong tool_type", manifest_path)
                except Exception as e:
                    logger.error("Failed to load manifest %s: %s", manifest_path, e)

            if found_count > 0:
                logger.info("Loaded built-in tools from manifest scan: %d", found_count)
                return

        # 回退：从集中式配置文件读取
        builtin_config_path = get_resource_path("config/tool_list_builtin.json")
        logger.info("Fallback to builtin config: %s", builtin_config_path)
        try:
            if builtin_config_path and builtin_config_path.exists():
                with open(builtin_config_path, 'r', encoding='utf-8') as f:
                    self.builtin_tools = json.load(f)
                logger.info("Loaded built-in tool list: %d categories", len(self.builtin_tools))
            else:
                logger.warning("Built-in tool config file does not exist!")
        except Exception as e:
            logger.error("Failed to load built-in tool list: %s", e)
            traceback.print_exc()

    """加载本地保存的非内置工具列表 - 增强版本"""
    def load_local_non_builtin_tools(self):
        local_config_path = self.config_dir / "tool_list_frontend.json"
        try:
            if local_config_path.exists():
                with open(local_config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.non_builtin_tools = data.get('tools', {})
                    # 校验本地缓存中 tool_ident 格式，过滤非法值
                    from tfp_toolkit.tfp_constants import validate_tool_ident_format
                    for category in list(self.non_builtin_tools.keys()):
                        if category in ('last_modified', 'version'):
                            continue
                        tools = self.non_builtin_tools[category]
                        if isinstance(tools, list):
                            valid_tools = []
                            for tool in tools:
                                if isinstance(tool, dict) and 'tool_ident' in tool:
                                    if not validate_tool_ident_format(tool['tool_ident']):
                                        logger.error("Local cache tool_ident has invalid format, skipped: %s", repr(tool['tool_ident']))
                                        continue
                                valid_tools.append(tool)
                            self.non_builtin_tools[category] = valid_tools
                    self.last_modified = data.get('last_modified', '1970-01-01T00:00:00Z')
                    logger.info("Loaded local non-built-in tool list: %d categories", len(self.non_builtin_tools))
            else:
                self.non_builtin_tools = {}
                self.last_modified = "1970-01-01T00:00:00Z"
                self.save_local_non_builtin_tools()
                logger.info("Created empty local tool config file")
        except Exception as e:
            logger.error("Failed to load local tool list: %s", e)
            # 出错时使用空配置
            self.non_builtin_tools = {}
            self.last_modified = "1970-01-01T00:00:00Z"

    """保存非内置工具列表到本地 - 增强版本：包含更新日期"""
    def save_local_non_builtin_tools(self):
        local_config_path = self.config_dir / "tool_list_frontend.json"
        try:
            data = {"last_modified": self.last_modified, "tools": self.non_builtin_tools}
            with open(local_config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("Saved local tool list config, updated date: %s", self.last_modified)
        except Exception as e:
            logger.error("Failed to save local tool list: %s", e)

    """从后端更新非内置工具列表 - 增强版本：支持强制更新"""
    def update_non_builtin_tools_from_backend(self, force_update=False):
        # 社区发布版（OSS）不连接后端，直接返回
        if IS_OSS_COMMUNITY_BUILD:
            return
        try:
            with self._tools_data_lock:
                last_modified_param = '1970-01-01T00:00:00Z' if force_update else self.last_modified
            response = requests.get(
                f"{self.backend_url}{API_V1_PREFIX}/tool_list",
                params={'last_modified': last_modified_param, 'frontend_version': self.frontend_version},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'no_change':
                    if force_update:
                        self.status_bar.SetStatusText(translate("status_ready"), 0)
                        self.status_bar.SetStatusText(translate("status_tools_up_to_date"), 1)
                    else:
                        self.status_bar.SetStatusText(translate("status_ready"), 0)
                        self.status_bar.SetStatusText(translate("status_tools_up_to_date"), 1)
                    return
                elif data.get('status') == 'updated':
                    backend_tools = data.get('tools', {})
                    with self._tools_data_lock:
                        self.backend_tools_cache = backend_tools.copy()
                        self.merge_tool_lists(backend_tools)
                        self.last_modified = data.get('last_modified', self.last_modified)
                        self.save_local_non_builtin_tools()
                    self.update_tool_buttons()
                    if force_update:
                        self.status_bar.SetStatusText(translate("status_ready"), 0)
                        self.status_bar.SetStatusText(translate("status_tools_force_updated"), 1)
                    else:
                        self.status_bar.SetStatusText(translate("status_ready"), 0)
                        self.status_bar.SetStatusText(translate("status_tools_updated"), 1)
            else:
                self.status_bar.SetStatusText(translate("status_ready"), 0)
                self.status_bar.SetStatusText(translate("status_backend_error"), 1)
        except requests.exceptions.ConnectionError:
            self.status_bar.SetStatusText(translate("status_ready"), 0)
            if self._is_backend_reachable():
                self.status_bar.SetStatusText(translate("status_network_or_server_error"), 1)
            else:
                self.status_bar.SetStatusText(self._backend_status_text("status_offline_mode"), 1)
        except requests.exceptions.Timeout:
            self.status_bar.SetStatusText(translate("status_ready"), 0)
            if self._is_backend_reachable():
                self.status_bar.SetStatusText(translate("status_connection_timeout_retry"), 1)
            else:
                self.status_bar.SetStatusText(self._backend_status_text("status_offline_mode"), 1)
        except Exception as e:
            self.status_bar.SetStatusText(translate("status_ready"), 0)
            if self._is_backend_reachable():
                self.status_bar.SetStatusText(translate("status_update_tools_failed").format(error=str(e)), 1)
            else:
                self.status_bar.SetStatusText(self._backend_status_text("status_offline_mode"), 1)

    """合并工具列表 - 重构版本：保持与后端一致的顺序并正确管理版本号"""
    def merge_tool_lists(self, backend_tools):
        try:
            from tfp_auth.tfp_permission_manager import permission_manager
            permission_manager.load_feature_permissions_from_tools(backend_tools)
            
            frontend_versions = {}
            for category, tools in self.non_builtin_tools.items():
                for tool in tools:
                    if isinstance(tool, dict) and 'tool_ident' in tool:
                        frontend_versions[tool['tool_ident']] = tool.get('tool_version', '0.0.0')
            logger.debug("Recorded frontend tool version numbers: %s", frontend_versions)
            
            backend_idents = set()
            new_non_builtin_tools = {}
            for category, tools in backend_tools.items():
                if category in ('last_modified', 'version'):
                    continue
                new_non_builtin_tools[category] = []
                for tool in tools:
                    if isinstance(tool, dict) and 'tool_ident' in tool:
                        tool_ident = tool['tool_ident']
                        # tool_ident 格式校验：过滤非法值（防止路径穿越/注入）
                        from tfp_toolkit.tfp_constants import validate_tool_ident_format
                        if not validate_tool_ident_format(tool_ident):
                            logger.error("Backend returned tool_ident has invalid format, skipped: %s", repr(tool_ident))
                            continue
                        new_tool = tool.copy()
                        backend_idents.add(tool_ident)
                        if tool_ident in frontend_versions:
                            new_tool['tool_version'] = frontend_versions[tool_ident]
                        else:
                            new_tool['tool_version'] = '0.0.0'
                            logger.info("New tool %s version set to: 0.0.0", tool_ident)
                        new_non_builtin_tools[category].append(new_tool)
            
            self.non_builtin_tools = new_non_builtin_tools
            logger.info("Merged tool list structure: %s", list(self.non_builtin_tools.keys()))
            for category, tools in self.non_builtin_tools.items():
                logger.debug("Category %s: %d tools", category, len(tools))
        except Exception as e:
            logger.error("Error merging tool lists: %s", e)
            traceback.print_exc()

    """获取本地化的工具标题"""
    def get_localized_tool_title(self, tool_info):
        tool_title = tool_info.get('tool_title', tool_info.get('tool_ident', 'Unknown'))
        if isinstance(tool_title, dict):
            current_lang = i18n.get_language_code()
            return tool_title.get(current_lang, tool_title.get('en', tool_info.get('tool_ident', 'Unknown')))
        return tool_title

    """获取本地化的工具描述"""
    def get_localized_tool_description(self, tool_info):
        tool_description = tool_info.get('tool_description', '')
        if isinstance(tool_description, dict):
            current_lang = i18n.get_language_code()
            return tool_description.get(current_lang, tool_description.get('en', ''))
        return tool_description

    """获取合并后的工具列表"""
    def get_combined_tool_list(self):
        combined = {}
        # 添加内置工具（排除last_modified字段）
        for category, tools in self.builtin_tools.items():
            if category not in ('last_modified', 'version'):
                combined[category] = tools.copy()
        # 添加非内置工具
        for category, tools in self.non_builtin_tools.items():
            if category not in combined: combined[category] = []
            combined[category].extend(tools)
        return combined

    """更新工具按钮"""
    def update_tool_buttons(self):
        self.tool_panels.clear()
        self._focused_panel = None  # 卡片被重建，清除旧焦点引用
        self.tools_grid_sizer.Clear(delete_windows=True)
        combined_tools = self.get_combined_tool_list()
        # 合并所有类别的工具到统一列表
        all_tools = []
        for category, tools in combined_tools.items():
            if category in ('last_modified', 'version') or not isinstance(tools, list):
                continue
            all_tools.extend(tools)
        # 排序规则：置顶工具始终在前(最后置顶的最靠前)，其余按当前排序模式排序
        pinned_idents = set(getattr(self, 'pinned', []))
        _DEFAULT_SORT = 2 ** 31 - 1
        def _sort_order_key(tool_info):
            v = tool_info.get('tool_sort_order')
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return v
            return _DEFAULT_SORT
        mode = getattr(self, 'sort_mode', 'default')
        pinned_tools = [t for t in all_tools if t['tool_ident'] in pinned_idents]
        pinned_tools.sort(key=lambda t: getattr(self, 'pinned', []).index(t['tool_ident']))
        other_tools = [t for t in all_tools if t['tool_ident'] not in pinned_idents]
        if mode == 'name':
            other_tools.sort(key=lambda t: (self.get_localized_tool_title(t).lower(), _sort_order_key(t)))
        elif mode == 'recent':
            # 最近使用降序：近期使用过的靠前；从未使用的排末尾
            other_tools.sort(key=lambda t: self.recent_usage.get(t['tool_ident'], ''), reverse=True)
        elif mode == 'popular':
            # 最多人用降序：按后端热度(使用次数)倒序
            other_tools.sort(key=lambda t: (self.popularity_cache.get(t['tool_ident'], 0), _sort_order_key(t)), reverse=True)
        elif mode == 'type':
            _TYPE_RANK = {'BuiltinProgram': 0, 'RemoteProgram': 1, 'RemoteWebpage': 2}
            other_tools.sort(key=lambda t: (_TYPE_RANK.get(t.get('tool_type'), 99), _sort_order_key(t)))
        elif mode == 'free_local':
            other_tools.sort(key=lambda t: (
                0 if t.get('tool_is_free') else 1,
                0 if t.get('tool_is_local', True) else 1,
                _sort_order_key(t)))
        else:  # 默认：按 tool_sort_order 升序，缺省排末尾
            other_tools.sort(key=_sort_order_key)
        ordered_tools = pinned_tools + other_tools
        for tool_info in ordered_tools:
            self.create_tool_button(self.tools_grid_sizer, self.tools_inner_panel, tool_info)
        self.tools_grid_sizer.Layout()
        self.tools_inner_panel.Layout()
        self.tools_scroll.Layout()
        self.tools_scroll.Refresh()
        self.tools_scroll.Update()
        self.home_panel.Layout()
        self.Layout()
        self.Refresh()
        self.Update()
        self.tools_locked = False

    """获取工具图标"""
    def get_tool_bitmap(self, tool_info):
        tool_ident = tool_info['tool_ident']
        tool_type = tool_info['tool_type']
        
        icon_paths = []
        
        if tool_type == 'BuiltinProgram':
            icon_paths.append(get_resource_path(f"tools_fe/tools_builtin_program/{tool_ident}/app_icon.ico"))
        elif tool_type == 'RemoteProgram':
            icon_paths.append(self.local_tools_dir / f"tools_remote_program/{tool_ident}/app_icon.ico")
        elif tool_type == 'RemoteWebpage':
            icon_paths.append(self.local_tools_dir / f"tools_remote_webpage/{tool_ident}/app_icon.ico")
        
        for icon_path in icon_paths:
            if icon_path.exists():
                try:
                    bitmap = _load_ico_bitmap(icon_path)
                    if bitmap and bitmap.IsOk():
                        return bitmap
                except Exception as e:
                    logger.warning("Failed to load tool icon %s: %s", icon_path, e)
        
        default_icon_path = get_resource_path("config/default_icon.ico")
        if default_icon_path.exists():
            try:
                bitmap = _load_ico_bitmap(default_icon_path)
                if bitmap and bitmap.IsOk():
                    return bitmap
            except Exception as e:
                logger.warning("Failed to load default icon %s: %s", default_icon_path, e)
        
        return None

    """锁定所有工具方块"""
    def lock_all_tools(self):
        self.tools_locked = True
        for panel in self.tool_panels:
            if panel:
                panel.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
                panel.Enable(False)
    
    """解锁所有工具方块"""
    def unlock_all_tools(self):
        self.tools_locked = False
        for panel in self.tool_panels:
            if panel:
                panel.SetCursor(wx.Cursor(wx.CURSOR_HAND))
                panel.Enable(True)
        # 工具启动流程结束（就绪/超时/失败）时清除"正在打开"提示
        self._clear_tools_launch_indicator()

    """按 tool_ident 查找工具卡片面板"""
    def _find_tool_panel_by_ident(self, tool_ident):
        if not tool_ident:
            return None
        for panel in self.tool_panels:
            if panel is not None and getattr(panel, 'tool_info', {}).get('tool_ident') == tool_ident:
                return panel
        return None

    """显示子工具"正在打开"提示（状态栏 + 卡片标题），并立即重绘
    确保进程内加载（BuiltinProgram）阻塞主线程前用户已能看到提示"""
    def _set_tools_launch_indicator(self, tool_info):
        tool_ident = tool_info.get('tool_ident', '')
        tool_name = self.get_localized_tool_title(tool_info)
        self._launching_tool_ident = tool_ident
        try:
            self.status_bar.SetStatusText(translate("status_opening_tool", tool_name=tool_name), 0)
        except Exception:
            pass
        try:
            self.SetCursor(wx.Cursor(wx.CURSOR_WAIT))
        except Exception:
            pass
        panel = self._find_tool_panel_by_ident(tool_ident)
        if panel is not None and getattr(panel, 'title_label', None) is not None:
            panel.title_label.SetLabel(translate("card_opening"))
            panel.Layout()
            panel.Refresh()
        # 强制处理待绘制的界面事件，保证阻塞型加载前的提示立即可见
        wx.Yield()

    """清除子工具"正在打开"提示，恢复状态栏/卡片标题/光标"""
    def _clear_tools_launch_indicator(self):
        tool_ident = self._launching_tool_ident
        if not tool_ident:
            return
        self._launching_tool_ident = None
        try:
            self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))
        except Exception:
            pass
        try:
            self.status_bar.SetStatusText(translate("status_ready"), 0)
        except Exception:
            pass
        panel = self._find_tool_panel_by_ident(tool_ident)
        if panel is not None and getattr(panel, 'title_label', None) is not None:
            panel.title_label.SetLabel(getattr(panel, 'title_text', ''))
            panel.Layout()
            panel.Refresh()
    
    """创建工具按钮"""
    def create_tool_button(self, parent_sizer, parent_panel, tool_info):
        localized_title = self.get_localized_tool_title(tool_info)
        localized_description = self.get_localized_tool_description(tool_info)
        
        panel = wx.Panel(parent_panel, size=(self.spx_calc(154), self.spx_calc(121)))
        panel.tool_info = tool_info

        # RemoteWebpage与RemoteProgram使用相同颜色
        colors = {
            'BuiltinProgram': '#E1F5FE',
            'RemoteProgram': '#FFEBEE',
            'RemoteWebpage': '#FFEBEE',
        }
        hover_colors = {
            'BuiltinProgram': '#B3E5FC',
            'RemoteProgram': '#FFCDD2',
            'RemoteWebpage': '#FFCDD2',
        }
        border_colors = {
            'BuiltinProgram': '#90CAF9',
            'RemoteProgram': '#EF9A9A',
            'RemoteWebpage': '#EF9A9A',
        }
        bg_color = colors.get(tool_info['tool_type'], wx.WHITE)
        hover_bg_color = hover_colors.get(tool_info['tool_type'], '#F5F5F5')
        border_color = border_colors.get(tool_info['tool_type'], '#CCCCCC')
        panel.SetBackgroundColour(bg_color)
        panel.border_color = border_color
        panel.bg_color = bg_color
        panel.hover_bg_color = hover_bg_color
        panel._hover = False
        panel._pressed = False
        panel._focused = False  # 键盘焦点效果（显示与鼠标悬停相同）
        panel._pinned = tool_info.get('tool_ident', '') in getattr(self, 'pinned', [])  # 是否被置顶
        # 保存工具名称用于日志
        panel._tool_name = localized_title

        # 自绘边框（支持hover/focus加粗3px + 背景色变化 + pressed缩小）
        def on_panel_paint(evt, p=panel, bc=border_color, bgc=bg_color, hbgc=hover_bg_color):
            dc = wx.PaintDC(p)
            _active = p._hover or getattr(p, '_focused', False)
            current_bg = hbgc if _active else bgc
            dc.SetBackground(wx.Brush(wx.Colour(current_bg)))
            dc.Clear()
            p.SetBackgroundColour(wx.Colour(current_bg))
            rect = p.GetClientRect()
            # 防止未布局完成(尺寸为0)时绘制负宽高矩形，触发 pixman "Invalid rectangle" 警告
            if rect.width <= 0 or rect.height <= 0:
                return
            pen_width = 3 if _active else 1
            dc.SetPen(wx.Pen(wx.Colour(bc), pen_width))
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            offset = pen_width // 2
            dc.DrawRectangle(offset, offset, rect.width - pen_width, rect.height - pen_width)
            # 置顶标记：右上角绘制一个小巧的灰色"带圆圈P"（圆圈 + 字母P，跨语言可靠显示）
            if getattr(p, '_pinned', False) and p.IsShown():
                _p_margin_r = self.spx_calc(8)   # 离右边框距离 = 之前的2倍
                _p_margin_t = self.spx_calc(6)   # 离上边框距离 = 之前的1.5倍
                _p_font = wx.Font(self.spx_calc(5), wx.FONTFAMILY_DEFAULT,
                                  wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
                dc.SetFont(_p_font)
                _tw, _th, _td, _tl = dc.GetFullTextExtent('P')
                _p_d = max(_tw, _th) + self.spx_calc(1)   # 圆圈直径（缩到约原来的1/2~2/3）
                _p_x = rect.width - _p_margin_r - _p_d
                _p_y = _p_margin_t
                # 圆圈
                dc.SetPen(wx.Pen(wx.Colour('#9E9E9E'), 1))
                dc.SetBrush(wx.TRANSPARENT_BRUSH)
                dc.DrawCircle(int(_p_x + _p_d / 2.0), int(_p_y + _p_d / 2.0), int(_p_d / 2.0))
                # 圈内居中的字母 P
                dc.SetTextForeground(wx.Colour('#757575'))
                dc.DrawText('P', int(_p_x + (_p_d - _tw) / 2.0), int(_p_y + (_p_d - _th) / 2.0))

        panel.Bind(wx.EVT_PAINT, on_panel_paint)
        # 原生焦点到达/离开卡片时，同步维护聚焦状态
        panel.Bind(wx.EVT_SET_FOCUS, lambda e, p=panel: self._on_panel_kb_focus(p))
        panel.Bind(wx.EVT_KILL_FOCUS, lambda e, p=panel: self._on_panel_kb_kill_focus(p))

        # Hover效果：边框加粗3px；点击缩小90%
        # 不使用Move（会导致WrapSizer重排卡片位置），仅通过边框加粗表示hover
        panel._hover_timer = None

        def check_hover(p=panel):
            """检查鼠标是否仍在panel区域内"""
            tool_name = getattr(p, '_tool_name', '?')
            if not p or not p.IsShownOnScreen():
                # 即使不可见，也要重置hover状态，防止下次显示时残留错误状态
                if p and hasattr(p, '_hover') and p._hover:
                    logger.info("[HOVER_DIAG] check_hover: panel=%s IsShownOnScreen=False, reset hover=False", tool_name)
                    p._hover = False
                else:
                    logger.info("[HOVER_DIAG] check_hover: panel=%s IsShownOnScreen=False, hover already False", tool_name)
                p._hover_timer = None
                return
            mouse_pos = wx.GetMousePosition()
            screen_rect = p.GetScreenRect()
            if screen_rect.Contains(mouse_pos):
                if not p._hover:
                    logger.info("[HOVER_DIAG] check_hover: panel=%s mouse in range, setting hover=True", tool_name)
                    p._hover = True
                    p.Refresh()
                else:
                    logger.info("[HOVER_DIAG] check_hover: panel=%s mouse in range, hover already True", tool_name)
            else:
                if p._hover:
                    logger.info("[HOVER_DIAG] check_hover: panel=%s mouse out of range, setting hover=False", tool_name)
                    p._hover = False
                    p.Refresh()
                else:
                    logger.info("[HOVER_DIAG] check_hover: panel=%s mouse out of range, hover already False", tool_name)
            p._hover_timer = None

        def on_enter(evt, p=panel):
            tool_name = getattr(p, '_tool_name', '?')
            logger.info("[HOVER_DIAG] on_enter: panel=%s current hover=%s", tool_name, p._hover)
            # 保险逻辑：先检查并还原其他卡片的hover状态，防止出现多个卡片同时高亮
            for other_panel in self.tool_panels:
                if other_panel and other_panel is not p and hasattr(other_panel, '_hover') and other_panel._hover:
                    other_tool_name = getattr(other_panel, '_tool_name', '?')
                    logger.info("[HOVER_DIAG] on_enter: restoring hover state of other card %s", other_tool_name)
                    other_panel._hover = False
                    other_panel.Refresh()
            if p._hover_timer is None:
                p._hover_timer = wx.CallLater(10, check_hover, p)
            evt.Skip()

        def on_leave(evt, p=panel):
            tool_name = getattr(p, '_tool_name', '?')
            logger.info("[HOVER_DIAG] on_leave: panel=%s current hover=%s", tool_name, p._hover)
            if p._hover_timer is None:
                p._hover_timer = wx.CallLater(10, check_hover, p)
            evt.Skip()

        def on_left_down(evt, p=panel):
            p._pressed = True
            p._original_size = p.GetSize()
            new_w = int(p._original_size.width * 0.9)
            new_h = int(p._original_size.height * 0.9)
            p.SetSize((new_w, new_h))
            p.Refresh()
            evt.Skip()

        def on_left_up(evt, p=panel):
            p._pressed = False
            if hasattr(p, '_original_size'):
                p.SetSize(p._original_size)
            p.Refresh()
            evt.Skip()

        panel.Bind(wx.EVT_ENTER_WINDOW, on_enter)
        panel.Bind(wx.EVT_LEAVE_WINDOW, on_leave)
        panel.Bind(wx.EVT_LEFT_DOWN, on_left_down)
        panel.Bind(wx.EVT_LEFT_UP, on_left_up)

        sizer = wx.BoxSizer(wx.VERTICAL)

        bitmap = self.get_tool_bitmap(tool_info)
        if bitmap and bitmap.IsOk():
            image = bitmap.ConvertToImage()
            icon_logical_size = 40
            icon_phys_size = self.spx_calc(icon_logical_size)
            image = image.Scale(icon_phys_size, icon_phys_size, wx.IMAGE_QUALITY_HIGH)
            # Linux python3-wxgtk4.0(wxPython 4.2.1 gtk3) 渲染带"每像素alpha通道"的
            # 位图(尤其是半透明渐变边缘)时无法正确合成，主界面子工具卡片图标显示为
            # 噪点/色块；而 Windows pip wxPython 4.2.4 能正确合成。将 alpha 按卡片背景色
            # 合成为完全不透明的 RGB 图像，彻底绕开 alpha 混合，保证跨平台渲染一致。
            if image.HasAlpha():
                bg = wx.Colour(bg_color)
                bg_r = bg.Red()
                bg_g = bg.Green()
                bg_b = bg.Blue()
                flat = wx.Image(image.GetWidth(), image.GetHeight())
                for y in range(image.GetHeight()):
                    for x in range(image.GetWidth()):
                        a = image.GetAlpha(x, y) / 255.0
                        flat.SetRGB(x, y,
                            int(round(image.GetRed(x, y) * a + bg_r * (1.0 - a))),
                            int(round(image.GetGreen(x, y) * a + bg_g * (1.0 - a))),
                            int(round(image.GetBlue(x, y) * a + bg_b * (1.0 - a))))
                image = flat
            scaled_bitmap = wx.Bitmap(image)
            if self.TFP_DPI_SCALE_FACTOR > 1.0:
                scaled_bitmap.SetScaleFactor(self.TFP_DPI_SCALE_FACTOR)
            icon_static = wx.StaticBitmap(panel, bitmap=scaled_bitmap)
            sizer.Add(icon_static, 0, wx.ALIGN_CENTER | wx.TOP, self.spx_calc(12))

        label = wx.StaticText(panel, label=localized_title, style=wx.ST_ELLIPSIZE_END | wx.ALIGN_CENTER_HORIZONTAL)
        label.SetMinSize(wx.Size(self.spx_calc(132), -1))
        label.SetMaxSize(wx.Size(self.spx_calc(132), -1))
        sizer.Add(label, 0, wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT | wx.TOP, self.spx_calc(6))
        # 记录标题控件与原文，供"正在打开"提示临时替换后恢复
        panel.title_label = label
        panel.title_text = localized_title

        # 标签：胶囊外框+简短文字
        tags_sizer = wx.BoxSizer(wx.HORIZONTAL)
        tags_sizer.AddStretchSpacer()

        is_open_source = tool_info.get('tool_is_open_source', False)
        is_free = tool_info.get('tool_is_free', False)
        is_local = tool_info.get('tool_is_local', True)

        # 统一标签样式：浅灰背景+深灰文字+灰色边框
        # 注：背景色保持固定，因为wxPython的透明背景在Windows上有兼容性问题
        tag_style = {'bg': (235, 235, 235), 'fg': (90, 90, 90), 'border': (180, 180, 180)}

        def create_styled_tag(parent, text):
            tag_panel = wx.Panel(parent, size=(-1, self.spx_calc(18)), style=wx.BORDER_NONE)
            tag_panel.SetBackgroundColour(wx.Colour(*tag_style['bg']))

            tag_sizer = wx.BoxSizer(wx.HORIZONTAL)
            tag_label = wx.StaticText(tag_panel, label=text)
            tag_label.SetForegroundColour(wx.Colour(*tag_style['fg']))
            tag_label.SetFont(wx.Font(7, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
            tag_sizer.Add(tag_label, 0, wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT, self.spx_calc(5))
            tag_panel.SetSizer(tag_sizer)

            def on_paint(evt):
                dc = wx.PaintDC(tag_panel)
                dc.SetBackground(wx.Brush(wx.Colour(*tag_style['bg'])))
                dc.Clear()
                rect = tag_panel.GetClientRect()
                # 防止未布局完成(尺寸为0)时绘制负宽高矩形，触发 pixman "Invalid rectangle" 警告
                if rect.width <= 0 or rect.height <= 0:
                    return
                dc.SetPen(wx.Pen(wx.Colour(*tag_style['border']), 1))
                dc.SetBrush(wx.Brush(wx.Colour(*tag_style['bg'])))
                # 使用很小的圆角(2px)，减少与卡片背景色的视觉冲突
                dc.DrawRoundedRectangle(rect.x, rect.y, rect.width - 1, rect.height - 1, 2)

            tag_panel.Bind(wx.EVT_PAINT, on_paint)
            tag_panel.Bind(wx.EVT_LEFT_DOWN, lambda e, t=tool_info: self.on_tool_panel_click_safe(t))
            tag_label.Bind(wx.EVT_LEFT_DOWN, lambda e, t=tool_info: self.on_tool_panel_click_safe(t))
            return tag_panel

        if is_open_source:
            tags_sizer.Add(create_styled_tag(panel, translate('label_tag_open')), 0, wx.ALIGN_CENTER | wx.RIGHT, self.spx_calc(3))

        if is_free:
            tags_sizer.Add(create_styled_tag(panel, translate('label_tag_free')), 0, wx.ALIGN_CENTER | wx.RIGHT, self.spx_calc(3))
        else:
            tags_sizer.Add(create_styled_tag(panel, translate('label_tag_paid')), 0, wx.ALIGN_CENTER | wx.RIGHT, self.spx_calc(3))

        if is_local:
            tags_sizer.Add(create_styled_tag(panel, translate('label_tag_local')), 0, wx.ALIGN_CENTER | wx.RIGHT, self.spx_calc(3))
        else:
            tags_sizer.Add(create_styled_tag(panel, translate('label_tag_cloud')), 0, wx.ALIGN_CENTER | wx.RIGHT, self.spx_calc(3))

        # 升级标签：当检测到版本更新时显示
        tool_ident = tool_info.get('tool_ident', '')
        if tool_ident in self._tools_with_update:
            upgrade_tag = wx.Panel(panel, size=(-1, self.spx_calc(18)), style=wx.BORDER_NONE)
            upgrade_tag.SetBackgroundColour(wx.Colour(255, 243, 224))  # 浅橙色背景

            upgrade_sizer = wx.BoxSizer(wx.HORIZONTAL)
            upgrade_label = wx.StaticText(upgrade_tag, label=translate('label_tag_upgrade'))
            upgrade_label.SetForegroundColour(wx.Colour(230, 81, 0))  # 深橙色文字
            upgrade_label.SetFont(wx.Font(7, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
            upgrade_sizer.Add(upgrade_label, 0, wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT, self.spx_calc(5))
            upgrade_tag.SetSizer(upgrade_sizer)

            def on_upgrade_tag_paint(evt, p=upgrade_tag):
                dc = wx.PaintDC(p)
                dc.SetBackground(wx.Brush(wx.Colour(255, 243, 224)))
                dc.Clear()
                rect = p.GetClientRect()
                # 防止未布局完成(尺寸为0)时绘制负宽高矩形，触发 pixman "Invalid rectangle" 警告
                if rect.width <= 0 or rect.height <= 0:
                    return
                dc.SetPen(wx.Pen(wx.Colour(255, 152, 0), 1))  # 橙色边框
                dc.SetBrush(wx.Brush(wx.Colour(255, 243, 224)))
                dc.DrawRoundedRectangle(rect.x, rect.y, rect.width - 1, rect.height - 1, 2)

            upgrade_tag.Bind(wx.EVT_PAINT, on_upgrade_tag_paint)
            upgrade_tag.Bind(wx.EVT_LEFT_DOWN, lambda e, t=tool_info: self.on_tool_upgrade_click(t))
            upgrade_label.Bind(wx.EVT_LEFT_DOWN, lambda e, t=tool_info: self.on_tool_upgrade_click(t))
            tags_sizer.Add(upgrade_tag, 0, wx.ALIGN_CENTER | wx.RIGHT, self.spx_calc(3))

        tags_sizer.AddStretchSpacer()
        sizer.Add(tags_sizer, 0, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, self.spx_calc(8))

        panel.SetSizer(sizer)

        # 工具提示
        tip_text = f"{localized_description}\n{translate('label_type')}: {tool_info['tool_type']}\n{translate('label_version')}: {tool_info.get('tool_version', '1.0.0')}"
        panel.SetToolTip(wx.ToolTip(tip_text))

        panel.SetCursor(wx.Cursor(wx.CURSOR_HAND))

        panel.Bind(wx.EVT_LEFT_DOWN, lambda e, t=tool_info: self.on_tool_panel_click_safe(t))
        # 右键菜单：收藏/取消收藏
        panel.Bind(wx.EVT_CONTEXT_MENU, lambda e, t=tool_info, p=panel: self.on_tool_context_menu(e, t, p))
        # 子控件也绑定hover/tooltip/点击/右键，使整个卡片行为一致
        for child in panel.GetChildren():
            child.SetCursor(wx.Cursor(wx.CURSOR_HAND))
            child.SetToolTip(wx.ToolTip(tip_text))
            child.Bind(wx.EVT_LEFT_DOWN, lambda e, t=tool_info: self.on_tool_panel_click_safe(t))
            child.Bind(wx.EVT_CONTEXT_MENU, lambda e, t=tool_info, p=panel: self.on_tool_context_menu(e, t, p))
            # 子控件的enter/leave转发到父panel以触发hover效果
            child.Bind(wx.EVT_ENTER_WINDOW, lambda e, p=panel: on_enter(e, p))
            child.Bind(wx.EVT_LEAVE_WINDOW, lambda e, p=panel: on_leave(e, p))
            # 标签面板的子控件也需要转发
            if isinstance(child, wx.Panel):
                for sub_child in child.GetChildren():
                    sub_child.SetCursor(wx.Cursor(wx.CURSOR_HAND))
                    sub_child.SetToolTip(wx.ToolTip(tip_text))
                    sub_child.Bind(wx.EVT_LEFT_DOWN, lambda e, t=tool_info: self.on_tool_panel_click_safe(t))
                    sub_child.Bind(wx.EVT_CONTEXT_MENU, lambda e, t=tool_info, p=panel: self.on_tool_context_menu(e, t, p))
                    sub_child.Bind(wx.EVT_ENTER_WINDOW, lambda e, p=panel: on_enter(e, p))
                    sub_child.Bind(wx.EVT_LEAVE_WINDOW, lambda e, p=panel: on_leave(e, p))

        self.tool_panels.append(panel)

        parent_sizer.Add(panel, 0, wx.ALL, self.spx_calc(5))
    
    """安全的工具面板点击事件，检查锁定状态"""
    def on_tool_upgrade_click(self, tool_info):
        """点击升级标签：重启工具以应用更新"""
        tool_ident = tool_info.get('tool_ident', '')
        tool_type = tool_info.get('tool_type', '')
        local_tool = self._find_tool_by_ident(tool_ident)
        local_version = local_tool.get('tool_version', '?') if local_tool else '?'
        backend_version = tool_info.get('tool_version', '?')

        msg = translate("upgrade_confirm_message",
                        tool_name=self.get_localized_tool_title(tool_info),
                        local_version=local_version,
                        backend_version=backend_version)
        dlg = wx.MessageDialog(self, msg, translate("upgrade_confirm_title"),
                               wx.YES_NO | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_YES:
            # 关闭当前运行的工具窗口
            if tool_ident in self.open_tool_windows:
                try:
                    self._close_tool_window(tool_ident)
                except Exception as e:
                    logger.warning("Failed to close tool window: %s", e)
            # 从升级列表中移除
            self._tools_with_update.discard(tool_ident)
            # 重新启动工具
            self.on_tool_panel_click_safe(tool_info)
        dlg.Destroy()

    def on_tool_panel_click_safe(self, tool_info):
        if self.tools_locked:
            return
        self.lock_all_tools()
        self._set_tools_launch_indicator(tool_info)
        try:
            success = self.on_tool_panel_click(tool_info)
            if not success:
                self.unlock_all_tools()
        except Exception as e:
            self.unlock_all_tools()
            wx.MessageBox(translate("message_run_tool_error").format(error=str(e)), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)

    """工具面板点击事件，返回是否成功启动工具"""
    def on_tool_panel_click(self, tool_info) -> bool:
        tool_type = tool_info['tool_type']
        # 记录该工具的本地最近使用时间（用于"最近使用"排序，不阻塞/不立即重建卡片）
        self._record_recent_usage(tool_info.get('tool_ident', ''))
        if tool_type == 'BuiltinProgram':
            return self.run_builtin_program(tool_info)
        elif tool_type == 'RemoteProgram':
            return self.run_remote_program(tool_info)
        elif tool_type == 'RemoteWebpage':
            return self.run_remote_webpage(tool_info)
        return False

    """工具按钮点击事件"""
    def on_tool_click(self, event):
        btn = event.GetEventObject()
        tool_info = btn.tool_info
        tool_type = tool_info['tool_type']
        try:
            if tool_type == 'BuiltinProgram':
                self.run_builtin_program(tool_info)
            elif tool_type in ('RemoteProgram', 'RemoteWebpage'):
                if not self._is_backend_reachable():
                    wx.MessageBox(translate("message_offline_remote_tool_unavailable"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
                    return
                if tool_type == 'RemoteProgram':
                    self.run_remote_program(tool_info)
                else:
                    self.run_remote_webpage(tool_info)
        except Exception as e:
            wx.MessageBox(translate("message_run_tool_error").format(error=str(e)), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)

    """Ctrl+F聚焦搜索框"""
    def on_search_focus(self, event):
        self.show_home_panel()
        self.search_ctrl.SetFocus()

    """EVT_CHAR_HOOK处理：确保Ctrl+F在任何焦点状态下都能聚焦搜索框，
    并统一处理Tab/Shift+Tab焦点导航与回车打开/聚焦工具卡片"""
    def _on_char_hook(self, event):
        modifiers = event.GetModifiers()
        key = event.GetKeyCode()
        # Ctrl+F 聚焦搜索框
        if modifiers == wx.MOD_CONTROL and key == ord('F'):
            self.on_search_focus(event)
            return
        if key == wx.WXK_ESCAPE and self.search_ctrl.HasFocus():
            self.search_ctrl.Clear()
            return
        if self._handle_nav_key(key, modifiers):
            return  # 已处理（Tab导航 / 回车）
        event.Skip()

    """搜索框按键事件：Esc清空；Tab/回车统一走焦点导航逻辑"""
    def on_search_key_down(self, event):
        key = event.GetKeyCode()
        modifiers = event.GetModifiers()
        if key == wx.WXK_ESCAPE:
            self.search_ctrl.Clear()
            return
        if self._handle_nav_key(key, modifiers):
            return
        event.Skip()

    """统一的Tab/回车键处理逻辑，返回True表示事件已被消耗"""
    def _handle_nav_key(self, key, modifiers):
        if key == wx.WXK_TAB:
            self._focus_navigate(backward=bool(modifiers & wx.MOD_SHIFT))
            return True
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            return self._handle_enter()
        return False

    """回车键处理：聚焦卡片→打开；搜索框→聚焦第一个匹配卡片(无匹配则全选)"""
    def _handle_enter(self):
        if self._focused_panel is not None and self._focused_panel.IsShown():
            tool_info = self._focused_panel.tool_info
            self.on_tool_panel_click_safe(tool_info)
            return True
        if self.search_ctrl.HasFocus():
            first_visible = self._get_first_visible_panel()
            if first_visible is not None:
                self._set_focused_panel(first_visible)
            else:
                self.search_ctrl.SetSelection(-1, -1)
            return True
        return False

    """返回当前显示（匹配搜索）的第一张工具卡片，无则None"""
    def _get_first_visible_panel(self):
        for panel in self.tool_panels:
            if panel and panel.IsShown():
                return panel
        return None

    """主界面启动后不聚焦任何控件：清除卡片聚焦效果，并把焦点置于窗口本身。
    GTK 下顶层窗口默认不可聚焦，直接 SetFocus() 会落到首个可聚焦子控件（如搜索框），
    故需先将窗口设为可聚焦；Windows 上 SetCanFocus 为无操作，SetFocus() 即聚焦窗口本身。"""
    def _clear_home_default_focus(self):
        self._clear_focused_panel()
        try:
            self.SetCanFocus(True)  # GTK 需要；非 GTK 平台无操作
            self.SetFocus()
        except Exception as e:  # 兜底：极端情况下不影响启动
            logger.debug("Clear home default focus failed: %s", e)

    """按Tab导航顺序返回当前主页的焦点目标列表（隐藏的卡片跳过）"""
    def _get_focus_targets(self):
        targets = [self.fav_button, self.search_ctrl, self.search_icon_btn, self.sort_button]
        for panel in self.tool_panels:
            if panel and panel.IsShown():
                targets.append(panel)
        return targets

    """判断当前焦点目标在导航列表中的索引"""
    def _get_current_focus_index(self, targets):
        if not targets:
            return -1
        # 优先使用手动维护的卡片焦点状态（GTK上卡片不总能保持原生焦点）
        if self._focused_panel in targets:
            return targets.index(self._focused_panel)
        focused = self.FindFocus()
        if focused in targets:
            return targets.index(focused)
        return -1  # -1 表示当前无导航目标获得焦点（如焦点在主窗口本身）

    """将焦点设置到指定目标（收藏按钮/搜索框/搜索按钮/工具卡片）"""
    def _focus_target(self, target):
        if target in self.tool_panels:
            self._set_focused_panel(target)
        else:
            self._clear_focused_panel()
            target.SetFocus()

    """Tab/Shift+Tab 在导航目标间循环切换焦点"""
    def _focus_navigate(self, backward=False):
        targets = self._get_focus_targets()
        if not targets:
            return
        cur_idx = self._get_current_focus_index(targets)
        if cur_idx < 0:
            # 当前无导航目标获得焦点：正向从第一个目标开始，反向从最后一个目标开始
            next_idx = len(targets) - 1 if backward else 0
        else:
            delta = -1 if backward else 1
            next_idx = (cur_idx + delta) % len(targets)
        self._focus_target(targets[next_idx])

    """将某张工具卡片设为键盘焦点，并显示与鼠标悬停相同的效果"""
    def _set_focused_panel(self, panel):
        for p in self.tool_panels:
            if p is not None and p is not panel and getattr(p, '_focused', False):
                p._focused = False
                p.Refresh()  # 立即重绘被取消焦点的卡片
        panel._focused = True
        self._focused_panel = panel
        panel.SetFocus()
        panel.Refresh()

    """清除当前工具卡片的聚焦效果"""
    def _clear_focused_panel(self):
        if self._focused_panel is not None:
            self._focused_panel._focused = False
            self._focused_panel.Refresh()
            self._focused_panel = None

    """原生焦点到达工具卡片时，同步显示聚焦效果"""
    def _on_panel_kb_focus(self, panel):
        self._set_focused_panel(panel)

    """原生焦点离开工具卡片时，清除聚焦效果"""
    def _on_panel_kb_kill_focus(self, panel):
        panel._focused = False
        panel.Refresh()
        if self._focused_panel is panel:
            self._focused_panel = None

    """顶部固定控件（收藏按钮/搜索框/搜索按钮）获得焦点时，清除卡片聚焦状态"""
    def _on_home_control_focus(self, event):
        self._clear_focused_panel()
        event.Skip()

    """搜索/收藏按钮上的Tab键处理，其余按键交回默认行为"""
    def _on_control_key_down(self, event):
        if event.GetKeyCode() == wx.WXK_TAB:
            self._focus_navigate(backward=bool(event.GetModifiers() & wx.MOD_SHIFT))
            return
        event.Skip()

    """搜索栏文本变化事件：实时过滤工具卡片"""
    def on_search_text_changed(self, event):
        keyword = self.search_ctrl.GetValue().strip().lower()
        visible_count = 0
        for panel in self.tool_panels:
            if not panel or not hasattr(panel, 'tool_info'):
                continue
            tool_info = panel.tool_info
            if not keyword:
                panel.Show()
                visible_count += 1
                continue
            # 搜索范围：工具名称 + 描述 + 标签
            title = self.get_localized_tool_title(tool_info).lower()
            desc = self.get_localized_tool_description(tool_info).lower()
            tags_text = ""
            if tool_info.get('tool_is_open_source'):
                tags_text += translate('label_open_source').lower() + " "
            if tool_info.get('tool_is_free'):
                tags_text += translate('label_free').lower() + " "
            else:
                tags_text += translate('label_paid').lower() + " "
            if tool_info.get('tool_is_local', True):
                tags_text += translate('label_local').lower() + " "
            else:
                tags_text += translate('label_cloud').lower() + " "
            match = keyword in title or keyword in desc or keyword in tags_text
            panel.Show(match)
            if match:
                visible_count += 1
        # 空状态提示
        if keyword and visible_count == 0:
            self.empty_state_panel.Show()
        else:
            self.empty_state_panel.Hide()
        # 若当前聚焦的卡片因过滤被隐藏，清除其聚焦状态
        if self._focused_panel is not None and not self._focused_panel.IsShown():
            self._clear_focused_panel()
        self.tools_grid_sizer.Layout()
        self.tools_inner_panel.Layout()
        self.tools_scroll.Layout()
        self.home_panel.Layout()

    """收藏按钮点击：弹出下拉菜单显示已收藏工具"""
    def on_fav_button_click(self, event):
        # 未登录时弹出登录提示；OSS 社区版离线也可用本地收藏，无需登录
        if not self._favorites_available():
            from tfp_auth import TFP_LoginRequiredDialog
            dlg = TFP_LoginRequiredDialog(self, feature_name=translate("label_favorite_tools"))
            dlg.ShowModal()
            dlg.Destroy()
            return
        menu = wx.Menu()
        if not self.favorites:
            item = menu.Append(wx.ID_ANY, translate("label_no_favorites"))
            menu.Enable(item.GetId(), False)
        else:
            combined_tools = self.get_combined_tool_list()
            all_tools = []
            for category, tools in combined_tools.items():
                if category in ('last_modified', 'version') or not isinstance(tools, list):
                    continue
                all_tools.extend(tools)
            for fav_ident in self.favorites:
                for tool_info in all_tools:
                    if tool_info.get('tool_ident') == fav_ident:
                        title = self.get_localized_tool_title(tool_info)
                        menu_item = menu.Append(wx.ID_ANY, title)
                        self.Bind(wx.EVT_MENU, lambda e, t=tool_info: self.on_tool_panel_click_safe(t), menu_item)
                        break
        # 分隔线 + 管理收藏
        menu.AppendSeparator()
        manage_item = menu.Append(wx.ID_ANY, translate("label_manage_favorites") + "...")
        self.Bind(wx.EVT_MENU, lambda e: self.on_manage_favorites(), manage_item)
        # 弹出菜单在按钮下方
        btn_pos = self.fav_button.ClientToScreen((0, self.fav_button.GetSize().height))
        self.PopupMenu(menu, self.ScreenToClient(btn_pos))
        menu.Destroy()

    """管理收藏对话框"""
    def on_manage_favorites(self):
        if not self.favorites:
            wx.MessageBox(translate("label_no_favorites"), translate("label_favorite_tools"), wx.OK | wx.ICON_INFORMATION)
            return
        combined_tools = self.get_combined_tool_list()
        all_tools = []
        for category, tools in combined_tools.items():
            if category in ('last_modified', 'version') or not isinstance(tools, list):
                continue
            all_tools.extend(tools)
        # 构建收藏工具名称列表
        fav_titles = []
        fav_idents_copy = list(self.favorites)
        for fav_ident in fav_idents_copy:
            found = False
            for tool_info in all_tools:
                if tool_info.get('tool_ident') == fav_ident:
                    fav_titles.append(self.get_localized_tool_title(tool_info))
                    found = True
                    break
            if not found:
                fav_titles.append(fav_ident)
        dlg = wx.Dialog(self, title=translate("label_manage_favorites"), size=(self.spx_calc(360), self.spx_calc(320)))
        dlg.SetFont(self.GetFont())
        sizer = wx.BoxSizer(wx.VERTICAL)
        # 说明文字
        hint = wx.StaticText(dlg, label=translate("label_manage_favorites_hint"))
        sizer.Add(hint, 0, wx.ALL, self.spx_calc(10))
        # 列表框
        self._fav_listbox = wx.ListBox(dlg, choices=fav_titles, style=wx.LB_SINGLE)
        self._fav_listbox.SetSelection(0)
        sizer.Add(self._fav_listbox, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, self.spx_calc(10))
        # 按钮行
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        close_btn = wx.Button(dlg, wx.ID_CLOSE, label=translate("button_close"))
        close_btn.Bind(wx.EVT_BUTTON, lambda e: dlg.EndModal(wx.ID_CANCEL))
        btn_sizer.Add(close_btn, 0, wx.RIGHT, self.spx_calc(8))
        remove_btn = wx.Button(dlg, label=translate("label_remove_from_favorites"))
        remove_btn.Bind(wx.EVT_BUTTON, lambda e: self._on_remove_favorite_from_dialog(dlg, fav_idents_copy))
        btn_sizer.Add(remove_btn, 0)
        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, self.spx_calc(10))
        dlg.SetSizer(sizer)
        dlg.Centre()
        dlg.ShowModal()
        dlg.Destroy()

    """从管理收藏对话框中移除选中项"""
    def _on_remove_favorite_from_dialog(self, dialog, fav_idents_copy):
        sel = self._fav_listbox.GetSelection()
        if sel == wx.NOT_FOUND:
            return
        ident_to_remove = fav_idents_copy[sel]
        self._remove_favorite(ident_to_remove)
        # 同步更新列表
        del fav_idents_copy[sel]
        self._fav_listbox.Delete(sel)
        if self._fav_listbox.GetCount() > 0:
            self._fav_listbox.SetSelection(min(sel, self._fav_listbox.GetCount() - 1))
        if self._fav_listbox.GetCount() == 0:
            dialog.EndModal(wx.ID_CANCEL)

    """工具卡片右键菜单：添加/移除收藏"""
    def on_tool_context_menu(self, event, tool_info, panel):
        menu = wx.Menu()
        tool_ident = tool_info.get('tool_ident', '')
        if not self._favorites_available():
            item = menu.Append(wx.ID_ANY, translate("label_add_to_favorites"))
            menu.Enable(item.GetId(), False)
        elif tool_ident in self.favorites:
            item = menu.Append(wx.ID_ANY, translate("label_remove_from_favorites"))
            self.Bind(wx.EVT_MENU, lambda e, tid=tool_ident: self._remove_favorite(tid), item)
        else:
            item = menu.Append(wx.ID_ANY, translate("label_add_to_favorites"))
            self.Bind(wx.EVT_MENU, lambda e, tid=tool_ident: self._add_favorite(tid), item)
        # 置顶/取消置顶（无需登录，OSS也可用）
        menu.AppendSeparator()
        if tool_ident in getattr(self, 'pinned', []):
            pin_item = menu.Append(wx.ID_ANY, translate("label_unpin_tool"))
            self.Bind(wx.EVT_MENU, lambda e, tid=tool_ident: self._unpin_tool(tid), pin_item)
        else:
            pin_item = menu.Append(wx.ID_ANY, translate("label_pin_tool"))
            self.Bind(wx.EVT_MENU, lambda e, tid=tool_ident: self._pin_tool(tid), pin_item)
        panel.PopupMenu(menu)
        menu.Destroy()

    """添加收藏"""
    def _add_favorite(self, tool_ident):
        if tool_ident not in self.favorites:
            self.favorites.append(tool_ident)
            self._save_favorites_local()
            self._sync_favorites_to_backend()
            logger.info("Favorite added: %s", tool_ident)

    """移除收藏"""
    def _remove_favorite(self, tool_ident):
        if tool_ident in self.favorites:
            self.favorites.remove(tool_ident)
            self._save_favorites_local()
            self._sync_favorites_to_backend()
            logger.info("Favorite removed: %s", tool_ident)

    """获取当前用户的置顶文件路径（按用户ID区分，未登录用匿名文件）"""
    def _get_pinned_file_path(self):
        if auth_manager.is_user_logged_in():
            user = auth_manager.get_current_user()
            if not isinstance(user.id, int) or user.id <= 0:
                return self.user_setting_dir / "pinned_anonymous.json"
            user_dir = self.user_setting_dir / str(user.id)
            user_dir.mkdir(parents=True, exist_ok=True)
            return user_dir / "pinned.json"
        return self.user_setting_dir / "pinned_anonymous.json"

    """从本地文件加载置顶数据（有序ident列表，前面为更晚置顶的工具）"""
    def _load_pinned(self):
        try:
            pin_file = self._get_pinned_file_path()
            if pin_file.exists():
                with open(pin_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return [p for p in data.get('pinned', []) if isinstance(p, str)]
            return []
        except Exception as e:
            logger.error("Failed to load pin data: %s", e)
            return []

    """保存置顶数据到本地文件"""
    def _save_pinned_local(self):
        try:
            pin_file = self._get_pinned_file_path()
            pin_file.parent.mkdir(parents=True, exist_ok=True)
            with open(pin_file, 'w', encoding='utf-8') as f:
                json.dump({'pinned': self.pinned}, f, ensure_ascii=False, indent=2)
            logger.debug("Pin data saved locally: %s", pin_file)
        except Exception as e:
            logger.error("Failed to save pin data locally: %s", e)

    """置顶某工具：放入置顶列表最前（最后一次置顶的排在最前）"""
    def _pin_tool(self, tool_ident):
        if tool_ident in self.pinned:
            self.pinned.remove(tool_ident)
        self.pinned.insert(0, tool_ident)
        self._save_pinned_local()
        self.update_tool_buttons()
        logger.info("Tool pinned: %s", tool_ident)

    """取消置顶某工具"""
    def _unpin_tool(self, tool_ident):
        if tool_ident in self.pinned:
            self.pinned.remove(tool_ident)
            self._save_pinned_local()
            self.update_tool_buttons()
            logger.info("Tool unpinned: %s", tool_ident)

    """获取最近使用记录文件路径（按用户ID区分，OSS未登录用匿名文件）"""
    def _get_recent_usage_file_path(self):
        if auth_manager.is_user_logged_in():
            user = auth_manager.get_current_user()
            if not isinstance(user.id, int) or user.id <= 0:
                return self.user_setting_dir / "recent_usage_anonymous.json"
            user_dir = self.user_setting_dir / str(user.id)
            user_dir.mkdir(parents=True, exist_ok=True)
            return user_dir / "recent_usage.json"
        return self.user_setting_dir / "recent_usage_anonymous.json"

    """从本地文件加载最近使用记录（ident -> ISO时间戳）"""
    def _load_recent_usage(self):
        try:
            f = self._get_recent_usage_file_path()
            if f.exists():
                with open(f, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                    return {i: ts for i, ts in data.get('recent', {}).items()
                            if isinstance(i, str) and isinstance(ts, str)}
            return {}
        except Exception as e:
            logger.error("Failed to load recent-use data: %s", e)
            return {}

    """保存最近使用记录到本地文件"""
    def _save_recent_usage_local(self):
        try:
            f = self._get_recent_usage_file_path()
            f.parent.mkdir(parents=True, exist_ok=True)
            with open(f, 'w', encoding='utf-8') as fh:
                json.dump({'recent': self.recent_usage}, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to save recent-use data: %s", e)

    """记录某工具的最近使用时间（仅落盘，不立即重建卡片，下次刷新生效）"""
    def _record_recent_usage(self, tool_ident):
        if not tool_ident:
            return
        self.recent_usage[tool_ident] = datetime.datetime.now().isoformat()
        self._save_recent_usage_local()

    """排序下拉按钮：弹出排序模式菜单"""
    def on_sort_button_click(self, event):
        menu = wx.Menu()
        for idx, label in enumerate(self._sort_labels):
            item = menu.AppendRadioItem(wx.ID_ANY, label)
            item.Check(idx == self._sort_index)
            self.Bind(wx.EVT_MENU, lambda e, i=idx: self._on_sort_selected(i), item)
        # 弹出菜单在按钮下方（与收藏按钮一致）
        btn_pos = self.sort_button.ClientToScreen((0, self.sort_button.GetSize().height))
        self.PopupMenu(menu, self.ScreenToClient(btn_pos))
        menu.Destroy()

    """排序模式选择处理（按索引）"""
    def _on_sort_selected(self, index):
        if index == self._sort_index:
            return
        self._sort_index = index
        self.sort_mode = self._sort_mode_list[index]
        self.sort_button.SetLabel(self._sort_labels[index] + " \u25BC")
        if self.sort_mode == 'popular' and not self.popularity_cache:
            # 首次选择"最多人用"：后台拉取后端热度后刷新，避免阻塞UI
            threading.Thread(target=self._fetch_popularity_and_refresh, daemon=True).start()
            return
        self.update_tool_buttons()

    """从后端拉取全局工具热度并刷新卡片顺序"""
    def _fetch_popularity_and_refresh(self):
        self._fetch_popularity()
        wx.CallAfter(self.update_tool_buttons)

    """请求后端全局工具热度接口并缓存到 self.popularity_cache"""
    def _fetch_popularity(self):
        if IS_OSS_COMMUNITY_BUILD or not self._is_backend_reachable():
            return
        try:
            response = requests.get(
                f"{self.backend_url}{API_V1_PREFIX}/tool_stats/popularity",
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                tools = data.get('tools', {}) or {}
                self.popularity_cache = {
                    ident: int(val.get('use_count', 0))
                    for ident, val in tools.items()
                }
        except Exception as e:
            logger.error("Failed to fetch tool heat: %s", e)

    """获取收藏文件路径（按用户ID区分）"""
    def _get_favorites_file_path(self):
        if auth_manager.is_user_logged_in():
            user = auth_manager.get_current_user()
            # 纵深防御：确认 user.id 为正整数后再拼入目录路径，防止路径穿越
            if not isinstance(user.id, int) or user.id <= 0:
                logger.error("user.id has invalid type or is not a positive integer: %s", repr(user.id))
                return self.user_setting_dir / "favorites_anonymous.json"
            user_dir = self.user_setting_dir / str(user.id)
            user_dir.mkdir(parents=True, exist_ok=True)
            return user_dir / "favorites.json"
        return self.user_setting_dir / "favorites_anonymous.json"

    """从本地文件加载收藏数据"""
    def _load_favorites(self):
        try:
            fav_file = self._get_favorites_file_path()
            if fav_file.exists():
                with open(fav_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('favorites', [])
            return []
        except Exception as e:
            logger.error("Failed to load favorites data: %s", e)
            return []

    """保存收藏数据到本地文件"""
    def _save_favorites_local(self):
        try:
            fav_file = self._get_favorites_file_path()
            fav_file.parent.mkdir(parents=True, exist_ok=True)
            with open(fav_file, 'w', encoding='utf-8') as f:
                json.dump({'favorites': self.favorites}, f, ensure_ascii=False, indent=2)
            logger.debug("Favorites data saved locally: %s", fav_file)
        except Exception as e:
            logger.error("Failed to save favorites data locally: %s", e)

    """全量同步收藏数据到后端"""
    def _sync_favorites_to_backend(self):
        if not auth_manager.is_user_logged_in():
            self._fav_dirty = True
            logger.debug("Not logged in; favorite changes marked as pending sync")
            return
        try:
            headers = auth_manager.get_auth_headers()
            headers["Content-Type"] = "application/json"
            response = requests.post(
                f"{self.backend_url}{API_V1_PREFIX}/user_favorites",
                json={"favorites": self.favorites},
                headers=headers,
                timeout=5
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "success":
                    self._fav_dirty = False
                    logger.debug("Favorites data synced to backend")
                else:
                    self._fav_dirty = True
                    logger.warning("Failed to sync favorites to backend: %s", result.get("message"))
            else:
                self._fav_dirty = True
                logger.warning("HTTP error syncing favorites to backend: %d", response.status_code)
        except Exception as e:
            self._fav_dirty = True
            logger.warning("Exception syncing favorites to backend: %s (offline mode, saved locally)", e)

    """从后端下载收藏数据"""
    def _download_favorites_from_backend(self):
        if not auth_manager.is_user_logged_in():
            return
        try:
            headers = auth_manager.get_auth_headers()
            response = requests.get(
                f"{self.backend_url}{API_V1_PREFIX}/user_favorites",
                headers=headers,
                timeout=5
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "success":
                    self.favorites = result.get("favorites", [])
                    self._save_favorites_local()
                    self._fav_dirty = False
                    logger.info("Downloaded favorites data from backend, %d items in total", len(self.favorites))
                else:
                    logger.warning("Failed to download favorites from backend: %s; using local cache", result.get("message"))
                    self.favorites = self._load_favorites()
            else:
                logger.warning("HTTP error downloading favorites from backend: %d; using local cache", response.status_code)
                self.favorites = self._load_favorites()
        except Exception as e:
            logger.warning("Exception downloading favorites from backend: %s (using local cache)", e)
            self.favorites = self._load_favorites()

    """认证状态变化时同步收藏数据"""
    def _on_auth_changed_sync_favorites(self):
        if auth_manager.is_user_logged_in():
            # 登录：从后端下载收藏，然后如果有待同步的变更则上传
            self._download_favorites_from_backend()
            if self._fav_dirty:
                self._sync_favorites_to_backend()
        else:
            # 登出：清空内存中的收藏（本地文件保留，下次登录可下载）
            self.favorites = []
            self._fav_dirty = False
        # 登录/登出后按当前用户重载置顶列表（置顶本地持久化）
        self.pinned = self._load_pinned()
        self._update_fav_button_state()

    """收藏功能是否可用：OSS 社区版离线可用本地收藏；完整版仍需登录（与后端同步）"""
    def _favorites_available(self):
        return IS_OSS_COMMUNITY_BUILD or auth_manager.is_user_logged_in()

    """更新收藏按钮的启用/禁用状态"""
    def _update_fav_button_state(self):
        if not hasattr(self, 'fav_button'):
            return
        self.fav_button.Enable(self._favorites_available())

    # ---------------- 前端自更新检查（T1.2，方案 1a：仅提示 + 跳转下载页） ----------------

    def _read_frontend_version_from_file(self):
        """从 config/version.txt（PyInstaller VSVersionInfo 结构）读取前端版本号。

        单一来源约定：ProductVersion 字段取前三段作为版本号；
        读取/解析失败时回退 "1.0.0" 并记 ERROR 日志（打包脚本自检会拦截占位值）。
        """
        try:
            version_file_path = os.path.join(self.base_path, 'config', 'version.txt')
            with open(version_file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            match = re.search(r"StringStruct\(u?'ProductVersion',\s*u?'(\d+(?:\.\d+){1,3})'\)", text)
            if not match:
                raise ValueError("ProductVersion field not found")
            return '.'.join(match.group(1).split('.')[:3])
        except (OSError, ValueError) as e:
            logger.error("Failed to read frontend version from config/version.txt, "
                         "falling back to 1.0.0: %s", e)
            return "1.0.0"

    def _start_frontend_update_check(self):
        """启动时异步检查前端新版本（daemon 线程，失败静默不阻塞、不弹窗）。"""
        if IS_OSS_COMMUNITY_BUILD or not self.backend_url:
            # OSS 社区版无后端，跳过自更新检查（T1.2 豁免规则）
            return
        threading.Thread(target=self._frontend_update_check_worker, daemon=True).start()

    def _frontend_update_check_worker(self):
        latest_info = None
        try:
            response = requests.get(self.backend_url + '/api/v1/frontend/latest', timeout=5)
            response.raise_for_status()
            latest_info = response.json()
        except Exception as e:
            # 后端不可达/接口异常时静默跳过：更新检查失败不应影响正常使用
            logger.info("Frontend update check skipped (non-blocking): %s", e)

        announcements_info = None
        try:
            response = requests.get(self.backend_url + '/api/v1/announcements', timeout=5)
            response.raise_for_status()
            announcements_info = response.json()
        except Exception as e:
            # 公告拉取失败静默跳过（T5.2：失败不阻塞、不弹窗，不影响正常使用）
            logger.info("Announcements fetch skipped (non-blocking): %s", e)

        # T8.3 主程序 i18n 远程覆盖层：拉取增量键合并进本地字典
        # （覆盖式、保离线；失败静默）。置于最低版本强提醒 early-return 之前，
        # 保证强提醒场景下覆盖同样已生效
        try:
            response = requests.get(self.backend_url + '/api/v1/frontend/i18n_overrides', timeout=5)
            response.raise_for_status()
            applied = i18n.apply_remote_overrides((response.json() or {}).get('i18n_overrides'))
            if applied:
                logger.info("Applied %d remote i18n override key(s)", applied)
        except Exception as e:
            # 覆盖层拉取失败静默跳过（T8.3.2：本地字典完整，离线/异常均不受影响）
            logger.info("i18n overrides fetch skipped (non-blocking): %s", e)

        latest_version = str((latest_info or {}).get('version', '') or '').strip()

        # T5.3 全局最低前端版本强提醒：当前版本低于阈值时每次启动弹强提醒并引导下载
        # （T1 自更新失效时的兜底；优先级高于普通更新提示，故弹强提醒后不再弹普通
        # 提示；升级前每次启动重现，不可永久关闭）
        min_version = str((announcements_info or {}).get('min_frontend_version', '') or '').strip()
        if min_version and version_tuple(min_version) > version_tuple(self.frontend_version):
            # T8.6.1：强提醒场景同时后台静默下载安装包（就绪后弹"更新包已就绪"），
            # 不具备下载条件时仅记日志（强提醒弹窗本身已引导下载页）
            if not self._start_installer_download(latest_info or {}):
                logger.info("Installer background download unavailable in force-update path")
            wx.CallAfter(self._prompt_frontend_force_update,
                         min_version,
                         latest_version,
                         str((latest_info or {}).get('changelog', '') or ''),
                         str((latest_info or {}).get('download_url', '') or ''))
            return

        if latest_version and version_tuple(latest_version) > version_tuple(self.frontend_version):
            # T8.6.1（A4 调整版）：可后台静默下载时抑制"前往下载页"弹窗（避免与
            # "更新包已就绪"弹窗重复），下载/验签失败时回退方案 1a 提示（worker 内）
            if not self._start_installer_download(latest_info or {}):
                wx.CallAfter(self._prompt_frontend_update,
                             latest_version,
                             str((latest_info or {}).get('changelog', '') or ''),
                             str((latest_info or {}).get('download_url', '') or ''))
        elif latest_version:
            logger.info("Frontend update check: up to date (current=%s)", self.frontend_version)

        # T5.2 公告展示（warning/critical 取最高级别一条弹窗，info 取第一条进状态栏）
        if announcements_info:
            self._dispatch_announcements(announcements_info.get('announcements') or [])

    def _prompt_frontend_update(self, latest_version, changelog, download_url):
        """版本落后时弹窗提示并引导跳转下载页（UI 线程，由 wx.CallAfter 调入）。"""
        if version_tuple(latest_version) <= version_tuple(self.frontend_version):
            return  # 弹窗前用户可能已在别处更新，二次确认避免误报
        text = translate("frontend_update_available_text").format(
            current=self.frontend_version, latest=latest_version)
        if changelog:
            text += "\n\n" + changelog
        dialog = wx.MessageDialog(
            self, text,
            translate("frontend_update_available_title"),
            wx.YES_NO | wx.ICON_INFORMATION
        )
        if dialog.ShowModal() == wx.ID_YES:
            url = download_url or FRONTEND_DOWNLOAD_PAGE_URL
            logger.info("Opening frontend download page: %s", url)
            wx.LaunchDefaultBrowser(url)
        dialog.Destroy()

    def _prompt_frontend_force_update(self, min_version, latest_version, changelog, download_url):
        """低于全局最低前端版本时弹强提醒（UI 线程，由 wx.CallAfter 调入）。

        与普通更新提示的区别：OK 单键确认后直接打开下载页（不询问）；升级前每次
        启动都会重现（后端撤除 min_frontend_version 或用户升级后消失）。
        """
        if version_tuple(min_version) <= version_tuple(self.frontend_version):
            return  # 弹窗前用户可能已在别处更新，二次确认避免误报
        text = translate("frontend_min_version_required_text").format(
            current=self.frontend_version, min_required=min_version,
            latest=latest_version or min_version)
        if changelog:
            text += "\n\n" + changelog
        dialog = wx.MessageDialog(
            self, text,
            translate("frontend_min_version_required_title"),
            wx.OK | wx.ICON_WARNING
        )
        dialog.ShowModal()
        dialog.Destroy()
        url = download_url or FRONTEND_DOWNLOAD_PAGE_URL
        logger.info("Opening frontend download page (min version enforcement): %s", url)
        wx.LaunchDefaultBrowser(url)

    def _prompt_installer_ready(self, installer_path, version):
        """T8.6.2 更新包就绪提示（UI 线程，由 wx.CallAfter 调入）。

        YES = 打开安装包所在文件夹；NO/关闭 = 保留缓存，下次启动再提示
        （下次启动版本检查仍发现新版本且缓存 sha256 匹配 → 重新弹本提示）。
        基础层不做自动调用安装器（无 OS 签名证书会被 SmartScreen/AV 拦截）；
        增强层预留见 tfp_tool_runner_mixin._start_installer_download 的 T8.6.3 注释。
        """
        text = translate("frontend_update_ready_text").format(
            version=version, path=str(installer_path))
        dialog = wx.MessageDialog(
            self, text,
            translate("frontend_update_ready_title"),
            wx.YES_NO | wx.ICON_INFORMATION
        )
        try:
            if dialog.ShowModal() == wx.ID_YES:
                self._open_folder_in_file_manager(installer_path.parent)
        finally:
            dialog.Destroy()

    def _open_folder_in_file_manager(self, folder_path):
        """用系统文件管理器打开目录（Windows explorer / Linux xdg-open）。"""
        try:
            if sys.platform.startswith('win'):
                os.startfile(str(folder_path))
            else:
                subprocess.Popen(['xdg-open', str(folder_path)])
            logger.info("Opened installer folder: %s", folder_path)
        except Exception as e:
            # 打开失败不阻断：兜底展示路径，用户可自行导航
            logger.error("Failed to open installer folder %s: %s", folder_path, e)
            wx.MessageBox(str(folder_path),
                          translate("frontend_update_ready_title"),
                          wx.OK | wx.ICON_INFORMATION)

    def _dispatch_announcements(self, announcements):
        """公告过滤与分发（T5.2）：warning/critical 取最高级别一条弹窗，info 取第一条进状态栏。

        条目级 min_frontend_version（后端透传字段）：仅展示给当前版本 >= 该值的
        用户（公告定向投放），其余用户跳过该条。
        """
        if not announcements:
            return
        current_tuple = version_tuple(self.frontend_version)
        severity_order = {'critical': 0, 'warning': 1, 'info': 2}
        valid = []
        for entry in announcements:
            if not isinstance(entry, dict):
                continue
            level = str(entry.get('level', 'info') or 'info').strip().lower()
            if level not in severity_order:
                level = 'info'
            entry_min = str(entry.get('min_frontend_version', '') or '').strip()
            if entry_min and current_tuple < version_tuple(entry_min):
                continue
            valid.append((severity_order[level], level, entry))
        if not valid:
            return
        valid.sort(key=lambda item: item[0])
        for _, level, entry in valid:
            if level in ('warning', 'critical'):
                wx.CallAfter(self._show_announcement_dialog, level, entry)
                break
        for _, level, entry in valid:
            if level == 'info':
                wx.CallAfter(self._show_announcement_status, entry)
                break

    @staticmethod
    def _pick_localized_text(text_map):
        """按当前界面语言从后端多语言字典取文案；缺失时回退 en，再回退任一可用项。"""
        if not isinstance(text_map, dict) or not text_map:
            return ''
        return str(text_map.get(i18n.get_language_code())
                   or text_map.get('en')
                   or next(iter(text_map.values()), ''))

    def _show_announcement_dialog(self, level, entry):
        """warning/critical 公告弹窗展示（UI 线程，由 wx.CallAfter 调入）。"""
        body = self._pick_localized_text(entry.get('body'))
        if not body:
            return
        title = self._pick_localized_text(entry.get('title'))
        icon = wx.ICON_ERROR if level == 'critical' else wx.ICON_WARNING
        dialog = wx.MessageDialog(self, body, title or translate("dialog_title_info"),
                                  wx.OK | icon)
        dialog.ShowModal()
        dialog.Destroy()

    def _show_announcement_status(self, entry):
        """info 公告状态栏展示（UI 线程，由 wx.CallAfter 调入；状态栏为瞬态展示）。"""
        title = self._pick_localized_text(entry.get('title'))
        body = self._pick_localized_text(entry.get('body'))
        text = f"{title} — {body}" if title and body else (title or body)
        if not text:
            return
        logger.info("Announcement: %s", text)
        if getattr(self, 'status_bar', None):
            self.status_bar.SetStatusText(text, 0)

    """刷新工具列表"""
    def on_check_update(self, event):
        """检查工具更新：从后端获取最新工具列表，对比本地版本"""
        if not self._is_backend_reachable():
            wx.MessageBox(translate("message_offline_check_update_unavailable"),
                          translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        self.status_bar.SetStatusText(translate("status_checking_update"), 0)
        self.update_non_builtin_tools_from_backend(force_update=True)

    def on_refresh_tool_list(self, event):
        if not self._is_backend_reachable():
            wx.MessageBox(translate("message_offline_refresh_unavailable"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        self.status_bar.SetStatusText(translate("status_refreshing_tools"), 0)
        self.status_bar.SetStatusText(translate("status_updating_from_backend"), 1)
        self.update_non_builtin_tools_from_backend(force_update=True)

    """删除缓存工具"""
    def on_clear_cache(self, event):
        dialog = wx.MessageDialog(
            self,
            translate("dialog_text_clear_cache_confirm"),
            translate("dialog_title_clear_cache_confirm"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING
        )
        if dialog.ShowModal() == wx.ID_YES:
            dialog.Destroy()
            self.lock_all_tools()
            busy_info = wx.BusyInfo(translate("busy_clearing_cache"), self)
            wx.Yield()
            result = self.clear_local_cache()
            busy_info = None
            wx.Yield()
            self.unlock_all_tools()
            if result:
                wx.MessageBox(result['message'], result['title'], result['style'])
        else:
            dialog.Destroy()

    """清除本地缓存 - 增强版本：先关闭所有工具，再清除目录"""
    def clear_local_cache(self):
        try:
            open_tool_count = len(self.embedded_tools)
            if open_tool_count > 0:
                logger.info("Closing %d opened sub-tools...", open_tool_count)
                self.close_all_embedded_tools()
                wx.Yield()
                import time
                time.sleep(0.5)
            
            self.reset_tool_versions()
            with self._tools_data_lock:
                self.last_modified = "1970-01-01T00:00:00Z"
            logger.info("Reset update date to: %s", self.last_modified)
            directories_to_clear = [
                "tools_remote_program",
                "tools_remote_webpage"
            ]
            cleared_dirs = []
            for dir_name in directories_to_clear:
                if self.clear_directory_contents(dir_name):
                    cleared_dirs.append(dir_name)
            for dir_name in directories_to_clear:
                category_dir = self.local_tools_dir / dir_name
                if category_dir.exists():
                    for tool_sub_dir in category_dir.iterdir():
                        if tool_sub_dir.is_dir():
                            self.clear_tool_module_cache(tool_sub_dir)
            self.save_local_non_builtin_tools()
            self.update_tool_buttons()
            self.status_bar.SetStatusText(translate("status_local_cache_cleared"), 0)
            self.status_bar.SetStatusText("", 1)
            # 删除所有日志文件（包括子工具日志和主程序日志）
            try:
                import logging as _logging
                log_dir = get_log_dir()
                if log_dir and log_dir.exists():
                    # 先关闭所有logger的文件handler，以便Windows允许删除日志文件
                    for _logger_name in list(_logging.Logger.manager.loggerDict.keys()):
                        _lgr = _logging.getLogger(_logger_name)
                        for _h in _lgr.handlers[:]:
                            if isinstance(_h, _logging.FileHandler):
                                _h.close()
                                _lgr.removeHandler(_h)
                    for _h in _logging.root.handlers[:]:
                        if isinstance(_h, _logging.FileHandler):
                            _h.close()
                            _logging.root.removeHandler(_h)
                    for log_file in log_dir.iterdir():
                        if log_file.is_file() and log_file.suffix == '.log':
                            try:
                                log_file.unlink()
                            except Exception:
                                pass
            except Exception:
                pass
            if cleared_dirs:
                return {
                    'message': translate("message_cache_cleared").format(count=len(cleared_dirs)),
                    'title': translate("dialog_title_operation_complete"),
                    'style': wx.OK | wx.ICON_INFORMATION
                }
            else:
                return {
                    'message': translate("message_no_cache_to_clear"),
                    'title': translate("dialog_title_info"),
                    'style': wx.OK | wx.ICON_INFORMATION
                }
        except Exception as e:
            error_msg = translate("message_clear_cache_error").format(error=str(e))
            logger.error(error_msg)
            return {
                'message': error_msg,
                'title': translate("dialog_title_error"),
                'style': wx.OK | wx.ICON_ERROR
            }
    def reset_tool_versions(self):
        try:
            reset_count = 0
            for category, tools in self.non_builtin_tools.items():
                for tool in tools:
                    if tool.get('tool_version') != '0.0.0':
                        tool['tool_version'] = '0.0.0'
                        reset_count += 1
                        logger.debug("Reset tool %s version to 0.0.0", tool['tool_ident'])
            self.save_local_non_builtin_tools()
            logger.info("Reset versions of %d non-built-in tools to 0.0.0", reset_count)
        except Exception as e:
            logger.error("Failed to reset tool version: %s", e)
            raise

    """清除指定目录中的所有内容 - 使用新的路径结构，保留app_icon.ico"""
    def clear_directory_contents(self, directory_name):
        try:
            target_dir = self.local_tools_dir / directory_name
            if not target_dir.exists():
                logger.debug("Directory does not exist: %s", target_dir)
                return False
            deleted_dirs = 0
            icon_backups = {}
            for item in target_dir.iterdir():
                if item.is_dir():
                    icon_path = item / "app_icon.ico"
                    if icon_path.exists():
                        try:
                            icon_backups[item.name] = icon_path.read_bytes()
                            logger.debug("Backing up icon: %s", icon_path)
                        except Exception as e:
                            logger.warning("Failed to back up icon %s: %s", icon_path, e)
            for item in target_dir.iterdir():
                if item.is_dir():
                    try:
                        shutil.rmtree(item)
                        deleted_dirs += 1
                        logger.debug("Deleted tool directory: %s", item.name)
                    except Exception as e:
                        logger.warning("Error deleting %s: %s", item, e)
            for dir_name, icon_data in icon_backups.items():
                try:
                    restore_dir = target_dir / dir_name
                    restore_dir.mkdir(parents=True, exist_ok=True)
                    (restore_dir / "app_icon.ico").write_bytes(icon_data)
                    logger.debug("Restored icon: %s/app_icon.ico", dir_name)
                except Exception as e:
                    logger.warning("Failed to restore icon %s: %s", dir_name, e)
            logger.info("Cleaned directory %s: deleted %d subdirectories, restored %d icons", directory_name, deleted_dirs, len(icon_backups))
            return deleted_dirs > 0
        except Exception as e:
            logger.error("Error cleaning directory %s: %s", directory_name, e)
            return False

    """显示关于对话框"""
    def _load_license_texts(self):
        """加载随二进制分发的 LICENSE.txt 与 docs/NOTICE.txt（OSS 合规 M-6，AGPL §5(a)/§6）。

        打包环境（PyInstaller onefile/onedir）中 datas 解包在 sys._MEIPASS；
        源码运行环境中位于 main.py 所在的项目根目录。任一文件缺失时返回 None。
        """
        try:
            base = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))
            license_path = os.path.join(base, 'LICENSE.txt')
            notice_path = os.path.join(base, 'docs', 'NOTICE.txt')
            parts = []
            if os.path.isfile(license_path):
                with open(license_path, 'r', encoding='utf-8') as f:
                    parts.append(f.read())
            if os.path.isfile(notice_path):
                if parts:
                    parts.append('=' * 78 + '\n\n')
                with open(notice_path, 'r', encoding='utf-8') as f:
                    parts.append(f.read())
            return ''.join(parts) if parts else None
        except Exception as e:
            logger.warning("Failed to load bundled license texts: %s", e)
            return None

    def on_about(self, event):
        try:
            info = wx.adv.AboutDialogInfo()
            info.SetName("TabulexFlow")
            info.SetVersion(self.frontend_version)
            info.SetDescription(translate("about_description"))
            info.SetCopyright("(C) 2024-2026 TabulexFlow Team")
            info.SetWebSite("https://tabulexflow.com")
            info.AddDeveloper("tabulexflow@outlook.com")
            # OSS 合规（M-6）：在 About 对话框内嵌完整 AGPL-3.0 许可证全文与第三方 NOTICE
            license_text = self._load_license_texts()
            if license_text:
                info.SetLicense(license_text)
            wx.adv.AboutBox(info)
        except AttributeError:
            about_msg = translate("about_message").format(version=self.frontend_version)
            wx.MessageBox(about_msg, translate("about_title"), wx.OK | wx.ICON_INFORMATION)

if __name__ == '__main__':
    # Linux 打包产物：RemoteWebpage 回退引擎（pywebview）通过 multiprocessing spawn
    # 启动独立子进程，freeze_support 必须在入口最前面调用，否则子进程会重复启动主程序
    import multiprocessing
    multiprocessing.freeze_support()

    def _global_exception_handler(exc_type, exc_value, exc_tb):
        import traceback
        logger.error("Uncaught global exception:\n%s", ''.join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    sys.excepthook = _global_exception_handler

    app = TFP_PlatformApp()
    app.MainLoop()
