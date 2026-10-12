# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
import os
import re
import datetime
import collections
import ctypes
import pathlib
import shutil
from tfo_CustomGrid import tfo_CustomGrid
from tfo_SearchWorker import tfo_SearchWorker
from tfo_RenameMoveWorker import tfo_RenameMoveWorker
from tfo_CopyWorker import tfo_CopyWorker
from tfo_DeleteWorker import tfo_DeleteWorker
from tfo_ZipWorker import tfo_ZipWorker
from tfo_UnZipWorker import tfo_UnZipWorker
from tfo_DuplicateWorker import tfo_DuplicateWorker
from tfo_utils.tfo_worker_mode import WorkerMode
from tfo_utils.tfo_logger import log_error
from tfo_FileDrop import tfo_FileDropToPathInput
from tfo_utils.tfo_i18n_manager import translate, translate_list, i18n
from tfp_toolkit.tfp_base_tool import TFP_BuiltinProgramTool
from tfp_toolkit.tfp_dpi import spx_calc as _spx_calc
from tfo_utils.tfo_logger import log_info, log_error, log_warning, log_debug
from tfo_utils.tfo_match_utils import check_name_match_part, wildcard_to_regex as _wildcard_to_regex
from tfo_utils.tfo_op_history import (
    _OpHistoryManager,
    OP_TYPE_SEARCH,
    OP_TYPE_RENAME_APPLY, OP_TYPE_RENAME_PREVIEW, OP_TYPE_RENAME_EXECUTE,
    OP_TYPE_MOVE_APPLY, OP_TYPE_MOVE_PREVIEW, OP_TYPE_MOVE_EXECUTE,
    OP_TYPE_COPY_APPLY, OP_TYPE_COPY_PREVIEW, OP_TYPE_COPY_EXECUTE,
    OP_TYPE_ZIP_APPLY, OP_TYPE_ZIP_PREVIEW, OP_TYPE_ZIP_EXECUTE,
    OP_TYPE_UNZIP_APPLY, OP_TYPE_UNZIP_PREVIEW, OP_TYPE_UNZIP_EXECUTE,
    OP_TYPE_DELETE_APPLY, OP_TYPE_DELETE_PREVIEW, OP_TYPE_DELETE_EXECUTE,
    OP_TYPE_DUPLICATE_APPLY, OP_TYPE_DUPLICATE_PREVIEW, OP_TYPE_DUPLICATE_EXECUTE,
)

# OSS 社区版（IS_OSS_COMMUNITY_BUILD=True，编译期由构建脚本写入 build_mode 并随主程序打包）
# 不显示"关于/About"标签页，仅非 OSS 版（源码/开发、完整版）显示。导入失败时按非 OSS 处理。
try:
    from build_mode import IS_OSS_COMMUNITY_BUILD
except ImportError:
    IS_OSS_COMMUNITY_BUILD = False

"""工具TabulexFileOperator的主类"""


def _wrap_text_to_width(text: str, font: wx.Font, max_width: int) -> str:
    """按像素宽度给文本换行（支持中英文混排）。

    `wx.StaticText.Wrap()` 只在空白处换行，对没有空格的中文无法断行，故自行实现：
    CJK 字符逐字断行，英文/数字按词断行。
    """
    if not text or max_width <= 0:
        return text
    dc = wx.ScreenDC()
    dc.SetFont(font)
    tokens = []
    buf = ""
    for ch in text:
        if ch == "\n":
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append("\n")
        elif ord(ch) > 0x2E80 or ch in "，。、；：（）《》“”‘’！？—【】…":
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
        elif ch == " ":
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(" ")
        else:
            buf += ch
    if buf:
        tokens.append(buf)

    lines = []
    cur = ""
    for tok in tokens:
        if tok == "\n":
            lines.append(cur)
            cur = ""
            continue
        if not cur or dc.GetTextExtent(cur + tok)[0] <= max_width:
            cur += tok
        else:
            lines.append(cur)
            cur = tok
    lines.append(cur)
    return "\n".join(lines)


class tfo_TabulexFileOperatorTool(TFP_BuiltinProgramTool):
    @property
    def tool_ident(self) -> str:
        return "TabulexFileOperator"

    @property
    def tool_name(self) -> str:
        return translate("tool_name")

    def __init__(self, parent):
        super().__init__(parent)
        self.search_folder = ""
        self.unique_ordered_match_list = []
        self.prev_match_method_key = ""
        self.TFP_DPI_SCALE_FACTOR = getattr(parent, 'TFP_DPI_SCALE_FACTOR', 1.0)
        self.init_combo_box_mappings()
        # 操作级撤销/重做管理器
        self._op_history_manager = _OpHistoryManager()
        # 启动时清除上次会话遗留的备份目录
        try:
            _OpHistoryManager.cleanup_stale_backups()
        except Exception as e:
            log_warning(f"清除遗留备份失败: {e}")
        # 当前操作级历史条目（begin_operation 后，commit/abort 前）
        self._current_op_entry = None

    def spx_calc(self, value):
        if value == -1:
            return -1
        return int(value * self.TFP_DPI_SCALE_FACTOR)

    def _apply_measured_min_size(self, label, text, font):
        """wxGTK下控件以创建时的旧字体建立尺寸缓存，SetFont不会刷新该缓存，
        导致首次布局分配的宽高不足、文本被裁剪；
        按新字体显式测量文本并用SetMinSize强制正确尺寸，禁止换行裁剪。"""
        dc = wx.ClientDC(label)
        dc.SetFont(font)
        tw, th = dc.GetTextExtent(text)
        label.SetMinSize((tw + 8, th))
        # 空闲后再次触发失效，配合统一的CallAfter重新布局覆盖wxGTK首次布局的过期尺寸缓存
        wx.CallAfter(label.InvalidateBestSize)

    def _on_tool_cards_size(self, event):
        event.Skip()
        wx.CallAfter(self._rewrap_tool_card_descriptions)

    def _rewrap_tool_card_descriptions(self):
        """让"更多效率工具"的两列卡片各占 50% 宽度，并按卡片可用宽度给工具描述换行"""
        labels = getattr(self, '_tool_card_desc_labels', None)
        if not labels:
            return
        container_w = self.moretool_container.GetClientSize().width
        card_w = max(self.spx_calc(150), (container_w - self.spx_calc(60)) // 2)
        # 扣除卡片内左侧图标列、图标与文字间距、右侧下载图标及其边距
        avail = max(self.spx_calc(80), card_w - self.spx_calc(115))
        if getattr(self, '_tool_card_wrap_width', None) == avail:
            return
        self._tool_card_wrap_width = avail
        for label, original in labels:
            label.SetLabel(_wrap_text_to_width(original, label.GetFont(), avail))
        self.moretool_container.Layout()

    """创建嵌入式界面"""
    def create_embedded_interface(self, parent_panel, parent_sizer):
        self.is_embedded = True
        self.panel = parent_panel
        self.sizer_main = parent_sizer
        self._build_interface()

    """显示操作文件表格界面"""
    def show_interface(self):
        if self.frame and self.frame.IsShown(): return
        self.is_embedded = False
        self.frame = wx.Frame(None, title=translate("tool_name"), size=(self.spx_calc(1000), self.spx_calc(600)), style=wx.DEFAULT_FRAME_STYLE | wx.RESIZE_BORDER)
        try:
            if hasattr(self.parent, 'base_path'):
                icon_path = self.parent.base_path / "app_icon.ico"
                # IconBundle 载入 ICO 内全部尺寸，Linux 任务栏才能正确显示（SetIcon 在 wxGTK 下只写单一尺寸）
                if icon_path.exists(): self.frame.SetIcons(wx.IconBundle(str(icon_path), wx.BITMAP_TYPE_ICO))
        except Exception:
            pass
        self.panel = wx.Panel(self.frame)
        self.sizer_main = wx.BoxSizer(wx.VERTICAL)
        self._build_interface()
        # 独立窗口模式：创建完整菜单栏（文件+编辑+设置+窗口+账户+帮助）
        if hasattr(self, '_edit_menu') and self._edit_menu:
            from tfp_utils.tfp_i18n_manager import translate as main_translate
            tool_menubar = wx.MenuBar()
            # 文件菜单（简化版，仅含关闭）
            file_menu = wx.Menu()
            file_menu.Append(wx.ID_CLOSE, main_translate("menu_close_tab") if main_translate("menu_close_tab") else "Close")
            tool_menubar.Append(file_menu, main_translate("menu_file"))
            # 编辑菜单（撤销/重做）
            tool_menubar.Append(self._edit_menu, translate("menu_edit"))
            # 帮助菜单
            help_menu = wx.Menu()
            help_menu.Append(wx.ID_ABOUT, main_translate("menu_about") if main_translate("menu_about") else "About")
            tool_menubar.Append(help_menu, main_translate("menu_help"))
            self.frame.SetMenuBar(tool_menubar)
            # 绑定撤销/重做事件
            self.frame.Bind(wx.EVT_MENU, self._on_undo_menu, self.menu_item_undo)
            self.frame.Bind(wx.EVT_MENU, self._on_redo_menu, self.menu_item_redo)
            self.frame.Bind(wx.EVT_MENU, self._on_reset_menu, self.menu_item_reset)
            self.frame.Bind(wx.EVT_MENU_OPEN, self._on_menu_open)
        self.frame.Show()
        parent_pos = self.parent.GetPosition()
        self.frame.SetPosition((parent_pos.x + 30, parent_pos.y + 50))

    """构建界面（共享逻辑）"""
    def _build_interface(self):
        # 总布局：创建Notebook（Tabs）
        self.notebook = wx.Notebook(self.panel)
        self.sizer_main.Add(self.notebook, 0, wx.EXPAND | wx.ALL, self.spx_calc(5))
        # 总布局：创建更多工具容器
        self.moretool_container = wx.Panel(self.panel)
        self.moretool_container.SetBackgroundColour(wx.WHITE)
        self.sizer_main.Add(self.moretool_container, 0, wx.EXPAND | wx.ALL, self.spx_calc(5))

        # ========== 搜索 Tab01 ==========
        self.tab01 = wx.Panel(self.notebook)
        sizer_tab01 = wx.BoxSizer(wx.VERTICAL)
        # 第1.1行：搜索方式、搜索内容、文件类型和执行搜索按钮
        sizer_tab01_row1 = wx.BoxSizer(wx.HORIZONTAL)
        # 搜索方式复选项
        self.label_search_method01 = wx.StaticText(self.tab01, label=translate("label_search_method"))
        self.check_search_recursive01 = wx.CheckBox(self.tab01, label=translate("check_recursive"))
        self.check_search_recursive01.SetValue(True)
        self.check_search_hidden01 = wx.CheckBox(self.tab01, label=translate("check_hidden"))
        self.vertical_line0111 = wx.StaticLine(self.tab01, style=wx.LI_VERTICAL)
        self.vertical_line0111.SetMinSize((self.spx_calc(1), self.spx_calc(25)))
        # 输出内容复选项
        self.label_output_content01 = wx.StaticText(self.tab01, label=translate("label_output_content"))
        self.check_output_dirname01 = wx.CheckBox(self.tab01, label=translate("check_dirname"))
        self.check_output_filename01 = wx.CheckBox(self.tab01, label=translate("check_filename"))
        self.check_output_filename01.SetValue(True)
        self.vertical_line01112 = wx.StaticLine(self.tab01, style=wx.LI_VERTICAL)
        self.vertical_line01112.SetMinSize((self.spx_calc(1), self.spx_calc(25)))
        # 搜索目录输入框
        self.label_search_path01 = wx.StaticText(self.tab01, label=translate("label_search_path"))
        self.input_search_path01 = wx.TextCtrl(self.tab01)
        self.input_search_path01.SetMinSize((self.spx_calc(160), -1))
        self.btn_search_browse01 = wx.Button(self.tab01, label=translate("btn_browse"))
        self.btn_search_browse01.SetMinSize((self.spx_calc(60), -1))
        # 应用按钮
        self.btn_apply_search01 = wx.Button(self.tab01, label=translate("btn_search_add"))
        self.btn_apply_search01.SetMinSize((self.spx_calc(70), -1))
        self.btn_apply_search01.Enable(False)
        # 添加到行布局
        sizer_tab01_row1.Add(self.label_search_method01, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab01_row1.Add(self.check_search_recursive01, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab01_row1.Add(self.check_search_hidden01, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab01_row1.Add(self.vertical_line0111, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(5))
        sizer_tab01_row1.Add(self.label_output_content01, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(5))
        sizer_tab01_row1.Add(self.check_output_dirname01, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab01_row1.Add(self.check_output_filename01, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab01_row1.Add(self.vertical_line01112, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(5))
        sizer_tab01_row1.Add(self.label_search_path01, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(5))
        sizer_tab01_row1.Add(self.input_search_path01, 7, wx.EXPAND | wx.RIGHT, self.spx_calc(5))
        sizer_tab01_row1.Add(self.btn_search_browse01, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab01_row1.Add(self.btn_apply_search01, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(10))

        # 第1.2行：匹配方式下拉框
        sizer_tab01_row2 = wx.BoxSizer(wx.HORIZONTAL)
        # 匹配方式下拉框
        self.label_match_method01 = wx.StaticText(self.tab01, label=translate("label_match_method"))
        self.combo_match_method01 = wx.ComboBox(self.tab01, choices=translate_list("combo_match_methods"), style=wx.CB_READONLY)
        self.combo_match_method01.SetSelection(0)
        # 初始化prev_match_method为当前选择
        self.combo_match_method01.Bind(wx.EVT_COMBOBOX, self.on_combo_match_method01_change)
        self.prev_match_method_key = self.get_combo_box_method(self.combo_match_method01, self.match_method_mapping)
        # 匹配名
        self.label_match_text01 = wx.StaticText(self.tab01, label=translate("label_match_text"))
        self.input_match_text01 = wx.TextCtrl(self.tab01)
        self.input_match_text01.SetMinSize((self.spx_calc(160), -1))
        self.btn_match_edit01 = wx.Button(self.tab01, label=translate("btn_match_edit"))
        self.btn_match_edit01.SetMinSize((self.spx_calc(60), -1))
        # 匹配方式的帮助图标（字号放大并加粗，突出可点击）
        self.help_match_method01 = wx.StaticText(self.tab01, label="?")
        font_help_match_method01 = self.help_match_method01.GetFont()
        font_help_match_method01.SetPointSize(int(font_help_match_method01.GetPointSize() * 1.5))
        font_help_match_method01.SetWeight(wx.FONTWEIGHT_BOLD)
        self.help_match_method01.SetFont(font_help_match_method01)
        self.help_match_method01.SetForegroundColour((128, 128, 128))
        self._apply_measured_min_size(self.help_match_method01, "?", font_help_match_method01)
        self.text_match_tip = translate("tooltip_match_method")
        self.help_match_method01.Bind(wx.EVT_LEFT_DOWN, lambda event: self.show_help_dialog(translate("dialog_title_help", title=translate("help_title_match_method")), self.text_match_tip))
        # 匹配方式的提示文本
        tip_match01 = wx.ToolTip(self.text_match_tip)
        tip_match01.SetDelay(500)
        tip_match01.SetAutoPop(10*1000)
        self.help_match_method01.SetToolTip(tip_match01)
        # 导入，导出表格的按钮
        self.btn_import_grid01 = wx.Button(self.tab01, label=translate("btn_import_grid"))
        self.btn_import_grid01.SetMinSize((self.spx_calc(60), -1))
        self.btn_export_grid01 = wx.Button(self.tab01, label=translate("btn_export_grid"))
        self.btn_export_grid01.SetMinSize((self.spx_calc(60), -1))
        # 添加到行布局
        sizer_tab01_row2.Add(self.label_match_method01, 0, wx.ALIGN_CENTER_VERTICAL, self.spx_calc(5))
        sizer_tab01_row2.Add(self.combo_match_method01, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab01_row2.Add(self.help_match_method01, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(6))
        sizer_tab01_row2.AddSpacer(self.spx_calc(8))
        sizer_tab01_row2.Add(self.label_match_text01, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab01_row2.Add(self.input_match_text01, 7, wx.EXPAND | wx.RIGHT, self.spx_calc(5))
        sizer_tab01_row2.Add(self.btn_match_edit01, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab01_row2.Add(self.btn_import_grid01, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(10))
        sizer_tab01_row2.Add(self.btn_export_grid01, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        # 添加到Tab布局
        sizer_tab01.Add(sizer_tab01_row1, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        sizer_tab01.Add(sizer_tab01_row2, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        self.tab01.SetSizer(sizer_tab01)

        # ========== 重命名 Tab02 ==========
        self.tab02 = wx.Panel(self.notebook)
        tab02_sizer02 = wx.BoxSizer(wx.VERTICAL)
        # 第2.1行：重命名操作
        sizer_tab02_row1 = wx.BoxSizer(wx.HORIZONTAL)
        self.label_naming_method02 = wx.StaticText(self.tab02, label=translate("label_naming_method"))
        self.combo_naming_method02 = wx.ComboBox(self.tab02, choices=translate_list("combo_naming_methods"), style=wx.CB_READONLY)
        self.combo_naming_method02.SetSelection(0)
        # 合并方式的子模式单选（按需显示）
        self.radio_replace_mode_text02 = wx.RadioButton(self.tab02, label=translate("radio_replace_by_text"), style=wx.RB_GROUP)
        self.radio_replace_mode_text02.SetValue(True)
        self.radio_replace_mode_position02 = wx.RadioButton(self.tab02, label=translate("radio_replace_by_position"))
        self.radio_affix_mode_suffix02 = wx.RadioButton(self.tab02, label=translate("radio_affix_suffix"), style=wx.RB_GROUP)
        self.radio_affix_mode_suffix02.SetValue(True)
        self.radio_affix_mode_prefix02 = wx.RadioButton(self.tab02, label=translate("radio_affix_prefix"))
        self.radio_case_mode_upper02 = wx.RadioButton(self.tab02, label=translate("radio_case_upper"), style=wx.RB_GROUP)
        self.radio_case_mode_upper02.SetValue(True)
        self.radio_case_mode_lower02 = wx.RadioButton(self.tab02, label=translate("radio_case_lower"))
        self.radio_case_mode_camel02 = wx.RadioButton(self.tab02, label=translate("radio_case_camel"))
        self.radio_case_mode_capitalize02 = wx.RadioButton(self.tab02, label=translate("radio_case_capitalize"))
        # MP3 命名格式单选（仅"对MP3重命名"显示）
        self.radio_mp3_artist_first02 = wx.RadioButton(self.tab02, label=translate("radio_mp3_artist_first"), style=wx.RB_GROUP)
        self.radio_mp3_artist_first02.SetValue(True)
        self.radio_mp3_title_first02 = wx.RadioButton(self.tab02, label=translate("radio_mp3_title_first"))
        self.radio_mp3_title_only02 = wx.RadioButton(self.tab02, label=translate("radio_mp3_title_only"))
        for _sub_widget in (self.radio_replace_mode_text02, self.radio_replace_mode_position02,
                            self.radio_affix_mode_suffix02, self.radio_affix_mode_prefix02,
                            self.radio_case_mode_upper02, self.radio_case_mode_lower02,
                            self.radio_case_mode_camel02, self.radio_case_mode_capitalize02,
                            self.radio_mp3_artist_first02, self.radio_mp3_title_first02,
                            self.radio_mp3_title_only02):
            _sub_widget.Hide()
        # 位置输入框（初始隐藏）
        self.label_naming_position02 = wx.StaticText(self.tab02, label=translate("label_position"))
        self.label_naming_position02.Hide()
        self.input_naming_position02 = wx.TextCtrl(self.tab02, size=(self.spx_calc(40), -1))
        self.input_naming_position02.Hide()
        # 长度输入框（初始隐藏）
        self.label_length02 = wx.StaticText(self.tab02, label=translate("label_length"))
        self.label_length02.Hide()
        self.input_length02 = wx.TextCtrl(self.tab02, size=(self.spx_calc(40), -1))
        self.input_length02.Hide()
        # 旧文输入框（初始隐藏）
        self.label_naming_oldtext02 = wx.StaticText(self.tab02, label=translate("label_old_text"))
        self.label_naming_oldtext02.Hide()
        self.input_naming_oldtext = wx.TextCtrl(self.tab02, size=(self.spx_calc(80), -1))
        self.input_naming_oldtext.Hide()
        # 文本输入框（始终显示）
        self.label_text02 = wx.StaticText(self.tab02, label=translate("label_new_text"))
        self.label_text02.Hide()
        self.input_naming_text02 = wx.TextCtrl(self.tab02, size=(self.spx_calc(100), -1))
        self.input_naming_text02.Hide()
        # 帮助图标 - 初始隐藏
        self.help_rename02 = wx.StaticText(self.tab02, label="?")
        font_help_rename02 = self.help_rename02.GetFont()
        font_help_rename02.SetPointSize(int(font_help_rename02.GetPointSize()))
        self.help_rename02.SetFont(font_help_rename02)
        self.help_rename02.SetForegroundColour((128, 128, 128))
        self.help_rename02.Hide()
        self.text_rename_tip = translate("tooltip_rename_placeholder")
        self.help_rename02.Bind(wx.EVT_LEFT_DOWN, lambda event: self.show_help_dialog(translate("dialog_title_help", title=translate("help_title_rename")), self.text_rename_tip))
        # 设置提示文本
        tip_rename02 = wx.ToolTip(self.text_rename_tip)
        tip_rename02.SetDelay(500)
        tip_rename02.SetAutoPop(10*1000)
        self.help_rename02.SetToolTip(tip_rename02)
        # 编号参数：位置（复选项，默认文件名末尾）+ 分组（单选项，默认不分组）
        self.label_number_position02 = wx.StaticText(self.tab02, label=translate("label_number_position"))
        self.check_number_pos_start02 = wx.CheckBox(self.tab02, label=translate("check_number_pos_start"))
        # 勾选=编号在文件名前面；不勾选（默认）=编号在文件名末尾
        self.check_number_pos_start02.SetValue(False)
        self.label_number_scope02 = wx.StaticText(self.tab02, label=translate("label_number_scope"))
        self.radio_number_scope_none02 = wx.RadioButton(self.tab02, label=translate("radio_number_scope_none"), style=wx.RB_GROUP)
        self.radio_number_scope_none02.SetValue(True)
        self.radio_number_scope_dir02 = wx.RadioButton(self.tab02, label=translate("radio_number_scope_dir"))
        self.radio_number_scope_match02 = wx.RadioButton(self.tab02, label=translate("radio_number_scope_match"))
        for _num_widget in (self.label_number_position02, self.check_number_pos_start02,
                            self.label_number_scope02,
                            self.radio_number_scope_none02, self.radio_number_scope_dir02,
                            self.radio_number_scope_match02):
            _num_widget.Hide()
        # 应用按钮
        self.btn_apply_naming02 = wx.Button(self.tab02, label=translate("btn_apply_naming"))
        self.btn_apply_naming02.SetMinSize((self.spx_calc(90), -1))
        # 添加到行布局
        sizer_tab02_row1.Add(self.label_naming_method02, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.combo_naming_method02, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(10))
        sizer_tab02_row1.Add(self.radio_replace_mode_text02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.radio_replace_mode_position02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.radio_affix_mode_suffix02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.radio_affix_mode_prefix02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.radio_case_mode_upper02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.radio_case_mode_lower02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.radio_case_mode_camel02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.radio_case_mode_capitalize02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.radio_mp3_artist_first02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.radio_mp3_title_first02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.radio_mp3_title_only02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.label_naming_position02, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT)
        sizer_tab02_row1.Add(self.input_naming_position02, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.label_length02, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab02_row1.Add(self.input_length02, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.label_naming_oldtext02, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab02_row1.Add(self.input_naming_oldtext, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.label_text02, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab02_row1.Add(self.input_naming_text02, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.help_rename02, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab02_row1.Add(self.label_number_position02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(10))
        sizer_tab02_row1.Add(self.check_number_pos_start02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.label_number_scope02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(10))
        sizer_tab02_row1.Add(self.radio_number_scope_none02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.radio_number_scope_dir02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab02_row1.Add(self.radio_number_scope_match02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab02_row1.AddStretchSpacer()
        sizer_tab02_row1.Add(self.btn_apply_naming02, 0, wx.ALIGN_CENTER_VERTICAL)

        # 第2.2行：执行操作
        sizer_tab02_row2 = wx.BoxSizer(wx.HORIZONTAL)
        # 冲突处理：分为文件冲突和目录冲突
        self.label_file_conflict0202 = wx.StaticText(self.tab02, label=translate("label_conflict_handling"))
        self.combo_file_conflict0202 = wx.ComboBox(self.tab02, choices=translate_list("combo_file_conflict"), style=wx.CB_READONLY)
        self.combo_file_conflict0202.SetSelection(0)
        self.combo_dir_conflict0202 = wx.ComboBox(self.tab02, choices=translate_list("combo_dir_conflict"), style=wx.CB_READONLY)
        self.combo_dir_conflict0202.SetSelection(0)
        # 预览结果/终止操作按钮
        self.btn_preview_stop0202 = wx.Button(self.tab02, label=translate("btn_preview"))
        self.btn_preview_stop0202.SetMinSize((self.spx_calc(65), -1))
        # 添加重命名按钮
        self.btn_execute_rename02 = wx.Button(self.tab02, label=translate("btn_execute_rename"))
        self.btn_execute_rename02.SetMinSize((self.spx_calc(90), -1))
        # 添加到行布局
        sizer_tab02_row2.Add(self.label_file_conflict0202, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab02_row2.Add(self.combo_file_conflict0202, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab02_row2.Add(self.combo_dir_conflict0202, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab02_row2.AddStretchSpacer()
        sizer_tab02_row2.Add(self.btn_preview_stop0202, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab02_row2.Add(self.btn_execute_rename02, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        # 添加到Tab布局
        tab02_sizer02.Add(sizer_tab02_row1, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        tab02_sizer02.Add(sizer_tab02_row2, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        self.tab02.SetSizer(tab02_sizer02)

        # ========== 移动 Tab03 ==========
        self.tab03 = wx.Panel(self.notebook)
        tab03_sizer = wx.BoxSizer(wx.VERTICAL)
        # 第3.1行：原来位置
        sizer_tab03_row1 = wx.BoxSizer(wx.HORIZONTAL)
        self.label_source_path03 = wx.StaticText(self.tab03, label=translate("label_source_path"))
        self.input_source_path03 = wx.TextCtrl(self.tab03)
        self.input_source_path03.SetMinSize((self.spx_calc(160), -1))
        self.btn_source_browse03 = wx.Button(self.tab03, label=translate("btn_browse"))
        self.btn_source_browse03.SetMinSize((self.spx_calc(60), -1))
        # 变更为的路径
        self.label_dest_path03 = wx.StaticText(self.tab03, label=translate("label_dest_path"))
        self.input_dest_path03 = wx.TextCtrl(self.tab03)
        self.input_dest_path03.SetMinSize((self.spx_calc(80), -1))
        self.btn_dest_browse03 = wx.Button(self.tab03, label=translate("btn_browse"))
        self.btn_dest_browse03.SetMinSize((self.spx_calc(60), -1))
        # 应用按钮
        self.btn_apply_path03 = wx.Button(self.tab03, label=translate("btn_apply_path"))
        self.btn_apply_path03.SetMinSize((self.spx_calc(90), -1))
        self.btn_apply_path03.Enable(False)
        # 添加到行布局
        sizer_tab03_row1.Add(self.label_source_path03, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab03_row1.Add(self.input_source_path03, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab03_row1.Add(self.btn_source_browse03, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(15))
        sizer_tab03_row1.Add(self.label_dest_path03, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab03_row1.Add(self.input_dest_path03, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab03_row1.Add(self.btn_dest_browse03, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(10))
        sizer_tab03_row1.Add(self.btn_apply_path03, 0, wx.ALIGN_CENTER_VERTICAL)

        # 第3.2行：冲突处理，分为文件冲突和目录冲突
        self.label_file_conflict0302 = wx.StaticText(self.tab03, label=translate("label_conflict_handling"))
        self.combo_file_conflict0302 = wx.ComboBox(self.tab03, choices=translate_list("combo_file_conflict"), style=wx.CB_READONLY)
        self.combo_file_conflict0302.SetSelection(0)
        self.combo_dir_conflict0302 = wx.ComboBox(self.tab03, choices=translate_list("combo_dir_conflict"), style=wx.CB_READONLY)
        self.combo_dir_conflict0302.SetSelection(0)
        # 移动复制选项
        sizer_tab03_row2 = wx.BoxSizer(wx.HORIZONTAL)
        self.label_create_folder03 = wx.StaticText(self.tab03, label=translate("label_create_folder"))
        self.combo_create_folder03 = wx.ComboBox(self.tab03, choices=translate_list("combo_create_folder"), style=wx.CB_READONLY)
        self.combo_create_folder03.SetSelection(0)
        self.vertical_line0321 = wx.StaticLine(self.tab03, style=wx.LI_VERTICAL)
        self.vertical_line0321.SetMinSize((self.spx_calc(1), self.spx_calc(25)))
        # 预览结果/终止操作按钮
        self.btn_preview_stop0302 = wx.Button(self.tab03, label=translate("btn_preview"))
        self.btn_preview_stop0302.SetMinSize((self.spx_calc(65), -1))
        # 添加移动按钮
        self.btn_execute_move03 = wx.Button(self.tab03, label=translate("btn_execute_move"))
        self.btn_execute_move03.SetMinSize((self.spx_calc(90), -1))
        # 添加到行布局
        sizer_tab03_row2.Add(self.label_file_conflict0302, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab03_row2.Add(self.combo_file_conflict0302, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab03_row2.Add(self.combo_dir_conflict0302, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab03_row2.Add(self.vertical_line0321, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(5))
        sizer_tab03_row2.Add(self.label_create_folder03, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(5))
        sizer_tab03_row2.Add(self.combo_create_folder03, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab03_row2.AddStretchSpacer()
        sizer_tab03_row2.Add(self.btn_preview_stop0302, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab03_row2.Add(self.btn_execute_move03, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        # 添加到Tab布局
        tab03_sizer.Add(sizer_tab03_row1, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        tab03_sizer.Add(sizer_tab03_row2, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        self.tab03.SetSizer(tab03_sizer)

        # ========== 复制 Tab04 ==========
        self.tab04 = wx.Panel(self.notebook)
        tab04_sizer = wx.BoxSizer(wx.VERTICAL)
        # 第4.1行：原来位置
        sizer_tab04_row1 = wx.BoxSizer(wx.HORIZONTAL)
        self.label_source_path04 = wx.StaticText(self.tab04, label=translate("label_source_path"))
        self.input_source_path04 = wx.TextCtrl(self.tab04)
        self.input_source_path04.SetMinSize((self.spx_calc(160), -1))
        self.btn_source_browse04 = wx.Button(self.tab04, label=translate("btn_browse"))
        self.btn_source_browse04.SetMinSize((self.spx_calc(60), -1))
        # 变更为的路径
        self.label_dest_path04 = wx.StaticText(self.tab04, label=translate("label_dest_path"))
        self.input_dest_path04 = wx.TextCtrl(self.tab04)
        self.input_dest_path04.SetMinSize((self.spx_calc(80), -1))
        self.btn_dest_browse04 = wx.Button(self.tab04, label=translate("btn_browse"))
        self.btn_dest_browse04.SetMinSize((self.spx_calc(60), -1))
        # 应用按钮
        self.btn_apply_path04 = wx.Button(self.tab04, label=translate("btn_apply_path"))
        self.btn_apply_path04.SetMinSize((self.spx_calc(90), -1))
        self.btn_apply_path04.Enable(False)
        # 添加到行布局
        sizer_tab04_row1.Add(self.label_source_path04, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab04_row1.Add(self.input_source_path04, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab04_row1.Add(self.btn_source_browse04, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(15))
        sizer_tab04_row1.Add(self.label_dest_path04, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab04_row1.Add(self.input_dest_path04, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab04_row1.Add(self.btn_dest_browse04, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(10))
        sizer_tab04_row1.Add(self.btn_apply_path04, 0, wx.ALIGN_CENTER_VERTICAL)

        # 第4.2行：冲突处理，分为文件冲突和目录冲突
        self.label_file_conflict0402 = wx.StaticText(self.tab04, label=translate("label_conflict_handling"))
        self.combo_file_conflict0402 = wx.ComboBox(self.tab04, choices=translate_list("combo_file_conflict"), style=wx.CB_READONLY)
        self.combo_file_conflict0402.SetSelection(0)
        self.combo_dir_conflict0402 = wx.ComboBox(self.tab04, choices=translate_list("combo_dir_conflict"), style=wx.CB_READONLY)
        self.combo_dir_conflict0402.SetSelection(0)
        # 移动复制选项
        sizer_tab04_row2 = wx.BoxSizer(wx.HORIZONTAL)
        self.label_create_folder04 = wx.StaticText(self.tab04, label=translate("label_create_folder"))
        self.combo_create_folder04 = wx.ComboBox(self.tab04, choices=translate_list("combo_create_folder"), style=wx.CB_READONLY)
        self.combo_create_folder04.SetSelection(0)
        self.vertical_line0421 = wx.StaticLine(self.tab04, style=wx.LI_VERTICAL)
        self.vertical_line0421.SetMinSize((self.spx_calc(1), self.spx_calc(25)))
        # 预览结果/终止操作按钮
        self.btn_preview_stop0402 = wx.Button(self.tab04, label=translate("btn_preview"))
        self.btn_preview_stop0402.SetMinSize((self.spx_calc(65), -1))
        # 添加复制按钮
        self.btn_execute_copy04 = wx.Button(self.tab04, label=translate("btn_execute_copy"))
        self.btn_execute_copy04.SetMinSize((self.spx_calc(90), -1))
        # 添加到行布局
        sizer_tab04_row2.Add(self.label_file_conflict0402, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab04_row2.Add(self.combo_file_conflict0402, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab04_row2.Add(self.combo_dir_conflict0402, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab04_row2.Add(self.vertical_line0421, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(5))
        sizer_tab04_row2.Add(self.label_create_folder04, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(5))
        sizer_tab04_row2.Add(self.combo_create_folder04, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab04_row2.AddStretchSpacer()
        sizer_tab04_row2.Add(self.btn_preview_stop0402, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab04_row2.Add(self.btn_execute_copy04, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        # 添加到Tab布局
        tab04_sizer.Add(sizer_tab04_row1, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        tab04_sizer.Add(sizer_tab04_row2, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        self.tab04.SetSizer(tab04_sizer)

        # ========== 压缩 Tab05 ==========
        self.tab05 = wx.Panel(self.notebook)
        tab05_sizer = wx.BoxSizer(wx.VERTICAL)
        # 第5.1行：压缩选项
        sizer_tab05_row1 = wx.BoxSizer(wx.HORIZONTAL)
        self.label_zip_group05 = wx.StaticText(self.tab05, label=translate("label_zip_group"))
        self.radio_zip_foldername05 = wx.RadioButton(self.tab05, label=translate("radio_zip_foldername"), style=wx.RB_GROUP)
        self.radio_zip_matchname05 = wx.RadioButton(self.tab05, label=translate("radio_zip_matchname"))
        self.radio_zip_foldername05.SetValue(True)
        # 压缩分组的帮助图标
        self.help_zip05 = wx.StaticText(self.tab05, label="?")
        font_help_zip05 = self.help_zip05.GetFont()
        font_help_zip05.SetPointSize(int(font_help_zip05.GetPointSize()))
        self.help_zip05.SetFont(font_help_zip05)
        self.help_zip05.SetForegroundColour((128, 128, 128))
        # 压缩分组的提示文本
        tip_zip05 = wx.ToolTip(translate("tooltip_zip_group"))
        tip_zip05.SetDelay(500)
        tip_zip05.SetAutoPop(10*1000)
        self.help_zip05.SetToolTip(tip_zip05)
        # 应用按钮
        self.btn_apply_zip05 = wx.Button(self.tab05, label=translate("btn_apply_zip"))
        self.btn_apply_zip05.SetMinSize((self.spx_calc(90), -1))
        # 压缩目标路径控件（与 Move/Copy 标签页的 Target Path 联动）
        self.label_zip_target05 = wx.StaticText(self.tab05, label=translate("label_zip_target"))
        self.input_zip_target05 = wx.TextCtrl(self.tab05)
        self.input_zip_target05.SetMinSize((self.spx_calc(100), -1))
        self.btn_zip_target_browse05 = wx.Button(self.tab05, label=translate("btn_browse"))
        self.btn_zip_target_browse05.SetMinSize((self.spx_calc(60), -1))
        # 添加到行布局
        sizer_tab05_row1.Add(self.label_zip_group05, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab05_row1.Add(self.radio_zip_foldername05, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab05_row1.Add(self.radio_zip_matchname05, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab05_row1.Add(self.help_zip05, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(15))
        sizer_tab05_row1.Add(self.label_zip_target05, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab05_row1.Add(self.input_zip_target05, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab05_row1.Add(self.btn_zip_target_browse05, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(10))
        sizer_tab05_row1.Add(self.btn_apply_zip05, 0, wx.ALIGN_CENTER_VERTICAL)

        # 第5.2行：添加压缩删除按钮
        sizer_tab05_row2 = wx.BoxSizer(wx.HORIZONTAL)
        # 冲突处理：分为文件冲突和目录冲突
        self.label_zip_conflict05 = wx.StaticText(self.tab05, label=translate("label_conflict_handling"))
        self.combo_file_conflict0502 = wx.ComboBox(self.tab05, choices=translate_list("combo_file_conflict"), style=wx.CB_READONLY)
        self.combo_file_conflict0502.SetSelection(1)  # 默认覆盖重名文件
        self.combo_dir_conflict0502 = wx.ComboBox(self.tab05, choices=translate_list("combo_dir_conflict"), style=wx.CB_READONLY)
        self.combo_dir_conflict0502.SetSelection(2)  # 默认替换重名目录
        # 预览结果/终止操作按钮
        self.btn_preview_stop0502 = wx.Button(self.tab05, label=translate("btn_preview"))
        self.btn_preview_stop0502.SetMinSize((self.spx_calc(65), -1))
        # 添加移动复制按钮
        self.btn_execute_zip05 = wx.Button(self.tab05, label=translate("btn_execute_zip"))
        self.btn_execute_zip05.SetMinSize((self.spx_calc(90), -1))
        # 添加到行布局
        sizer_tab05_row2.Add(self.label_zip_conflict05, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab05_row2.Add(self.combo_file_conflict0502, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab05_row2.Add(self.combo_dir_conflict0502, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab05_row2.AddStretchSpacer()
        sizer_tab05_row2.Add(self.btn_preview_stop0502, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab05_row2.Add(self.btn_execute_zip05, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        # 添加到Tab布局
        tab05_sizer.Add(sizer_tab05_row1, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        tab05_sizer.Add(sizer_tab05_row2, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        self.tab05.SetSizer(tab05_sizer)

        # ========== 解压 Tab06 ==========
        self.tab06 = wx.Panel(self.notebook)
        tab06_sizer = wx.BoxSizer(wx.VERTICAL)
        # 第6.1行：解压分组选项
        sizer_tab06_row1 = wx.BoxSizer(wx.HORIZONTAL)
        self.label_unzip_group06 = wx.StaticText(self.tab06, label=translate("label_unzip_group"))
        self.radio_unzip_package06 = wx.RadioButton(self.tab06, label=translate("radio_unzip_package"), style=wx.RB_GROUP)
        self.radio_unzip_match06 = wx.RadioButton(self.tab06, label=translate("radio_unzip_match"))
        self.radio_unzip_package06.SetValue(True)
        # 解压分组的帮助图标
        self.help_unzip06 = wx.StaticText(self.tab06, label="?")
        font_help_unzip06 = self.help_unzip06.GetFont()
        font_help_unzip06.SetPointSize(int(font_help_unzip06.GetPointSize()))
        self.help_unzip06.SetFont(font_help_unzip06)
        self.help_unzip06.SetForegroundColour((128, 128, 128))
        # 解压分组的提示文本
        tip_unzip06 = wx.ToolTip(translate("tooltip_unzip_group"))
        tip_unzip06.SetDelay(500)
        tip_unzip06.SetAutoPop(10*1000)
        self.help_unzip06.SetToolTip(tip_unzip06)
        # 应用按钮
        self.btn_apply_unzip06 = wx.Button(self.tab06, label=translate("btn_apply_unzip"))
        self.btn_apply_unzip06.SetMinSize((self.spx_calc(90), -1))
        # 解压目标路径控件（与 Move/Copy/Compress 标签页的 Target Path 四方联动）
        self.label_unzip_target06 = wx.StaticText(self.tab06, label=translate("label_unzip_target"))
        self.input_unzip_target06 = wx.TextCtrl(self.tab06)
        self.input_unzip_target06.SetMinSize((self.spx_calc(100), -1))
        self.btn_unzip_target_browse06 = wx.Button(self.tab06, label=translate("btn_browse"))
        self.btn_unzip_target_browse06.SetMinSize((self.spx_calc(60), -1))
        # 添加到行布局
        sizer_tab06_row1.Add(self.label_unzip_group06, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab06_row1.Add(self.radio_unzip_package06, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab06_row1.Add(self.radio_unzip_match06, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab06_row1.Add(self.help_unzip06, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(15))
        sizer_tab06_row1.Add(self.label_unzip_target06, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab06_row1.Add(self.input_unzip_target06, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab06_row1.Add(self.btn_unzip_target_browse06, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(10))
        sizer_tab06_row1.Add(self.btn_apply_unzip06, 0, wx.ALIGN_CENTER_VERTICAL)

        # 第6.2行：冲突处理 + 预览/执行按钮
        sizer_tab06_row2 = wx.BoxSizer(wx.HORIZONTAL)
        # 冲突处理：分为文件冲突和目录冲突（与压缩 Tab05 相同，且与其他标签页联动）
        self.label_unzip_conflict06 = wx.StaticText(self.tab06, label=translate("label_conflict_handling"))
        self.combo_file_conflict0602 = wx.ComboBox(self.tab06, choices=translate_list("combo_file_conflict"), style=wx.CB_READONLY)
        self.combo_file_conflict0602.SetSelection(1)  # 默认覆盖重名文件
        self.combo_dir_conflict0602 = wx.ComboBox(self.tab06, choices=translate_list("combo_dir_conflict"), style=wx.CB_READONLY)
        self.combo_dir_conflict0602.SetSelection(2)  # 默认替换重名目录
        # 预览结果/终止操作按钮
        self.btn_preview_stop0602 = wx.Button(self.tab06, label=translate("btn_preview"))
        self.btn_preview_stop0602.SetMinSize((self.spx_calc(65), -1))
        # 执行按钮
        self.btn_execute_unzip06 = wx.Button(self.tab06, label=translate("btn_execute_unzip"))
        self.btn_execute_unzip06.SetMinSize((self.spx_calc(90), -1))
        # 添加到行布局
        sizer_tab06_row2.Add(self.label_unzip_conflict06, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab06_row2.Add(self.combo_file_conflict0602, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab06_row2.Add(self.combo_dir_conflict0602, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab06_row2.AddStretchSpacer()
        sizer_tab06_row2.Add(self.btn_preview_stop0602, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab06_row2.Add(self.btn_execute_unzip06, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        # 添加到Tab布局
        tab06_sizer.Add(sizer_tab06_row1, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        tab06_sizer.Add(sizer_tab06_row2, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        self.tab06.SetSizer(tab06_sizer)

        # ========== 删除 Tab07 ==========
        self.tab07 = wx.Panel(self.notebook)
        tab07_sizer = wx.BoxSizer(wx.VERTICAL)
        # 第6.1行：删除算法
        sizer_tab07_row1 = wx.BoxSizer(wx.HORIZONTAL)
        self.label_delete_filter07 = wx.StaticText(self.tab07, label=translate("label_delete_filter"))
        self.combo_delete_filter07 = wx.ComboBox(self.tab07, choices=translate_list("combo_delete_filters"), style=wx.CB_READONLY)
        self.combo_delete_filter07.SetSelection(0)
        self.combo_delete_filter07.Bind(wx.EVT_COMBOBOX, self.on_delete_filter_change)
        
        # 添加输入字段
        # 文本输入（用于文件名过滤）
        self.label_text_filter07 = wx.StaticText(self.tab07, label=translate("label_text_filter"))
        self.txt_filename_filter07 = wx.TextCtrl(self.tab07, size=(self.spx_calc(150), -1))
        
        # 数字输入（用于文件大小过滤）
        self.label_size_min07 = wx.StaticText(self.tab07, label=translate("label_size_min"))
        self.txt_size_min07 = wx.TextCtrl(self.tab07, size=(self.spx_calc(80), -1))
        self.combo_size_unit07 = wx.ComboBox(self.tab07, choices=translate_list("combo_size_unit"), style=wx.CB_READONLY)
        self.combo_size_unit07.SetSelection(2)  # 默认MB
        self.label_size_max07 = wx.StaticText(self.tab07, label=translate("label_size_max"))
        self.txt_size_max07 = wx.TextCtrl(self.tab07, size=(self.spx_calc(80), -1))
        
        # 日期时间输入（用于时间过滤）
        self.label_date_from07 = wx.StaticText(self.tab07, label=translate("label_date_from"))
        self.date_from07 = wx.adv.DatePickerCtrl(self.tab07, style=wx.adv.DP_DROPDOWN | wx.adv.DP_SHOWCENTURY)
        self.time_from07 = wx.adv.TimePickerCtrl(self.tab07)
        self.label_date_to07 = wx.StaticText(self.tab07, label=translate("label_date_to"))
        self.date_to07 = wx.adv.DatePickerCtrl(self.tab07, style=wx.adv.DP_DROPDOWN | wx.adv.DP_SHOWCENTURY)
        self.time_to07 = wx.adv.TimePickerCtrl(self.tab07)
        
        # 初始化时隐藏所有输入字段
        self.label_text_filter07.Hide()
        self.txt_filename_filter07.Hide()
        self.label_size_min07.Hide()
        self.txt_size_min07.Hide()
        self.combo_size_unit07.Hide()
        self.label_size_max07.Hide()
        self.txt_size_max07.Hide()
        self.label_date_from07.Hide()
        self.date_from07.Hide()
        self.time_from07.Hide()
        self.label_date_to07.Hide()
        self.date_to07.Hide()
        self.time_to07.Hide()
        
        # 删除过滤的帮助图标
        self.help_delete_filter07 = wx.StaticText(self.tab07, label="?")
        font_help_delete_filter07 = self.help_delete_filter07.GetFont()
        font_help_delete_filter07.SetPointSize(int(font_help_delete_filter07.GetPointSize()))
        self.help_delete_filter07.SetFont(font_help_delete_filter07)
        self.help_delete_filter07.SetForegroundColour((128, 128, 128))
        # 删除过滤的提示文本
        tip_delete_filter07 = wx.ToolTip(translate("tooltip_delete_filter"))
        tip_delete_filter07.SetDelay(500)
        tip_delete_filter07.SetAutoPop(10*1000)
        self.help_delete_filter07.SetToolTip(tip_delete_filter07)
        # 应用按钮
        self.btn_apply_delete07 = wx.Button(self.tab07, label=translate("btn_apply_delete"))
        self.btn_apply_delete07.SetMinSize((self.spx_calc(90), -1))
        self.btn_apply_delete07.Bind(wx.EVT_BUTTON, self.on_apply_delete_filter)
        # 添加到行布局
        sizer_tab07_row1.Add(self.label_delete_filter07, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab07_row1.Add(self.combo_delete_filter07, 0, wx.ALIGN_CENTER_VERTICAL, self.spx_calc(5))
        
        # 添加输入字段到布局
        sizer_tab07_row1.Add(self.label_text_filter07, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(10))
        sizer_tab07_row1.Add(self.txt_filename_filter07, 0, wx.ALIGN_CENTER_VERTICAL)
        
        sizer_tab07_row1.Add(self.label_size_min07, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(10))
        sizer_tab07_row1.Add(self.txt_size_min07, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab07_row1.Add(self.label_size_max07, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(10))
        sizer_tab07_row1.Add(self.txt_size_max07, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab07_row1.Add(self.combo_size_unit07, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        
        sizer_tab07_row1.Add(self.label_date_from07, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(10))
        sizer_tab07_row1.Add(self.date_from07, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab07_row1.Add(self.time_from07, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab07_row1.Add(self.label_date_to07, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(10))
        sizer_tab07_row1.Add(self.date_to07, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab07_row1.Add(self.time_to07, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        
        sizer_tab07_row1.Add(self.help_delete_filter07, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(5))
        sizer_tab07_row1.AddStretchSpacer()
        sizer_tab07_row1.Add(self.btn_apply_delete07, 0, wx.ALIGN_CENTER_VERTICAL)

        # 第6.2行：删除目标
        self.label_delete_target07 = wx.StaticText(self.tab07, label=translate("label_delete_target"))
        self.radio_delete_target_old07 = wx.RadioButton(self.tab07, label=translate("radio_delete_target_old"), style=wx.RB_GROUP)
        self.radio_delete_target_old07.SetValue(True)
        self.radio_delete_target_new07 = wx.RadioButton(self.tab07, label=translate("radio_delete_target_new"))
        # 预览结果/终止操作按钮
        sizer_tab07_row2 = wx.BoxSizer(wx.HORIZONTAL)
        # 预览结果/终止操作按钮
        self.btn_preview_stop0702 = wx.Button(self.tab07, label=translate("btn_preview"))
        self.btn_preview_stop0702.SetMinSize((self.spx_calc(65), -1))
        # 添加删除按钮
        self.btn_execute_delete07 = wx.Button(self.tab07, label=translate("btn_execute_delete"))
        self.btn_execute_delete07.SetMinSize((self.spx_calc(90), -1))
        # 添加到行布局
        sizer_tab07_row2.Add(self.label_delete_target07, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab07_row2.Add(self.radio_delete_target_old07, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab07_row2.Add(self.radio_delete_target_new07, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab07_row2.AddStretchSpacer()
        sizer_tab07_row2.Add(self.btn_preview_stop0702, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab07_row2.Add(self.btn_execute_delete07, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        # 添加到Tab布局
        tab07_sizer.Add(sizer_tab07_row1, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        tab07_sizer.Add(sizer_tab07_row2, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        self.tab07.SetSizer(tab07_sizer)

        # ========== 去重 Tab08 ==========
        self.tab08 = wx.Panel(self.notebook)
        tab08_sizer = wx.BoxSizer(wx.VERTICAL)
        # 第7.1行：查重算法
        sizer_tab08_row1 = wx.BoxSizer(wx.HORIZONTAL)
        self.label_duplicate_algorithm08 = wx.StaticText(self.tab08, label=translate("label_duplicate_algorithm"))
        self.combo_duplicate_algorithm08 = wx.ComboBox(self.tab08, choices=translate_list("combo_duplicate_algorithms"), style=wx.CB_READONLY)
        self.combo_duplicate_algorithm08.SetSelection(0)
        # 压缩分组的帮助图标
        self.help_duplicate_algorithm08 = wx.StaticText(self.tab08, label="?")
        font_help_duplicate_algorithm08 = self.help_duplicate_algorithm08.GetFont()
        font_help_duplicate_algorithm08.SetPointSize(int(font_help_duplicate_algorithm08.GetPointSize()))
        self.help_duplicate_algorithm08.SetFont(font_help_duplicate_algorithm08)
        self.help_duplicate_algorithm08.SetForegroundColour((128, 128, 128))
        # 去重规则
        self.label_duplicate_group08 = wx.StaticText(self.tab08, label=translate("label_duplicate_rule"))
        self.combo_duplicate_rule08 = wx.ComboBox(self.tab08, choices=translate_list("combo_duplicate_rules"), style=wx.CB_READONLY)
        self.combo_duplicate_rule08.SetSelection(0)
        # 查重算法的提示文本
        tip_duplicate_algorithm08 = wx.ToolTip(translate("tooltip_duplicate_algorithm"))
        tip_duplicate_algorithm08.SetDelay(500)
        tip_duplicate_algorithm08.SetAutoPop(10*1000)
        self.help_duplicate_algorithm08.SetToolTip(tip_duplicate_algorithm08)
        self.btn_apply_duplicate08 = wx.Button(self.tab08, label=translate("btn_apply_duplicate"))
        self.btn_apply_duplicate08.SetMinSize((self.spx_calc(90), -1))
        # 添加到行布局
        sizer_tab08_row1.Add(self.label_duplicate_algorithm08, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab08_row1.Add(self.combo_duplicate_algorithm08, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab08_row1.Add(self.label_duplicate_group08, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab08_row1.Add(self.combo_duplicate_rule08, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        sizer_tab08_row1.Add(self.help_duplicate_algorithm08, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(5))
        sizer_tab08_row1.AddStretchSpacer()
        sizer_tab08_row1.Add(self.btn_apply_duplicate08, 0, wx.ALIGN_CENTER_VERTICAL)

        # 第7.2行：删除选项
        self.label_delete_method08 = wx.StaticText(self.tab08, label=translate("label_delete_method"))
        self.radio_delete_recycle08 = wx.RadioButton(self.tab08, label=translate("radio_delete_recycle"), style=wx.RB_GROUP)
        self.radio_delete_recycle08.SetValue(True)
        # 预览结果/终止操作按钮
        sizer_tab08_row2 = wx.BoxSizer(wx.HORIZONTAL)
        # 预览结果/终止操作按钮
        self.btn_preview_stop0802 = wx.Button(self.tab08, label=translate("btn_preview"))
        self.btn_preview_stop0802.SetMinSize((self.spx_calc(65), -1))
        # 添加去重按钮
        self.btn_execute_duplicate08 = wx.Button(self.tab08, label=translate("btn_execute_duplicate"))
        self.btn_execute_duplicate08.SetMinSize((self.spx_calc(90), -1))
        # 添加到行布局
        sizer_tab08_row2.Add(self.label_delete_method08, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_tab08_row2.Add(self.radio_delete_recycle08, 0, wx.ALIGN_CENTER_VERTICAL, self.spx_calc(5))
        sizer_tab08_row2.AddStretchSpacer()
        sizer_tab08_row2.Add(self.btn_preview_stop0802, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_tab08_row2.Add(self.btn_execute_duplicate08, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        # 添加到Tab布局
        tab08_sizer.Add(sizer_tab08_row1, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        tab08_sizer.Add(sizer_tab08_row2, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        self.tab08.SetSizer(tab08_sizer)

        # ========== 更多工具 Tab09 ==========
        self.tab09 = wx.Panel(self.notebook)
        self.tab09.SetBackgroundColour(wx.Colour(248, 248, 248))
        tab09_sizer = wx.BoxSizer(wx.VERTICAL)
        # 第8.1行：标题区域 - 灵表文件处理工具
        sizer_tab09_row1 = wx.BoxSizer(wx.HORIZONTAL)
        title09_text = translate("label_title")
        self.label_title09 = wx.StaticText(self.tab09, label=title09_text)
        font_title09 = self.label_title09.GetFont()
        font_title09.SetPointSize(int(font_title09.GetPointSize() * 1.4))
        font_title09.SetWeight(wx.FONTWEIGHT_BOLD)
        self.label_title09.SetFont(font_title09)
        self.label_title09.SetForegroundColour((0, 51, 102))
        self._apply_measured_min_size(self.label_title09, title09_text, font_title09)
        sizer_tab09_row1.Add(self.label_title09, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(20))
        sizer_tab09_row1.AddStretchSpacer()
        # 第8.2行：版本、开发者和开源协议信息
        sizer_tab09_row2 = wx.BoxSizer(wx.HORIZONTAL)
        self.label_intro09 = wx.StaticText(self.tab09, label=translate("label_intro"))
        font_intro09 = self.label_intro09.GetFont()
        font_intro09.SetPointSize(int(font_intro09.GetPointSize() * 0.95))
        self.label_intro09.SetFont(font_intro09)
        self.label_intro09.SetForegroundColour((80, 80, 80))
        sizer_tab09_row2.Add(self.label_intro09, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(20))
        sizer_tab09_row2.AddStretchSpacer()
        # 第8.3行：官方网站和反馈链接
        sizer_tab09_row3 = wx.BoxSizer(wx.HORIZONTAL)
        self.label_website09 = wx.StaticText(self.tab09, label=translate("label_website"))
        font_website09 = self.label_website09.GetFont()
        font_website09.SetPointSize(int(font_website09.GetPointSize() * 0.9))
        self.label_website09.SetFont(font_website09)
        self.label_website09.SetForegroundColour((0, 102, 204))
        self.label_website09.Bind(wx.EVT_LEFT_DOWN, lambda event: self.on_tool_click_09("https://tabulexflow.com"))
        self._bind_link_cursor(self.label_website09, self.tab09)
        sizer_tab09_row3.Add(self.label_website09, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(20))
        sizer_tab09_row3.AddStretchSpacer()
        self.label_feedback09 = wx.StaticText(self.tab09, label=translate("label_feedback"))
        font_feedback09 = self.label_feedback09.GetFont()
        font_feedback09.SetPointSize(int(font_feedback09.GetPointSize() * 0.9))
        self.label_feedback09.SetFont(font_feedback09)
        self.label_feedback09.SetForegroundColour((0, 102, 204))
        self.label_feedback09.Bind(wx.EVT_LEFT_DOWN, lambda event: self.on_tool_click_09("https://tabulexflow.com/feedback"))
        self._bind_link_cursor(self.label_feedback09, self.tab09)
        sizer_tab09_row3.Add(self.label_feedback09, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(20))
        # 添加到Tab布局
        tab09_sizer.Add(sizer_tab09_row1, 0, wx.EXPAND | wx.TOP, self.spx_calc(20))
        tab09_sizer.Add(sizer_tab09_row2, 0, wx.EXPAND | wx.TOP, self.spx_calc(5))
        tab09_sizer.Add(sizer_tab09_row3, 0, wx.EXPAND | wx.TOP, self.spx_calc(5))
        self.tab09.SetSizer(tab09_sizer)
        
        # ========== 更多工具容器 ==========
        moretool_container_sizer = wx.BoxSizer(wx.VERTICAL)
        # 第8.4行：更多效率工具区域标题
        sizer_more_row1 = wx.BoxSizer(wx.HORIZONTAL)
        self.label_tools_title09 = wx.StaticText(self.moretool_container, label=translate("label_tools_title"))
        font_tools_title09 = self.label_tools_title09.GetFont()
        font_tools_title09.SetPointSize(int(font_tools_title09.GetPointSize() * 1.4))
        font_tools_title09.SetWeight(wx.FONTWEIGHT_BOLD)
        self.label_tools_title09.SetFont(font_tools_title09)
        self.label_tools_title09.SetForegroundColour((0, 51, 102))
        self._apply_measured_min_size(self.label_tools_title09, translate("label_tools_title"), font_tools_title09)
        sizer_more_row1.Add(self.label_tools_title09, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(20))
        sizer_more_row1.AddStretchSpacer()
        moretool_container_sizer.Add(sizer_more_row1, 0, wx.EXPAND | wx.TOP, self.spx_calc(10))
        # 第8.5行：工具卡片容器 (2行2列)
        sizer_more_tools = wx.BoxSizer(wx.VERTICAL)
        # 工具1：批量文件创建
        self.panel_tool1_09 = RoundedPanel(self.moretool_container, radius=4, border_colour=(220, 220, 220), background_colour=wx.WHITE)
        self.panel_tool1_09.SetMinSize((self.spx_calc(120), self.spx_calc(70)))
        sizer_tool1_09 = wx.BoxSizer(wx.HORIZONTAL)
        self.label_tool1_icon_09 = wx.StaticText(self.panel_tool1_09, label="📂")
        font_tool1_icon = self.label_tool1_icon_09.GetFont()
        font_tool1_icon.SetPointSize(int(font_tool1_icon.GetPointSize() * 3.0))
        self.label_tool1_icon_09.SetFont(font_tool1_icon)
        self.label_tool1_icon_09.SetForegroundColour((255, 180, 0))
        self._apply_measured_min_size(self.label_tool1_icon_09, "📂", font_tool1_icon)
        sizer_tool1_right = wx.BoxSizer(wx.VERTICAL)
        self.label_tool1_name_09 = wx.StaticText(self.panel_tool1_09, label=translate("label_tool1_name"))
        font_tool1_name = self.label_tool1_name_09.GetFont()
        font_tool1_name.SetWeight(wx.FONTWEIGHT_BOLD)
        self.label_tool1_name_09.SetFont(font_tool1_name)
        self.label_tool1_name_09.SetForegroundColour((0, 51, 102))
        self._apply_measured_min_size(self.label_tool1_name_09, translate("label_tool1_name"), font_tool1_name)
        sizer_tool1_desc_row = wx.BoxSizer(wx.HORIZONTAL)
        self.label_tool1_desc_09 = wx.StaticText(self.panel_tool1_09, label=translate("label_tool1_desc"))
        font_tool1_desc = self.label_tool1_desc_09.GetFont()
        font_tool1_desc.SetPointSize(int(font_tool1_desc.GetPointSize() * 0.85))
        self.label_tool1_desc_09.SetFont(font_tool1_desc)
        self.label_tool1_desc_09.SetForegroundColour((100, 100, 100))
        sizer_tool1_desc_row.Add(self.label_tool1_desc_09, 1, wx.ALIGN_CENTER_VERTICAL)
        self.label_tool1_download_09 = wx.StaticText(self.panel_tool1_09, label="⏬")
        self.label_tool1_download_09.SetForegroundColour((0, 102, 204))
        self.label_tool1_download_09.SetToolTip(translate("tooltip_download"))
        self.label_tool1_download_09.Bind(wx.EVT_LEFT_DOWN, lambda event: self.on_tool_click_09("https://tabulexflow.com/download"))
        self._bind_link_cursor(self.label_tool1_download_09, self.panel_tool1_09)
        sizer_tool1_desc_row.Add(self.label_tool1_download_09, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(5))
        sizer_tool1_right.Add(self.label_tool1_name_09, 0, wx.ALIGN_LEFT | wx.TOP, self.spx_calc(2))
        sizer_tool1_right.Add(sizer_tool1_desc_row, 1, wx.EXPAND | wx.BOTTOM, self.spx_calc(2))
        sizer_tool1_09.Add(self.label_tool1_icon_09, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(15))
        sizer_tool1_09.Add(sizer_tool1_right, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(10))
        self.panel_tool1_09.SetSizer(sizer_tool1_09)
        # 工具2：批量格式转换
        self.panel_tool2_09 = RoundedPanel(self.moretool_container, radius=4, border_colour=(220, 220, 220), background_colour=wx.WHITE)
        self.panel_tool2_09.SetMinSize((self.spx_calc(120), self.spx_calc(70)))
        sizer_tool2_09 = wx.BoxSizer(wx.HORIZONTAL)
        self.label_tool2_icon_09 = wx.StaticText(self.panel_tool2_09, label="🔄")
        font_tool2_icon = self.label_tool2_icon_09.GetFont()
        font_tool2_icon.SetPointSize(int(font_tool2_icon.GetPointSize() * 3.0))
        self.label_tool2_icon_09.SetFont(font_tool2_icon)
        self.label_tool2_icon_09.SetForegroundColour((0, 150, 255))
        self._apply_measured_min_size(self.label_tool2_icon_09, "🔄", font_tool2_icon)
        sizer_tool2_right = wx.BoxSizer(wx.VERTICAL)
        self.label_tool2_name_09 = wx.StaticText(self.panel_tool2_09, label=translate("label_tool2_name"))
        font_tool2_name = self.label_tool2_name_09.GetFont()
        font_tool2_name.SetWeight(wx.FONTWEIGHT_BOLD)
        self.label_tool2_name_09.SetFont(font_tool2_name)
        self.label_tool2_name_09.SetForegroundColour((0, 51, 102))
        self._apply_measured_min_size(self.label_tool2_name_09, translate("label_tool2_name"), font_tool2_name)
        sizer_tool2_desc_row = wx.BoxSizer(wx.HORIZONTAL)
        self.label_tool2_desc_09 = wx.StaticText(self.panel_tool2_09, label=translate("label_tool2_desc"))
        font_tool2_desc = self.label_tool2_desc_09.GetFont()
        font_tool2_desc.SetPointSize(int(font_tool2_desc.GetPointSize() * 0.85))
        self.label_tool2_desc_09.SetFont(font_tool2_desc)
        self.label_tool2_desc_09.SetForegroundColour((100, 100, 100))
        sizer_tool2_desc_row.Add(self.label_tool2_desc_09, 1, wx.ALIGN_CENTER_VERTICAL)
        self.label_tool2_download_09 = wx.StaticText(self.panel_tool2_09, label="⏬")
        self.label_tool2_download_09.SetForegroundColour((0, 102, 204))
        self.label_tool2_download_09.SetToolTip(translate("tooltip_download"))
        self.label_tool2_download_09.Bind(wx.EVT_LEFT_DOWN, lambda event: self.on_tool_click_09("https://tabulexflow.com/download"))
        self._bind_link_cursor(self.label_tool2_download_09, self.panel_tool2_09)
        sizer_tool2_desc_row.Add(self.label_tool2_download_09, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(5))
        sizer_tool2_right.Add(self.label_tool2_name_09, 0, wx.ALIGN_LEFT | wx.TOP, self.spx_calc(2))
        sizer_tool2_right.Add(sizer_tool2_desc_row, 1, wx.EXPAND | wx.BOTTOM, self.spx_calc(2))
        sizer_tool2_09.Add(self.label_tool2_icon_09, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(15))
        sizer_tool2_09.Add(sizer_tool2_right, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(10))
        self.panel_tool2_09.SetSizer(sizer_tool2_09)
        # 第一行工具
        sizer_more_tools_row1 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_more_tools_row1.Add(self.panel_tool1_09, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, self.spx_calc(10))
        sizer_more_tools_row1.Add(self.panel_tool2_09, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, self.spx_calc(10))
        # 工具3：BOM创建工具
        self.panel_tool3_09 = RoundedPanel(self.moretool_container, radius=4, border_colour=(220, 220, 220), background_colour=wx.WHITE)
        self.panel_tool3_09.SetMinSize((self.spx_calc(120), self.spx_calc(70)))
        sizer_tool3_09 = wx.BoxSizer(wx.HORIZONTAL)
        self.label_tool3_icon_09 = wx.StaticText(self.panel_tool3_09, label="📦")
        font_tool3_icon = self.label_tool3_icon_09.GetFont()
        font_tool3_icon.SetPointSize(int(font_tool3_icon.GetPointSize() * 3.0))
        self.label_tool3_icon_09.SetFont(font_tool3_icon)
        self.label_tool3_icon_09.SetForegroundColour((0, 180, 150))
        self._apply_measured_min_size(self.label_tool3_icon_09, "📦", font_tool3_icon)
        sizer_tool3_right = wx.BoxSizer(wx.VERTICAL)
        self.label_tool3_name_09 = wx.StaticText(self.panel_tool3_09, label=translate("label_tool3_name"))
        font_tool3_name = self.label_tool3_name_09.GetFont()
        font_tool3_name.SetWeight(wx.FONTWEIGHT_BOLD)
        self.label_tool3_name_09.SetFont(font_tool3_name)
        self.label_tool3_name_09.SetForegroundColour((0, 51, 102))
        self._apply_measured_min_size(self.label_tool3_name_09, translate("label_tool3_name"), font_tool3_name)
        sizer_tool3_desc_row = wx.BoxSizer(wx.HORIZONTAL)
        self.label_tool3_desc_09 = wx.StaticText(self.panel_tool3_09, label=translate("label_tool3_desc"))
        font_tool3_desc = self.label_tool3_desc_09.GetFont()
        font_tool3_desc.SetPointSize(int(font_tool3_desc.GetPointSize() * 0.85))
        self.label_tool3_desc_09.SetFont(font_tool3_desc)
        self.label_tool3_desc_09.SetForegroundColour((100, 100, 100))
        sizer_tool3_desc_row.Add(self.label_tool3_desc_09, 1, wx.ALIGN_CENTER_VERTICAL)
        self.label_tool3_download_09 = wx.StaticText(self.panel_tool3_09, label="⏬")
        self.label_tool3_download_09.SetForegroundColour((0, 102, 204))
        self.label_tool3_download_09.SetToolTip(translate("tooltip_download"))
        self.label_tool3_download_09.Bind(wx.EVT_LEFT_DOWN, lambda event: self.on_tool_click_09("https://tabulexflow.com/download"))
        self._bind_link_cursor(self.label_tool3_download_09, self.panel_tool3_09)
        sizer_tool3_desc_row.Add(self.label_tool3_download_09, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(5))
        sizer_tool3_right.Add(self.label_tool3_name_09, 0, wx.ALIGN_LEFT | wx.TOP, self.spx_calc(2))
        sizer_tool3_right.Add(sizer_tool3_desc_row, 1, wx.EXPAND | wx.BOTTOM, self.spx_calc(2))
        sizer_tool3_09.Add(self.label_tool3_icon_09, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(15))
        sizer_tool3_09.Add(sizer_tool3_right, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(10))
        self.panel_tool3_09.SetSizer(sizer_tool3_09)
        # 工具4：获取更多工具
        self.panel_tool4_09 = RoundedPanel(self.moretool_container, radius=4, border_colour=(220, 220, 220), background_colour=wx.WHITE)
        self.panel_tool4_09.SetMinSize((self.spx_calc(120), self.spx_calc(70)))
        sizer_tool4_09 = wx.BoxSizer(wx.HORIZONTAL)
        self.label_tool4_icon_09 = wx.StaticText(self.panel_tool4_09, label="🌟")
        font_tool4_icon = self.label_tool4_icon_09.GetFont()
        font_tool4_icon.SetPointSize(int(font_tool4_icon.GetPointSize() * 3.0))
        self.label_tool4_icon_09.SetFont(font_tool4_icon)
        self.label_tool4_icon_09.SetForegroundColour((255, 200, 50))
        self._apply_measured_min_size(self.label_tool4_icon_09, "🌟", font_tool4_icon)
        sizer_tool4_right = wx.BoxSizer(wx.VERTICAL)
        self.label_tool4_name_09 = wx.StaticText(self.panel_tool4_09, label=translate("label_tool4_name"))
        font_tool4_name = self.label_tool4_name_09.GetFont()
        font_tool4_name.SetWeight(wx.FONTWEIGHT_BOLD)
        self.label_tool4_name_09.SetFont(font_tool4_name)
        self.label_tool4_name_09.SetForegroundColour((0, 51, 102))
        self._apply_measured_min_size(self.label_tool4_name_09, translate("label_tool4_name"), font_tool4_name)
        sizer_tool4_desc_row = wx.BoxSizer(wx.HORIZONTAL)
        self.label_tool4_desc_09 = wx.StaticText(self.panel_tool4_09, label=translate("label_tool4_desc"))
        font_tool4_desc = self.label_tool4_desc_09.GetFont()
        font_tool4_desc.SetPointSize(int(font_tool4_desc.GetPointSize() * 0.85))
        self.label_tool4_desc_09.SetFont(font_tool4_desc)
        self.label_tool4_desc_09.SetForegroundColour((100, 100, 100))
        sizer_tool4_desc_row.Add(self.label_tool4_desc_09, 1, wx.ALIGN_CENTER_VERTICAL)
        self.label_tool4_download_09 = wx.StaticText(self.panel_tool4_09, label="⏬")
        self.label_tool4_download_09.SetForegroundColour((0, 102, 204))
        self.label_tool4_download_09.SetToolTip(translate("tooltip_download"))
        self.label_tool4_download_09.Bind(wx.EVT_LEFT_DOWN, lambda event: self.on_tool_click_09("https://tabulexflow.com/download"))
        self._bind_link_cursor(self.label_tool4_download_09, self.panel_tool4_09)
        sizer_tool4_desc_row.Add(self.label_tool4_download_09, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(5))
        sizer_tool4_right.Add(self.label_tool4_name_09, 0, wx.ALIGN_LEFT | wx.TOP, self.spx_calc(2))
        sizer_tool4_right.Add(sizer_tool4_desc_row, 1, wx.EXPAND | wx.BOTTOM, self.spx_calc(2))
        sizer_tool4_09.Add(self.label_tool4_icon_09, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(15))
        sizer_tool4_09.Add(sizer_tool4_right, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(10))
        self.panel_tool4_09.SetSizer(sizer_tool4_09)
        # 第二行工具
        sizer_more_tools_row2 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_more_tools_row2.Add(self.panel_tool3_09, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, self.spx_calc(10))
        sizer_more_tools_row2.Add(self.panel_tool4_09, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, self.spx_calc(10))
        # 添加工具行到主容器
        sizer_more_tools.Add(sizer_more_tools_row1, 1, wx.EXPAND)
        sizer_more_tools.Add(sizer_more_tools_row2, 1, wx.EXPAND | wx.TOP, self.spx_calc(10))
        # 减少"更多效率工具"下面的空白，并添加左边距与标题对齐
        moretool_container_sizer.Add(sizer_more_tools, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, self.spx_calc(10))
        # 添加开发者和开源协议行到主容器
        # "更多效率工具"卡片描述（保留原始文本，用于按可用宽度重新换行）
        self._tool_card_desc_labels = [
            (self.label_tool1_desc_09, translate("label_tool1_desc")),
            (self.label_tool2_desc_09, translate("label_tool2_desc")),
            (self.label_tool3_desc_09, translate("label_tool3_desc")),
            (self.label_tool4_desc_09, translate("label_tool4_desc")),
        ]
        self.moretool_container.SetSizer(moretool_container_sizer)
        # 全部控件尺寸修正后统一再次布局（覆盖wxGTK首次布局使用的过期尺寸缓存）
        wx.CallAfter(self.tab09.Layout)
        # 两列卡片等宽；工具描述按卡片可用宽度换行（容器尺寸变化时重新换行）
        self._tool_card_wrap_width = -1
        self.moretool_container.Bind(wx.EVT_SIZE, self._on_tool_cards_size)
        wx.CallAfter(self._rewrap_tool_card_descriptions)

        # 总布局：添加加Tab到Notebook
        self.notebook.AddPage(self.tab01, translate("tab_search"))
        self.notebook.AddPage(self.tab02, translate("tab_rename"))
        self.notebook.AddPage(self.tab03, translate("tab_move"))
        self.notebook.AddPage(self.tab04, translate("tab_copy"))
        self.notebook.AddPage(self.tab05, translate("tab_zip"))
        self.notebook.AddPage(self.tab06, translate("tab_unzip"))
        self.notebook.AddPage(self.tab07, translate("tab_delete"))
        self.notebook.AddPage(self.tab08, translate("tab_duplicate"))
        # OSS 社区版不显示"关于"标签页（仅非 OSS 版显示）；该页关联的"更多效率工具"卡片随之不展示
        if not IS_OSS_COMMUNITY_BUILD:
            self.notebook.AddPage(self.tab09, translate("tab_more"))
        # 总布局：创建grid表格
        callbacks = {
            'update_status': lambda text: self.status_bar.SetStatusText(text, 0),
            'disable_controls': self.disable_controls_during_operation,
            'restore_controls': self.restore_controls_after_operation,
            'get_search_folder': lambda: self.search_folder,
            'set_search_folder': self.set_search_folder,
            'adjust_table_rows': self.adjust_table_rows,
            'layout_frame': self.layout_frame
        }
        parent_for_grid = self.frame if not self.is_embedded else self.panel.GetTopLevelParent()
        self.file_grid = tfo_CustomGrid(self.panel, parent_for_grid, callbacks, editable=True)
        # 总布局：状态栏
        self.status_bar = wx.StatusBar(self.panel)
        self.status_bar.SetFieldsCount(2)
        self.status_bar.SetStatusWidths([-1, self.spx_calc(200)])
        self.status_bar.SetStatusText(translate("status_ready"), 0)
        self.status_bar.SetStatusText("", 1)
        # 初始化时隐藏moretool_container
        self.moretool_container.Hide()

        # 绑定按钮事件
        self.btn_search_browse01.Bind(wx.EVT_BUTTON, self.on_browse_source)
        self.btn_match_edit01.Bind(wx.EVT_BUTTON, self.on_match_edit)
        self.btn_apply_search01.Bind(wx.EVT_BUTTON, self.on_apply_search)
        self.btn_import_grid01.Bind(wx.EVT_BUTTON, self.on_import_grid01)
        self.btn_export_grid01.Bind(wx.EVT_BUTTON, self.on_export_grid01)
        self.btn_apply_naming02.Bind(wx.EVT_BUTTON, self.on_apply_naming)
        self.btn_execute_rename02.Bind(wx.EVT_BUTTON, self.on_execute_move)
        self.btn_preview_stop0202.Bind(wx.EVT_BUTTON, self.on_preview_rename_move_copy)
        self.btn_preview_stop0302.Bind(wx.EVT_BUTTON, self.on_preview_rename_move_copy)
        self.btn_preview_stop0402.Bind(wx.EVT_BUTTON, self.on_preview_rename_move_copy)
        self.btn_preview_stop0502.Bind(wx.EVT_BUTTON, self.on_preview_zip)
        self.btn_preview_stop0602.Bind(wx.EVT_BUTTON, self.on_preview_unzip)
        self.btn_preview_stop0702.Bind(wx.EVT_BUTTON, self.on_preview_delete)
        self.btn_preview_stop0802.Bind(wx.EVT_BUTTON, self.on_preview_duplicate)
        self.btn_execute_move03.Bind(wx.EVT_BUTTON, self.on_execute_move)
        self.btn_execute_copy04.Bind(wx.EVT_BUTTON, self.on_execute_copy)
        self.btn_dest_browse03.Bind(wx.EVT_BUTTON, self.on_browse_dest)
        
        # 绑定删除目标单选框事件（tab07和tab08联动）
        self.radio_delete_target_old07.Bind(wx.EVT_RADIOBUTTON, self.on_delete_target_change)
        self.radio_delete_target_new07.Bind(wx.EVT_RADIOBUTTON, self.on_delete_target_change)
        
        # 绑定notebook页面切换事件
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_notebook_page_changed)
        self.btn_source_browse03.Bind(wx.EVT_BUTTON, self.on_browse_source)
        self.btn_apply_path03.Bind(wx.EVT_BUTTON, self.on_apply_path)
        self.btn_dest_browse04.Bind(wx.EVT_BUTTON, self.on_browse_dest)
        self.btn_source_browse04.Bind(wx.EVT_BUTTON, self.on_browse_source)
        self.btn_apply_path04.Bind(wx.EVT_BUTTON, self.on_apply_path)
        self.btn_execute_zip05.Bind(wx.EVT_BUTTON, self.on_execute_zip)
        self.btn_apply_zip05.Bind(wx.EVT_BUTTON, self.on_apply_zip_group)
        self.btn_zip_target_browse05.Bind(wx.EVT_BUTTON, self.on_browse_zip_target)
        self.btn_execute_unzip06.Bind(wx.EVT_BUTTON, self.on_execute_unzip)
        self.btn_apply_unzip06.Bind(wx.EVT_BUTTON, self.on_apply_unzip)
        self.btn_unzip_target_browse06.Bind(wx.EVT_BUTTON, self.on_browse_unzip_target)
        self.btn_execute_delete07.Bind(wx.EVT_BUTTON, self.on_execute_delete)
        self.btn_apply_duplicate08.Bind(wx.EVT_BUTTON, self.on_apply_duplicate)
        self.btn_execute_duplicate08.Bind(wx.EVT_BUTTON, self.on_execute_duplicate)
        # 绑定创建目录下拉框事件
        self.combo_file_conflict0202.Bind(wx.EVT_COMBOBOX, self.on_combo_file_conflict_change)
        self.combo_dir_conflict0202.Bind(wx.EVT_COMBOBOX, self.on_combo_dir_conflict_change)
        self.combo_file_conflict0302.Bind(wx.EVT_COMBOBOX, self.on_combo_file_conflict_change)
        self.combo_dir_conflict0302.Bind(wx.EVT_COMBOBOX, self.on_combo_dir_conflict_change)
        self.combo_file_conflict0402.Bind(wx.EVT_COMBOBOX, self.on_combo_file_conflict_change)
        self.combo_dir_conflict0402.Bind(wx.EVT_COMBOBOX, self.on_combo_dir_conflict_change)
        self.combo_file_conflict0502.Bind(wx.EVT_COMBOBOX, self.on_combo_file_conflict_change)
        self.combo_dir_conflict0502.Bind(wx.EVT_COMBOBOX, self.on_combo_dir_conflict_change)
        self.combo_file_conflict0602.Bind(wx.EVT_COMBOBOX, self.on_combo_file_conflict_change)
        self.combo_dir_conflict0602.Bind(wx.EVT_COMBOBOX, self.on_combo_dir_conflict_change)

        self.input_search_path01.Bind(wx.EVT_TEXT, self.on_search_path_changed)
        self.input_match_text01.Bind(wx.EVT_TEXT, self.on_match_text_inputted)
        self.combo_naming_method02.Bind(wx.EVT_COMBOBOX, self.on_combo_naming_method02_changed)
        for _sub_radio in (self.radio_replace_mode_text02, self.radio_replace_mode_position02,
                           self.radio_affix_mode_suffix02, self.radio_affix_mode_prefix02,
                           self.radio_case_mode_upper02, self.radio_case_mode_lower02,
                           self.radio_case_mode_camel02, self.radio_case_mode_capitalize02,
                           self.radio_mp3_artist_first02, self.radio_mp3_title_first02,
                           self.radio_mp3_title_only02):
            _sub_radio.Bind(wx.EVT_RADIOBUTTON, self.on_naming_submode_changed)
        # 绑定创建目录组合框的联动事件
        self.combo_create_folder03.Bind(wx.EVT_COMBOBOX, self.on_combo_create_folder_changed)
        self.combo_create_folder04.Bind(wx.EVT_COMBOBOX, self.on_combo_create_folder_changed)
        self.input_source_path03.Bind(wx.EVT_TEXT, self.on_source_path_changed)
        self.input_dest_path03.Bind(wx.EVT_TEXT, self.on_dest_path_changed)
        self.input_source_path04.Bind(wx.EVT_TEXT, self.on_source_path_changed)
        self.input_dest_path04.Bind(wx.EVT_TEXT, self.on_dest_path_changed)
        self.input_zip_target05.Bind(wx.EVT_TEXT, self.on_dest_path_changed)
        self.input_unzip_target06.Bind(wx.EVT_TEXT, self.on_dest_path_changed)
        # 组装主布局
        self.sizer_main.Add(self.file_grid, 1, wx.EXPAND | wx.ALL, self.spx_calc(10))

        self.sizer_main.Add(self.status_bar, 0, wx.EXPAND)
        if not self.is_embedded:
            self.panel.SetSizer(self.sizer_main)
        # 设置拖放目标
        self.input_search_path01.SetDropTarget(tfo_FileDropToPathInput(self.input_search_path01, self))
        self.input_source_path03.SetDropTarget(tfo_FileDropToPathInput(self.input_source_path03, self))
        self.input_dest_path03.SetDropTarget(tfo_FileDropToPathInput(self.input_dest_path03, self))
        self.input_source_path04.SetDropTarget(tfo_FileDropToPathInput(self.input_source_path04, self))
        self.input_dest_path04.SetDropTarget(tfo_FileDropToPathInput(self.input_dest_path04, self))
        self.input_zip_target05.SetDropTarget(tfo_FileDropToPathInput(self.input_zip_target05, self))
        self.input_unzip_target06.SetDropTarget(tfo_FileDropToPathInput(self.input_unzip_target06, self))
        # 嵌入式模式不需要显示frame
        if self.is_embedded:
            self.panel.Layout()
        # 创建操作级撤销/重做菜单栏（嵌入式模式由主框架通过get_menu_bar()使用，
        # 独立窗口模式由show_interface()设置到frame上）
        self._create_tool_menu_bar()

    """获取父窗口（用于对话框）"""
    def get_parent_window(self):
        if self.is_embedded:
            return self.panel.GetTopLevelParent()
        return self.frame

    """布局更新"""
    def layout_frame(self):
        if self.is_embedded:
            self.panel.Layout()
            self.panel.GetTopLevelParent().Layout()
        elif self.frame:
            self.frame.Layout()

    """通用帮助对话框，显示可选择的文本内容，支持Ctrl+C复制选中的文本"""
    def show_help_dialog(self, text_help_title, text_help_content):
        parent_window = self.get_parent_window()
        dlg = wx.Dialog(parent_window, title=text_help_title, size=(self.spx_calc(660), self.spx_calc(480)), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        # 创建面板
        panel = wx.Panel(dlg)
        sizer = wx.BoxSizer(wx.VERTICAL)
        # 创建标题和图标
        title_sizer = wx.BoxSizer(wx.HORIZONTAL)
        icon = wx.StaticBitmap(panel, bitmap=wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, wx.ART_OTHER, (32, 32)))
        title = wx.StaticText(panel, label=text_help_title)
        font = title.GetFont()
        font.SetPointSize(int(font.GetPointSize() + 1))
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(font)
        title_sizer.Add(icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(10))
        title_sizer.Add(title, 0, wx.ALIGN_CENTER_VERTICAL)
        # 创建ScrolledText控件（带滚动条的多行文本框）
        text_ctrl = wx.TextCtrl(
            panel,
            value=text_help_content,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.HSCROLL | wx.VSCROLL
        )
        # 设置字体为等宽字体，便于阅读代码/格式文本
        font = wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        text_ctrl.SetFont(font)
        # 设置背景色和前景色
        text_ctrl.SetBackgroundColour(wx.Colour(248, 248, 248))
        text_ctrl.SetForegroundColour(wx.Colour(0, 0, 0))
        # 设置文本框大小
        text_ctrl.SetMinSize((self.spx_calc(630), self.spx_calc(320)))
        # 创建提示文本
        self.hint_text = wx.StaticText(panel, label=translate("hint_text_selection"))
        self.hint_text.SetForegroundColour(wx.Colour(100, 100, 100))
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        close_button = wx.Button(panel, wx.ID_CLOSE, translate("close"))
        close_button.SetFocus()  # 设置焦点到关闭按钮，便于按Enter关闭
        # 绑定按钮事件
        def on_close(event):
            """关闭对话框"""
            dlg.EndModal(wx.ID_CLOSE)
        close_button.Bind(wx.EVT_BUTTON, on_close)
        # 添加按钮到按钮sizer
        button_sizer.AddStretchSpacer()
        button_sizer.Add(close_button, 0, wx.ALL, self.spx_calc(5))
        # 布局
        sizer.Add(title_sizer, 0, wx.ALL | wx.EXPAND, self.spx_calc(10))
        sizer.Add(text_ctrl, 1, wx.ALL | wx.EXPAND, self.spx_calc(10))
        sizer.Add(self.hint_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, self.spx_calc(10))
        sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, self.spx_calc(10))
        panel.SetSizer(sizer)
        # 绑定文本框的复制事件
        def on_copy_text(event):
            """处理复制事件，在对话框内显示已复制的文本"""
            # 获取选中的文本
            selected_text = text_ctrl.GetStringSelection()
            if selected_text:
                # 在对话框内的提示位置显示已复制的文本（限制显示长度，避免过长）
                display_text = selected_text.strip()
                if len(display_text) > 50:
                    display_text = display_text[:47] + "..."
                # 在对话框内部的提示文本位置显示复制反馈
                self.hint_text.SetLabel(translate("hint_text_copied", text=display_text))
                self.hint_text.SetForegroundColour(wx.Colour(0, 128, 0))  # 绿色表示成功
                self.hint_text.Refresh()
            # 让事件继续传播，执行默认的复制操作
            event.Skip()
        # 绑定文本框的复制事件
        text_ctrl.Bind(wx.EVT_TEXT_COPY, on_copy_text)
        # 显示对话框
        dlg.ShowModal()
        dlg.Destroy()

    """匹配名编辑按钮点击事件"""
    def on_match_edit(self, event):
        # 第一步：收集匹配名列表（改进版，换行符分割，保持顺序不变，不去掉内部空格）
        match_str = self.input_match_text01.GetValue()
        all_match_list = match_str.split("/") if match_str.strip() else []
        seen = set()
        self.unique_ordered_match_list = []
        for match_name in all_match_list:
            if match_name not in seen:
                seen.add(match_name)
                self.unique_ordered_match_list.append(match_name)
        # 设置初始文本：保持按'/'分割出来的元素的顺序不变
        if len(self.unique_ordered_match_list) == 0:
            initial_text = ""
        elif len(self.unique_ordered_match_list) == 1:
            initial_text = self.unique_ordered_match_list[0]
        else:
            initial_text = "\n".join(self.unique_ordered_match_list) + "\n\n"
        """弹出匹配名输入对话框"""
        dlg = wx.Dialog(self.get_parent_window(), title=translate("dialog_title_match_edit"), size=(self.spx_calc(500), self.spx_calc(400)))
        # 创建面板和布局
        panel = wx.Panel(dlg)
        sizer = wx.BoxSizer(wx.VERTICAL)
        # 创建标题和图标
        title_sizer = wx.BoxSizer(wx.HORIZONTAL)
        icon = wx.StaticBitmap(panel, bitmap=wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, wx.ART_OTHER, (32, 32)))
        title = wx.StaticText(panel, label=translate("dialog_title_match_edit"))
        font = title.GetFont()
        font.SetPointSize(int(font.GetPointSize() + 1))
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(font)
        title_sizer.Add(icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(10))
        title_sizer.Add(title, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(title_sizer, 0, wx.ALL, self.spx_calc(10))
        # 创建标签 - 初始显示统计信息
        non_duplicate_count = len(self.unique_ordered_match_list)
        duplicate_count = len(all_match_list) - non_duplicate_count
        label_text02 = wx.StaticText(panel, label=translate("dialog_text_match_edit", non_duplicate=non_duplicate_count, duplicate=duplicate_count))
        sizer.Add(label_text02, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, self.spx_calc(10))
        # 创建多行文本输入框
        text_match_input = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.HSCROLL | wx.VSCROLL)
        text_match_input.SetMinSize((self.spx_calc(460), self.spx_calc(250)))
        text_match_input.SetValue(initial_text)
        sizer.Add(text_match_input, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, self.spx_calc(10))
        # 创建按钮
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, translate("dialog_btn_cancel"))
        btn_ok = wx.Button(panel, wx.ID_OK, translate("dialog_btn_ok"))
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_cancel, 0, wx.ALL, self.spx_calc(5))
        btn_sizer.Add(btn_ok, 0, wx.ALL, self.spx_calc(5))
        btn_sizer.AddStretchSpacer()
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.BOTTOM, self.spx_calc(10))
        panel.SetSizer(sizer)
        # 设置对话框属性
        dlg.SetEscapeId(wx.ID_CANCEL)  # 按Esc取消
        """实时更新标签中的非重复和重复匹配名数量"""
        def update_label():
            current_text = text_match_input.GetValue()
            lines = current_text.splitlines()
            # 统计非重复行（忽略空行和纯空格行）
            seen_lines = set()
            non_duplicate = 0
            for line in lines:
                stripped_line = line.strip()
                if stripped_line and stripped_line not in seen_lines:
                    seen_lines.add(stripped_line)
                    non_duplicate += 1
            # 计算重复行数
            total_lines = len([line for line in lines if line.strip()])
            duplicate = total_lines - non_duplicate
            # 更新标签文本
            label_text02.SetLabel(translate("dialog_text_match_edit_updated", non_duplicate=non_duplicate, duplicate=duplicate))
            dlg.Layout()  # 重新布局以适应新标签大小
        # 在对话框显示前设置光标位置
        def set_cursor_position():
            if len(self.unique_ordered_match_list) == 1:
                # 只有一个元素：光标定位到最末尾
                text_match_input.SetFocus()
                text_match_input.SetInsertionPointEnd()
            elif len(self.unique_ordered_match_list) > 1:
                # 多个元素：光标定位到最后一个空行
                text_match_input.SetFocus()
                text_match_input.SetInsertionPointEnd()
        # 绑定文本变化事件
        text_match_input.Bind(wx.EVT_TEXT, lambda e: update_label())
        # 使用CallAfter确保在UI更新后设置光标位置
        wx.CallLater(100, set_cursor_position)
        # 显示对话框并获取结果
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            # 获取输入的文本
            text_match = text_match_input.GetValue()
            # 处理文本：按行分割，保留顺序并去重
            lines = text_match.splitlines()
            # 保持顺序的去重：保留第一次出现的项，丢弃后面出现的重复项
            seen = set()
            non_empty_unique_lines = []
            for line in lines:
                stripped_line = line.strip()
                if stripped_line and stripped_line not in seen:
                    seen.add(stripped_line)
                    non_empty_unique_lines.append(line)  # 保留原始格式（不去掉内部空格）
            # 更新输入框（用'/'连接）
            self.input_match_text01.SetValue("/".join(non_empty_unique_lines))
        # 关闭窗口，并触发事件
        dlg.Destroy()
        if event: event.Skip()

    """命名方式下拉框变化事件"""
    def on_combo_naming_method02_changed(self, event):
        self._update_naming_param_visibility()

    """合并命名方式的子模式单选变化事件"""
    def on_naming_submode_changed(self, event):
        self._update_naming_param_visibility()

    def _update_naming_param_visibility(self):
        """根据当前命名方式及其子模式单选，显示/隐藏对应参数控件"""
        method_key = self.naming_method_mapping.get(self.combo_naming_method02.GetSelection(), "original_name")
        # 先全部隐藏
        for _w in (self.label_naming_position02, self.input_naming_position02,
                   self.label_length02, self.input_length02,
                   self.label_naming_oldtext02, self.input_naming_oldtext,
                   self.label_text02, self.input_naming_text02, self.help_rename02,
                   self.label_number_position02, self.check_number_pos_start02,
                   self.label_number_scope02, self.radio_number_scope_none02,
                   self.radio_number_scope_dir02, self.radio_number_scope_match02,
                   self.radio_replace_mode_text02, self.radio_replace_mode_position02,
                   self.radio_affix_mode_suffix02, self.radio_affix_mode_prefix02,
                   self.radio_case_mode_upper02, self.radio_case_mode_lower02,
                   self.radio_case_mode_camel02, self.radio_case_mode_capitalize02,
                   self.radio_mp3_artist_first02, self.radio_mp3_title_first02,
                   self.radio_mp3_title_only02):
            _w.Hide()
        # 默认标签文本
        self.label_naming_oldtext02.SetLabel(translate("label_old_text"))
        self.label_text02.SetLabel(translate("label_text"))

        if method_key == "replace":
            # 按文本（默认）/ 按位置
            self.radio_replace_mode_text02.Show()
            self.radio_replace_mode_position02.Show()
            if self.radio_replace_mode_position02.GetValue():
                self.label_naming_position02.Show()
                self.input_naming_position02.Show()
                self.label_length02.Show()
                self.input_length02.Show()
                self.label_text02.SetLabel(translate("label_text"))
            else:
                self.label_naming_oldtext02.Show()
                self.input_naming_oldtext.Show()
                self.label_text02.SetLabel(translate("label_new_text"))
            self.label_text02.Show()
            self.input_naming_text02.Show()
        elif method_key == "insert_by_position":
            self.label_naming_position02.Show()
            self.input_naming_position02.Show()
            self.label_text02.Show()
            self.input_naming_text02.Show()
            self.label_text02.SetLabel(translate("label_text"))
        elif method_key == "delete_by_position":
            self.label_naming_position02.Show()
            self.input_naming_position02.Show()
            self.label_length02.Show()
            self.input_length02.Show()
        elif method_key == "add_affix":
            # 后缀（默认）/ 前缀
            self.radio_affix_mode_suffix02.Show()
            self.radio_affix_mode_prefix02.Show()
            self.label_text02.Show()
            self.input_naming_text02.Show()
            if self.radio_affix_mode_prefix02.GetValue():
                self.label_text02.SetLabel(translate("label_prefix"))
            else:
                self.label_text02.SetLabel(translate("label_suffix"))
        elif method_key == "change_case":
            self.radio_case_mode_upper02.Show()
            self.radio_case_mode_lower02.Show()
            self.radio_case_mode_camel02.Show()
            self.radio_case_mode_capitalize02.Show()
        elif method_key == "regex_replace":
            self.label_naming_oldtext02.Show()
            self.input_naming_oldtext.Show()
            self.label_naming_oldtext02.SetLabel(translate("label_regex_pattern"))
            self.label_text02.Show()
            self.input_naming_text02.Show()
            self.label_text02.SetLabel(translate("label_regex_replacement"))
        elif method_key == "add_number":
            self.label_number_position02.Show()
            self.check_number_pos_start02.Show()
            self.label_number_scope02.Show()
            self.radio_number_scope_none02.Show()
            self.radio_number_scope_dir02.Show()
            self.radio_number_scope_match02.Show()
        elif method_key == "convert_by_placeholder":
            self.label_text02.Show()
            self.input_naming_text02.Show()
            self.help_rename02.Show()
            self.label_text02.SetLabel(translate("label_format"))
        elif method_key == "rename_mp3":
            # MP3 命名格式：歌手-歌名（默认）/ 歌名-歌手 / 仅歌名
            self.radio_mp3_artist_first02.Show()
            self.radio_mp3_title_first02.Show()
            self.radio_mp3_title_only02.Show()
        # original_name：无需参数
        self.tab02.Layout()
    
    """匹配名输入框文本变化事件"""
    def on_match_text_inputted(self, event):
        match_text = self.input_match_text01.GetValue().strip()
        if not match_text:
            new_label = translate("label_match_text_count", count=0)
        else:
            match_count = len(match_text.split('/'))
            new_label = translate("label_match_text_count", count=match_count)
        # 更新标签文本
        self.label_match_text01.SetLabel(new_label)
        self.tab01.Layout()

    """搜索目录输入框文本变化事件"""
    def on_search_path_changed(self, event):
        # 检查路径是否有效：路径存在就恢复默认颜色，不存在或为空则设置为红色
        search_path_val = self.input_search_path01.GetValue().strip()
        search_path_exist = bool(search_path_val and os.path.exists(search_path_val))
        if search_path_exist:
            self.input_search_path01.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
        else:
            self.input_search_path01.SetForegroundColour(wx.RED)
        # 若旧路径为空，则设置为它的默认值
        source_path03_val = self.input_source_path03.GetValue().strip()
        if search_path_exist and not source_path03_val:
            self.input_source_path03.SetValue(self.input_search_path01.GetValue())
            self.input_dest_path03.SetFocus()
        source_path04_val = self.input_source_path04.GetValue().strip()
        if search_path_exist and not source_path04_val:
            self.input_source_path04.SetValue(self.input_search_path01.GetValue())
            self.input_dest_path04.SetFocus()
        # 刷新文本框显示，并更新按钮状态
        self.search_folder = search_path_val
        self.btn_apply_search01.Enable(search_path_exist)
        self.input_search_path01.Refresh()

    """原来位置输入框文本变化事件"""
    def on_source_path_changed(self, event):
        # 获取触发事件的控件
        sender = event.GetEventObject()
        # 检查路径是否有效：路径存在就恢复默认颜色
        source_path03_val = self.input_source_path03.GetValue().strip()
        source_path03_exist = bool(source_path03_val and os.path.exists(source_path03_val))
        if source_path03_exist:
            self.input_source_path03.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
            self.input_source_path04.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
        else:
            self.input_source_path03.SetForegroundColour(wx.RED)
            self.input_source_path04.SetForegroundColour(wx.RED)
        # 若搜索目录为空，则设置为它的默认值
        search_path_val = self.input_search_path01.GetValue().strip()
        if source_path03_exist and not search_path_val:
            self.input_search_path01.SetValue(self.input_source_path03.GetValue())
        # 设置搜索按钮是否可用，以及若旧路径为空则设置搜索目录为它的默认值
        dest_path03_str = self.input_dest_path03.GetValue().strip()
        dest_path03_valid = bool(dest_path03_str and self.is_valid_path(dest_path03_str))
        # 刷新文本框显示，并更新按钮状态
        self.btn_apply_path03.Enable(source_path03_exist and dest_path03_valid)
        self.btn_apply_path04.Enable(source_path03_exist and dest_path03_valid)
        self.input_source_path03.Refresh()
        self.input_source_path04.Refresh()
        # 联动input_source_path04
        # 注意：必须用 ChangeValue 而非 SetValue —— wxGTK3 下 SetValue 总是触发
        # EVT_TEXT（即使值未变化），若用它做兄弟联动，03↔04 会互相触发导致
        # 无限递归（RecursionError）并冻结主线程；ChangeValue 不触发事件。
        if sender == self.input_source_path03:
            self.input_source_path04.ChangeValue(self.input_source_path03.GetValue())
        elif sender == self.input_source_path04:
            self.input_source_path03.ChangeValue(self.input_source_path04.GetValue())

    """变更为位置输入框文本变化事件"""
    def on_dest_path_changed(self, event):
        # 获取触发事件的控件
        sender = event.GetEventObject()
        # 联动input_dest_path03/04、压缩Tab目标路径、解压Tab目标路径（四方联动）
        # 与 on_source_path_changed 同理：用 ChangeValue 避免 03↔04↔05↔06 互相触发
        # EVT_TEXT 造成无限递归（RecursionError）并冻结主线程。
        if sender == self.input_dest_path03:
            self.input_dest_path04.ChangeValue(self.input_dest_path03.GetValue())
            self.input_zip_target05.ChangeValue(self.input_dest_path03.GetValue())
            self.input_unzip_target06.ChangeValue(self.input_dest_path03.GetValue())
        elif sender == self.input_dest_path04:
            self.input_dest_path03.ChangeValue(self.input_dest_path04.GetValue())
            self.input_zip_target05.ChangeValue(self.input_dest_path04.GetValue())
            self.input_unzip_target06.ChangeValue(self.input_dest_path04.GetValue())
        elif sender == self.input_zip_target05:
            self.input_dest_path03.ChangeValue(self.input_zip_target05.GetValue())
            self.input_dest_path04.ChangeValue(self.input_zip_target05.GetValue())
            self.input_unzip_target06.ChangeValue(self.input_zip_target05.GetValue())
        elif sender == self.input_unzip_target06:
            self.input_dest_path03.ChangeValue(self.input_unzip_target06.GetValue())
            self.input_dest_path04.ChangeValue(self.input_unzip_target06.GetValue())
            self.input_zip_target05.ChangeValue(self.input_unzip_target06.GetValue())
        # 注意：必须先完成四个输入框的联动同步，再根据同步后的最终值校验颜色。
        # 若先校验后同步，当在压缩Tab输入时，Move/Copy输入框仍持有旧值（空），
        # 会被误判为非法而标红——即使填写/选择的是存在且合法的路径。
        source_path03_val = self.input_source_path03.GetValue().strip()
        source_path03_exist = bool(source_path03_val and os.path.exists(source_path03_val))
        # 检查路径是否有效：路径合法就恢复默认颜色
        dest_path03_str = self.input_dest_path03.GetValue().strip()
        dest_path03_valid = bool(dest_path03_str and self.is_valid_path(dest_path03_str))
        if dest_path03_valid:
            self.input_dest_path03.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
            self.input_dest_path04.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
            self.input_zip_target05.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
            self.input_unzip_target06.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
        else:
            self.input_dest_path03.SetForegroundColour(wx.RED)
            self.input_dest_path04.SetForegroundColour(wx.RED)
            self.input_zip_target05.SetForegroundColour(wx.RED)
            self.input_unzip_target06.SetForegroundColour(wx.RED)
        # 刷新文本框显示，并更新按钮状态
        self.btn_apply_path03.Enable(source_path03_exist and dest_path03_valid)
        self.btn_apply_path04.Enable(source_path03_exist and dest_path03_valid)
        self.input_dest_path03.Refresh()
        self.input_dest_path04.Refresh()
        self.input_zip_target05.Refresh()
        self.input_unzip_target06.Refresh()

    """浏览原来位置"""
    def on_browse_source(self, event):
        sender = event.GetEventObject()
        dialog = wx.DirDialog(self.get_parent_window(), translate("dialog_select_source_folder"), style=wx.DD_DEFAULT_STYLE)
        if dialog.ShowModal() == wx.ID_OK:
            selected_path = dialog.GetPath()
            if sender == self.btn_search_browse01:
                self.input_search_path01.SetValue(selected_path)
            else:
                self.input_source_path03.SetValue(selected_path)
                self.input_source_path04.SetValue(selected_path)
        dialog.Destroy()

    """浏览变更为位置"""
    def on_browse_dest(self, event):
        dialog = wx.DirDialog(self.get_parent_window(), translate("dialog_select_dest_folder"), style=wx.DD_DEFAULT_STYLE)
        if dialog.ShowModal() == wx.ID_OK:
            selected_path = dialog.GetPath()
            self.input_dest_path03.SetValue(selected_path)
            self.input_dest_path04.SetValue(selected_path)
        dialog.Destroy()

    """浏览压缩目标路径"""
    def on_browse_zip_target(self, event):
        dialog = wx.DirDialog(self.get_parent_window(), translate("dialog_select_zip_target"), style=wx.DD_DEFAULT_STYLE)
        if dialog.ShowModal() == wx.ID_OK:
            self.input_zip_target05.SetValue(dialog.GetPath())
        dialog.Destroy()

    """浏览解压目标路径"""
    def on_browse_unzip_target(self, event):
        dialog = wx.DirDialog(self.get_parent_window(), translate("dialog_select_unzip_target"), style=wx.DD_DEFAULT_STYLE)
        if dialog.ShowModal() == wx.ID_OK:
            self.input_unzip_target06.SetValue(dialog.GetPath())
        dialog.Destroy()

    """检查路径是否是一个有效的路径格式"""
    def is_valid_path(self, path):
        # 根据操作系统定义非法字符集合
        if os.name == 'nt':  # Windows 系统
            invalid_chars = set(r'<>:"|?*')  # 反斜杠 '\' 是合法的路径分隔符
        else:  # 非 Windows 系统（如 Linux, macOS）
            invalid_chars = set(r'<>:"\|?*')  # 正斜杠 '/' 是合法的路径分隔符
        # 尝试规范化路径，如果失败则路径不合法
        try:
            normalized_path = os.path.normpath(path)
        except Exception as e:
            log_error(f"规范化路径失败: {e}")
            return False
        # 检查路径是否以盘符开头（仅适用于 Windows）
        if os.name == 'nt':
            # Windows 路径应以有效的驱动器号开头，例如 C:\
            if len(normalized_path) > 2 and normalized_path[1] == ':' and normalized_path[2] == os.sep:
                # 检查盘符是否为字母
                drive_letter = normalized_path[0]
                if not drive_letter.isalpha(): return False
                # 去掉盘符部分，检查剩余路径中的非法字符
                path_to_check = normalized_path[3:]
            else:
                # 如果路径不以有效的驱动器号开头，则路径不合法
                return False
        else:
            # 对于非 Windows 系统，直接检查路径中的非法字符
            path_to_check = normalized_path
        # 检查路径中是否包含非法字符
        if any((char in invalid_chars) for char in path_to_check): return False
        # 对于其他操作系统，只需确保路径格式正确
        return True

    """将文件搜索通配符转换成正则表达式"""
    def wildcard_to_regex(self, wildcard:str):
        return _wildcard_to_regex(wildcard)

    def check_name_match(self, name, match_name, match_method):
        current_method = self.get_match_method_from_text(match_method)
        result = check_name_match_part(name, match_name, current_method)
        return result is not None
    
    def get_match_method_from_text(self, method_text):
        """根据方法文本获取对应的标识符"""
        valid_keys = set(self.match_method_mapping.values())
        if method_text in valid_keys:
            return method_text
        if hasattr(self, 'combo_match_method01'):
            for idx in range(self.combo_match_method01.GetCount()):
                if self.combo_match_method01.GetString(idx) == method_text:
                    return self.match_method_mapping.get(idx, method_text)
        return method_text

    """获取分区名称的方法"""
    def get_partition_name(self, input_folder_path):
        if not input_folder_path: return "root"
        # 规范化路径
        normalized_path = os.path.normpath(input_folder_path)
        # Windows系统处理
        if os.name == 'nt':
            # 检查是否是根目录（如C:\）
            if len(normalized_path) == 3 and normalized_path[1:3] == ":\\":
                return normalized_path[0]  # 返回盘符，如"C"
            # 检查是否是根目录的其他形式（如C:）
            elif len(normalized_path) == 2 and normalized_path[1] == ":":
                return normalized_path[0]  # 返回盘符，如"C"
        # Unix/Linux/MacOS系统处理
        else:
            # 检查是否是根目录
            if normalized_path == "/":
                return "root"
        # 如果不是根目录，返回原文件夹名称
        return os.path.basename(normalized_path)

    """格式化文件时间"""
    def format_file_time(self, timestamp):
        try:
            dt = datetime.datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, AttributeError):
            return translate("unknown_time")

    """搜索原来位置并填充表格 - 使用工作线程"""
    def on_apply_search(self, event):
        search_path_val = self.input_search_path01.GetValue().strip()
        if not search_path_val or not os.path.exists(search_path_val):
            log_warning("无效的搜索路径")
            wx.MessageBox(translate("message_invalid_source_path"), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
            return
        # 自动将搜索路径填入空白的Move来源路径：
        # 仅需填写Move（input_source_path03），其绑定的 on_source_path_changed
        # 联动事件会把该值同步到Copy（input_source_path04），无需单独填写。
        if not self.input_source_path03.GetValue().strip():
            self.input_source_path03.SetValue(search_path_val)
        log_info(f"开始搜索: path={search_path_val}")
        match_method = self.get_combo_box_method(self.combo_match_method01, self.match_method_mapping)
        recursive = self.check_search_recursive01.GetValue()
        search_filename = self.check_output_filename01.GetValue()
        search_dirname = self.check_output_dirname01.GetValue()
        search_hidden = self.check_search_hidden01.GetValue()
        match_str = self.input_match_text01.GetValue()
        all_match_list = match_str.split("/") if match_str.strip() else []
        seen = set()
        self.unique_ordered_match_list = []
        for match_name in all_match_list:
            cleaned_name = match_name.strip()
            if cleaned_name and cleaned_name not in seen:
                seen.add(cleaned_name)
                self.unique_ordered_match_list.append(cleaned_name)
        is_match_all = False
        if not self.unique_ordered_match_list: 
            is_match_all = True
            self.unique_ordered_match_list = [""]
        # 操作级历史记录：捕获 before_grid 快照
        self._begin_op_history(OP_TYPE_SEARCH, 0)
        self.disable_controls_during_operation()
        self.search_worker = tfo_SearchWorker(
            self, search_path_val, self.unique_ordered_match_list, match_method,
            recursive, search_filename, search_dirname,
            search_hidden, is_match_all
        )
        self.search_worker.start()
        self.search_progress_timer = wx.Timer(self.get_parent_window())
        self.get_parent_window().Bind(wx.EVT_TIMER, self.check_search_progress, self.search_progress_timer)
        self.search_progress_timer.Start(100)  # 每100毫秒检查一次

    """检查搜索进度"""
    def check_search_progress(self, event):
        if hasattr(self, 'search_worker') and self.search_worker.is_alive():
            # 获取进度信息
            progress_info = self.search_worker.get_progress_info()
            if progress_info:
                finished, total, matched_count, current_path, results, unmatched_match_names = progress_info
                # 更新状态栏
                if current_path:
                    self.status_bar.SetStatusText(translate("status_searching_with_path", count=matched_count, path=current_path), 0)
                else:
                    self.status_bar.SetStatusText(translate("status_searching_generic", count=matched_count), 0)
        else:
            # 线程已完成，停止定时器
            if hasattr(self, 'search_progress_timer'):
                self.search_progress_timer.Stop()
                del self.search_progress_timer
            # 获取搜索结果
            if hasattr(self, 'search_worker'):
                progress_info = self.search_worker.get_progress_info()
                if progress_info:
                    finished, total, matched_count, current_path, results, unmatched_match_names = progress_info
                    log_info(f"搜索完成: 找到 {len(results)} 个结果")
                    self._process_search_results(results, unmatched_match_names, is_match_all=self.search_worker.is_match_all)
            self.restore_controls_after_operation()

    """处理搜索结果并更新表格"""
    def _process_search_results(self, results, unmatched_match_names, is_match_all=False, write_unmatched_names=False):
        existing_paths = set()
        for row in range(self.file_grid.GetNumberRows()):
            old_path = self.file_grid.GetCellValue(row, self.file_grid.COL_OLD_PATH)
            if old_path and old_path.strip():
                existing_paths.add(old_path.strip())
        last_notblank_row = -1
        for row_loop in range(self.file_grid.GetNumberRows()):
            old_path = self.file_grid.GetCellValue(row_loop, self.file_grid.COL_OLD_PATH)
            new_path = self.file_grid.GetCellValue(row_loop, self.file_grid.COL_NEW_PATH)
            if old_path or new_path:
                last_notblank_row = row_loop
        loop_row_index = 0
        if last_notblank_row >= 0:
            loop_row_index = last_notblank_row + 1
        loop_match_names = [''] if is_match_all else list(results.keys())
        new_paths_count = 0
        for match_name in loop_match_names:
            if match_name in results and results[match_name]:
                for full_path, result_match_name, is_dir, depth in results[match_name]:
                    if full_path not in existing_paths:
                        new_paths_count += 1
        rows_needed = loop_row_index + new_paths_count
        rows_current = self.file_grid.GetNumberRows()
        if rows_needed > rows_current:
            self.file_grid.AppendRows(rows_needed - rows_current + 10)
        self.file_grid.Freeze()
        for match_name in loop_match_names:
            if match_name in results and results[match_name]:
                for full_path, result_match_name, is_dir, depth in results[match_name]:
                    if full_path not in existing_paths:
                        self.file_grid.write_row_by_old_path(loop_row_index, full_path, "", result_match_name, "", depth)
                        loop_row_index += 1
        self.file_grid.Thaw()
        self.file_grid.ForceRefresh()
        self.file_grid.Update()
        # 并把所有旧路径列空白的行里的匹配名清空
        for row in range(self.file_grid.GetNumberRows()):
            match_name = self.file_grid.GetCellValue(row, self.file_grid.COL_MATCH_NAME)
            old_path = self.file_grid.GetCellValue(row, self.file_grid.COL_OLD_PATH)
            new_path = self.file_grid.GetCellValue(row, self.file_grid.COL_NEW_PATH)
            if not old_path and not new_path:
                for col in range(self.file_grid.GetNumberCols()):
                    self.file_grid.SetCellValue(row, col, "")
        existing_match_names = set()
        for row in range(self.file_grid.GetNumberRows()):
            match_name = self.file_grid.GetCellValue(row, self.file_grid.COL_MATCH_NAME).strip()
            if match_name:
                existing_match_names.add(match_name)
        first_empty_row = -1
        for row in range(self.file_grid.GetNumberRows()):
            old_path = self.file_grid.GetCellValue(row, self.file_grid.COL_OLD_PATH).strip()
            new_path = self.file_grid.GetCellValue(row, self.file_grid.COL_NEW_PATH).strip()
            match_name = self.file_grid.GetCellValue(row, self.file_grid.COL_MATCH_NAME).strip()
            result_val = self.file_grid.GetCellValue(row, self.file_grid.COL_RESULT).strip()
            if not old_path and not new_path and not match_name and not result_val:
                first_empty_row = row
                break
        if first_empty_row == -1:
            self.file_grid.AppendRows(10)
            first_empty_row = self.file_grid.GetNumberRows() - 10
        if write_unmatched_names:
            current_row = first_empty_row
            for match_name in unmatched_match_names:
                if current_row >= self.file_grid.GetNumberRows():
                    self.file_grid.AppendRows(10)
                self.file_grid.SetCellValue(current_row, self.file_grid.COL_MATCH_NAME, match_name)
                current_row += 1
        if last_notblank_row >= 0:
            for row_loop in range(last_notblank_row):
                old_path = self.file_grid.GetCellValue(row_loop, self.file_grid.COL_OLD_PATH)
                new_path = self.file_grid.GetCellValue(row_loop, self.file_grid.COL_NEW_PATH)
                if not old_path and not new_path:
                    self.file_grid.DeleteRows(row_loop, 1)
        # 确保最后一个非空行后面有5个空行，且只有5个空行
        self.adjust_table_rows()
        # 更新状态栏
        all_found_path = []
        for sublist in results.values():
            for subtuple in sublist:
                all_found_path.append(subtuple[0])
        counter_found_path = collections.Counter(all_found_path)
        count_total_repeated = sum(count for count in counter_found_path.values() if count > 1)
        count_unique_repeated = sum(1 for count in counter_found_path.values() if count > 1)
        count_extra_repeated = count_total_repeated - count_unique_repeated
        # 统计新增的文件和目录数量
        new_files_count = 0
        new_dirs_count = 0
        # 检查新增的项目（不在existing_paths中的）
        for match_name in loop_match_names:
            if match_name in results and results[match_name]:
                for full_path, result_match_name, is_dir, depth in results[match_name]:
                    if full_path not in existing_paths:
                        if is_dir:
                            new_dirs_count += 1
                        else:
                            new_files_count += 1
        total_new = new_files_count + new_dirs_count
        if not all_found_path:
            status_result_str = translate("message_no_search_results")
        else:
            status_result_str = translate("message_search_completed", count=len(all_found_path), repeated=count_extra_repeated, new=total_new, files=new_files_count, dirs=new_dirs_count)
            if unmatched_match_names:
                status_result_str += translate("message_no_match_results", unmatched=len(unmatched_match_names), total=len(self.unique_ordered_match_list))
        self.status_bar.SetStatusText(status_result_str, 0)
        if all_found_path:
            self.status_bar.SetStatusText(translate("status_search_total", total=len(all_found_path)), 1)
        
        # 清除排序箭头，恢复初始状态
        self.file_grid.set_col_sort_indicator()

    """从表格设置搜索文件夹"""
    def set_search_folder(self, folder_path, need_raise_event=False):
        if folder_path and os.path.exists(folder_path):
            self.search_folder = folder_path
            self.input_search_path01.SetValue(folder_path)
            if need_raise_event: self.on_search_path_changed(None)

    """调整表格行数，确保最后一个非空行后面有5个空行，且只有5个空行"""
    def adjust_table_rows(self):
        # 如果没有行，添加20行
        total_rows = self.file_grid.GetNumberRows()
        if total_rows == 0:
            self.file_grid.AppendRows(20)
            return

        # 找到最后一个非空行（"旧路径"不为空）
        last_nonempty_row = -1
        for row in range(total_rows-1, -1, -1):
            old_path = self.file_grid.GetCellValue(row, self.file_grid.COL_OLD_PATH)
            new_path = self.file_grid.GetCellValue(row, self.file_grid.COL_NEW_PATH)
            match_name = self.file_grid.GetCellValue(row, self.file_grid.COL_MATCH_NAME)
            if (old_path and old_path.strip()) or (new_path and new_path.strip()) or (match_name and match_name.strip()):
                last_nonempty_row = row
                break
        if last_nonempty_row == -1:
            if total_rows > 20:
                self.file_grid.DeleteRows(20, total_rows-2)
            elif total_rows < 20:
                self.file_grid.AppendRows(20-total_rows)
            return
        empty_rows_after = 0
        for row in range(last_nonempty_row+1, total_rows):
            old_path = self.file_grid.GetCellValue(row, self.file_grid.COL_OLD_PATH)
            if not old_path or not old_path.strip():
                empty_rows_after += 1
            else:
                empty_rows_after = 0
                last_nonempty_row = row

        # 需要5个空行：缺少则添加缺少的空行，多余则删除多余的空行
        if empty_rows_after < 5:
            self.file_grid.AppendRows(5 - empty_rows_after)
        elif empty_rows_after > 5:
            extra_rows_count = empty_rows_after - 5
            delete_start = total_rows - extra_rows_count
            if delete_start < last_nonempty_row + 1:
                delete_start = last_nonempty_row + 1
            self.file_grid.DeleteRows(delete_start, extra_rows_count)
        # 如果调整后总行数小于20，则增加到20行
        total_rows = self.file_grid.GetNumberRows()
        if total_rows < 20: self.file_grid.AppendRows(20 - total_rows)

    """应用路径变更按钮事件 - 按照新要求修改"""
    def on_combo_match_method01_change(self, event):
        current_method = self.get_combo_box_method(self.combo_match_method01, self.match_method_mapping)
        preset_methods = {"images_preset", "documents_preset", "compressed_preset", "text_preset"}
        was_preset = self.prev_match_method_key in preset_methods
        is_preset = current_method in preset_methods
        if current_method == "images_preset":
            self.input_match_text01.SetValue(".jpg/.jpeg/.png/.gif/.bmp/.tiff/.webp/.svg/.ico")
        elif current_method == "documents_preset":
            self.input_match_text01.SetValue(".xls/.xlsx/.doc/.docx/.ppt/.pptx/.pdf/.csv/.rtf/.odt/.ods/.odp")
        elif current_method == "compressed_preset":
            self.input_match_text01.SetValue(".zip/.rar/.7z/.tar/.gz/.bz2/.xz/.iso")
        elif current_method == "text_preset":
            self.input_match_text01.SetValue(".txt")
        elif was_preset and not is_preset:
            self.input_match_text01.SetValue("")
        self.prev_match_method_key = current_method

    """导入表格按钮点击事件"""
    def on_import_grid01(self, event):
        self.file_grid.on_import_grid(event)

    """导出表格按钮点击事件"""
    def on_export_grid01(self, event):
        self.file_grid.on_export_grid(event)

    """创建文件冲突处理下拉框变化事件，实现联动"""
    def on_combo_file_conflict_change(self, event):
        # 获取触发事件的控件
        sender = event.GetEventObject()
        # 获取当前选择的索引
        selection = sender.GetSelection()
        # 更新其他创建目录下拉框的选择
        if sender != self.combo_file_conflict0202:
            self.combo_file_conflict0202.SetSelection(selection)
        if sender != self.combo_file_conflict0302:
            self.combo_file_conflict0302.SetSelection(selection)
        if sender != self.combo_file_conflict0402:
            self.combo_file_conflict0402.SetSelection(selection)
        if sender != self.combo_file_conflict0502:
            self.combo_file_conflict0502.SetSelection(selection)
        if sender != self.combo_file_conflict0602:
            self.combo_file_conflict0602.SetSelection(selection)

    """创建目录冲突处理下拉框变化事件，实现联动"""
    def on_combo_dir_conflict_change(self, event):
        # 获取触发事件的控件
        sender = event.GetEventObject()
        # 获取当前选择的索引
        selection = sender.GetSelection()
        # 更新其他创建目录下拉框的选择
        if sender != self.combo_dir_conflict0202:
            self.combo_dir_conflict0202.SetSelection(selection)
        if sender != self.combo_dir_conflict0302:
            self.combo_dir_conflict0302.SetSelection(selection)
        if sender != self.combo_dir_conflict0402:
            self.combo_dir_conflict0402.SetSelection(selection)
        if sender != self.combo_dir_conflict0502:
            self.combo_dir_conflict0502.SetSelection(selection)
        if sender != self.combo_dir_conflict0602:
            self.combo_dir_conflict0602.SetSelection(selection)

    def on_combo_create_folder_changed(self, event):
        # 获取触发事件的控件
        sender = event.GetEventObject()
        # 获取当前选择的索引
        selection = sender.GetSelection()
        # 更新另一个创建目录下拉框的选择
        if sender == self.combo_create_folder03:
            self.combo_create_folder04.SetSelection(selection)
        elif sender == self.combo_create_folder04:
            self.combo_create_folder03.SetSelection(selection)

    """应用重命名按钮事件"""
    def on_apply_naming(self, event):
        # 操作级历史记录：捕获 before_grid 快照
        self._begin_op_history(OP_TYPE_RENAME_APPLY, 1)
        # 禁用控件
        self.disable_controls_during_operation()
        try:
            worker = tfo_RenameMoveWorker(self, is_rename=True, worker_mode=WorkerMode.PREVIEW)
            worker.apply_naming()
        finally:
            # 无论是否异常都必须恢复控件状态，避免界面控件永久禁用
            self.restore_controls_after_operation()

    """应用路径变更按钮事件"""
    def on_apply_path(self, event):
        # 来源/目标输入框为空时无法计算新路径，提前提示并返回
        if not self.input_source_path03.GetValue().strip() or not self.input_dest_path03.GetValue().strip():
            wx.MessageBox(translate("warning_source_dest_empty"), translate("dialog_title_warning"), wx.OK | wx.ICON_WARNING)
            return
        self.disable_controls_during_operation()
        try:
            event_obj = event.GetEventObject()
            if event_obj == self.btn_apply_path03:
                # 操作级历史记录：捕获 before_grid 快照
                self._begin_op_history(OP_TYPE_MOVE_APPLY, 2)
                worker = tfo_RenameMoveWorker(self, is_rename=False, worker_mode=WorkerMode.PREVIEW)
                worker.apply_path()
            else:
                # 操作级历史记录：捕获 before_grid 快照
                self._begin_op_history(OP_TYPE_COPY_APPLY, 3)
                worker = tfo_CopyWorker(self, worker_mode=WorkerMode.PREVIEW)
                worker.apply_path()
        finally:
            # 无论是否异常都必须恢复控件状态，避免界面控件永久禁用
            self.restore_controls_after_operation()

    """压缩文件和目录按钮事件 - 改进版本"""
    def on_execute_zip(self, event):
        # 第一步：检查路径有效性
        count_source = 0
        rows_total = self.file_grid.GetNumberRows()
        for row_idx in range(rows_total):
            old_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_OLD_PATH).strip()
            new_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_NEW_PATH).strip()
            if old_path: count_source += 1
        if count_source == 0:
            wx.MessageBox(translate("message_no_zip_items"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        use_match_name = self.radio_zip_matchname05.GetValue()
        file_conflict_method = self.get_combo_box_method(self.combo_file_conflict0502, self.conflict_method_mapping)
        dir_conflict_method = self.get_combo_box_method(self.combo_dir_conflict0502, self.conflict_method_mapping)
        # 第四步：创建对话框
        dlg = wx.Dialog(self.get_parent_window(), title=translate("dialog_title_zip"))
        # 创建标题和图标
        title_sizer = wx.BoxSizer(wx.HORIZONTAL)
        icon = wx.StaticBitmap(dlg, bitmap=wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, wx.ART_OTHER, (32, 32)))
        title = wx.StaticText(dlg, label=translate("dialog_title_zip"))
        font = title.GetFont()
        font.SetPointSize(font.GetPointSize() + 1)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(font)
        title_sizer.Add(icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        title_sizer.Add(title, 0, wx.ALIGN_CENTER_VERTICAL)
        # 显示压缩选项
        zip_group_text = translate("radio_zip_matchname") if use_match_name else translate("radio_zip_foldername")
        file_conflict_text = self.combo_file_conflict0502.GetStringSelection()
        dir_conflict_text = self.combo_dir_conflict0502.GetStringSelection()
        options_label = translate("dialog_text_zip_options", zip_group=zip_group_text, file_conflict=file_conflict_text, dir_conflict=dir_conflict_text)
        options_text = wx.StaticText(dlg, label=options_label)
        options_text.Wrap(450)
        # 创建信息文本
        info_text = wx.StaticText(dlg, label=translate("dialog_text_zip_info"))
        info_text.Wrap(450)
        # 创建按钮
        btn_cancel = wx.Button(dlg, label=translate("cancel"))
        btn_zip_original = wx.Button(dlg, label=translate("btn_execute_zip"))
        if count_source == 0: btn_zip_original.Disable()
        # 绑定按钮事件
        btn_zip_original.Bind(wx.EVT_BUTTON, lambda e: dlg.EndModal(wx.ID_YES))
        btn_cancel.Bind(wx.EVT_BUTTON, lambda e: dlg.EndModal(wx.ID_CANCEL))
        # 设置焦点到取消按钮
        btn_cancel.SetFocus()
        # 布局
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(title_sizer, 0, wx.ALL | wx.EXPAND, 10)
        sizer.Add(options_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        sizer.Add(info_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        # 按钮布局
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_cancel, 0, wx.ALL, 5)
        btn_sizer.Add(btn_zip_original, 0, wx.ALL, 5)
        btn_sizer.AddStretchSpacer()
        sizer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, 10)
        dlg.SetSizerAndFit(sizer)
        # 添加键盘快捷键支持（ESC取消，Enter触发默认按钮）
        def on_char(event):
            keycode = event.GetKeyCode()
            if keycode == wx.WXK_ESCAPE:
                dlg.EndModal(wx.ID_CANCEL)
            elif keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
                # 查找当前焦点在哪个按钮上
                focused = wx.Window.FindFocus()
                if focused == btn_zip_original:
                    dlg.EndModal(wx.ID_YES)
                elif focused == btn_cancel:
                    dlg.EndModal(wx.ID_CANCEL)
                else:
                    # 默认行为：如果没有焦点在按钮上，则触发取消按钮
                    dlg.EndModal(wx.ID_CANCEL)
            event.Skip()
        dlg.Bind(wx.EVT_CHAR_HOOK, on_char)
        # 显示对话框并获取结果
        result = dlg.ShowModal()
        dlg.Destroy()
        # 检查结果
        if result == wx.ID_CANCEL: return

        # 目标路径校验：非空时必须为目录；目录不存在则自动创建；为空则按原逻辑自动计算路径
        target_path = self.input_zip_target05.GetValue().strip()
        if not target_path:
            target_path = None
        elif os.path.exists(target_path):
            # 已存在：只允许为目录
            if not os.path.isdir(target_path):
                wx.MessageBox(translate("error_target_is_file"), translate("dialog_title_warning"), wx.OK | wx.ICON_WARNING)
                return
        else:
            # 不存在：自动创建目标目录
            try:
                os.makedirs(target_path, exist_ok=True)
            except OSError as e:
                wx.MessageBox(translate("error_target_create_failed", error=str(e)), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
                return

        # 操作级历史记录：捕获 before_grid 快照
        self._begin_op_history(OP_TYPE_ZIP_EXECUTE, 4)
        # 第五步：禁用相关控件
        self.disable_controls_during_operation()
        # 将"预览结果"按钮改为"中断执行"
        self.btn_preview_stop0502.SetLabel(translate("btn_stop"))
        self.btn_preview_stop0502.Bind(wx.EVT_BUTTON, self.on_stop_operation)
        self.btn_preview_stop0502.Enable()
        self.tab05.Layout()
        
        # 第六步：创建并启动压缩线程
        self.file_grid.ForceRefresh()
        self.file_grid.Update()
        wx.Yield()
        self.zip_worker = tfo_ZipWorker(self, True, use_match_name,
                                target_path, file_conflict_method, dir_conflict_method, worker_mode=WorkerMode.EXECUTE)
        self.zip_worker.start()
        # 第七步：启动进度检查定时器
        self.zip_progress_timer = wx.Timer(self.get_parent_window())
        self.get_parent_window().Bind(wx.EVT_TIMER, self.check_zip_progress, self.zip_progress_timer)
        self.zip_progress_timer.Start(100)  # 每100毫秒检查一次

    """执行解压按钮事件"""
    def on_execute_unzip(self, event):
        # 第一步：检查路径有效性
        count_source = 0
        rows_total = self.file_grid.GetNumberRows()
        for row_idx in range(rows_total):
            old_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_OLD_PATH).strip()
            if old_path: count_source += 1
        if count_source == 0:
            wx.MessageBox(translate("message_no_unzip_items"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        use_match_name = self.radio_unzip_match06.GetValue()
        file_conflict_method = self.get_combo_box_method(self.combo_file_conflict0602, self.conflict_method_mapping)
        dir_conflict_method = self.get_combo_box_method(self.combo_dir_conflict0602, self.conflict_method_mapping)
        # 创建确认对话框
        dlg = wx.Dialog(self.get_parent_window(), title=translate("dialog_title_unzip"))
        title_sizer = wx.BoxSizer(wx.HORIZONTAL)
        icon = wx.StaticBitmap(dlg, bitmap=wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, wx.ART_OTHER, (32, 32)))
        title = wx.StaticText(dlg, label=translate("dialog_title_unzip"))
        font = title.GetFont()
        font.SetPointSize(font.GetPointSize() + 1)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(font)
        title_sizer.Add(icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        title_sizer.Add(title, 0, wx.ALIGN_CENTER_VERTICAL)
        # 显示解压选项
        unzip_group_text = translate("radio_unzip_match") if use_match_name else translate("radio_unzip_package")
        file_conflict_text = self.combo_file_conflict0602.GetStringSelection()
        dir_conflict_text = self.combo_dir_conflict0602.GetStringSelection()
        options_label = translate("dialog_text_unzip_options", unzip_group=unzip_group_text, file_conflict=file_conflict_text, dir_conflict=dir_conflict_text)
        options_text = wx.StaticText(dlg, label=options_label)
        options_text.Wrap(450)
        # 创建信息文本
        info_text = wx.StaticText(dlg, label=translate("dialog_text_unzip_info"))
        info_text.Wrap(450)
        # 创建按钮
        btn_cancel = wx.Button(dlg, label=translate("cancel"))
        btn_unzip_original = wx.Button(dlg, label=translate("btn_execute_unzip"))
        if count_source == 0: btn_unzip_original.Disable()
        # 绑定按钮事件
        btn_unzip_original.Bind(wx.EVT_BUTTON, lambda e: dlg.EndModal(wx.ID_YES))
        btn_cancel.Bind(wx.EVT_BUTTON, lambda e: dlg.EndModal(wx.ID_CANCEL))
        # 设置焦点到取消按钮
        btn_cancel.SetFocus()
        # 布局
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(title_sizer, 0, wx.ALL | wx.EXPAND, 10)
        sizer.Add(options_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        sizer.Add(info_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_cancel, 0, wx.ALL, 5)
        btn_sizer.Add(btn_unzip_original, 0, wx.ALL, 5)
        btn_sizer.AddStretchSpacer()
        sizer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, 10)
        dlg.SetSizerAndFit(sizer)
        # 添加键盘快捷键支持（ESC取消，Enter触发默认按钮）
        def on_char(event):
            keycode = event.GetKeyCode()
            if keycode == wx.WXK_ESCAPE:
                dlg.EndModal(wx.ID_CANCEL)
            elif keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
                focused = wx.Window.FindFocus()
                if focused == btn_unzip_original:
                    dlg.EndModal(wx.ID_YES)
                elif focused == btn_cancel:
                    dlg.EndModal(wx.ID_CANCEL)
                else:
                    dlg.EndModal(wx.ID_CANCEL)
            event.Skip()
        dlg.Bind(wx.EVT_CHAR_HOOK, on_char)
        result = dlg.ShowModal()
        dlg.Destroy()
        if result == wx.ID_CANCEL: return

        # 目标路径校验：非空时必须为目录；目录不存在则自动创建；为空则自动计算
        target_path = self.input_unzip_target06.GetValue().strip()
        if not target_path:
            target_path = None
        elif os.path.exists(target_path):
            if not os.path.isdir(target_path):
                wx.MessageBox(translate("error_target_is_file"), translate("dialog_title_warning"), wx.OK | wx.ICON_WARNING)
                return
        else:
            try:
                os.makedirs(target_path, exist_ok=True)
            except OSError as e:
                wx.MessageBox(translate("error_target_create_failed", error=str(e)), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
                return

        # 操作级历史记录：捕获 before_grid 快照 (Tab06 -> tab_index=5)
        self._begin_op_history(OP_TYPE_UNZIP_EXECUTE, 5)
        # 禁用相关控件
        self.disable_controls_during_operation()
        # 将"预览结果"按钮改为"中断执行"
        self.btn_preview_stop0602.SetLabel(translate("btn_stop"))
        self.btn_preview_stop0602.Bind(wx.EVT_BUTTON, self.on_stop_operation)
        self.btn_preview_stop0602.Enable()
        self.tab06.Layout()

        # 创建并启动解压线程
        self.file_grid.ForceRefresh()
        self.file_grid.Update()
        wx.Yield()
        self.unzip_worker = tfo_UnZipWorker(self, use_match_name,
                                target_path, file_conflict_method, dir_conflict_method, worker_mode=WorkerMode.EXECUTE)
        self.unzip_worker.start()
        # 启动进度检查定时器
        self.unzip_progress_timer = wx.Timer(self.get_parent_window())
        self.get_parent_window().Bind(wx.EVT_TIMER, self.check_unzip_progress, self.unzip_progress_timer)
        self.unzip_progress_timer.Start(100)  # 每100毫秒检查一次

    """应用解压按钮事件"""
    def on_apply_unzip(self, event):
        # 检查是否有需要解压的项目
        count_source = 0
        rows_total = self.file_grid.GetNumberRows()
        for row_idx in range(rows_total):
            old_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_OLD_PATH).strip()
            if old_path:
                count_source += 1
        if count_source == 0:
            wx.MessageBox(translate("message_no_unzip_items"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        use_match_name = self.radio_unzip_match06.GetValue()
        file_conflict_method = self.get_combo_box_method(self.combo_file_conflict0602, self.conflict_method_mapping)
        dir_conflict_method = self.get_combo_box_method(self.combo_dir_conflict0602, self.conflict_method_mapping)
        # 目标路径：非空时用目标路径重写NewPath列（空则自动计算）
        apply_target_path = self.input_unzip_target06.GetValue().strip()
        if not apply_target_path:
            apply_target_path = None
        # 操作级历史记录：捕获 before_grid 快照 (Tab06 -> tab_index=5)
        self._begin_op_history(OP_TYPE_UNZIP_APPLY, 5)
        # 禁用相关控件
        self.disable_controls_during_operation()
        # 禁用tab06里的交互控件
        self.radio_unzip_package06.Enable(False)
        self.radio_unzip_match06.Enable(False)
        self.combo_file_conflict0602.Enable(False)
        self.combo_dir_conflict0602.Enable(False)
        self.input_unzip_target06.Enable(False)
        self.btn_unzip_target_browse06.Enable(False)

        # 创建并启动解压线程（不执行解压，只计算目标路径）
        self.unzip_worker = tfo_UnZipWorker(self, use_match_name,
                                apply_target_path, file_conflict_method, dir_conflict_method, worker_mode=WorkerMode.APPLY)
        self.unzip_worker.start()
        # 启动进度检查定时器
        self.unzip_progress_timer = wx.Timer(self.get_parent_window())
        self.get_parent_window().Bind(wx.EVT_TIMER, self.check_unzip_progress, self.unzip_progress_timer)
        self.unzip_progress_timer.Start(100)

    """预览解压结果"""
    def on_preview_unzip(self, event):
        rows_total = self.file_grid.GetNumberRows()
        count_total = 0
        for row_idx in range(rows_total):
            old_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_OLD_PATH).strip()
            if old_path:
                count_total += 1
        if count_total == 0:
            wx.MessageBox(translate("message_no_preview_items"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return

        # 操作级历史记录：捕获 before_grid 快照 (Tab06 -> tab_index=5)
        self._begin_op_history(OP_TYPE_UNZIP_PREVIEW, 5)
        # 禁用相关控件，显示终止按钮
        self.disable_controls_during_operation()
        self.btn_preview_stop0602.Enable()
        self.tab06.Layout()

        # 获取解压选项（与 Execute 一致：尊重目标路径与用户填写的非空新路径）
        use_match_name = self.radio_unzip_match06.GetValue()
        file_conflict_method = self.get_combo_box_method(self.combo_file_conflict0602, self.conflict_method_mapping)
        dir_conflict_method = self.get_combo_box_method(self.combo_dir_conflict0602, self.conflict_method_mapping)
        target_path = self.input_unzip_target06.GetValue().strip() or None

        # 创建并启动解压工作线程（预览模式）
        self.unzip_worker = tfo_UnZipWorker(self, use_match_name,
                                   target_path, file_conflict_method, dir_conflict_method,
                                   worker_mode=WorkerMode.PREVIEW)
        self.unzip_worker.start()
        # 启动进度检查定时器
        self.unzip_progress_timer = wx.Timer(self.get_parent_window())
        self.get_parent_window().Bind(wx.EVT_TIMER, self.check_unzip_progress, self.unzip_progress_timer)
        self.unzip_progress_timer.Start(100)

    """删除文件和目录按钮事件"""
    def on_execute_delete(self, event):
        delete_original = self.radio_delete_target_old07.GetValue()
        # 第一步：检查路径有效性
        count_source = 0
        rows_total = self.file_grid.GetNumberRows()
        for row_idx in range(rows_total):
            if delete_original:
                check_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_OLD_PATH).strip()
            else:
                check_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_NEW_PATH).strip()
            if check_path: count_source += 1
        if count_source == 0:
            wx.MessageBox(translate("message_no_delete_items"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        # 第二步：创建对话框
        dlg = wx.Dialog(self.get_parent_window(), title=translate("dialog_title_delete"), size=(self.spx_calc(500), self.spx_calc(300)))
        
        # 创建标题和图标
        title_sizer = wx.BoxSizer(wx.HORIZONTAL)
        icon = wx.StaticBitmap(dlg, bitmap=wx.ArtProvider.GetBitmap(wx.ART_WARNING, wx.ART_OTHER, (32, 32)))
        title = wx.StaticText(dlg, label=translate("dialog_title_delete"))
        font = title.GetFont()
        font.SetPointSize(int(font.GetPointSize() + 1))
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(font)
        title_sizer.Add(icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(10))
        title_sizer.Add(title, 0, wx.ALIGN_CENTER_VERTICAL)
        
        # 依combo_delete_filter07的选择显示不同的删除过滤文本
        delete_filter_text = self.combo_delete_filter07.GetStringSelection()
        delete_target_text = translate("radio_delete_target_old") if delete_original else translate("radio_delete_target_new")
        
        # 创建信息文本
        info_text = wx.StaticText(dlg, label=translate("dialog_text_confirm_delete_settings", delete_filter=delete_filter_text, delete_target=delete_target_text))
        info_text.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        
        # 创建按钮
        btn_cancel = wx.Button(dlg, label=translate("dialog_btn_cancel"))
        btn_ok = wx.Button(dlg, label=translate("dialog_btn_confirm_delete"))
        
        # 绑定按钮事件
        btn_ok.Bind(wx.EVT_BUTTON, lambda e: dlg.EndModal(wx.ID_OK))
        btn_cancel.Bind(wx.EVT_BUTTON, lambda e: dlg.EndModal(wx.ID_CANCEL))
        # 设置焦点到取消按钮
        btn_cancel.SetFocus()
        
        # 布局
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(title_sizer, 0, wx.ALL | wx.EXPAND, self.spx_calc(10))
        sizer.Add(info_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, self.spx_calc(10))
        # 按钮布局
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_cancel, 0, wx.ALL, self.spx_calc(5))
        btn_sizer.Add(btn_ok, 0, wx.ALL, self.spx_calc(5))
        btn_sizer.AddStretchSpacer()
        sizer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, self.spx_calc(10))
        dlg.SetSizer(sizer)
        # 添加键盘快捷键支持（ESC取消，Enter触发默认按钮）
        def on_char(event):
            keycode = event.GetKeyCode()
            if keycode == wx.WXK_ESCAPE:
                dlg.EndModal(wx.ID_CANCEL)
            elif keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
                # 查找当前焦点在哪个按钮上
                focused = wx.Window.FindFocus()
                if focused == btn_ok:
                    dlg.EndModal(wx.ID_OK)
                elif focused == btn_cancel:
                    dlg.EndModal(wx.ID_CANCEL)
                else:
                    # 默认行为：如果没有焦点在按钮上，则触发取消按钮
                    dlg.EndModal(wx.ID_CANCEL)
            event.Skip()
        dlg.Bind(wx.EVT_CHAR_HOOK, on_char)
        # 显示对话框并获取结果
        result = dlg.ShowModal()
        dlg.Destroy()
        # 检查结果
        if result != wx.ID_OK: return
        # 使用删除目标选择
        use_old_path = delete_original
        # 第三步：在后台线程里进行删除操作
        self.file_grid.ForceRefresh()
        self.file_grid.Update()
        wx.Yield()
        self.execute_delete_in_thread(use_old_path)

    def _collect_delete_paths_info(self, delete_original=True):
        paths_info = []
        rows_total = self.file_grid.GetNumberRows()
        for row_idx in range(rows_total):
            if delete_original:
                delete_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_OLD_PATH).strip()
                path_type = translate("path_type_old")
            else:
                delete_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_NEW_PATH).strip()
                path_type = translate("path_type_new")
            paths_info.append((row_idx, delete_path, path_type))
        return paths_info

    """在后台线程中进行删除操作"""
    def execute_delete_in_thread(self, delete_original=True, execute=True):
        # 获取删除过滤选项
        delete_filter = self.get_combo_box_method(self.combo_delete_filter07, self.delete_filter_mapping)
        
        # 获取过滤参数
        filter_params = {}
        filter_key = delete_filter
        if filter_key in ["name_contains", "name_not_contains"]:
            filter_params["text"] = self.txt_filename_filter07.GetValue().strip()
        elif filter_key in ["size_less_than", "size_greater_than", "size_between"]:
            try:
                size_min_str = self.txt_size_min07.GetValue().strip()
                size_max_str = self.txt_size_max07.GetValue().strip()
                
                unit = self.combo_size_unit07.GetValue()
                unit_multiplier = {
                    "B": 1,
                    "KB": 1024,
                    "MB": 1024 * 1024,
                    "GB": 1024 * 1024 * 1024
                }
                
                if unit not in unit_multiplier:
                    wx.MessageBox(translate("message_invalid_size_unit"), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
                    return
                
                if filter_key == "size_less_than":
                    if size_min_str:
                        try:
                            filter_params["size_max"] = float(size_min_str) * unit_multiplier[unit]
                        except ValueError:
                            wx.MessageBox(translate("message_invalid_size_input"), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
                            return
                    else:
                        filter_params["size_max"] = 0
                elif filter_key == "size_greater_than":
                    if size_min_str:
                        try:
                            filter_params["size_min"] = float(size_min_str) * unit_multiplier[unit]
                        except ValueError:
                            wx.MessageBox(translate("message_invalid_size_input"), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
                            return
                    else:
                        filter_params["size_min"] = 0
                elif filter_key == "size_between":
                    if size_min_str:
                        try:
                            filter_params["size_min"] = float(size_min_str) * unit_multiplier[unit]
                        except ValueError:
                            wx.MessageBox(translate("message_invalid_size_input"), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
                            return
                    else:
                        filter_params["size_min"] = 0
                    
                    if size_max_str:
                        try:
                            filter_params["size_max"] = float(size_max_str) * unit_multiplier[unit]
                        except ValueError:
                            wx.MessageBox(translate("message_invalid_size_input"), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
                            return
                    else:
                        filter_params["size_max"] = float('inf')
            except Exception as e:
                wx.MessageBox(translate("message_size_error", error=str(e)), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
                return
        elif filter_key in ["create_time_before", "modify_time_before"]:
            # 早于：只使用结束时间
            date_to = self.date_to07.GetValue()
            time_to = self.time_to07.GetValue()
            dt_to = datetime.datetime(date_to.year, date_to.month + 1, date_to.day, time_to.hour, time_to.minute, time_to.second)  # wx.DateTime.GetMonth() returns 0-11, Python datetime expects 1-12
            filter_params["date_to"] = dt_to
        elif filter_key in ["create_time_after", "modify_time_after"]:
            # 晚于：只使用开始时间
            date_from = self.date_from07.GetValue()
            time_from = self.time_from07.GetValue()
            dt_from = datetime.datetime(date_from.year, date_from.month + 1, date_from.day, time_from.hour, time_from.minute, time_from.second)  # wx.DateTime.GetMonth() returns 0-11, Python datetime expects 1-12
            filter_params["date_from"] = dt_from
        elif filter_key in ["create_time_between", "modify_time_between"]:
            # 介于之间：使用开始和结束时间
            date_from = self.date_from07.GetValue()
            time_from = self.time_from07.GetValue()
            dt_from = datetime.datetime(date_from.year, date_from.month + 1, date_from.day, time_from.hour, time_from.minute, time_from.second)  # wx.DateTime.GetMonth() returns 0-11, Python datetime expects 1-12
            date_to = self.date_to07.GetValue()
            time_to = self.time_to07.GetValue()
            dt_to = datetime.datetime(date_to.year, date_to.month + 1, date_to.day, time_to.hour, time_to.minute, time_to.second)  # wx.DateTime.GetMonth() returns 0-11, Python datetime expects 1-12
            filter_params["date_from"] = dt_from
            filter_params["date_to"] = dt_to
        
        # 操作级历史记录：捕获 before_grid 快照（依据 execute 参数确定操作类型）
        self._begin_op_history(OP_TYPE_DELETE_EXECUTE if execute else OP_TYPE_DELETE_APPLY, 6)
        # 禁用相关控件
        self.disable_controls_during_operation()
        # 将"预览结果"按钮改为"中断执行"
        self.btn_preview_stop0702.SetLabel(translate("btn_stop"))
        self.btn_preview_stop0702.Bind(wx.EVT_BUTTON, self.on_stop_operation)
        self.btn_preview_stop0702.Enable()
        self.tab07.Layout()
        # 创建并启动删除工作线程
        paths_info = self._collect_delete_paths_info(delete_original)
        self.delete_worker = tfo_DeleteWorker(self, delete_original, paths_info, worker_mode=WorkerMode.EXECUTE if execute else WorkerMode.APPLY, delete_filter=delete_filter, filter_params=filter_params)
        self.delete_worker.start()
        # 启动进度检查定时器
        self.delete_progress_timer = wx.Timer(self.get_parent_window())
        self.get_parent_window().Bind(wx.EVT_TIMER, self.check_delete_progress, self.delete_progress_timer)
        self.delete_progress_timer.Start(100)  # 每100毫秒检查一次

    """检查删除进度"""
    def check_delete_progress(self, event):
        if hasattr(self, 'delete_worker') and self.delete_worker.is_alive():
            # 获取进度信息
            progress_info = self.delete_worker.get_progress_info()
            if progress_info:
                finished, total, ok_files, ok_dirs = progress_info
                if total > 0:
                    if self.delete_worker.worker_mode != WorkerMode.APPLY:
                        delete_type = translate("path_type_old") if self.delete_worker.delete_original else translate("path_type_new")
                        self.status_bar.SetStatusText(translate("status_deleting", finished=finished, total=total, type=delete_type, files=ok_files, dirs=ok_dirs), 0)
                        self.status_bar.SetStatusText(f"{finished}/{total}", 1)
                    else:
                        self.status_bar.SetStatusText(translate("status_filtering", finished=finished, total=total), 0)
                        self.status_bar.SetStatusText(f"{finished}/{total}", 1)
        else:
            # 线程已完成，停止定时器
            if hasattr(self, 'delete_progress_timer'):
                self.delete_progress_timer.Stop()
                del self.delete_progress_timer
            # 恢复控件状态
            self.restore_controls_after_operation()
            # 恢复"预览结果"按钮
            self.btn_preview_stop0702.SetLabel(translate("btn_preview"))
            self.btn_preview_stop0702.Bind(wx.EVT_BUTTON, self.on_preview_delete)
            self.tab07.Layout()
            # 更新状态栏
            if hasattr(self, 'delete_worker'):
                if self.delete_worker.worker_mode != WorkerMode.APPLY:
                    progress_info = self.delete_worker.get_progress_info()
                    if progress_info:
                        finished, total, ok_files, ok_dirs = progress_info
                        if total > 0:
                            delete_type = translate("path_type_old") if self.delete_worker.delete_original else translate("path_type_new")
                            self.status_bar.SetStatusText(translate("status_delete_completed", total=total, type=delete_type, operated=ok_files + ok_dirs, dirs=ok_dirs, files=ok_files), 0)
                            # 在右侧状态栏显示简要结果
                            deleted_count = ok_files + ok_dirs
                            self.status_bar.SetStatusText(translate("status_brief_deleted", deleted=deleted_count), 1)
                else:
                    delete_count = self.delete_worker.get_to_delete_count()
                    self.status_bar.SetStatusText(translate("status_filtered_result", count=delete_count), 0)
                    self.status_bar.SetStatusText("", 1)
            # 刷新表格
            self.file_grid.ForceRefresh()

    """检查压缩进度"""
    def check_zip_progress(self, event):
        if hasattr(self, 'zip_worker') and self.zip_worker.is_alive():
            # 获取进度信息
            progress_info = self.zip_worker.get_progress_info()
            if progress_info:
                finished, total, ok = progress_info
                if total > 0:
                    # 根据是否执行压缩显示不同的进度信息
                    if getattr(self.zip_worker, 'execute_zip', True):
                        self.status_bar.SetStatusText(translate("status_compressing", finished=finished, total=total, ok=ok), 0)
                    else:
                        self.status_bar.SetStatusText(translate("status_calculating", finished=finished, total=total), 0)
                    self.status_bar.SetStatusText(f"{finished}/{total}", 1)
        else:
            # 线程已完成，停止定时器
            if hasattr(self, 'zip_progress_timer'):
                self.zip_progress_timer.Stop()
                del self.zip_progress_timer
            # 恢复控件状态
            self.restore_controls_after_operation()
            # 恢复"预览结果"按钮
            self.btn_preview_stop0502.SetLabel(translate("btn_preview"))
            self.btn_preview_stop0502.Bind(wx.EVT_BUTTON, self.on_preview_zip)
            self.tab05.Layout()
            # 添加压缩完成后的状态显示
            if hasattr(self, 'zip_worker'):
                # 获取ZIP统计信息
                total_zips = getattr(self.zip_worker, 'total_zips', 0)
                created_zips = getattr(self.zip_worker, 'created_zips', 0)
                # 根据是否执行压缩显示不同的完成信息
                if getattr(self.zip_worker, 'execute_zip', True):
                    # 执行压缩完成
                    # 获取保存位置
                    save_location = translate("unknown")
                    if hasattr(self.zip_worker, 'save_dir') and self.zip_worker.save_dir:
                        save_location = self.zip_worker.save_dir
                    # 更新状态栏
                    self.status_bar.SetStatusText(translate("status_zip_completed", total=total_zips, created=created_zips, location=save_location), 0)
                    # 在右侧状态栏显示简要结果
                    self.status_bar.SetStatusText(translate("status_brief_zipped", ok=created_zips), 1)
                else:
                    self.status_bar.SetStatusText(translate("status_zip_grouped", total=total_zips), 0)
                    self.status_bar.SetStatusText("", 1)

    """检查解压进度"""
    def check_unzip_progress(self, event):
        if hasattr(self, 'unzip_worker') and self.unzip_worker.is_alive():
            # 获取进度信息
            progress_info = self.unzip_worker.get_progress_info()
            if progress_info:
                finished, total, ok = progress_info
                if total > 0:
                    # 根据是否执行解压显示不同的进度信息
                    if self.unzip_worker.worker_mode == WorkerMode.EXECUTE:
                        self.status_bar.SetStatusText(translate("status_unzipping", finished=finished, total=total, ok=ok), 0)
                    else:
                        self.status_bar.SetStatusText(translate("status_calculating", finished=finished, total=total), 0)
                    self.status_bar.SetStatusText(f"{finished}/{total}", 1)
        else:
            # 线程已完成，停止定时器
            if hasattr(self, 'unzip_progress_timer'):
                self.unzip_progress_timer.Stop()
                del self.unzip_progress_timer
            # 恢复控件状态
            self.restore_controls_after_operation()
            # 恢复"预览结果"按钮
            self.btn_preview_stop0602.SetLabel(translate("btn_preview"))
            self.btn_preview_stop0602.Bind(wx.EVT_BUTTON, self.on_preview_unzip)
            self.tab06.Layout()
            # 添加解压完成后的状态显示
            if hasattr(self, 'unzip_worker'):
                total_packages = getattr(self.unzip_worker, 'total_packages', 0)
                unzipped_packages = getattr(self.unzip_worker, 'unzipped_packages', 0)
                if self.unzip_worker.worker_mode == WorkerMode.EXECUTE:
                    save_location = translate("unknown")
                    if getattr(self.unzip_worker, 'save_dir', None):
                        save_location = self.unzip_worker.save_dir
                    self.status_bar.SetStatusText(translate("status_unzip_completed", total=total_packages, unzipped=unzipped_packages, location=save_location), 0)
                    self.status_bar.SetStatusText(translate("status_brief_unzipped", ok=unzipped_packages), 1)
                else:
                    self.status_bar.SetStatusText(translate("status_unzip_calculated", total=total_packages), 0)
                    self.status_bar.SetStatusText("", 1)

    """检查去重进度"""
    def check_duplicate_progress(self, event):
        if hasattr(self, 'duplicate_worker') and self.duplicate_worker.is_alive():
            progress_info = self.duplicate_worker.get_progress_info()
            hash_progress = self.duplicate_worker.get_hash_progress_info()
            if progress_info:
                if len(progress_info) == 5:
                    finished, total, duplicate_groups, files_to_delete, deleted_count = progress_info
                    if total > 0:
                        self.status_bar.SetStatusText(translate("status_deleting_duplicates", deleted=deleted_count, total=files_to_delete), 0)
                        self.status_bar.SetStatusText(f"{deleted_count}/{files_to_delete}", 1)
                else:
                    finished, total, duplicate_groups, files_to_delete = progress_info
                    if hash_progress and hash_progress[1] > 0:
                        hash_current, hash_total = hash_progress
                        percent = int(hash_current * 100 / hash_total) if hash_total > 0 else 0
                        self.status_bar.SetStatusText(translate("status_hashing_progress", current=hash_current, total=hash_total, percent=percent), 0)
                    elif total > 0:
                        self.status_bar.SetStatusText(translate("status_deduplicating", finished=finished, total=total), 0)
                        self.status_bar.SetStatusText(f"{finished}/{total}", 1)
        else:
            # 线程已完成，停止定时器
            if hasattr(self, 'duplicate_progress_timer'):
                self.duplicate_progress_timer.Stop()
                del self.duplicate_progress_timer
            # 恢复控件状态
            self.restore_controls_after_operation()
            # 恢复"预览结果"按钮
            self.btn_preview_stop0802.SetLabel(translate("btn_preview"))
            self.btn_preview_stop0802.Bind(wx.EVT_BUTTON, self.on_preview_duplicate)
            self.tab08.Layout()
            # 更新状态栏
            if hasattr(self, 'duplicate_worker'):
                progress_info = self.duplicate_worker.get_progress_info()
                if progress_info:
                    # 检查进度信息的长度，判断是否执行了删除
                    if len(progress_info) == 5:
                        # 执行了删除
                        finished, total, duplicate_groups, files_to_delete, deleted_count = progress_info
                        if total > 0:
                            self.status_bar.SetStatusText(translate("status_deduplicate_completed", groups=duplicate_groups, deleted=deleted_count), 0)
                            # 在右侧状态栏显示简要结果
                            self.status_bar.SetStatusText(translate("status_brief_dedup", deleted=deleted_count), 1)
                    else:
                        # 仅查重
                        finished, total, duplicate_groups, files_to_delete = progress_info
                        if total > 0:
                            self.status_bar.SetStatusText(translate("status_deduplicate_found", groups=duplicate_groups, files=files_to_delete), 0)
                            self.status_bar.SetStatusText("", 1)

    """执行移动或重命名按钮事件"""
    """执行重命名/移动按钮事件"""
    def on_execute_move(self, event):
        # 获取触发事件的按钮对象
        event_obj = event.GetEventObject()
        # 判断操作类型
        if event_obj == self.btn_execute_rename02:
            operation_type = "rename"
            operation_name = translate("operation_rename")
        elif event_obj == self.btn_execute_move03:
            operation_type = "move"
            operation_name = translate("operation_move")
        else:
            operation_type = "move"
            operation_name = translate("operation_move")
        # 检查是否有需要处理的项目
        count_source_and_new = 0
        rows_total = self.file_grid.GetNumberRows()
        for row_idx in range(rows_total):
            old_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_OLD_PATH).strip()
            new_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_NEW_PATH).strip()
            if old_path or new_path:
                count_source_and_new += 1
        if count_source_and_new == 0:
            wx.MessageBox(translate("message_no_operation_items", operation=operation_name), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        # 获取冲突处理方式
        file_conflict = self.combo_file_conflict0202.GetStringSelection()
        dir_conflict = self.combo_dir_conflict0202.GetStringSelection()
        # 弹出确认对话框
        dlg = wx.Dialog(self.get_parent_window(), title=translate("dialog_title_confirm_operation", operation=operation_name), size=(self.spx_calc(500), self.spx_calc(250)))
        # 创建标题和图标
        title_sizer = wx.BoxSizer(wx.HORIZONTAL)
        icon = wx.StaticBitmap(dlg, bitmap=wx.ArtProvider.GetBitmap(wx.ART_WARNING, wx.ART_OTHER, (32, 32)))
        title = wx.StaticText(dlg, label=translate("dialog_title_confirm_operation", operation=operation_name))
        font = title.GetFont()
        font.SetPointSize(int(font.GetPointSize() + 1))
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(font)
        title_sizer.Add(icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(10))
        title_sizer.Add(title, 0, wx.ALIGN_CENTER_VERTICAL)
        # 创建信息文本
        info_text = wx.StaticText(dlg, label=translate("dialog_text_confirm_operation", operation=operation_name, file_conflict=file_conflict, dir_conflict=dir_conflict))
        # 创建按钮
        btn_cancel = wx.Button(dlg, label=translate("cancel"), id=wx.ID_CANCEL)
        btn_ok = wx.Button(dlg, label=translate("dialog_btn_execute_operation", operation=operation_name), id=wx.ID_OK)
        # 设置焦点到取消按钮
        btn_cancel.SetFocus()
        # 布局
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(title_sizer, 0, wx.ALL | wx.EXPAND, self.spx_calc(10))
        sizer.Add(info_text, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM, self.spx_calc(20))
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_cancel, 0, wx.ALL, self.spx_calc(5))
        btn_sizer.Add(btn_ok, 0, wx.ALL, self.spx_calc(5))
        btn_sizer.AddStretchSpacer()
        sizer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, self.spx_calc(10))
        dlg.SetSizer(sizer)
        # 显示对话框
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            # 操作级历史记录：捕获 before_grid 快照
            if operation_type == "rename":
                self._begin_op_history(OP_TYPE_RENAME_EXECUTE, 1)
            else:
                self._begin_op_history(OP_TYPE_MOVE_EXECUTE, 2)
            # 用户确认，在后台线程中执行操作
            self.file_grid.ForceRefresh()
            self.file_grid.Update()
            wx.Yield()
            self.execute_movecopy_in_thread(operation_type=operation_type)
        else:
            # 用户取消
            self.status_bar.SetStatusText(translate("status_operation_cancelled", operation=operation_name), 0)
        dlg.Destroy()

    """执行复制按钮事件"""
    def on_execute_copy(self, event):
        count_source_and_new = 0
        rows_total = self.file_grid.GetNumberRows()
        for row_idx in range(rows_total):
            old_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_OLD_PATH).strip()
            new_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_NEW_PATH).strip()
            if old_path or new_path:
                count_source_and_new += 1
        if count_source_and_new == 0:
            wx.MessageBox(translate("message_no_copy_items"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        # 获取冲突处理方式
        file_conflict = self.combo_file_conflict0402.GetStringSelection()
        dir_conflict = self.combo_dir_conflict0402.GetStringSelection()
        # 弹出确认对话框
        dlg = wx.Dialog(self.get_parent_window(), title=translate("dialog_title_confirm_copy"), size=(self.spx_calc(500), self.spx_calc(250)))
        # 创建标题和图标
        title_sizer = wx.BoxSizer(wx.HORIZONTAL)
        icon = wx.StaticBitmap(dlg, bitmap=wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, wx.ART_OTHER, (32, 32)))
        title = wx.StaticText(dlg, label=translate("dialog_title_confirm_copy"))
        font = title.GetFont()
        font.SetPointSize(int(font.GetPointSize() + 1))
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(font)
        title_sizer.Add(icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(10))
        title_sizer.Add(title, 0, wx.ALIGN_CENTER_VERTICAL)
        info_text = wx.StaticText(dlg, label=translate("dialog_text_confirm_copy", file_conflict=file_conflict, dir_conflict=dir_conflict))
        btn_cancel = wx.Button(dlg, label=translate("cancel"), id=wx.ID_CANCEL)
        btn_ok = wx.Button(dlg, label=translate("btn_execute_copy"), id=wx.ID_OK)
        # 设置焦点到取消按钮
        btn_cancel.SetFocus()
        # 布局
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(title_sizer, 0, wx.ALL | wx.EXPAND, self.spx_calc(10))
        sizer.Add(info_text, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM, self.spx_calc(20))
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_cancel, 0, wx.ALL, self.spx_calc(5))
        btn_sizer.Add(btn_ok, 0, wx.ALL, self.spx_calc(5))
        btn_sizer.AddStretchSpacer()
        sizer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, self.spx_calc(10))
        dlg.SetSizer(sizer)
        # 显示对话框
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            # 操作级历史记录：捕获 before_grid 快照
            self._begin_op_history(OP_TYPE_COPY_EXECUTE, 3)
            # 用户确认，在后台线程中执行复制操作
            self.file_grid.ForceRefresh()
            self.file_grid.Update()
            wx.Yield()
            self.execute_movecopy_in_thread(operation_type="copy")
        else:
            # 用户取消
            self.status_bar.SetStatusText(translate("status_copy_cancelled"), 0)
        dlg.Destroy()

    """在后台线程中执行重命名/移动/复制操作"""
    def execute_movecopy_in_thread(self, operation_type="move"):
        rows_total = self.file_grid.GetNumberRows()
        count_total = 0
        for row_idx in range(rows_total):
            old_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_OLD_PATH).strip()
            new_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_NEW_PATH).strip()
            if old_path or new_path:
                count_total += 1
        if count_total == 0:
            wx.MessageBox(translate("message_no_execute_items"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        # 禁用相关控件，显示终止按钮
        self.disable_controls_during_operation()
        # 将"预览结果"按钮改为"中断执行"
        self.btn_preview_stop0202.SetLabel(translate("btn_stop"))
        self.btn_preview_stop0202.Bind(wx.EVT_BUTTON, self.on_stop_operation)
        self.btn_preview_stop0202.Enable()
        self.tab02.Layout()
        # 创建并启动重命名/移动/复制工作线程
        # Preview/Execute 不再自动执行 Apply：不修改任何行的 Old/New Path；
        # 对 New Path 为空的行按"未设置新路径"处理并跳过（详见 Note 13.0）。
        if operation_type == "copy":
            self.movecopy_worker = tfo_CopyWorker(self, worker_mode=WorkerMode.EXECUTE)
        else:
            is_rename = (operation_type == "rename")
            self.movecopy_worker = tfo_RenameMoveWorker(self, is_rename=is_rename, worker_mode=WorkerMode.EXECUTE)
        self.movecopy_worker.start()
        # 启动进度检查定时器
        self.movecopy_progress_timer = wx.Timer(self.get_parent_window())
        self.get_parent_window().Bind(wx.EVT_TIMER, self.check_movecopy_progress, self.movecopy_progress_timer)
        self.movecopy_progress_timer.Start(100)  # 每100毫秒检查一次

    """检查重命名/移动/复制进度"""
    def check_movecopy_progress(self, event):
        if hasattr(self, 'movecopy_worker') and self.movecopy_worker.is_alive():
            # 获取进度信息
            progress_info = self.movecopy_worker.get_progress_info()
            if progress_info:
                finished, total, ok = progress_info[:3]
                if total > 0:
                    operation_name = self.movecopy_worker._get_operation_name()
                    self.status_bar.SetStatusText(translate("status_operation_in_progress", operation=operation_name, finished=finished, total=total, ok=ok), 0)
                    self.status_bar.SetStatusText(f"{finished}/{total}", 1)
        else:
            # 线程已完成，停止定时器
            if hasattr(self, 'movecopy_progress_timer'):
                self.movecopy_progress_timer.Stop()
                del self.movecopy_progress_timer
            # 恢复控件状态
            self.restore_controls_after_operation()
            # 恢复"预览结果"按钮
            self.btn_preview_stop0202.SetLabel(translate("btn_preview"))
            self.btn_preview_stop0202.Bind(wx.EVT_BUTTON, self.on_preview_rename_move_copy)
            self.tab02.Layout()
            # 更新状态栏
            if hasattr(self, 'movecopy_worker'):
                progress_info = self.movecopy_worker.get_progress_info()
                if progress_info:
                    finished, total, ok, operated = progress_info
                    if total > 0:
                        operation_name = self.movecopy_worker._get_operation_name()
                        self.status_bar.SetStatusText(translate("status_operation_completed", operation=operation_name, total=total, operated=operated), 0)
                        # 在右侧状态栏显示简要结果
                        failed = total - ok
                        if failed > 0:
                            self.status_bar.SetStatusText(translate("status_brief_success_fail", ok=ok, fail=failed), 1)
                        else:
                            self.status_bar.SetStatusText(translate("status_brief_success", ok=ok), 1)

    """终止操作按钮事件"""
    def on_stop_operation(self, event):
        """终止当前正在进行的操作"""
        # 检查是否有移动/复制线程在运行
        if hasattr(self, 'movecopy_worker') and self.movecopy_worker.is_alive():
            # 设置终止标志
            self.movecopy_worker.stop()
            # 等待线程结束（最多等待2秒）
            self.movecopy_worker.join(2)
            if self.movecopy_worker.is_alive():
                # 如果线程还在运行，强制终止
                try:
                    thread_id = self.movecopy_worker.ident
                    if thread_id:
                        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, ctypes.py_object(SystemExit))
                        if res > 1:
                            ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
                except Exception:
                    pass
            # 获取进度信息
            progress_info = self.movecopy_worker.get_progress_info()
            operation_name = self.movecopy_worker._get_operation_name()
            if progress_info:
                finished, total, ok, operated = progress_info
                if total > 0:
                    self.status_bar.SetStatusText(translate("status_operation_interrupted_detailed", operation=operation_name, total=total, operated=operated), 0)
                else:
                    self.status_bar.SetStatusText(translate("status_operation_interrupted_generic", operation=operation_name), 0)
            else:
                self.status_bar.SetStatusText(translate("status_operation_interrupted_generic", operation=operation_name), 0)
            self.status_bar.SetStatusText("", 1)
            # 恢复控件状态
            self.restore_controls_after_operation()
            # 恢复"预览结果"按钮
            self.btn_preview_stop0202.SetLabel(translate("btn_preview"))
            self.btn_preview_stop0202.Bind(wx.EVT_BUTTON, self.on_preview_rename_move_copy)
            self.tab02.Layout()
            # 停止进度定时器
            if hasattr(self, 'movecopy_progress_timer'):
                self.movecopy_progress_timer.Stop()
                del self.movecopy_progress_timer
        # 检查是否有压缩线程在运行
        elif hasattr(self, 'zip_worker') and self.zip_worker.is_alive():
            # 设置终止标志
            self.zip_worker.stop()
            # 等待线程结束（最多等待2秒）
            self.zip_worker.join(2)
            if self.zip_worker.is_alive():
                # 如果线程还在运行，强制终止
                try:
                    thread_id = self.zip_worker.ident
                    if thread_id:
                        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, ctypes.py_object(SystemExit))
                        if res > 1:
                            ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
                except Exception:
                    pass
            # 更新状态栏
            self.status_bar.SetStatusText(translate("status_zip_interrupted"), 0)
            self.status_bar.SetStatusText("", 1)
            # 恢复控件状态
            self.restore_controls_after_operation()
            self.radio_zip_foldername05.Enable(True)
            self.radio_zip_matchname05.Enable(True)
            self.combo_file_conflict0502.Enable(True)
            self.combo_dir_conflict0502.Enable(True)
            self.btn_apply_zip05.Enable(True)
            self.btn_execute_zip05.Enable(True)
            self.tab05.Layout()
            # 停止进度定时器
            if hasattr(self, 'zip_progress_timer'):
                self.zip_progress_timer.Stop()
                del self.zip_progress_timer
        # 检查是否有解压线程在运行
        elif hasattr(self, 'unzip_worker') and self.unzip_worker.is_alive():
            # 设置终止标志
            self.unzip_worker.stop()
            # 等待线程结束（最多等待2秒）
            self.unzip_worker.join(2)
            if self.unzip_worker.is_alive():
                # 如果线程还在运行，强制终止
                try:
                    thread_id = self.unzip_worker.ident
                    if thread_id:
                        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, ctypes.py_object(SystemExit))
                        if res > 1:
                            ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
                except Exception:
                    pass
            # 更新状态栏
            self.status_bar.SetStatusText(translate("status_unzip_interrupted"), 0)
            self.status_bar.SetStatusText("", 1)
            # 恢复控件状态
            self.restore_controls_after_operation()
            self.radio_unzip_package06.Enable(True)
            self.radio_unzip_match06.Enable(True)
            self.combo_file_conflict0602.Enable(True)
            self.combo_dir_conflict0602.Enable(True)
            self.input_unzip_target06.Enable(True)
            self.btn_unzip_target_browse06.Enable(True)
            self.btn_apply_unzip06.Enable(True)
            self.btn_execute_unzip06.Enable(True)
            # 恢复"预览结果"按钮
            self.btn_preview_stop0602.SetLabel(translate("btn_preview"))
            self.btn_preview_stop0602.Bind(wx.EVT_BUTTON, self.on_preview_unzip)
            self.tab06.Layout()
            # 停止进度定时器
            if hasattr(self, 'unzip_progress_timer'):
                self.unzip_progress_timer.Stop()
                del self.unzip_progress_timer
        # 检查是否有删除线程在运行
        elif hasattr(self, 'delete_worker') and self.delete_worker.is_alive():
            # 设置终止标志
            self.delete_worker.stop()
            # 等待线程结束（最多等待2秒）
            self.delete_worker.join(2)
            if self.delete_worker.is_alive():
                # 如果线程还在运行，强制终止
                try:
                    thread_id = self.delete_worker.ident
                    if thread_id:
                        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, ctypes.py_object(SystemExit))
                        if res > 1:
                            ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
                except Exception:
                    pass
            # 获取进度信息
            progress_info = self.delete_worker.get_progress_info()
            delete_type = translate("path_type_old") if self.delete_worker.delete_original else translate("path_type_new")
            if progress_info:
                finished, total, ok_files, ok_dirs = progress_info
                if total > 0:
                    self.status_bar.SetStatusText(translate("status_delete_interrupted", total=total, type=delete_type, operated=ok_files + ok_dirs), 0)
                else:
                    self.status_bar.SetStatusText(translate("status_delete_interrupted_generic"), 0)
            else:
                self.status_bar.SetStatusText(translate("status_delete_interrupted_generic"), 0)
            self.status_bar.SetStatusText("", 1)
            # 恢复控件状态
            self.restore_controls_after_operation()
            self.tab07.Layout()
            # 停止进度定时器
            if hasattr(self, 'delete_progress_timer'):
                self.delete_progress_timer.Stop()
                del self.delete_progress_timer
        # 检查是否有去重线程在运行
        elif hasattr(self, 'duplicate_worker') and self.duplicate_worker.is_alive():
            # 设置终止标志
            self.duplicate_worker.stop()
            # 等待线程结束（最多等待2秒）
            self.duplicate_worker.join(2)
            if self.duplicate_worker.is_alive():
                # 如果线程还在运行，强制终止
                try:
                    thread_id = self.duplicate_worker.ident
                    if thread_id:
                        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, ctypes.py_object(SystemExit))
                        if res > 1:
                            ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
                except Exception:
                    pass
            # 更新状态栏
            self.status_bar.SetStatusText(translate("status_deduplicate_interrupted"), 0)
            self.status_bar.SetStatusText("", 1)
            # 恢复控件状态
            self.restore_controls_after_operation()
            self.tab08.Layout()
            # 停止进度定时器
            if hasattr(self, 'duplicate_progress_timer'):
                self.duplicate_progress_timer.Stop()
                del self.duplicate_progress_timer

    """预览重命名/移动/复制结果"""
    def on_preview_rename_move_copy(self, event):
        """预览重命名/移动/复制结果功能"""
        # 获取当前活动的tab
        current_tab = self.notebook.GetSelection()
        # 确定操作类型
        if current_tab == 1:
            operation_type = "rename"
        elif current_tab == 2:
            operation_type = "move"
        else:
            operation_type = "copy"
        
        # 检查是否有Old Path
        rows_total = self.file_grid.GetNumberRows()
        has_old_path = False
        for row_idx in range(rows_total):
            old_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_OLD_PATH).strip()
            if old_path:
                has_old_path = True
                break
        
        if not has_old_path:
            wx.MessageBox(translate("message_no_preview_items"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        
        # 操作级历史记录：捕获 before_grid 快照
        if operation_type == "rename":
            self._begin_op_history(OP_TYPE_RENAME_PREVIEW, 1)
        elif operation_type == "move":
            self._begin_op_history(OP_TYPE_MOVE_PREVIEW, 2)
        else:
            self._begin_op_history(OP_TYPE_COPY_PREVIEW, 3)
        # 禁用控件
        self.disable_controls_during_operation()
        # 创建worker并执行预览
        # Preview 不再自动执行 Apply：不修改任何行的 Old/New Path；
        # 对 New Path 为空的行按"未设置新路径"处理（详见 Note 13.0）
        if operation_type == "copy":
            worker = tfo_CopyWorker(self, worker_mode=WorkerMode.PREVIEW)
        else:
            is_rename = (operation_type == "rename")
            worker = tfo_RenameMoveWorker(self, is_rename=is_rename, worker_mode=WorkerMode.PREVIEW)
        worker.start()
        # 启动进度检查定时器
        self.movecopy_progress_timer = wx.Timer(self.get_parent_window())
        self.get_parent_window().Bind(wx.EVT_TIMER, self.check_movecopy_progress, self.movecopy_progress_timer)
        self.movecopy_progress_timer.Start(100)

    """预览压缩结果"""
    def on_preview_zip(self, event):
        rows_total = self.file_grid.GetNumberRows()
        count_total = 0
        for row_idx in range(rows_total):
            old_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_OLD_PATH).strip()
            if old_path:
                count_total += 1
        if count_total == 0:
            wx.MessageBox(translate("message_no_preview_items"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        
        # 操作级历史记录：捕获 before_grid 快照
        self._begin_op_history(OP_TYPE_ZIP_PREVIEW, 4)
        # 禁用相关控件，显示终止按钮
        self.disable_controls_during_operation()
        self.btn_preview_stop0502.Enable()
        self.tab05.Layout()
        
        # 获取压缩选项（与 Execute 一致：尊重目标路径与用户填写的非空新路径）
        use_old_path = True
        use_match_name = self.radio_zip_matchname05.GetValue()
        file_conflict_method = self.get_combo_box_method(self.combo_file_conflict0502, self.conflict_method_mapping)
        dir_conflict_method = self.get_combo_box_method(self.combo_dir_conflict0502, self.conflict_method_mapping)
        target_path = self.input_zip_target05.GetValue().strip() or None
        
        # 创建并启动压缩工作线程（预览模式）
        self.zip_worker = tfo_ZipWorker(self, use_old_path, use_match_name, 
                                   target_path, file_conflict_method, dir_conflict_method, 
                                   worker_mode=WorkerMode.PREVIEW)
        self.zip_worker.start()
        
        # 启动进度检查定时器
        self.zip_progress_timer = wx.Timer(self.get_parent_window())
        self.get_parent_window().Bind(wx.EVT_TIMER, self.check_zip_progress, self.zip_progress_timer)
        self.zip_progress_timer.Start(100)  # 每100毫秒检查一次

    """预览删除结果"""
    def on_preview_delete(self, event):
        """预览删除结果功能"""
        delete_original = self.radio_delete_target_old07.GetValue()
        # 检查是否有需要处理的项目
        rows_total = self.file_grid.GetNumberRows()
        count_total = 0
        for row_idx in range(rows_total):
            if delete_original:
                check_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_OLD_PATH).strip()
            else:
                check_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_NEW_PATH).strip()
            if check_path:
                count_total += 1
        if count_total == 0:
            wx.MessageBox(translate("message_no_preview_items"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        
        # 禁用相关控件，显示终止按钮
        self.disable_controls_during_operation()
        self.btn_preview_stop0702.Enable()
        self.tab07.Layout()
        
        # 使用删除目标选择
        delete_original = self.radio_delete_target_old07.GetValue()
        delete_filter = self._get_delete_filter_key()
        
        # 获取过滤参数（复制自on_execute_delete函数）
        filter_params = {}
        filter_key = delete_filter
        if filter_key in ["name_contains", "name_not_contains"]:
            filter_params["text"] = self.txt_filename_filter07.GetValue().strip()
        elif filter_key in ["size_less_than", "size_greater_than", "size_between"]:
            try:
                size_min_str = self.txt_size_min07.GetValue().strip()
                size_max_str = self.txt_size_max07.GetValue().strip()
                
                unit = self.combo_size_unit07.GetValue()
                unit_multiplier = {
                    "B": 1,
                    "KB": 1024,
                    "MB": 1024 * 1024,
                    "GB": 1024 * 1024 * 1024
                }
                
                if unit not in unit_multiplier:
                    wx.MessageBox(translate("message_invalid_size_unit"), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
                    self.restore_controls_after_operation()
                    return
                
                if filter_key == "size_less_than":
                    if size_min_str:
                        try:
                            filter_params["size_max"] = float(size_min_str) * unit_multiplier[unit]
                        except ValueError:
                            wx.MessageBox(translate("message_invalid_size_input"), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
                            self.restore_controls_after_operation()
                            return
                    else:
                        filter_params["size_max"] = 0
                elif filter_key == "size_greater_than":
                    if size_min_str:
                        try:
                            filter_params["size_min"] = float(size_min_str) * unit_multiplier[unit]
                        except ValueError:
                            wx.MessageBox(translate("message_invalid_size_input"), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
                            self.restore_controls_after_operation()
                            return
                    else:
                        filter_params["size_min"] = 0
                elif filter_key == "size_between":
                    if size_min_str:
                        try:
                            filter_params["size_min"] = float(size_min_str) * unit_multiplier[unit]
                        except ValueError:
                            wx.MessageBox(translate("message_invalid_size_input"), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
                            self.restore_controls_after_operation()
                            return
                    else:
                        filter_params["size_min"] = 0
                    
                    if size_max_str:
                        try:
                            filter_params["size_max"] = float(size_max_str) * unit_multiplier[unit]
                        except ValueError:
                            wx.MessageBox(translate("message_invalid_size_input"), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
                            self.restore_controls_after_operation()
                            return
                    else:
                        filter_params["size_max"] = float('inf')
            except Exception as e:
                wx.MessageBox(translate("message_size_error", error=str(e)), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
                self.restore_controls_after_operation()
                return
        elif filter_key in ["create_time_before", "modify_time_before"]:
            # 早于：只使用结束时间
            date_to = self.date_to07.GetValue()
            time_to = self.time_to07.GetValue()
            dt_to = datetime.datetime(date_to.year, date_to.month + 1, date_to.day, time_to.hour, time_to.minute, time_to.second)  # wx.DateTime.GetMonth() returns 0-11, Python datetime expects 1-12
            filter_params["date_to"] = dt_to
        elif filter_key in ["create_time_after", "modify_time_after"]:
            # 晚于：只使用开始时间
            date_from = self.date_from07.GetValue()
            time_from = self.time_from07.GetValue()
            dt_from = datetime.datetime(date_from.year, date_from.month + 1, date_from.day, time_from.hour, time_from.minute, time_from.second)  # wx.DateTime.GetMonth() returns 0-11, Python datetime expects 1-12
            filter_params["date_from"] = dt_from
        elif filter_key in ["create_time_between", "modify_time_between"]:
            # 介于之间：使用开始和结束时间
            date_from = self.date_from07.GetValue()
            time_from = self.time_from07.GetValue()
            dt_from = datetime.datetime(date_from.year, date_from.month + 1, date_from.day, time_from.hour, time_from.minute, time_from.second)  # wx.DateTime.GetMonth() returns 0-11, Python datetime expects 1-12
            date_to = self.date_to07.GetValue()
            time_to = self.time_to07.GetValue()
            dt_to = datetime.datetime(date_to.year, date_to.month + 1, date_to.day, time_to.hour, time_to.minute, time_to.second)  # wx.DateTime.GetMonth() returns 0-11, Python datetime expects 1-12
            filter_params["date_from"] = dt_from
            filter_params["date_to"] = dt_to
        
        
        # 操作级历史记录：捕获 before_grid 快照
        self._begin_op_history(OP_TYPE_DELETE_PREVIEW, 6)
        paths_info = self._collect_delete_paths_info(delete_original)
        self.delete_worker = tfo_DeleteWorker(self, delete_original, paths_info, 
                                         worker_mode=WorkerMode.PREVIEW,
                                         delete_filter=delete_filter, filter_params=filter_params)
        self.delete_worker.start()
        
        # 启动进度检查定时器
        self.delete_progress_timer = wx.Timer(self.get_parent_window())
        self.get_parent_window().Bind(wx.EVT_TIMER, self.check_delete_progress, self.delete_progress_timer)
        self.delete_progress_timer.Start(100)

    """预览去重结果"""
    def on_preview_duplicate(self, event):
        """预览去重结果功能"""
        # 检查是否有需要处理的项目
        rows_total = self.file_grid.GetNumberRows()
        count_total = 0
        for row_idx in range(rows_total):
            old_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_OLD_PATH).strip()
            if old_path:
                count_total += 1
        if count_total == 0:
            wx.MessageBox(translate("message_no_preview_items"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        # 操作级历史记录：捕获 before_grid 快照
        self._begin_op_history(OP_TYPE_DUPLICATE_PREVIEW, 7)
        self.disable_controls_during_operation()
        self.btn_preview_stop0802.Enable()
        self.tab08.Layout()
        
        # 获取去重选项
        algorithm = self.get_combo_box_method(self.combo_duplicate_algorithm08, self.duplicate_algorithm_mapping)
        rule = self.get_combo_box_method(self.combo_duplicate_rule08, self.duplicate_rule_mapping)
        
        self.duplicate_worker = tfo_DuplicateWorker(self, algorithm, rule, 
                                               worker_mode=WorkerMode.PREVIEW)
        self.duplicate_worker.start()
        
        # 启动进度检查定时器
        self.duplicate_progress_timer = wx.Timer(self.get_parent_window())
        self.get_parent_window().Bind(wx.EVT_TIMER, self.check_duplicate_progress, self.duplicate_progress_timer)
        self.duplicate_progress_timer.Start(100)

    # ================================================================
    #  操作级撤销/重做菜单处理
    # ================================================================

    def _create_tool_menu_bar(self):
        """创建编辑菜单（含撤销/重做项），供插入到主框架菜单栏

        在 _build_interface() 末尾调用，仅创建 wx.Menu 对象（不创建 MenuBar）。
        嵌入式模式：bind_menu_events() 将此菜单插入到主框架的 _main_menubar
        独立窗口模式：show_interface() 创建独立 MenuBar 并设置到 frame
        """
        self._edit_menu = wx.Menu()
        self.menu_item_undo = self._edit_menu.Append(
            wx.ID_ANY, translate('menu_undo_op'))
        self.menu_item_redo = self._edit_menu.Append(
            wx.ID_ANY, translate('menu_redo_op'))
        # 重置菜单项：重置所有输入为初始值并清空Grid表格
        self._edit_menu.AppendSeparator()
        self.menu_item_reset = self._edit_menu.Append(
            wx.ID_ANY, translate('menu_reset'))
        # 初始更新菜单项状态
        self._update_undo_redo_menu()

    def get_menu_bar(self):
        """主框架调用此方法获取子工具的菜单栏

        返回 None 表示不替换主框架的菜单栏，而是通过 bind_menu_events()
        在主框架的 _main_menubar 上插入"编辑"菜单。
        独立窗口模式下返回包含主框架菜单+编辑菜单的完整 MenuBar。
        """
        return None

    def bind_menu_events(self, main_frame):
        """主框架调用此方法绑定菜单事件（嵌入式模式）

        在主框架的 _main_menubar 上插入"编辑"菜单（在"文件"菜单之后），
        并绑定撤销/重做事件到主框架窗口。

        Args:
            main_frame: 主框架 wx.Frame 实例
        """
        if not hasattr(self, '_edit_menu') or not main_frame:
            return
        main_menubar = main_frame.GetMenuBar()
        if not main_menubar:
            return
        # 检查是否已插入（防止重复插入）
        for i in range(main_menubar.GetMenuCount()):
            if main_menubar.GetMenu(i) is self._edit_menu:
                return
        # 在"文件"菜单后（索引1）插入"编辑"菜单
        insert_pos = 1
        # 找到"文件"菜单的位置
        from tfp_utils.tfp_i18n_manager import translate as main_translate
        file_menu_title = main_translate("menu_file")
        for i in range(main_menubar.GetMenuCount()):
            if main_menubar.GetMenuLabel(i) == file_menu_title:
                insert_pos = i + 1
                break
        main_menubar.Insert(insert_pos, self._edit_menu, translate("menu_edit"))
        # 绑定菜单事件
        main_frame.Bind(wx.EVT_MENU, self._on_undo_menu, self.menu_item_undo)
        main_frame.Bind(wx.EVT_MENU, self._on_redo_menu, self.menu_item_redo)
        main_frame.Bind(wx.EVT_MENU, self._on_reset_menu, self.menu_item_reset)
        main_frame.Bind(wx.EVT_MENU_OPEN, self._on_menu_open)
        self._update_undo_redo_menu()

    def unbind_menu_events(self, main_frame):
        """主框架调用此方法清理菜单扩展（切回主页或切换工具时）

        从主框架的 _main_menubar 上移除"编辑"菜单，并解绑事件。

        Args:
            main_frame: 主框架 wx.Frame 实例
        """
        if not hasattr(self, '_edit_menu') or not main_frame:
            return
        main_menubar = main_frame.GetMenuBar()
        if not main_menubar:
            return
        # 找到并移除"编辑"菜单
        edit_menu_title = translate("menu_edit")
        for i in range(main_menubar.GetMenuCount()):
            if main_menubar.GetMenu(i) is self._edit_menu:
                main_menubar.Remove(i)
                break
        # 解绑事件
        try:
            main_frame.Unbind(wx.EVT_MENU, self.menu_item_undo)
            main_frame.Unbind(wx.EVT_MENU, self.menu_item_redo)
            main_frame.Unbind(wx.EVT_MENU, self.menu_item_reset)
            main_frame.Unbind(wx.EVT_MENU_OPEN, handler=self._on_menu_open)
        except Exception:
            pass

    def _on_menu_open(self, event):
        """菜单打开前动态更新撤销/重做菜单项的文本和启用状态"""
        if hasattr(self, 'menu_item_undo'):
            self._update_undo_redo_menu()
        event.Skip()

    def _on_undo_menu(self, event):
        """撤销菜单项点击：撤销最近一步操作"""
        if not self._op_history_manager.can_undo() or self.is_operating:
            return
        self.disable_controls_during_operation()
        try:
            self.status_bar.SetStatusText(translate("undo_op_in_progress"), 0)
            wx.Yield()
            # 获取将被撤销的操作信息（用于状态栏提示）
            history = self._op_history_manager.get_undo_history()
            op_entry = history[0] if history else None
            self._op_history_manager.undo(self)
            # 状态栏显示撤销结果
            if op_entry:
                msg = translate("undo_op_done").format(
                    op_label=op_entry.op_label, op_summary=op_entry.op_summary)
                # 执行类操作撤销后，控件参数与Grid数据可能不一致，追加提示
                if op_entry.is_execute_op():
                    msg += " " + translate("undo_op_ctrl_hint")
                self.status_bar.SetStatusText(msg, 0)
            else:
                self.status_bar.SetStatusText(translate("status_ready"), 0)
        except Exception as e:
            log_error(f"撤销操作失败: {e}")
            self.status_bar.SetStatusText(f"撤销失败: {e}", 0)
        finally:
            self.restore_controls_after_operation()

    def _on_redo_menu(self, event):
        """重做菜单项点击：重做最近一步撤销的操作"""
        if not self._op_history_manager.can_redo() or self.is_operating:
            return
        self.disable_controls_during_operation()
        try:
            self.status_bar.SetStatusText(translate("redo_op_in_progress"), 0)
            wx.Yield()
            # 获取将被重做的操作信息（用于状态栏提示）
            history = self._op_history_manager.get_redo_history()
            op_entry = history[-1] if history else None
            self._op_history_manager.redo(self)
            # 状态栏显示重做结果
            if op_entry:
                msg = translate("redo_op_done").format(
                    op_label=op_entry.op_label, op_summary=op_entry.op_summary)
                self.status_bar.SetStatusText(msg, 0)
            else:
                self.status_bar.SetStatusText(translate("status_ready"), 0)
        except Exception as e:
            log_error(f"重做操作失败: {e}")
            self.status_bar.SetStatusText(f"重做失败: {e}", 0)
        finally:
            self.restore_controls_after_operation()

    def _on_reset_menu(self, event):
        """重置菜单项点击：将所有输入重置为初始值并清空Grid表格"""
        if self.is_operating:
            return
        # 二次确认：清空表格属于破坏性操作，防止误触
        dlg = wx.MessageDialog(
            self.get_parent_window(),
            translate("menu_reset_confirm"),
            translate("dialog_title_warning"),
            wx.YES_NO | wx.ICON_WARNING
        )
        dlg.SetYesNoLabels(translate("dialog_btn_ok"), translate("dialog_btn_cancel"))
        result = dlg.ShowModal()
        dlg.Destroy()
        if result != wx.ID_YES:
            return
        try:
            self._reset_all_inputs()
            self.status_bar.SetStatusText(translate("menu_reset_done"), 0)
            self.status_bar.SetStatusText("", 1)
        except Exception as e:
            log_error(f"重置失败: {e}")
            wx.MessageBox(translate("menu_reset_failed", error=str(e)), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)

    def _reset_all_inputs(self):
        """将所有输入重置为初始值并清空Grid表格

        与工具启动时的默认状态保持一致：
        - 各Tab的输入控件恢复默认值
        - 路径输入框恢复系统默认前景色（空路径不再标红）
        - 应用按钮恢复禁用状态
        - Grid表格清空为20个空行
        - 清空操作级撤销/重做历史与Grid单元格级撤销历史
        """
        default_color = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)

        # ---- Tab01 搜索 ----
        self.input_search_path01.SetValue("")
        self.input_match_text01.SetValue("")
        self.combo_match_method01.SetSelection(0)
        self.check_search_recursive01.SetValue(True)
        self.check_search_hidden01.SetValue(False)
        self.check_output_dirname01.SetValue(False)
        self.check_output_filename01.SetValue(True)
        self.label_match_text01.SetLabel(translate("label_match_text_count", count=0))
        # 同步匹配方法成员变量
        self.prev_match_method_key = self.get_combo_box_method(self.combo_match_method01, self.match_method_mapping)

        # ---- Tab02 重命名 ----
        self.combo_naming_method02.SetSelection(0)
        self.combo_file_conflict0202.SetSelection(0)
        self.combo_dir_conflict0202.SetSelection(0)
        self.input_naming_position02.SetValue("")
        self.input_length02.SetValue("")
        self.input_naming_oldtext.SetValue("")
        self.input_naming_text02.SetValue("")
        # 编号参数恢复默认：位置=文件名末尾（Before 不勾选），分组=不分组
        self.check_number_pos_start02.SetValue(False)
        self.radio_number_scope_none02.SetValue(True)
        self.label_number_position02.Hide()
        self.check_number_pos_start02.Hide()
        self.label_number_scope02.Hide()
        self.radio_number_scope_none02.Hide()
        self.radio_number_scope_dir02.Hide()
        self.radio_number_scope_match02.Hide()
        # 合并方式子模式恢复默认：替换=按文本、前后缀=后缀、大小写=全部大写
        self.radio_replace_mode_text02.SetValue(True)
        self.radio_affix_mode_suffix02.SetValue(True)
        self.radio_case_mode_upper02.SetValue(True)
        self.radio_mp3_artist_first02.SetValue(True)
        for _sub_radio in (self.radio_replace_mode_text02, self.radio_replace_mode_position02,
                           self.radio_affix_mode_suffix02, self.radio_affix_mode_prefix02,
                           self.radio_case_mode_upper02, self.radio_case_mode_lower02,
                           self.radio_case_mode_camel02, self.radio_case_mode_capitalize02,
                           self.radio_mp3_artist_first02, self.radio_mp3_title_first02,
                           self.radio_mp3_title_only02):
            _sub_radio.Hide()
        # 重置为"原来的名字"时隐藏所有相关控件
        self.label_naming_position02.Hide()
        self.input_naming_position02.Hide()
        self.label_length02.Hide()
        self.input_length02.Hide()
        self.label_naming_oldtext02.Hide()
        self.input_naming_oldtext.Hide()
        self.label_text02.Hide()
        self.input_naming_text02.Hide()
        self.help_rename02.Hide()
        self.label_text02.SetLabel(translate("label_text"))

        # ---- Tab03 移动 ----
        self.input_source_path03.SetValue("")
        self.input_dest_path03.SetValue("")
        self.combo_file_conflict0302.SetSelection(0)
        self.combo_dir_conflict0302.SetSelection(0)
        self.combo_create_folder03.SetSelection(0)

        # ---- Tab04 复制 ----
        self.input_source_path04.SetValue("")
        self.input_dest_path04.SetValue("")
        self.combo_file_conflict0402.SetSelection(0)
        self.combo_dir_conflict0402.SetSelection(0)
        self.combo_create_folder04.SetSelection(0)

        # ---- Tab05 压缩 ----
        self.radio_zip_foldername05.SetValue(True)
        self.radio_zip_matchname05.SetValue(False)
        self.input_zip_target05.SetValue("")
        self.combo_file_conflict0502.SetSelection(1)
        self.combo_dir_conflict0502.SetSelection(2)

        # ---- Tab06 解压 ----
        self.radio_unzip_package06.SetValue(True)
        self.radio_unzip_match06.SetValue(False)
        self.input_unzip_target06.SetValue("")
        self.combo_file_conflict0602.SetSelection(1)
        self.combo_dir_conflict0602.SetSelection(2)

        # ---- Tab07 删除 ----
        self.combo_delete_filter07.SetSelection(0)
        self.txt_filename_filter07.SetValue("")
        self.txt_size_min07.SetValue("")
        self.txt_size_max07.SetValue("")
        self.combo_size_unit07.SetSelection(2)
        self.radio_delete_target_old07.SetValue(True)
        self.radio_delete_target_new07.SetValue(False)
        # 隐藏所有过滤输入字段
        self.label_text_filter07.Hide()
        self.txt_filename_filter07.Hide()
        self.label_size_min07.Hide()
        self.txt_size_min07.Hide()
        self.combo_size_unit07.Hide()
        self.label_size_max07.Hide()
        self.txt_size_max07.Hide()
        self.label_date_from07.Hide()
        self.date_from07.Hide()
        self.time_from07.Hide()
        self.label_date_to07.Hide()
        self.date_to07.Hide()
        self.time_to07.Hide()

        # ---- Tab08 去重 ----
        self.combo_duplicate_algorithm08.SetSelection(0)
        self.combo_duplicate_rule08.SetSelection(0)
        self.radio_delete_recycle08.SetValue(True)

        # ---- 路径输入框恢复默认颜色（与工具启动时一致） ----
        self.input_search_path01.SetForegroundColour(default_color)
        self.input_source_path03.SetForegroundColour(default_color)
        self.input_source_path04.SetForegroundColour(default_color)
        self.input_dest_path03.SetForegroundColour(default_color)
        self.input_dest_path04.SetForegroundColour(default_color)
        self.input_zip_target05.SetForegroundColour(default_color)
        self.input_unzip_target06.SetForegroundColour(default_color)

        # ---- 应用按钮恢复禁用状态 ----
        self.btn_apply_search01.Enable(False)
        self.btn_apply_path03.Enable(False)
        self.btn_apply_path04.Enable(False)

        # ---- 状态成员变量重置 ----
        self.search_folder = ""
        self.unique_ordered_match_list = []

        # ---- 清空Grid表格（内部会清空Grid单元格级撤销历史） ----
        self.file_grid.on_clear_adjust_table(20)
        self.file_grid.set_col_sort_indicator()

        # ---- 清空操作级撤销/重做历史 ----
        self._op_history_manager.clear_all()
        self._current_op_entry = None
        self._update_undo_redo_menu()

        # ---- 刷新 ----
        self.input_search_path01.Refresh()
        self.input_source_path03.Refresh()
        self.input_source_path04.Refresh()
        self.input_dest_path03.Refresh()
        self.input_dest_path04.Refresh()
        self.input_zip_target05.Refresh()
        self.input_unzip_target06.Refresh()
        self.tab02.Layout()
        self.tab07.Layout()
        self.panel.Layout()
        self.layout_frame()

    def _update_undo_redo_menu(self):
        """更新撤销/重做菜单项的文本和启用状态

        - 栈非空时显示操作名和摘要（如"撤销操作 (重命名/执行 — 5项操作)"）
        - 栈空时仅显示基础文本（如"撤销操作"）
        - 操作执行中（is_operating）时禁用
        - 不设置快捷键（Ctrl+Z/Y属于单元格级撤销/重做）
        """
        if not hasattr(self, 'menu_item_undo') or not hasattr(self, 'menu_item_redo'):
            return
        can_undo = self._op_history_manager.can_undo() and not self.is_operating
        can_redo = self._op_history_manager.can_redo() and not self.is_operating
        # 重置菜单项：操作执行中禁用，其余时间可用
        if hasattr(self, 'menu_item_reset'):
            self.menu_item_reset.Enable(not self.is_operating)
        # 动态显示操作名和摘要
        if can_undo:
            history = self._op_history_manager.get_undo_history()
            if history:
                entry = history[0]
                if entry.op_summary:
                    undo_label = f"{translate('menu_undo_op')} ({entry.op_label} — {entry.op_summary})"
                else:
                    undo_label = f"{translate('menu_undo_op')} ({entry.op_label})"
            else:
                undo_label = translate('menu_undo_op')
        else:
            undo_label = translate('menu_undo_op')
        if can_redo:
            history = self._op_history_manager.get_redo_history()
            if history:
                entry = history[-1]
                if entry.op_summary:
                    redo_label = f"{translate('menu_redo_op')} ({entry.op_label} — {entry.op_summary})"
                else:
                    redo_label = f"{translate('menu_redo_op')} ({entry.op_label})"
            else:
                redo_label = translate('menu_redo_op')
        else:
            redo_label = translate('menu_redo_op')
        self.menu_item_undo.SetItemLabel(undo_label)
        self.menu_item_redo.SetItemLabel(redo_label)
        self.menu_item_undo.Enable(can_undo)
        self.menu_item_redo.Enable(can_redo)

    def _begin_op_history(self, op_type, tab_index):
        """开始一个操作级历史记录

        在按钮处理函数真正开始执行后调用（参数校验通过后）。
        若存在未提交的旧 entry（上次操作未正常 commit/abort），先 abort 之。
        """
        if self._current_op_entry is not None:
            self._abort_op_history()
        try:
            self._current_op_entry = self._op_history_manager.begin_operation(op_type, tab_index, self)
            return self._current_op_entry
        except Exception as e:
            log_error(f"开始操作历史记录失败: {e}")
            self._current_op_entry = None
            return None

    def _commit_op_history(self):
        """提交当前操作级历史记录

        在按钮处理函数操作完成后调用
        """
        try:
            if self._current_op_entry is not None:
                self._op_history_manager.commit_operation(self._current_op_entry, self)
            self._current_op_entry = None
            self._update_undo_redo_menu()
        except Exception as e:
            log_error(f"提交操作历史记录失败: {e}")
            self._current_op_entry = None

    def _abort_op_history(self):
        """中止当前操作级历史记录

        在按钮处理函数因参数无效而提前返回时调用
        """
        try:
            if self._current_op_entry is not None:
                self._op_history_manager.abort_operation(self._current_op_entry)
            self._current_op_entry = None
        except Exception as e:
            log_error(f"中止操作历史记录失败: {e}")
            self._current_op_entry = None

    """在执行操作期间禁用相关控件"""
    def disable_controls_during_operation(self):
        log_debug("禁用控件 - 操作开始")
        self.is_operating = True
        # 方案6/3：进入网格写回节流 + 当前执行行高亮模式（进度更直观、且不被逐行写满事件队列）
        if hasattr(self, 'file_grid'):
            self.file_grid.begin_operation_progress()
        self.btn_states = {
            'apply_search': self.btn_apply_search01.IsEnabled(),
            'apply_naming': self.btn_apply_naming02.IsEnabled(),
            'apply_path': self.btn_apply_path03.IsEnabled(),
            'apply_zip': self.btn_apply_zip05.IsEnabled(),
            'apply_unzip': self.btn_apply_unzip06.IsEnabled(),
            'apply_delete': self.btn_apply_delete07.IsEnabled(),
            'apply_duplicate': self.btn_apply_duplicate08.IsEnabled(),
            'import_table': self.btn_import_grid01.IsEnabled(),
            'export_table': self.btn_export_grid01.IsEnabled(),
            'execute_naming': self.btn_execute_rename02.IsEnabled(),
            'execute_move': self.btn_execute_move03.IsEnabled(),
            'execute_copy': self.btn_execute_copy04.IsEnabled(),
            'execute_zip': self.btn_execute_zip05.IsEnabled(),
            'execute_unzip': self.btn_execute_unzip06.IsEnabled(),
            'execute_delete': self.btn_execute_delete07.IsEnabled(),
            'execute_duplicate': self.btn_execute_duplicate08.IsEnabled(),
        }
        self.preview_btn_states = {
            'preview_02': self.btn_preview_stop0202.IsEnabled(),
            'preview_03': self.btn_preview_stop0302.IsEnabled(),
            'preview_04': self.btn_preview_stop0402.IsEnabled(),
            'preview_05': self.btn_preview_stop0502.IsEnabled(),
            'preview_06': self.btn_preview_stop0602.IsEnabled(),
            'preview_07': self.btn_preview_stop0702.IsEnabled(),
            'preview_08': self.btn_preview_stop0802.IsEnabled(),
        }
        self.tab05_input_states = {
            'radio_zip_foldername': self.radio_zip_foldername05.IsEnabled(),
            'radio_zip_matchname': self.radio_zip_matchname05.IsEnabled(),
            'combo_file_conflict': self.combo_file_conflict0502.IsEnabled(),
            'combo_dir_conflict': self.combo_dir_conflict0502.IsEnabled(),
            'input_zip_target': self.input_zip_target05.IsEnabled(),
            'btn_zip_target_browse': self.btn_zip_target_browse05.IsEnabled(),
        }
        self.tab06_input_states = {
            'radio_unzip_package': self.radio_unzip_package06.IsEnabled(),
            'radio_unzip_match': self.radio_unzip_match06.IsEnabled(),
            'combo_file_conflict': self.combo_file_conflict0602.IsEnabled(),
            'combo_dir_conflict': self.combo_dir_conflict0602.IsEnabled(),
            'input_unzip_target': self.input_unzip_target06.IsEnabled(),
            'btn_unzip_target_browse': self.btn_unzip_target_browse06.IsEnabled(),
        }
        self.tab07_input_states = {
            'combo_delete_filter': self.combo_delete_filter07.IsEnabled(),
            'txt_filename_filter': self.txt_filename_filter07.IsEnabled(),
            'txt_size_min': self.txt_size_min07.IsEnabled(),
            'combo_size_unit': self.combo_size_unit07.IsEnabled(),
            'txt_size_max': self.txt_size_max07.IsEnabled(),
            'date_from': self.date_from07.IsEnabled(),
            'time_from': self.time_from07.IsEnabled(),
            'date_to': self.date_to07.IsEnabled(),
            'time_to': self.time_to07.IsEnabled(),
            'help_delete_filter': self.help_delete_filter07.IsEnabled(),
            'radio_delete_target_old': self.radio_delete_target_old07.IsEnabled(),
            'radio_delete_target_new': self.radio_delete_target_new07.IsEnabled(),
        }
        self.tab08_input_states = {
            'combo_duplicate_algorithm': self.combo_duplicate_algorithm08.IsEnabled(),
            'combo_duplicate_rule': self.combo_duplicate_rule08.IsEnabled(),
            'radio_delete_recycle': self.radio_delete_recycle08.IsEnabled(),
        }
        self.btn_apply_search01.Enable(False)
        self.btn_apply_naming02.Enable(False)
        self.btn_apply_path03.Enable(False)
        self.btn_apply_path04.Enable(False)
        self.btn_apply_zip05.Enable(False)
        self.btn_apply_unzip06.Enable(False)
        self.btn_apply_delete07.Enable(False)
        self.btn_apply_duplicate08.Enable(False)
        self.btn_import_grid01.Enable(False)
        self.btn_export_grid01.Enable(False)
        self.btn_execute_rename02.Enable(False)
        self.btn_execute_move03.Enable(False)
        self.btn_execute_copy04.Enable(False)
        self.btn_execute_zip05.Enable(False)
        self.btn_execute_unzip06.Enable(False)
        self.btn_execute_delete07.Enable(False)
        self.btn_execute_duplicate08.Enable(False)
        # 禁用操作级撤销/重做菜单项
        if hasattr(self, 'menu_item_undo'):
            self.menu_item_undo.Enable(False)
            self.menu_item_redo.Enable(False)
        # 禁用重置菜单项
        if hasattr(self, 'menu_item_reset'):
            self.menu_item_reset.Enable(False)
        self.file_grid.EnableEditing(False)
        self.file_grid.Enable(False)
        self.notebook.Enable(False)
        self.status_bar.SetStatusText(translate("status_executing_operation"), 0)
        wx.Yield()

    """在执行操作后恢复相关控件"""
    def restore_controls_after_operation(self):
        log_debug("恢复控件 - 操作结束")
        self.is_operating = False
        # 方案6/3：同步落盘全部挂起写入并清除当前行高亮（完成后统计/展示依赖网格最新内容）
        if hasattr(self, 'file_grid'):
            self.file_grid.end_operation_progress()
        if hasattr(self, 'btn_states'):
            self.btn_apply_search01.Enable(self.btn_states['apply_search'])
            self.btn_apply_naming02.Enable(self.btn_states['apply_naming'])
            self.btn_apply_path03.Enable(self.btn_states['apply_path'])
            self.btn_apply_path04.Enable(self.btn_states['apply_path'])
            self.btn_apply_zip05.Enable(self.btn_states['apply_zip'])
            self.btn_apply_unzip06.Enable(self.btn_states['apply_unzip'])
            self.btn_apply_delete07.Enable(self.btn_states['apply_delete'])
            self.btn_apply_duplicate08.Enable(self.btn_states['apply_duplicate'])
            self.btn_import_grid01.Enable(self.btn_states['import_table'])
            self.btn_export_grid01.Enable(self.btn_states['export_table'])
            self.btn_execute_rename02.Enable(self.btn_states['execute_naming'])
            self.btn_execute_move03.Enable(self.btn_states['execute_move'])
            self.btn_execute_copy04.Enable(self.btn_states['execute_copy'])
            self.btn_execute_zip05.Enable(self.btn_states['execute_zip'])
            self.btn_execute_unzip06.Enable(self.btn_states['execute_unzip'])
            self.btn_execute_delete07.Enable(self.btn_states['execute_delete'])
            self.btn_execute_duplicate08.Enable(self.btn_states['execute_duplicate'])
        if hasattr(self, 'preview_btn_states'):
            self.btn_preview_stop0202.Enable(self.preview_btn_states['preview_02'])
            self.btn_preview_stop0302.Enable(self.preview_btn_states['preview_03'])
            self.btn_preview_stop0402.Enable(self.preview_btn_states['preview_04'])
            self.btn_preview_stop0502.Enable(self.preview_btn_states['preview_05'])
            self.btn_preview_stop0602.Enable(self.preview_btn_states['preview_06'])
            self.btn_preview_stop0702.Enable(self.preview_btn_states['preview_07'])
            self.btn_preview_stop0802.Enable(self.preview_btn_states['preview_08'])
        if hasattr(self, 'tab05_input_states'):
            self.radio_zip_foldername05.Enable(self.tab05_input_states['radio_zip_foldername'])
            self.radio_zip_matchname05.Enable(self.tab05_input_states['radio_zip_matchname'])
            self.combo_file_conflict0502.Enable(self.tab05_input_states['combo_file_conflict'])
            self.combo_dir_conflict0502.Enable(self.tab05_input_states['combo_dir_conflict'])
            self.input_zip_target05.Enable(self.tab05_input_states['input_zip_target'])
            self.btn_zip_target_browse05.Enable(self.tab05_input_states['btn_zip_target_browse'])
        if hasattr(self, 'tab06_input_states'):
            self.radio_unzip_package06.Enable(self.tab06_input_states['radio_unzip_package'])
            self.radio_unzip_match06.Enable(self.tab06_input_states['radio_unzip_match'])
            self.combo_file_conflict0602.Enable(self.tab06_input_states['combo_file_conflict'])
            self.combo_dir_conflict0602.Enable(self.tab06_input_states['combo_dir_conflict'])
            self.input_unzip_target06.Enable(self.tab06_input_states['input_unzip_target'])
            self.btn_unzip_target_browse06.Enable(self.tab06_input_states['btn_unzip_target_browse'])
        if hasattr(self, 'tab07_input_states'):
            self.combo_delete_filter07.Enable(self.tab07_input_states['combo_delete_filter'])
            self.txt_filename_filter07.Enable(self.tab07_input_states['txt_filename_filter'])
            self.txt_size_min07.Enable(self.tab07_input_states['txt_size_min'])
            self.combo_size_unit07.Enable(self.tab07_input_states['combo_size_unit'])
            self.txt_size_max07.Enable(self.tab07_input_states['txt_size_max'])
            self.date_from07.Enable(self.tab07_input_states['date_from'])
            self.time_from07.Enable(self.tab07_input_states['time_from'])
            self.date_to07.Enable(self.tab07_input_states['date_to'])
            self.time_to07.Enable(self.tab07_input_states['time_to'])
            self.help_delete_filter07.Enable(self.tab07_input_states['help_delete_filter'])
            self.radio_delete_target_old07.Enable(self.tab07_input_states['radio_delete_target_old'])
            self.radio_delete_target_new07.Enable(self.tab07_input_states['radio_delete_target_new'])
        if hasattr(self, 'tab08_input_states'):
            self.combo_duplicate_algorithm08.Enable(self.tab08_input_states['combo_duplicate_algorithm'])
            self.combo_duplicate_rule08.Enable(self.tab08_input_states['combo_duplicate_rule'])
            self.radio_delete_recycle08.Enable(self.tab08_input_states['radio_delete_recycle'])
        self.file_grid.Enable(True)
        self.file_grid.EnableEditing(True)
        self.notebook.Enable(True)
        # 提交当前操作级历史记录（捕获 after_grid 快照并推入 undo 栈）
        # 对于同步操作（apply_*）和异步操作（worker 完成后的 check_*_progress）
        # 都会调用 restore_controls_after_operation，所以统一在此提交
        self._commit_op_history()
        # 恢复操作级撤销/重做菜单项状态（根据栈状态）
        self._update_undo_redo_menu()
        wx.Yield()

    """合并目录（用于目录冲突处理中的合并选项）"""
    def merge_directories(self, src_dir, dst_dir, is_move=False, file_conflict="skip"):
        """合并源目录到目标目录

        file_conflict: 目标已存在同名项时按冲突下拉框选择处理
            "skip"=跳过（保留目标原项，规格13.2 默认）, "overwrite"=覆盖
        目录与目录同名时始终递归合并（合并语义）。
        """
        try:
            # 确保目标目录存在
            if not os.path.exists(dst_dir):
                os.makedirs(dst_dir, exist_ok=True)
            # 遍历源目录
            for item in os.listdir(src_dir):
                src_item = os.path.join(src_dir, item)
                dst_item = os.path.join(dst_dir, item)
                if os.path.isdir(src_item) and os.path.isdir(dst_item):
                    # 目录同名：递归合并
                    self.merge_directories(src_item, dst_item, is_move, file_conflict)
                    continue
                if os.path.exists(dst_item):
                    # 目标已存在且非"目录-目录"：按文件冲突策略处理
                    if file_conflict != "overwrite":
                        continue  # 跳过：保留目标原项
                    if os.path.isdir(dst_item):
                        shutil.rmtree(dst_item)
                    else:
                        os.remove(dst_item)
                if os.path.isdir(src_item):
                    if is_move:
                        shutil.move(src_item, dst_item)
                    else:
                        shutil.copytree(src_item, dst_item, symlinks=True)
                else:
                    # 如果是文件，移动或复制
                    if is_move:
                        shutil.move(src_item, dst_item)
                    else:
                        shutil.copy2(src_item, dst_item)
            # 如果是移动操作，删除空源目录
            if is_move and os.path.exists(src_dir):
                try:
                    os.rmdir(src_dir)
                except OSError:
                    pass  # 目录可能不为空（存在被跳过的项），跳过
        except Exception as e:
            log_error(f"合并目录失败: {e}")
            raise Exception(f"Failed to merge directories: {str(e)}")

    """更新状态栏显示进度"""
    def update_status_bar(self, finished, total, ok):
        """更新状态栏显示进度"""
        if total > 0:
            progress = f"{finished}/{total}"
            self.status_bar.SetStatusText(progress, 1)
            self.status_bar.SetStatusText(translate("status_processing", finished=finished, total=total, ok=ok), 0)
            wx.Yield()  # 更新UI

    """应用删除过滤"""
    def on_apply_delete_filter(self, event):
        delete_original = self.radio_delete_target_old07.GetValue()
        self.execute_delete_in_thread(delete_original=delete_original, execute=False)
    
    """删除过滤选项变化时的处理"""
    def on_delete_filter_change(self, event):
        # 隐藏所有输入字段
        self.label_text_filter07.Hide()
        self.txt_filename_filter07.Hide()
        self.label_size_min07.Hide()
        self.txt_size_min07.Hide()
        self.combo_size_unit07.Hide()
        self.label_size_max07.Hide()
        self.txt_size_max07.Hide()
        self.label_date_from07.Hide()
        self.date_from07.Hide()
        self.time_from07.Hide()
        self.label_date_to07.Hide()
        self.date_to07.Hide()
        self.time_to07.Hide()
        
        filter_key = self._get_delete_filter_key()
        
        # 根据选择的选项显示相应的输入字段
        if filter_key == "name_contains":
            # 显示文本输入字段
            self.label_text_filter07.SetLabel(translate("label_contains_text"))
            self.label_text_filter07.Show()
            self.txt_filename_filter07.Show()
        elif filter_key == "name_not_contains":
            # 显示文本输入字段
            self.label_text_filter07.SetLabel(translate("label_not_contains_text"))
            self.label_text_filter07.Show()
            self.txt_filename_filter07.Show()
        elif filter_key == "size_less_than":
            # 显示单个数字输入字段
            self.label_size_min07.Show()
            self.txt_size_min07.Show()
            self.combo_size_unit07.Show()
        elif filter_key == "size_greater_than":
            # 显示单个数字输入字段
            self.label_size_min07.Show()
            self.txt_size_min07.Show()
            self.combo_size_unit07.Show()
        elif filter_key == "size_between":
            # 显示两个数字输入字段
            self.label_size_min07.Show()
            self.txt_size_min07.Show()
            self.label_size_max07.Show()
            self.txt_size_max07.Show()
            self.combo_size_unit07.Show()
        elif filter_key in ["create_time_before", "modify_time_before"]:
            # 显示结束时间输入字段（早于某个时间）
            self.label_date_to07.Show()
            self.date_to07.Show()
            self.time_to07.Show()
        elif filter_key in ["create_time_after", "modify_time_after"]:
            # 显示开始时间输入字段（晚于某个时间）
            self.label_date_from07.Show()
            self.date_from07.Show()
            self.time_from07.Show()
        elif filter_key in ["create_time_between", "modify_time_between"]:
            # 显示两个日期时间输入字段
            self.label_date_from07.Show()
            self.date_from07.Show()
            self.time_from07.Show()
            self.label_date_to07.Show()
            self.date_to07.Show()
            self.time_to07.Show()
        
        # 调整布局
        self.tab07.Layout()
    
    def _get_delete_filter_key(self):
        selection = self.combo_delete_filter07.GetSelection()
        if selection >= 0 and selection in self.delete_filter_mapping:
            return self.delete_filter_mapping[selection]
        return "delete_all"
    
    """删除目标变化时的处理（tab07和tab08联动）"""
    def on_delete_target_change(self, event):
        is_old = self.radio_delete_target_old07.GetValue()
        self.radio_delete_target_old07.SetValue(is_old)
        self.radio_delete_target_new07.SetValue(not is_old)
    
    """notebook页面切换时的处理"""
    def on_notebook_page_changed(self, event):
        # 跳过事件以避免默认行为
        event.Skip()
        
        # 获取当前选中的页面索引
        current_page = self.notebook.GetSelection()
        
        # 获取 sizer_main 中的 notebook 和 moretool_container item
        notebook_item = self.sizer_main.GetItem(self.notebook)
        moretool_item = self.sizer_main.GetItem(self.moretool_container)
        
        # 如果是tab09（索引8），显示moretool_container，隐藏file_grid
        if current_page == 8:
            self.moretool_container.Show()
            self.file_grid.Hide()
            # 设置 notebook 占据 0 比例，moretool_container 占据 1 比例（占用file_grid的空间）
            notebook_item.SetProportion(0)
            moretool_item.SetProportion(1)
            # 容器首次显示后按实际宽度重新给工具卡片描述换行
            wx.CallAfter(self._rewrap_tool_card_descriptions)
        # 如果是tab01-tab08（索引0-7），显示file_grid，隐藏moretool_container
        else:
            self.moretool_container.Hide()
            self.file_grid.Show()
            # 设置 notebook 占据 0 比例，moretool_container 占据 0 比例
            notebook_item.SetProportion(0)
            moretool_item.SetProportion(0)
        
        # 调整布局
        self.panel.Layout()
        self.layout_frame()
    
    def update_combo_boxes_after_language_change(self):
        """在语言切换后更新所有ComboBox的选项"""
        # Tab01: 搜索
        if hasattr(self, 'combo_match_method01'):
            current_selection = self.combo_match_method01.GetSelection()
            self.combo_match_method01.SetItems(translate("combo_match_methods"))
            if current_selection >= 0 and current_selection < len(translate("combo_match_methods")):
                self.combo_match_method01.SetSelection(current_selection)
        # Tab01: 帮助图标的悬停提示与弹窗内容随语言刷新（点击时读取 self.text_match_tip）
        if hasattr(self, 'help_match_method01'):
            self.text_match_tip = translate("tooltip_match_method")
            tip_match01 = wx.ToolTip(self.text_match_tip)
            tip_match01.SetDelay(500)
            tip_match01.SetAutoPop(10*1000)
            self.help_match_method01.SetToolTip(tip_match01)
        
        # Tab02: 重命名
        if hasattr(self, 'combo_naming_method02'):
            current_selection = self.combo_naming_method02.GetSelection()
            self.combo_naming_method02.SetItems(translate("combo_naming_methods"))
            if current_selection >= 0 and current_selection < len(translate("combo_naming_methods")):
                self.combo_naming_method02.SetSelection(current_selection)
        
        if hasattr(self, 'combo_file_conflict0202'):
            current_selection = self.combo_file_conflict0202.GetSelection()
            self.combo_file_conflict0202.SetItems(translate("combo_file_conflict"))
            if current_selection >= 0 and current_selection < len(translate("combo_file_conflict")):
                self.combo_file_conflict0202.SetSelection(current_selection)
        
        if hasattr(self, 'combo_dir_conflict0202'):
            current_selection = self.combo_dir_conflict0202.GetSelection()
            self.combo_dir_conflict0202.SetItems(translate("combo_dir_conflict"))
            if current_selection >= 0 and current_selection < len(translate("combo_dir_conflict")):
                self.combo_dir_conflict0202.SetSelection(current_selection)
        
        # Tab03: 移动
        if hasattr(self, 'combo_file_conflict0302'):
            current_selection = self.combo_file_conflict0302.GetSelection()
            self.combo_file_conflict0302.SetItems(translate("combo_file_conflict"))
            if current_selection >= 0 and current_selection < len(translate("combo_file_conflict")):
                self.combo_file_conflict0302.SetSelection(current_selection)
        
        if hasattr(self, 'combo_dir_conflict0302'):
            current_selection = self.combo_dir_conflict0302.GetSelection()
            self.combo_dir_conflict0302.SetItems(translate("combo_dir_conflict"))
            if current_selection >= 0 and current_selection < len(translate("combo_dir_conflict")):
                self.combo_dir_conflict0302.SetSelection(current_selection)
        
        if hasattr(self, 'combo_create_folder03'):
            current_selection = self.combo_create_folder03.GetSelection()
            self.combo_create_folder03.SetItems(translate("combo_create_folder"))
            if current_selection >= 0 and current_selection < len(translate("combo_create_folder")):
                self.combo_create_folder03.SetSelection(current_selection)
        
        # Tab04: 复制
        if hasattr(self, 'combo_file_conflict0402'):
            current_selection = self.combo_file_conflict0402.GetSelection()
            self.combo_file_conflict0402.SetItems(translate("combo_file_conflict"))
            if current_selection >= 0 and current_selection < len(translate("combo_file_conflict")):
                self.combo_file_conflict0402.SetSelection(current_selection)
        
        if hasattr(self, 'combo_dir_conflict0402'):
            current_selection = self.combo_dir_conflict0402.GetSelection()
            self.combo_dir_conflict0402.SetItems(translate("combo_dir_conflict"))
            if current_selection >= 0 and current_selection < len(translate("combo_dir_conflict")):
                self.combo_dir_conflict0402.SetSelection(current_selection)
        
        if hasattr(self, 'combo_create_folder04'):
            current_selection = self.combo_create_folder04.GetSelection()
            self.combo_create_folder04.SetItems(translate("combo_create_folder"))
            if current_selection >= 0 and current_selection < len(translate("combo_create_folder")):
                self.combo_create_folder04.SetSelection(current_selection)
        
        # Tab05: 压缩
        if hasattr(self, 'combo_file_conflict0502'):
            current_selection = self.combo_file_conflict0502.GetSelection()
            self.combo_file_conflict0502.SetItems(translate("combo_file_conflict"))
            if current_selection >= 0 and current_selection < len(translate("combo_file_conflict")):
                self.combo_file_conflict0502.SetSelection(current_selection)
        
        if hasattr(self, 'combo_dir_conflict0502'):
            current_selection = self.combo_dir_conflict0502.GetSelection()
            self.combo_dir_conflict0502.SetItems(translate("combo_dir_conflict"))
            if current_selection >= 0 and current_selection < len(translate("combo_dir_conflict")):
                self.combo_dir_conflict0502.SetSelection(current_selection)

        # Tab06: 解压
        if hasattr(self, 'combo_file_conflict0602'):
            current_selection = self.combo_file_conflict0602.GetSelection()
            self.combo_file_conflict0602.SetItems(translate("combo_file_conflict"))
            if current_selection >= 0 and current_selection < len(translate("combo_file_conflict")):
                self.combo_file_conflict0602.SetSelection(current_selection)

        if hasattr(self, 'combo_dir_conflict0602'):
            current_selection = self.combo_dir_conflict0602.GetSelection()
            self.combo_dir_conflict0602.SetItems(translate("combo_dir_conflict"))
            if current_selection >= 0 and current_selection < len(translate("combo_dir_conflict")):
                self.combo_dir_conflict0602.SetSelection(current_selection)

        # Tab07: 删除
        if hasattr(self, 'combo_delete_filter07'):
            current_selection = self.combo_delete_filter07.GetSelection()
            self.combo_delete_filter07.SetItems(translate("combo_delete_filters"))
            if current_selection >= 0 and current_selection < len(translate("combo_delete_filters")):
                self.combo_delete_filter07.SetSelection(current_selection)
        
        if hasattr(self, 'combo_size_unit07'):
            current_selection = self.combo_size_unit07.GetSelection()
            self.combo_size_unit07.SetItems(translate("combo_size_unit"))
            if current_selection >= 0 and current_selection < len(translate("combo_size_unit")):
                self.combo_size_unit07.SetSelection(current_selection)
        
        # Tab08: 去重
        if hasattr(self, 'combo_duplicate_algorithm08'):
            current_selection = self.combo_duplicate_algorithm08.GetSelection()
            self.combo_duplicate_algorithm08.SetItems(translate("combo_duplicate_algorithms"))
            if current_selection >= 0 and current_selection < len(translate("combo_duplicate_algorithms")):
                self.combo_duplicate_algorithm08.SetSelection(current_selection)
        
        if hasattr(self, 'combo_duplicate_rule08'):
            current_selection = self.combo_duplicate_rule08.GetSelection()
            self.combo_duplicate_rule08.SetItems(translate("combo_duplicate_rules"))
            if current_selection >= 0 and current_selection < len(translate("combo_duplicate_rules")):
                self.combo_duplicate_rule08.SetSelection(current_selection)
        
        print("All ComboBox options updated to current language")
    
    def _save_combo_selections(self):
        """保存所有ComboBox的当前选择"""
        selections = {}
        combo_list = [
            'combo_match_method01',
            'combo_naming_method02',
            'combo_file_conflict0202',
            'combo_dir_conflict0202',
            'combo_file_conflict0302',
            'combo_dir_conflict0302',
            'combo_create_folder03',
            'combo_file_conflict0402',
            'combo_dir_conflict0402',
            'combo_create_folder04',
            'combo_file_conflict0502',
            'combo_dir_conflict0502',
            'combo_file_conflict0602',
            'combo_dir_conflict0602',
            'combo_delete_filter07',
            'combo_size_unit07',
            'combo_duplicate_algorithm08',
            'combo_duplicate_rule08'
        ]
        for combo_name in combo_list:
            if hasattr(self, combo_name):
                combo = getattr(self, combo_name)
                selections[combo_name] = combo.GetSelection()
        return selections
    
    def _restore_combo_selections(self, selections):
        """恢复之前保存的ComboBox选择"""
        for combo_name, selection in selections.items():
            if hasattr(self, combo_name):
                combo = getattr(self, combo_name)
                if selection >= 0 and selection < combo.GetCount():
                    combo.SetSelection(selection)
    
    """应用压缩分组"""
    def on_apply_zip_group(self, event):
        """应用压缩分组功能"""
        # 与"执行"按钮保持一致：选择"按匹配名分组"时，匹配名为空或剪去前后空格后
        # 为空的行，其 New Path 回落到"按父目录名分组"规则（与解压标签页的
        # "按匹配名分组"回落"按压缩包分组"行为一致），不再弹错误警告。
        use_match_name = self.radio_zip_matchname05.GetValue()
        # 操作级历史记录：捕获 before_grid 快照
        self._begin_op_history(OP_TYPE_ZIP_APPLY, 4)
        # 禁用相关控件
        self.disable_controls_during_operation()
        # 禁用tab05里的交互控件
        self.radio_zip_foldername05.Enable(False)
        self.radio_zip_matchname05.Enable(False)
        self.combo_file_conflict0502.Enable(False)
        self.combo_dir_conflict0502.Enable(False)
        self.input_zip_target05.Enable(False)
        self.btn_zip_target_browse05.Enable(False)
        
        # 获取压缩分组选项
        file_conflict_method = self.get_combo_box_method(self.combo_file_conflict0502, self.conflict_method_mapping)
        dir_conflict_method = self.get_combo_box_method(self.combo_dir_conflict0502, self.conflict_method_mapping)
        
        # 目标路径：非空时用目标路径重写NewPath列（空则自动计算路径）
        apply_target_path = self.input_zip_target05.GetValue().strip()
        if not apply_target_path:
            apply_target_path = None
        
        # 创建并启动ZipWorker线程（不执行压缩，只计算路径）
        self.zip_worker = tfo_ZipWorker(self, True, use_match_name,
                                apply_target_path, file_conflict_method, dir_conflict_method, worker_mode=WorkerMode.APPLY)
        self.zip_worker.start()
        
        # 启动进度检查定时器
        self.zip_progress_timer = wx.Timer(self.get_parent_window())
        self.get_parent_window().Bind(wx.EVT_TIMER, self.check_zip_progress, self.zip_progress_timer)
        self.zip_progress_timer.Start(100)

    """应用查重按钮事件"""
    def on_apply_duplicate(self, event):
        # 操作级历史记录：捕获 before_grid 快照
        self._begin_op_history(OP_TYPE_DUPLICATE_APPLY, 7)
        # 禁用相关控件
        self.disable_controls_during_operation()
        
        # 禁用tab08里的交互控件
        self.combo_duplicate_algorithm08.Enable(False)
        self.combo_duplicate_rule08.Enable(False)
        self.radio_delete_recycle08.Enable(False)
        self.btn_apply_duplicate08.Enable(False)
        self.btn_execute_duplicate08.Enable(False)
        
        # 获取选择的算法和规则
        algorithm = self.get_combo_box_method(self.combo_duplicate_algorithm08, self.duplicate_algorithm_mapping)
        rule = self.get_combo_box_method(self.combo_duplicate_rule08, self.duplicate_rule_mapping)
        
        # 创建并启动去重线程
        self.duplicate_worker = tfo_DuplicateWorker(self, algorithm, rule, worker_mode=WorkerMode.APPLY)
        self.duplicate_worker.start()
        
        # 启动进度检查定时器
        self.duplicate_progress_timer = wx.Timer(self.get_parent_window())
        self.get_parent_window().Bind(wx.EVT_TIMER, self.check_duplicate_progress, self.duplicate_progress_timer)
        self.duplicate_progress_timer.Start(100)

    """执行去重按钮事件"""
    def on_execute_duplicate(self, event):
        # 检查是否有需要处理的项目
        rows_total = self.file_grid.GetNumberRows()
        count_total = 0
        for row_idx in range(rows_total):
            old_path = self.file_grid.GetCellValue(row_idx, self.file_grid.COL_OLD_PATH).strip()
            if old_path:
                count_total += 1
        if count_total == 0:
            wx.MessageBox(translate("message_no_duplicate_items"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        
        # 获取选择的算法、规则和删除方法
        algorithm = self.get_combo_box_method(self.combo_duplicate_algorithm08, self.duplicate_algorithm_mapping)
        rule = self.get_combo_box_method(self.combo_duplicate_rule08, self.duplicate_rule_mapping)
        algorithm_text = self.combo_duplicate_algorithm08.GetStringSelection()
        rule_text = self.combo_duplicate_rule08.GetStringSelection()
        delete_method_text = translate("delete_method_recycle")
        
        # 弹出确认对话框
        dlg = wx.Dialog(self.get_parent_window(), title=translate("dialog_title_confirm_duplicate"), size=(self.spx_calc(500), self.spx_calc(300)))
        title_sizer = wx.BoxSizer(wx.HORIZONTAL)
        icon = wx.StaticBitmap(dlg, bitmap=wx.ArtProvider.GetBitmap(wx.ART_WARNING, wx.ART_OTHER, (32, 32)))
        title = wx.StaticText(dlg, label=translate("dialog_title_confirm_duplicate"))
        font = title.GetFont()
        font.SetPointSize(int(font.GetPointSize() + 1))
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(font)
        title_sizer.Add(icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(10))
        title_sizer.Add(title, 0, wx.ALIGN_CENTER_VERTICAL)
        
        info_text = wx.StaticText(dlg, label=translate("dialog_text_confirm_duplicate", algorithm=algorithm_text, rule=rule_text, delete_method=delete_method_text))
        
        btn_cancel = wx.Button(dlg, label=translate("cancel"), id=wx.ID_CANCEL)
        btn_ok = wx.Button(dlg, label=translate("btn_execute_duplicate"), id=wx.ID_OK)
        
        # 布局
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(title_sizer, 0, wx.ALL | wx.EXPAND, self.spx_calc(10))
        sizer.Add(info_text, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM, self.spx_calc(20))
        
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.Add(btn_cancel, 0, wx.ALL, self.spx_calc(5))
        button_sizer.Add(btn_ok, 0, wx.ALL, self.spx_calc(5))
        
        sizer.Add(button_sizer, 0, wx.ALIGN_CENTER | wx.BOTTOM, self.spx_calc(10))
        dlg.SetSizer(sizer)
        
        # 显示对话框
        result = dlg.ShowModal()
        dlg.Destroy()
        
        # 如果用户点击取消，则不执行操作
        if result != wx.ID_OK:
            return

        # 操作级历史记录：捕获 before_grid 快照
        self._begin_op_history(OP_TYPE_DUPLICATE_EXECUTE, 7)
        # 禁用相关控件
        self.disable_controls_during_operation()
        # 将"预览结果"按钮改为"中断执行"
        self.btn_preview_stop0802.SetLabel(translate("btn_stop"))
        self.btn_preview_stop0802.Bind(wx.EVT_BUTTON, self.on_stop_operation)
        self.btn_preview_stop0802.Enable()
        self.tab08.Layout()
        
        # 创建并启动去重线程（带删除功能）
        self.duplicate_worker = tfo_DuplicateWorker(self, algorithm, rule, worker_mode=WorkerMode.EXECUTE)
        self.duplicate_worker.start()
        
        # 启动进度检查定时器
        self.duplicate_progress_timer = wx.Timer(self.get_parent_window())
        self.get_parent_window().Bind(wx.EVT_TIMER, self.check_duplicate_progress, self.duplicate_progress_timer)
        self.duplicate_progress_timer.Start(100)

    """处理tab09工具点击事件，在浏览器中打开指定URL"""
    def on_tool_click_09(self, url):
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception as e:
            wx.MessageBox(translate("message_open_link_error", url=url, error=str(e)), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)

    def _bind_link_cursor(self, link_label, cursor_host):
        """跨平台链接光标处理：
        wxGTK3下StaticText(GtkLabel)没有独立GdkWindow，SetCursor以及
        ENTER/LEAVE_WINDOW事件都不可靠（设了不生效，或泄漏到宿主窗口），
        因此改用鼠标移动事件+屏幕坐标命中检测：鼠标在链接文字上时宿主面板
        显示手形光标，其余区域显示箭头；非GTK平台则直接在标签上设置光标。"""
        hand = wx.Cursor(wx.CURSOR_HAND)
        arrow = wx.Cursor(wx.CURSOR_ARROW)

        # 非GTK平台：StaticText有独立窗口，直接设置光标即可生效
        if wx.Platform != "__WXGTK__":
            link_label.SetCursor(hand)

        # GTK平台：用鼠标移动事件做命中检测（无论事件落在宿主还是标签上，
        # 统一取屏幕坐标判断鼠标是否在某个链接文字上）
        def _on_motion(event):
            pos_screen = event.GetEventObject().ClientToScreen(event.GetPosition())
            hovered = any(
                label.GetScreenRect().Contains(pos_screen)
                for label in getattr(cursor_host, "_link_labels", ())
            )
            cursor_host.SetCursor(hand if hovered else arrow)
            event.Skip()

        links = getattr(cursor_host, "_link_labels", None)
        if links is None:
            links = cursor_host._link_labels = []

            def _on_leave(event):
                cursor_host.SetCursor(arrow)
                event.Skip()

            cursor_host.Bind(wx.EVT_MOTION, _on_motion)
            cursor_host.Bind(wx.EVT_LEAVE_WINDOW, _on_leave)

        # 事件若被路由到标签自身（无窗口子控件），也在标签上绑定同一处理器
        link_label.Bind(wx.EVT_MOTION, _on_motion)
        links.append(link_label)

    def init_combo_box_mappings(self):
        """初始化ComboBox选项的索引映射"""
        # 匹配方法映射
        self.match_method_mapping = {
            0: "contains_full_name",
            1: "contains_all_fragments", 
            2: "contains_any_fragment",
            3: "equals_name",
            4: "starts_with_name",
            5: "ends_with_name",
            6: "images_preset",
            7: "documents_preset",
            8: "compressed_preset",
            9: "text_preset",
            10: "exclude_full_names",
            11: "exclude_wildcards",
            12: "matches_wildcard",
            13: "matches_regex"
        }
        
        # 重命名方法映射
        self.naming_method_mapping = {
            0: "original_name",
            1: "replace",
            2: "insert_by_position",
            3: "delete_by_position",
            4: "add_affix",
            5: "change_case",
            6: "regex_replace",
            7: "add_number",
            8: "convert_by_placeholder",
            9: "rename_mp3"
        }
        
        # 删除过滤方法映射
        self.delete_filter_mapping = {
            0: "delete_all",
            1: "name_contains",
            2: "name_not_contains",
            3: "size_less_than",
            4: "size_greater_than",
            5: "size_between",
            6: "create_time_before",
            7: "create_time_after",
            8: "create_time_between",
            9: "modify_time_before",
            10: "modify_time_after",
            11: "modify_time_between"
        }
        
        # 去重算法映射
        self.duplicate_algorithm_mapping = {
            0: "filename",
            1: "filename_size",
            2: "file_fingerprint",
            3: "file_hash"
        }
        
        # 去重规则映射
        self.duplicate_rule_mapping = {
            0: "keep_create_time_latest",
            1: "keep_create_time_earliest",
            2: "keep_modify_time_latest",
            3: "keep_modify_time_earliest",
            4: "keep_filename_longest",
            5: "keep_filename_shortest",
            6: "keep_path_longest",
            7: "keep_path_shortest"
        }
        
        # 冲突处理方法映射
        self.conflict_method_mapping = {
            0: "skip",
            1: "overwrite",
            2: "replace"
        }
        
        # 创建文件夹方法映射
        self.create_folder_mapping = {
            0: "no_subdirectories",
            1: "single_level_subdirectories",
            2: "multi_level_subdirectories",
            3: "remove_parent_directory",
            4: "flatten_all_files"
        }
        
        # 文件大小单位映射
        self.size_unit_mapping = {
            0: "B",
            1: "KB",
            2: "MB",
            3: "GB"
        }
    
    def get_combo_box_method(self, combo_box, mapping_dict):
        """获取ComboBox当前选择对应的方法标识"""
        selection = combo_box.GetSelection()
        if selection >= 0 and selection in mapping_dict:
            return mapping_dict[selection]
        return None
    
    def is_match_method(self, combo_box, method_name):
        """检查匹配方法是否为指定方法"""
        current_method = self.get_combo_box_method(combo_box, self.match_method_mapping)
        return current_method == method_name
    
    def is_naming_method(self, combo_box, method_name):
        """检查重命名方法是否为指定方法"""
        current_method = self.get_combo_box_method(combo_box, self.naming_method_mapping)
        return current_method == method_name
    
    def is_delete_filter(self, combo_box, filter_name):
        """检查删除过滤方法是否为指定方法"""
        current_method = self.get_combo_box_method(combo_box, self.delete_filter_mapping)
        return current_method == filter_name
    
    def is_duplicate_algorithm(self, combo_box, algorithm_name):
        """检查去重算法是否为指定算法"""
        current_method = self.get_combo_box_method(combo_box, self.duplicate_algorithm_mapping)
        return current_method == algorithm_name
    
    def is_duplicate_rule(self, combo_box, rule_name):
        """检查去重规则是否为指定规则"""
        current_method = self.get_combo_box_method(combo_box, self.duplicate_rule_mapping)
        return current_method == rule_name
    
    def is_conflict_method(self, combo_box, method_name):
        """检查冲突处理方法是否为指定方法"""
        current_method = self.get_combo_box_method(combo_box, self.conflict_method_mapping)
        return current_method == method_name

class RoundedPanel(wx.Panel):
    def __init__(self, parent, radius=8, border_colour=(220, 220, 220), background_colour=wx.WHITE):
        wx.Panel.__init__(self, parent)
        self.radius = radius
        self.border_colour = border_colour
        self.background_colour = background_colour
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.on_erase_background)

    def on_erase_background(self, event):
        pass

    def on_size(self, event):
        self.Refresh()
        event.Skip()

    def on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.background_colour))
        dc.Clear()
        rect = self.GetClientRect()
        if rect.width > 0 and rect.height > 0:
            dc.SetPen(wx.Pen(self.border_colour, 1))
            dc.SetBrush(wx.Brush(self.background_colour))
            dc.DrawRoundedRectangle(rect, self.radius)

# 主程序：初始化工具类来显示工具界面
def create_tool(parent, user_setting_base_dir=None):
    return tfo_TabulexFileOperatorTool(parent)

