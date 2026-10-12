# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
import os
import re
import shutil
import pathlib
import threading
from tdc_CustomGrid import tdc_CustomGrid
from tdc_FileDrop import tdc_FileDropToGrid
from tdc_i18n_manager import translate, translate_list, i18n, tdc_I18nManager as I18nManager, get_all_translations
from tfp_toolkit.tfp_base_tool import TFP_BuiltinProgramTool
from tfp_toolkit.tfp_dpi import spx_calc as _spx_calc
from tdc_logger import log_info, log_error, log_warning, log_debug, clear_log

# OSS 社区版（IS_OSS_COMMUNITY_BUILD=True，编译期由构建脚本写入 build_mode 并随主程序打包）
# 不显示"关于/About"标签页，仅非 OSS 版（源码/开发、完整版）显示。导入失败时按非 OSS 处理。
try:
    from build_mode import IS_OSS_COMMUNITY_BUILD
except ImportError:
    IS_OSS_COMMUNITY_BUILD = False


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


class tdc_TabulexDocCreatorTool(TFP_BuiltinProgramTool):
    # Create Doc → Get Doc Info 切换时，数据列非空单元格数超过该值才弹确认框（含表头行）
    MODE_SWITCH_CLEAR_CONFIRM_THRESHOLD = 3

    @property
    def tool_ident(self) -> str:
        return "TabulexDocCreator"

    @property
    def tool_name(self) -> str:
        return translate("tool_name")

    def __init__(self, parent):
        super().__init__(parent)
        self.current_tab = 'excel'
        self.grids = {}
        self.worker_thread = None
        self.worker = None
        self.current_worker_doc_type = None
        self._operation_lock = threading.Lock()
        self.operation_modes = {}
        self.fill_methods = {}
        self.image_width_inputs = {}
        self.image_height_inputs = {}
        self.image_panels = {}
        self.table_cols_inputs = {}
        self.table_tight_checkboxes = {}
        self.table_panels = {}
        self.status_labels_left = {}
        self.status_labels_right = {}
        self.insert_position_inputs = {}
        self.total_width_inputs = {}
        self.insert_position_panels = {}
        self.table_row_heights = {}
        self.total_width_labels = {}
        # PDF“行高/宽度”参数按填写方式分别记忆，默认值不同（行高0.015，图片宽度0.06）
        self.total_width_defaults = {'add_text': '0.015', 'add_table': '0.015', 'add_image': '0.06'}
        self.total_width_values = dict(self.total_width_defaults)
        self.last_fill_methods = {}
        self.TFP_DPI_SCALE_FACTOR = getattr(parent, 'TFP_DPI_SCALE_FACTOR', 1.0)
        self.init_combo_box_mappings()

    def spx_calc(self, value):
        if value == -1:
            return -1
        return int(value * self.TFP_DPI_SCALE_FACTOR)
    
    def create_embedded_interface(self, parent_panel, parent_sizer):
        self.is_embedded = True
        self.panel = parent_panel
        self.sizer_main = parent_sizer
        self._build_interface()
    
    def show_interface(self):
        if self.frame and self.frame.IsShown():
            return
        self.is_embedded = False
        self.frame = wx.Frame(None, title=translate("tool_name"), size=(self.spx_calc(1200), self.spx_calc(700)), style=wx.DEFAULT_FRAME_STYLE | wx.RESIZE_BORDER)
        try:
            if hasattr(self.parent, 'base_path'):
                icon_path = self.parent.base_path / "app_icon.ico"
                if icon_path.exists():
                    # IconBundle 载入 ICO 内全部尺寸，Linux 任务栏才能正确显示（SetIcon 在 wxGTK 下只写单一尺寸）
                    self.frame.SetIcons(wx.IconBundle(str(icon_path), wx.BITMAP_TYPE_ICO))
        except Exception:
            pass
        self.panel = wx.Panel(self.frame)
        self.sizer_main = wx.BoxSizer(wx.VERTICAL)
        self._build_interface()
        self.frame.Show()
        if self.parent:
            parent_pos = self.parent.GetPosition()
            self.frame.SetPosition((parent_pos.x + self.spx_calc(30), parent_pos.y + self.spx_calc(50)))
    
    def _build_interface(self):
        self.notebook = wx.Notebook(self.panel)
        self.sizer_main.Add(self.notebook, 1, wx.EXPAND | wx.ALL, self.spx_calc(5))
        self._build_excel_tab()
        self._build_word_tab()
        self._build_ppt_tab()
        self._build_pdf_tab()
        # OSS 社区版不显示"关于"标签页（仅非 OSS 版显示）；该页关联的"更多效率工具"卡片随之不展示
        if not IS_OSS_COMMUNITY_BUILD:
            self._build_about_tab()
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._on_tab_changed)
    
    def _build_excel_tab(self):
        self.tab_excel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_params = self._build_params_row(self.tab_excel, 'excel')
        sizer.Add(sizer_params, 0, wx.EXPAND | wx.ALL, self.spx_calc(5))
        self.grid_excel = tdc_CustomGrid(self.tab_excel, self, 'excel', 'placeholder')
        sizer.Add(self.grid_excel, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self.spx_calc(5))
        self.grids['excel'] = self.grid_excel
        sizer_status = self._build_status_bar(self.tab_excel, 'excel')
        sizer.Add(sizer_status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self.spx_calc(5))
        self.tab_excel.SetSizer(sizer)
        self.notebook.AddPage(self.tab_excel, translate('tab_excel'))
    
    def _build_word_tab(self):
        self.tab_word = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_params = self._build_params_row(self.tab_word, 'word')
        sizer.Add(sizer_params, 0, wx.EXPAND | wx.ALL, self.spx_calc(5))
        self.grid_word = tdc_CustomGrid(self.tab_word, self, 'word', 'placeholder')
        sizer.Add(self.grid_word, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self.spx_calc(5))
        self.grids['word'] = self.grid_word
        sizer_status = self._build_status_bar(self.tab_word, 'word')
        sizer.Add(sizer_status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self.spx_calc(5))
        self.tab_word.SetSizer(sizer)
        self.notebook.AddPage(self.tab_word, translate('tab_word'))
    
    def _build_ppt_tab(self):
        self.tab_ppt = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_params = self._build_params_row(self.tab_ppt, 'ppt')
        sizer.Add(sizer_params, 0, wx.EXPAND | wx.ALL, self.spx_calc(5))
        self.grid_ppt = tdc_CustomGrid(self.tab_ppt, self, 'ppt', 'placeholder')
        sizer.Add(self.grid_ppt, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self.spx_calc(5))
        self.grids['ppt'] = self.grid_ppt
        sizer_status = self._build_status_bar(self.tab_ppt, 'ppt')
        sizer.Add(sizer_status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self.spx_calc(5))
        self.tab_ppt.SetSizer(sizer)
        self.notebook.AddPage(self.tab_ppt, translate('tab_ppt'))
    
    def _build_pdf_tab(self):
        self.tab_pdf = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_params = self._build_params_row(self.tab_pdf, 'pdf')
        sizer.Add(sizer_params, 0, wx.EXPAND | wx.ALL, self.spx_calc(5))
        self.grid_pdf = tdc_CustomGrid(self.tab_pdf, self, 'pdf', 'placeholder')
        sizer.Add(self.grid_pdf, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self.spx_calc(5))
        self.grids['pdf'] = self.grid_pdf
        sizer_status = self._build_status_bar(self.tab_pdf, 'pdf')
        sizer.Add(sizer_status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self.spx_calc(5))
        self.tab_pdf.SetSizer(sizer)
        self.notebook.AddPage(self.tab_pdf, translate('tab_pdf'))
    
    def _build_status_bar(self, parent, doc_type):
        status_panel = wx.Panel(parent)
        status_sizer = wx.BoxSizer(wx.HORIZONTAL)
        label_left = wx.StaticText(status_panel, label='', style=wx.ST_ELLIPSIZE_END)
        label_left.SetBackgroundColour(wx.Colour(240, 240, 240))
        label_right = wx.StaticText(status_panel, label='', style=wx.ST_ELLIPSIZE_END)
        label_right.SetBackgroundColour(wx.Colour(240, 240, 240))
        self.status_labels_left[doc_type] = label_left
        self.status_labels_right[doc_type] = label_right
        status_sizer.Add(label_left, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(5))
        status_sizer.Add(label_right, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(5))
        label_right.SetMinSize((self.spx_calc(200), -1))
        status_panel.SetSizer(status_sizer)
        status_panel.Layout()
        return status_panel
    
    def update_status_left(self, doc_type, message):
        if doc_type in self.status_labels_left:
            self.status_labels_left[doc_type].SetLabel(message)
    
    def update_status_right(self, doc_type, message):
        if doc_type in self.status_labels_right:
            self.status_labels_right[doc_type].SetLabel(message)
    
    def update_progress(self, doc_type, current, total, filename=''):
        if doc_type in self.status_labels_left:
            progress_text = translate('status_processing', current=current, total=total)
            if filename:
                progress_text += f' - {filename}'
            self.status_labels_left[doc_type].SetLabel(progress_text)
            self.status_labels_left[doc_type].Update()
        if doc_type in self.status_labels_right:
            percent = int(current * 100 / total) if total > 0 else 0
            self.status_labels_right[doc_type].SetLabel(f'{percent}%')
            self.status_labels_right[doc_type].Update()
        # 方案3：执行期间按当前处理的保存文件高亮对应数据行（逐文件可见进度）
        grid = self.grids.get(doc_type)
        if grid and filename and hasattr(grid, 'highlight_save_basename'):
            grid.highlight_save_basename(filename)
    
    def clear_progress(self, doc_type):
        if doc_type in self.status_labels_left:
            self.status_labels_left[doc_type].SetLabel('')
    
    def _build_params_row(self, parent, doc_type):
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        label_operation = wx.StaticText(parent, label=translate('label_operation_mode'))
        combo_operation = wx.ComboBox(parent, choices=translate_list('combo_operation_modes'), style=wx.CB_READONLY)
        combo_operation.SetSelection(0)
        combo_operation.Bind(wx.EVT_COMBOBOX, lambda e: self._on_operation_mode_changed(doc_type, e))
        self.operation_modes[doc_type] = combo_operation
        sizer.Add(label_operation, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer.Add(combo_operation, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(15))
        label_fill = wx.StaticText(parent, label=translate('label_fill_method'))
        fill_methods_key = f'combo_{doc_type}_fill_methods'
        fill_methods_list = translate_list(fill_methods_key)
        combo_fill = wx.ComboBox(parent, choices=fill_methods_list, style=wx.CB_READONLY,
                                 size=(self.spx_calc(125), -1))
        combo_fill.SetSelection(0)
        combo_fill.Bind(wx.EVT_COMBOBOX, lambda e: self._on_fill_method_changed(doc_type, e))
        self.fill_methods[doc_type] = combo_fill
        sizer.Add(label_fill, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer.Add(combo_fill, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(15))
        if not hasattr(self, 'fill_method_widgets'):
            self.fill_method_widgets = {}
        self.fill_method_widgets[doc_type] = {'label': label_fill, 'combo': combo_fill}
        panel_image = wx.Panel(parent)
        sizer_image = wx.BoxSizer(wx.HORIZONTAL)
        label_width = wx.StaticText(panel_image, label=translate('label_image_width'))
        input_width = wx.TextCtrl(panel_image, size=(self.spx_calc(60), -1))
        input_width.SetValue('200')
        label_height = wx.StaticText(panel_image, label=translate('label_image_height'))
        input_height = wx.TextCtrl(panel_image, size=(self.spx_calc(60), -1))
        input_height.SetValue('200')
        sizer_image.Add(label_width, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_image.Add(input_width, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(10))
        sizer_image.Add(label_height, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        sizer_image.Add(input_height, 0, wx.ALIGN_CENTER_VERTICAL)
        panel_image.SetSizer(sizer_image)
        self.image_width_inputs[doc_type] = input_width
        self.image_height_inputs[doc_type] = input_height
        self.image_panels[doc_type] = panel_image
        sizer.Add(panel_image, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(15))
        if doc_type == 'pdf':
            panel_insert_position = wx.Panel(parent)
            sizer_insert = wx.BoxSizer(wx.HORIZONTAL)
            label_insert_position = wx.StaticText(panel_insert_position, label=translate('label_insert_position'))
            combo_insert_position = wx.ComboBox(panel_insert_position, choices=translate_list('combo_insert_positions'), style=wx.CB_READONLY,
                                                size=(self.spx_calc(125), -1))
            combo_insert_position.SetSelection(0)
            sizer_insert.Add(label_insert_position, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
            sizer_insert.Add(combo_insert_position, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(15))
            panel_insert_position.SetSizer(sizer_insert)
            self.insert_position_inputs[doc_type] = combo_insert_position
            self.insert_position_panels[doc_type] = panel_insert_position
            panel_insert_position.Hide()
            sizer.Add(panel_insert_position, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
            panel_total_width = wx.Panel(parent)
            sizer_total = wx.BoxSizer(wx.HORIZONTAL)
            label_row_height = wx.StaticText(panel_total_width, label=translate('label_row_height'))
            input_total_width = wx.TextCtrl(panel_total_width, size=(self.spx_calc(56), -1))
            input_total_width.SetValue('0.015')
            sizer_total.Add(label_row_height, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
            sizer_total.Add(input_total_width, 0, wx.ALIGN_CENTER_VERTICAL)
            panel_total_width.SetSizer(sizer_total)
            self.total_width_inputs[doc_type] = input_total_width
            self.table_row_heights[doc_type] = panel_total_width
            self.total_width_labels[doc_type] = label_row_height
            panel_total_width.Hide()
            sizer.Add(panel_total_width, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(15))
            panel_table = wx.Panel(parent)
            sizer_table = wx.BoxSizer(wx.HORIZONTAL)
            checkbox_tight = wx.CheckBox(panel_table, label=translate('label_tight'))
            checkbox_tight.SetValue(False)
            sizer_table.Add(checkbox_tight, 0, wx.ALIGN_CENTER_VERTICAL)
            self.table_cols_inputs[doc_type] = None
            panel_table.SetSizer(sizer_table)
            self.table_tight_checkboxes[doc_type] = checkbox_tight
            self.table_panels[doc_type] = panel_table
            panel_table.Hide()
            sizer.Add(panel_table, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(15))
        sizer.AddStretchSpacer()
        btn_preview = wx.Button(parent, label=translate('btn_preview'))
        btn_preview.Bind(wx.EVT_BUTTON, lambda e: self._on_preview(doc_type))
        sizer.Add(btn_preview, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.spx_calc(5))
        if not hasattr(self, 'preview_buttons'):
            self.preview_buttons = {}
        self.preview_buttons[doc_type] = btn_preview
        btn_execute = wx.Button(parent, label=translate('btn_execute'))
        btn_execute.Bind(wx.EVT_BUTTON, lambda e: self._on_execute(doc_type))
        sizer.Add(btn_execute, 0, wx.ALIGN_CENTER_VERTICAL)
        if not hasattr(self, 'execute_buttons'):
            self.execute_buttons = {}
        self.execute_buttons[doc_type] = btn_execute
        return sizer
    
    def _on_tab_changed(self, event):
        old_selection = event.GetOldSelection()
        new_selection = event.GetSelection()
        if new_selection == 0:
            self.current_tab = 'excel'
        elif new_selection == 1:
            self.current_tab = 'word'
        elif new_selection == 2:
            self.current_tab = 'ppt'
        elif new_selection == 3:
            self.current_tab = 'pdf'
        elif new_selection == 4:
            self.current_tab = 'about'
        event.Skip()
    
    def _confirm_mode_switch_clear(self, doc_type, grid, new_mode):
        """Create Doc → Get Doc Info 且数据列非空单元格（含表头行）超过阈值时弹确认框

        返回 True 表示允许切换（无风险或用户确认）；返回 False 表示用户取消，
        此时需回退 Mode 下拉框到原模式且不清空（编程式 SetSelection 不触发 COMBOBOX 事件）。
        仅 Create→Get 方向弹框；Get→Create 直接清空。
        """
        prev_mode = grid.operation_mode
        if not (prev_mode == 'create_from_template' and new_mode == 'get_file_info'):
            return True
        count = grid.count_nonempty_data_cells()
        if count <= self.MODE_SWITCH_CLEAR_CONFIRM_THRESHOLD:
            return True
        msg = translate('msg_mode_switch_clear_confirm', count=count)
        if wx.MessageBox(msg, translate('msg_warning'), wx.YES_NO | wx.ICON_WARNING) == wx.YES:
            return True
        for index, mode in self.operation_mode_mapping.items():
            if mode == prev_mode:
                self.operation_modes[doc_type].SetSelection(index)
                break
        return False

    def _on_operation_mode_changed(self, doc_type, event):
        operation_mode = self.get_combo_box_method(self.operation_modes[doc_type], self.operation_mode_mapping)
        grid = self.grids.get(doc_type)
        if grid:
            if not self._confirm_mode_switch_clear(doc_type, grid, operation_mode):
                return
            grid.set_operation_mode(operation_mode)
        
        if operation_mode == 'get_file_info':
            fill_method_widgets = self.fill_method_widgets.get(doc_type)
            if fill_method_widgets:
                fill_method_widgets['label'].Disable()
                fill_method_widgets['combo'].Disable()
            image_panel = self.image_panels.get(doc_type)
            if image_panel:
                image_panel.Disable()
            if doc_type == 'pdf':
                insert_position_panel = self.insert_position_panels.get(doc_type)
                if insert_position_panel:
                    insert_position_panel.Disable()
                table_panel = self.table_panels.get(doc_type)
                if table_panel:
                    table_panel.Disable()
            table_row_height = self.table_row_heights.get(doc_type)
            if table_row_height:
                table_row_height.Disable()
            self._sync_preview_button_enabled(doc_type)
            return
        
        fill_method_widgets = self.fill_method_widgets.get(doc_type)
        if fill_method_widgets:
            fill_method_widgets['label'].Enable()
            fill_method_widgets['combo'].Enable()
        self._sync_preview_button_enabled(doc_type)
        
        self._on_fill_method_changed(doc_type, event)
    
    def _on_fill_method_changed(self, doc_type, event):
        fill_method = self.get_fill_method(doc_type)
        grid = self.grids.get(doc_type)
        if grid:
            grid.update_fill_method(fill_method)
        is_placeholder = fill_method == 'placeholder'
        is_title_fill = fill_method == 'title_fill'
        is_add_image = fill_method == 'add_image'
        image_panel = self.image_panels.get(doc_type)
        if image_panel:
            if doc_type == 'pdf':
                # 规格7.3：插入图片使用“图片总宽”参数，不显示“图片宽高”面板
                show_image_panel = is_placeholder
            else:
                show_image_panel = is_placeholder or is_title_fill
            if show_image_panel:
                image_panel.Show()
            else:
                image_panel.Hide()
            parent = image_panel.GetParent()
            if parent:
                parent.Layout()
        if doc_type == 'pdf':
            # “行高/图片总宽”参数按填写方式分别记忆，切换时载入各自默认值/上次输入
            input_total_width = self.total_width_inputs.get(doc_type)
            if input_total_width:
                prev_method = self.last_fill_methods.get(doc_type)
                if prev_method in self.total_width_values:
                    self.total_width_values[prev_method] = input_total_width.GetValue()
                if fill_method in self.total_width_values:
                    input_total_width.SetValue(self.total_width_values[fill_method])
                self.last_fill_methods[doc_type] = fill_method
            insert_position_panel = self.insert_position_panels.get(doc_type)
            if insert_position_panel:
                is_delete_table = fill_method == 'delete_table'
                if is_placeholder or is_delete_table:
                    insert_position_panel.Hide()
                else:
                    insert_position_panel.Show()
                parent = insert_position_panel.GetParent()
                if parent:
                    parent.Layout()
            total_width_label = self.total_width_labels.get(doc_type)
            table_row_height = self.table_row_heights.get(doc_type)
            if table_row_height:
                is_delete_table = fill_method == 'delete_table'
                is_table = fill_method == 'add_table'
                is_image = fill_method == 'add_image'
                is_text = fill_method == 'add_text'
                if is_delete_table or is_placeholder:
                    table_row_height.Hide()
                elif is_image:
                    if total_width_label:
                        total_width_label.SetLabel(translate('label_row_height_image'))
                    table_row_height.Show()
                elif is_table:
                    if total_width_label:
                        total_width_label.SetLabel(translate('label_row_height_table'))
                    table_row_height.Show()
                elif is_text:
                    if total_width_label:
                        total_width_label.SetLabel(translate('label_row_height'))
                    table_row_height.Show()
                else:
                    table_row_height.Hide()
                parent = table_row_height.GetParent()
                if parent:
                    parent.Layout()
            table_panel = self.table_panels.get(doc_type)
            if table_panel:
                show_table_panel = fill_method == 'add_table'
                if show_table_panel:
                    table_panel.Show()
                else:
                    table_panel.Hide()
                parent = table_panel.GetParent()
                if parent:
                    parent.Layout()
    
    def _on_preview(self, doc_type):
        # Get Doc Info 模式不存在预览，直接返回
        if self.get_operation_mode(doc_type) == 'get_file_info':
            return
        log_debug(f'[tool] _on_preview doc_type={doc_type}')
        if self.worker_thread and self.worker_thread.is_alive():
            if getattr(self, 'current_worker_doc_type', None) == doc_type:
                self._cancel_operation(doc_type)
            return
        clear_log()
        grid = self.grids.get(doc_type)
        if not grid:
            return
        data = grid.get_data_rows()
        if not data:
            wx.MessageBox(translate('msg_no_data'), translate('msg_error'), wx.OK | wx.ICON_WARNING)
            return
        self._disable_for_preview()
        selected_row = grid.get_selected_data_row()
        if selected_row:
            preview_index = selected_row.get('row_index', grid.header_rows) - grid.header_rows
        else:
            preview_index = 0
        preview_index = max(0, min(preview_index, len(data) - 1))
        self.update_status_left(doc_type, translate('msg_processing'))
        self.update_status_right(doc_type, '')
        wx.Yield()
        self._show_preview_dialog(doc_type, data, preview_index)
        self.clear_progress(doc_type)
        self._enable_after_preview()
    
    def _show_preview_dialog(self, doc_type, data, current_index):
        from tdc_PreviewDialog import tdc_PreviewDialog
        dialog = tdc_PreviewDialog(self.frame if self.frame else self.panel, self, doc_type, data, current_index)
        dialog.ShowModal()
        dialog.Destroy()
    
    def _disable_for_preview(self):
        self.disable_all_inputs()
        for dt in ['excel', 'word', 'ppt', 'pdf']:
            if dt in self.grids:
                self.grids[dt].Disable()
            if dt in self.preview_buttons:
                self.preview_buttons[dt].Disable()
            if dt in self.execute_buttons:
                self.execute_buttons[dt].Disable()
    
    def _enable_after_preview(self):
        self.enable_all_inputs()
        for dt in ['excel', 'word', 'ppt', 'pdf']:
            if dt in self.grids:
                self.grids[dt].Enable()
            self._sync_preview_button_enabled(dt)
            if dt in self.execute_buttons:
                self.execute_buttons[dt].Enable()
    
    def _on_execute(self, doc_type):
        clear_log()
        log_debug(f'[tool] _on_execute doc_type={doc_type}')
        grid = self.grids.get(doc_type)
        if not grid:
            return
        fill_method = self.get_fill_method(doc_type)
        operation_mode = self.get_combo_box_method(self.operation_modes[doc_type], self.operation_mode_mapping)
        
        if not self._operation_lock.acquire(blocking=False):
            wx.MessageBox(translate('msg_operation_in_progress'), translate('msg_error'), wx.OK | wx.ICON_WARNING)
            return
        
        if operation_mode == 'get_file_info':
            grid.set_fill_method('placeholder')
            data = grid.get_data_rows()
            if not data:
                self._operation_lock.release()
                wx.MessageBox(translate('msg_no_data'), translate('msg_error'), wx.OK | wx.ICON_WARNING)
                return
            self.update_status_left(doc_type, translate('msg_processing'))
            self.update_status_right(doc_type, '')
            wx.Yield()
            self._disable_for_execute(doc_type)
            self._update_preview_button_state(doc_type, True)
            self._execute_operation(doc_type, data, operation_mode, fill_method)
            return
        
        grid.set_fill_method(fill_method)
        data = grid.get_data_rows()
        if not data:
            self._operation_lock.release()
            wx.MessageBox(translate('msg_no_data'), translate('msg_error'), wx.OK | wx.ICON_WARNING)
            return
        validation_errors = self._validate_data(doc_type, data)
        if validation_errors:
            self._operation_lock.release()
            msg = '\n'.join(validation_errors[:10])
            if len(validation_errors) > 10:
                msg += f'\n... ({len(validation_errors) - 10} more)'
            wx.MessageBox(msg, translate('msg_error'), wx.OK | wx.ICON_ERROR)
            return
        if operation_mode != 'get_file_info':
            # 先排除“执行结果列已有值、本次会被跳过”的组：不对不会生成的文件弹覆盖确认；
            # 全部组都会被跳过时不再弹覆盖确认，直接执行并给出“已跳过”提示（避免先问覆盖、再说没生成）。
            unskipped_rows = self._get_unskipped_rows(data)
            conflicts = self._check_output_conflicts(unskipped_rows)
            if conflicts:
                self._operation_lock.release()
                msg = translate('msg_output_conflict') + '\n' + '\n'.join(conflicts[:5])
                if len(conflicts) > 5:
                    msg += f'\n... ({len(conflicts) - 5} more)'
                result = wx.MessageBox(msg, translate('msg_warning'), wx.YES_NO | wx.ICON_WARNING)
                if result != wx.YES:
                    return
                if not self._operation_lock.acquire(blocking=False):
                    wx.MessageBox(translate('msg_operation_in_progress'), translate('msg_error'), wx.OK | wx.ICON_WARNING)
                    return
            existing_files = self._check_existing_save_files(unskipped_rows)
            if existing_files:
                self._operation_lock.release()
                msg = translate('msg_file_exists') + '\n' + '\n'.join(existing_files[:5])
                if len(existing_files) > 5:
                    msg += f'\n... ({len(existing_files) - 5} more)'
                result = wx.MessageBox(msg, translate('msg_confirm_overwrite'), wx.YES_NO | wx.ICON_WARNING)
                if result != wx.YES:
                    return
                if not self._operation_lock.acquire(blocking=False):
                    wx.MessageBox(translate('msg_operation_in_progress'), translate('msg_error'), wx.OK | wx.ICON_WARNING)
                    return
        self.update_status_left(doc_type, translate('msg_processing'))
        self.update_status_right(doc_type, '')
        wx.Yield()
        self._disable_for_execute(doc_type)
        self._update_preview_button_state(doc_type, True)
        self._execute_operation(doc_type, data, operation_mode, fill_method)
    
    def _execute_operation(self, doc_type, data, operation_mode, fill_method):
        try:
            params = self.get_all_params(doc_type)
            if doc_type == 'excel':
                from tdc_ExcelWorker import tdc_ExcelWorker
                worker = tdc_ExcelWorker(self, data, operation_mode, fill_method, params)
            elif doc_type == 'word':
                from tdc_WordWorker import tdc_WordWorker
                worker = tdc_WordWorker(self, data, operation_mode, fill_method, params)
            elif doc_type == 'ppt':
                from tdc_PowerPointWorker import tdc_PowerPointWorker
                worker = tdc_PowerPointWorker(self, data, operation_mode, fill_method, params)
            elif doc_type == 'pdf':
                from tdc_PDFWorker import tdc_PDFWorker
                worker = tdc_PDFWorker(self, data, operation_mode, fill_method, params)
            else:
                self._operation_lock.release()
                return
            self.worker = worker
            self.current_worker_doc_type = doc_type
            self.worker_thread = threading.Thread(target=self._run_worker, args=(doc_type, worker))
            self.worker_thread.start()
        except Exception:
            self._operation_lock.release()
            raise
    
    def _run_worker(self, doc_type, worker):
        worker.execute()
        wx.CallAfter(self._on_worker_completed, doc_type)
    
    def _on_worker_completed(self, doc_type):
        worker = self.worker
        self.worker_thread = None
        self.worker = None
        self.current_worker_doc_type = None
        self._update_preview_button_state(doc_type, False)
        self._enable_after_execute()
        try:
            self._operation_lock.release()
        except RuntimeError:
            pass
        if worker and hasattr(worker, 'results') and not getattr(worker, 'cancelled', False):
            success_count = sum(1 for r in worker.results if r.get('success'))
            total_count = len(worker.results)
            total_groups = getattr(worker, '_total_groups', 0)
            if total_count > 0:
                self.update_status_left(doc_type, '')
                message = (worker._build_completion_message(success_count, total_count)
                           if hasattr(worker, '_build_completion_message')
                           else f'{translate("msg_completed")}: {success_count}/{total_count}')
                self.update_status_right(doc_type, message)
            elif total_groups > 0:
                # 全部因“执行结果”列已有值被跳过：状态栏给出简短说明（弹窗给出完整说明）
                skipped = getattr(worker, '_skipped_success', 0) + getattr(worker, '_skipped_error', 0)
                self.update_status_left(doc_type, '')
                self.update_status_right(doc_type, f'{translate("msg_skipped_label")}: {skipped}')
            elif getattr(worker, 'operation_mode', '') == 'get_file_info':
                self.update_status_left(doc_type, '')
                self.update_status_right(doc_type, translate('msg_completed'))
    
    def _cancel_operation(self, doc_type):
        if self.worker:
            self.worker.cancel()
        self.update_status_left(doc_type, '')
        self.update_status_right(doc_type, translate('msg_operation_cancelled'))
        self.worker_thread = None
        self.worker = None
        self.current_worker_doc_type = None
        self._update_preview_button_state(doc_type, False)
        self.clear_progress(doc_type)
        self._enable_after_execute()
        try:
            self._operation_lock.release()
        except RuntimeError:
            pass
    
    def _check_output_conflicts(self, data):
        # 规格3.4/4.6：多值机制通过“多行相同保存文件”实现，同一来源的重复保存文件不算冲突；
        # 仅当不同来源文件映射到同一输出文件时才提示冲突。
        save_file_sources = {}
        save_file_originals = {}
        for row in data:
            save_file = row.get('save_file', '')
            if not save_file:
                continue
            if not os.path.isabs(save_file):
                source_file = row.get('source_file', '')
                if source_file:
                    source_dir = os.path.dirname(source_file)
                    if source_dir:
                        save_file = os.path.join(source_dir, save_file)
            key = save_file.lower()
            save_file_originals.setdefault(key, save_file)
            source_file = (row.get('source_file') or '').strip()
            save_file_sources.setdefault(key, set())
            if source_file:
                save_file_sources[key].add(os.path.abspath(source_file))
        conflicts = [save_file_originals[k] for k, v in save_file_sources.items() if len(v) > 1]
        return conflicts
    
    def _check_existing_save_files(self, data):
        existing = []
        seen = set()
        for row in data:
            save_file = row.get('save_file', '')
            source_file = row.get('source_file', '')
            if save_file:
                if not os.path.isabs(save_file) and source_file:
                    source_dir = os.path.dirname(source_file)
                    if source_dir:
                        save_file = os.path.join(source_dir, save_file)
                save_file_lower = save_file.lower()
                if save_file_lower not in seen and os.path.exists(save_file):
                    existing.append(save_file)
                    seen.add(save_file_lower)
        return existing

    def _get_unskipped_rows(self, data):
        """返回“本次执行真正会处理”的行（排除执行结果列已有值、会被跳过的 Source File 组）。

        与各 Worker 的 `_get_group_result_state` 保持一致：按保存文件分组，组内任一行的
        “执行结果”列非空即整组跳过。用于避免对“本就会被跳过”的输出文件弹出覆盖确认。
        """
        groups = {}
        order = []
        for row in data:
            save_file = row.get('save_file', '')
            if not save_file:
                continue
            source_file = row.get('source_file', '')
            if not os.path.isabs(save_file) and source_file:
                source_dir = os.path.dirname(source_file)
                if source_dir:
                    save_file = os.path.join(source_dir, save_file)
            try:
                key = os.path.abspath(save_file).lower()
            except Exception:
                key = save_file.lower()
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(row)
        unskipped = []
        for key in order:
            rows = groups[key]
            if not any((r.get('result') or '').strip() for r in rows):
                unskipped.extend(rows)
        return unskipped
    
    def _is_safe_path(self, file_path):
        try:
            if '..' in os.path.normpath(file_path).split(os.sep):
                return False
            return True
        except Exception:
            return False

    def _validate_data(self, doc_type, data):
        errors = []
        # “图片”填写数量按全部语言的选项文本匹配（只匹配 en/zh 会漏判其他语言下选择的值）
        image_labels = [v[2] for v in get_all_translations('combo_value_counts')
                        if isinstance(v, list) and len(v) > 2 and v[2]]
        for row in data:
            row_index = row.get('row_index', 0)
            source_file = row.get('source_file', '')
            if source_file and source_file.strip():
                if not self._is_safe_path(source_file):
                    errors.append(f'{translate("msg_validation_row", row=row_index)}{translate("msg_source_not_found")} - {translate("msg_unsafe_path")}: {source_file}')
                elif not os.path.exists(source_file):
                    errors.append(f'{translate("msg_validation_row", row=row_index)}{translate("msg_source_not_found")} - {source_file}')
            for item in row.get('data', []):
                value_count = item.get('value_count', '')
                value = item.get('value', '').strip()
                if value and any(label.lower() in value_count.lower() for label in image_labels):
                    if not self._is_safe_path(value):
                        errors.append(f'{translate("msg_validation_row", row=row_index)}{translate("msg_image_not_found")} - {translate("msg_unsafe_path")}: {value}')
                    elif not os.path.exists(value):
                        errors.append(f'{translate("msg_validation_row", row=row_index)}{translate("msg_image_not_found")} - {value}')
        return errors
    def _sync_preview_button_enabled(self, doc_type):
        """Get Doc Info 模式没有预览，禁用 Preview 按钮；其余模式启用"""
        preview_button = self.preview_buttons.get(doc_type)
        if preview_button:
            preview_button.Enable(self.get_operation_mode(doc_type) != 'get_file_info')
    
    def _update_preview_button_state(self, doc_type, is_running):
        preview_button = self.preview_buttons.get(doc_type)
        if preview_button:
            if is_running:
                preview_button.SetLabel(translate('btn_cancel'))
            else:
                preview_button.SetLabel(translate('btn_preview'))
    
    def _disable_for_execute(self, exclude_doc_type):
        self.disable_all_inputs()
        # 方案6：进入网格写回节流 + 当前执行行高亮模式（Worker 逐项写回按节拍批量落盘）
        grid = self.grids.get(exclude_doc_type)
        if grid and hasattr(grid, 'begin_operation_progress'):
            grid.begin_operation_progress()
        for dt in ['excel', 'word', 'ppt', 'pdf']:
            if dt in self.grids:
                self.grids[dt].Disable()
            if dt in self.execute_buttons:
                self.execute_buttons[dt].Disable()
            if dt in self.preview_buttons and dt != exclude_doc_type:
                self.preview_buttons[dt].Disable()
    
    def _enable_after_execute(self):
        self.enable_all_inputs()
        for dt in ['excel', 'word', 'ppt', 'pdf']:
            if dt in self.grids:
                # 方案6：同步落盘全部挂起写入并清除当前行高亮（完成后统计/展示依赖网格最新内容）
                if hasattr(self.grids[dt], 'end_operation_progress'):
                    self.grids[dt].end_operation_progress()
                self.grids[dt].Enable()
            if dt in self.execute_buttons:
                self.execute_buttons[dt].Enable()
            self._sync_preview_button_enabled(dt)
    
    def get_image_params(self, doc_type):
        input_width = self.image_width_inputs.get(doc_type)
        input_height = self.image_height_inputs.get(doc_type)
        if input_width and input_height:
            try:
                width = int(input_width.GetValue())
            except (ValueError, TypeError):
                width = 200
            try:
                height = int(input_height.GetValue())
            except (ValueError, TypeError):
                height = 200
            return {'width': width, 'height': height}
        return {'width': 200, 'height': 200}
    
    def get_table_column_widths(self, doc_type):
        grid = self.grids.get(doc_type)
        if grid and hasattr(grid, 'get_column_widths'):
            return grid.get_column_widths()
        return None
    
    def get_table_row_height(self, doc_type):
        grid = self.grids.get(doc_type)
        if grid and hasattr(grid, 'get_data_row_height'):
            return grid.get_data_row_height()
        return None
    
    def get_table_params(self, doc_type):
        input_cols = self.table_cols_inputs.get(doc_type)
        checkbox_tight = self.table_tight_checkboxes.get(doc_type)
        tight = checkbox_tight.GetValue() if checkbox_tight else False
        if doc_type == 'pdf':
            return {'cols': 'auto', 'tight': tight}
        if input_cols:
            try:
                cols = int(input_cols.GetValue())
            except (ValueError, TypeError):
                cols = 3
            return {'cols': cols, 'tight': tight}
        return {'cols': 3, 'tight': tight}
    
    def get_insert_position(self, doc_type):
        combo = self.insert_position_inputs.get(doc_type)
        if combo:
            return combo.GetValue()
        return "after_selected"
    
    def get_insert_position_index(self, doc_type):
        combo = self.insert_position_inputs.get(doc_type)
        if combo:
            return combo.GetSelection()
        return 0
    
    def get_total_width(self, doc_type):
        input_total_width = self.total_width_inputs.get(doc_type)
        if input_total_width:
            try:
                return float(input_total_width.GetValue())
            except (ValueError, TypeError):
                return 0.2
        return 0.2
    
    def get_all_params(self, doc_type):
        return {
            'operation_mode': self.get_operation_mode(doc_type),
            'fill_method': self.get_fill_method(doc_type),
            'image_params': self.get_image_params(doc_type),
            'table_params': self.get_table_params(doc_type),
            'insert_position_index': self.get_insert_position_index(doc_type),
            'insert_position': self.get_insert_position(doc_type),
            'total_width': self.get_total_width(doc_type),
            'table_column_widths': self.get_table_column_widths(doc_type),
            'table_row_height': self.get_table_row_height(doc_type)
        }
    
    def disable_all_inputs(self, exclude_doc_type=None):
        for dt in ['excel', 'word', 'ppt', 'pdf']:
            if dt == exclude_doc_type:
                continue
            if dt in self.operation_modes:
                self.operation_modes[dt].Disable()
            if dt in self.fill_methods:
                self.fill_methods[dt].Disable()
            if dt in self.image_panels:
                self.image_panels[dt].Disable()
            if dt in self.table_panels:
                self.table_panels[dt].Disable()
            if dt in self.insert_position_panels:
                self.insert_position_panels[dt].Disable()
            if dt in self.table_row_heights:
                self.table_row_heights[dt].Disable()
    
    def enable_all_inputs(self, exclude_doc_type=None):
        for dt in ['excel', 'word', 'ppt', 'pdf']:
            if dt == exclude_doc_type:
                continue
            self._enable_inputs_for_type(dt, check_conditions=False)
    
    def _enable_inputs_for_type(self, doc_type, check_conditions=True):
        if doc_type in self.operation_modes:
            self.operation_modes[doc_type].Enable()
        if doc_type in self.fill_methods:
            self.fill_methods[doc_type].Enable()
        if doc_type in self.image_panels:
            if not check_conditions:
                self.image_panels[doc_type].Enable()
            else:
                fill_method = self.get_fill_method(doc_type)
                is_image_mode = fill_method == 'add_image'
                if is_image_mode:
                    self.image_panels[doc_type].Enable()
        if doc_type in self.table_panels:
            if not check_conditions:
                self.table_panels[doc_type].Enable()
            else:
                fill_method = self.get_fill_method(doc_type)
                is_table_mode = fill_method == 'add_table'
                if is_table_mode:
                    self.table_panels[doc_type].Enable()
        if doc_type in self.insert_position_panels:
            if not check_conditions:
                self.insert_position_panels[doc_type].Enable()
            else:
                fill_method = self.get_fill_method(doc_type)
                is_add_mode = fill_method and 'add' in fill_method.lower()
                if is_add_mode:
                    self.insert_position_panels[doc_type].Enable()
        if doc_type in self.table_row_heights:
            if not check_conditions:
                self.table_row_heights[doc_type].Enable()
            else:
                fill_method = self.get_fill_method(doc_type)
                is_placeholder_or_title = fill_method in ('placeholder', 'title_fill')
                if is_placeholder_or_title:
                    self.table_row_heights[doc_type].Enable()
    
    def init_combo_box_mappings(self):
        """初始化ComboBox选项的索引映射"""
        self.operation_mode_mapping = {
            0: "create_from_template",
            1: "get_file_info"
        }
        
        self.excel_fill_method_mapping = {
            0: "placeholder",
            1: "title_fill"
        }
        
        self.word_fill_method_mapping = {
            0: "placeholder"
        }
        
        self.ppt_fill_method_mapping = {
            0: "placeholder"
        }
        
        self.pdf_fill_method_mapping = {
            0: "placeholder",
            1: "add_image",
            2: "add_text",
            3: "add_table",
            4: "delete_table"
        }
        
        self.fill_method_mappings = {
            'excel': self.excel_fill_method_mapping,
            'word': self.word_fill_method_mapping,
            'ppt': self.ppt_fill_method_mapping,
            'pdf': self.pdf_fill_method_mapping
        }
        
        self.content_type_mapping = {
            0: "multi_line_text",
            1: "local_table"
        }
        
        self.fill_direction_mapping = {
            0: "down",
            1: "right",
            2: "coordinate"
        }
        
        self.value_count_mapping = {
            0: "single_value",
            1: "multi_value",
            2: "image"
        }
        
        self.insert_position_mapping = {
            0: "all_any",
            1: "all_bottom_left",
            2: "all_bottom_right",
            3: "all_top_left",
            4: "all_top_right",
            5: "frame_any",
            6: "frame_bottom_left",
            7: "frame_bottom_right",
            8: "frame_top_left",
            9: "frame_top_right"
        }
    
    def get_combo_box_method(self, combo_box, mapping_dict):
        """通过索引获取ComboBox的方法键名"""
        if combo_box is None:
            return None
        selection = combo_box.GetSelection()
        if selection >= 0 and selection in mapping_dict:
            return mapping_dict[selection]
        return None
    
    def get_fill_method(self, doc_type):
        """获取填写方式的键名"""
        combo = self.fill_methods.get(doc_type)
        mapping = self.fill_method_mappings.get(doc_type)
        if combo and mapping:
            return self.get_combo_box_method(combo, mapping)
        return "placeholder"
    
    def get_operation_mode(self, doc_type):
        """获取操作模式的键名"""
        combo = self.operation_modes.get(doc_type)
        if combo:
            return self.get_combo_box_method(combo, self.operation_mode_mapping)
        return "create_from_template"
    
    def get_operation_mode_display(self, doc_type):
        """获取操作模式的显示文本"""
        combo = self.operation_modes.get(doc_type)
        if combo:
            return combo.GetValue()
        return ""
    
    def get_fill_method_display(self, doc_type):
        combo = self.fill_methods.get(doc_type)
        if combo:
            return combo.GetValue()
        return ""

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

    def _on_about_cards_size(self, event):
        event.Skip()
        wx.CallAfter(self._rewrap_about_card_descriptions)

    def _rewrap_about_card_descriptions(self):
        """让"更多效率工具"的两列卡片各占 50% 宽度，并按卡片可用宽度给工具描述换行"""
        labels = getattr(self, '_tool_card_desc_labels', None)
        if not labels:
            return
        container_w = self.tab_about.GetClientSize().width
        card_w = max(self.spx_calc(150), (container_w - self.spx_calc(60)) // 2)
        # 扣除卡片内左侧图标列、图标与文字间距、右侧下载图标及其边距
        avail = max(self.spx_calc(80), card_w - self.spx_calc(115))
        if getattr(self, '_tool_card_wrap_width', None) == avail:
            return
        self._tool_card_wrap_width = avail
        for label, original in labels:
            label.SetLabel(_wrap_text_to_width(original, label.GetFont(), avail))
        self.tab_about.Layout()

    def _build_about_tab(self):
        self.tab_about = wx.Panel(self.notebook)
        self.tab_about.SetBackgroundColour(wx.Colour(248, 248, 248))
        sizer = wx.BoxSizer(wx.VERTICAL)
        row1 = wx.BoxSizer(wx.HORIZONTAL)
        title_text = translate("label_title")
        label_title = wx.StaticText(self.tab_about, label=title_text)
        font_title = label_title.GetFont()
        font_title.SetPointSize(int(font_title.GetPointSize() * 1.4))
        font_title.SetWeight(wx.FONTWEIGHT_BOLD)
        label_title.SetFont(font_title)
        label_title.SetForegroundColour((0, 51, 102))
        self._apply_measured_min_size(label_title, title_text, font_title)
        row1.Add(label_title, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 20)
        row1.AddStretchSpacer()
        sizer.Add(row1, 0, wx.EXPAND | wx.TOP, 20)
        row2 = wx.BoxSizer(wx.HORIZONTAL)
        label_intro = wx.StaticText(self.tab_about, label=translate("label_intro"))
        font_intro = label_intro.GetFont()
        font_intro.SetPointSize(int(font_intro.GetPointSize() * 0.95))
        label_intro.SetFont(font_intro)
        label_intro.SetForegroundColour((80, 80, 80))
        row2.Add(label_intro, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 20)
        row2.AddStretchSpacer()
        sizer.Add(row2, 0, wx.EXPAND | wx.TOP, 5)
        row3 = wx.BoxSizer(wx.HORIZONTAL)
        label_website = wx.StaticText(self.tab_about, label=translate("label_website"))
        font_website = label_website.GetFont()
        font_website.SetPointSize(int(font_website.GetPointSize() * 0.9))
        label_website.SetFont(font_website)
        label_website.SetForegroundColour((0, 102, 204))
        label_website.Bind(wx.EVT_LEFT_DOWN, lambda event: self.on_tool_click("https://tabulexflow.com"))
        self._bind_link_cursor(label_website, self.tab_about)
        row3.Add(label_website, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 20)
        row3.AddStretchSpacer()
        label_feedback = wx.StaticText(self.tab_about, label=translate("label_feedback"))
        font_feedback = label_feedback.GetFont()
        font_feedback.SetPointSize(int(font_feedback.GetPointSize() * 0.9))
        label_feedback.SetFont(font_feedback)
        label_feedback.SetForegroundColour((0, 102, 204))
        label_feedback.Bind(wx.EVT_LEFT_DOWN, lambda event: self.on_tool_click("https://tabulexflow.com/feedback"))
        self._bind_link_cursor(label_feedback, self.tab_about)
        row3.Add(label_feedback, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 20)
        sizer.Add(row3, 0, wx.EXPAND | wx.TOP, 5)
        separator = wx.Panel(self.tab_about, size=(-1, self.spx_calc(12)))
        separator.SetBackgroundColour(wx.Colour(230, 230, 230))
        sizer.Add(separator, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, self.spx_calc(15))
        sizer_more_title = wx.BoxSizer(wx.HORIZONTAL)
        label_tools_title = wx.StaticText(self.tab_about, label=translate("label_tools_title"))
        font_tools_title = label_tools_title.GetFont()
        font_tools_title.SetPointSize(int(font_tools_title.GetPointSize() * 1.4))
        font_tools_title.SetWeight(wx.FONTWEIGHT_BOLD)
        label_tools_title.SetFont(font_tools_title)
        label_tools_title.SetForegroundColour((0, 51, 102))
        self._apply_measured_min_size(label_tools_title, translate("label_tools_title"), font_tools_title)
        sizer_more_title.Add(label_tools_title, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(20))
        sizer_more_title.AddStretchSpacer()
        sizer.Add(sizer_more_title, 0, wx.EXPAND | wx.TOP, self.spx_calc(10))
        sizer_more_tools = wx.BoxSizer(wx.VERTICAL)
        tool_data = [
            ("📁", (0, 102, 204), "label_tool1_name", "label_tool1_desc"),
            ("🔄", (0, 150, 255), "label_tool2_name", "label_tool2_desc"),
            ("📦", (0, 180, 150), "label_tool3_name", "label_tool3_desc"),
            ("🌟", (255, 200, 50), "label_tool4_name", "label_tool4_desc"),
        ]
        panels = []
        desc_labels = []
        for i, (icon, color, name_key, desc_key) in enumerate(tool_data):
            panel = tdc_RoundedPanel(self.tab_about, radius=4, border_colour=(220, 220, 220), background_colour=wx.WHITE)
            panel.SetBackgroundColour(wx.WHITE)
            panel.SetMinSize((self.spx_calc(120), self.spx_calc(70)))
            sizer_tool = wx.BoxSizer(wx.HORIZONTAL)
            label_icon = wx.StaticText(panel, label=icon)
            label_icon.SetBackgroundColour(wx.WHITE)
            font_icon = label_icon.GetFont()
            font_icon.SetPointSize(int(font_icon.GetPointSize() * 3.0))
            label_icon.SetFont(font_icon)
            label_icon.SetForegroundColour(color)
            self._apply_measured_min_size(label_icon, icon, font_icon)
            sizer_right = wx.BoxSizer(wx.VERTICAL)
            label_name = wx.StaticText(panel, label=translate(name_key))
            label_name.SetBackgroundColour(wx.WHITE)
            font_name = label_name.GetFont()
            font_name.SetWeight(wx.FONTWEIGHT_BOLD)
            label_name.SetFont(font_name)
            label_name.SetForegroundColour((0, 51, 102))
            self._apply_measured_min_size(label_name, translate(name_key), font_name)
            sizer_desc_row = wx.BoxSizer(wx.HORIZONTAL)
            label_desc = wx.StaticText(panel, label=translate(desc_key))
            label_desc.SetBackgroundColour(wx.WHITE)
            font_desc = label_desc.GetFont()
            font_desc.SetPointSize(int(font_desc.GetPointSize() * 0.85))
            label_desc.SetFont(font_desc)
            label_desc.SetForegroundColour((100, 100, 100))
            desc_labels.append((label_desc, translate(desc_key)))
            sizer_desc_row.Add(label_desc, 1, wx.ALIGN_CENTER_VERTICAL)
            label_download = wx.StaticText(panel, label="⏬")
            label_download.SetBackgroundColour(wx.WHITE)
            label_download.SetForegroundColour((0, 102, 204))
            label_download.SetToolTip(translate("tooltip_download"))
            label_download.Bind(wx.EVT_LEFT_DOWN, lambda event, url="https://tabulexflow.com/download": self.on_tool_click(url))
            self._bind_link_cursor(label_download, panel)
            sizer_desc_row.Add(label_download, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, self.spx_calc(5))
            sizer_right.Add(label_name, 0, wx.ALIGN_LEFT | wx.TOP, self.spx_calc(2))
            sizer_right.Add(sizer_desc_row, 1, wx.EXPAND | wx.BOTTOM, self.spx_calc(2))
            sizer_tool.Add(label_icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(15))
            sizer_tool.Add(sizer_right, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.spx_calc(10))
            panel.SetSizer(sizer_tool)
            panels.append(panel)
        sizer_row1 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_row1.Add(panels[0], 1, wx.EXPAND | wx.LEFT | wx.RIGHT, self.spx_calc(10))
        sizer_row1.Add(panels[1], 1, wx.EXPAND | wx.LEFT | wx.RIGHT, self.spx_calc(10))
        sizer_row2 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_row2.Add(panels[2], 1, wx.EXPAND | wx.LEFT | wx.RIGHT, self.spx_calc(10))
        sizer_row2.Add(panels[3], 1, wx.EXPAND | wx.LEFT | wx.RIGHT, self.spx_calc(10))
        sizer_more_tools.Add(sizer_row1, 1, wx.EXPAND)
        sizer_more_tools.Add(sizer_row2, 1, wx.EXPAND | wx.TOP, self.spx_calc(10))
        sizer.Add(sizer_more_tools, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, self.spx_calc(10))
        self.tab_about.SetSizer(sizer)
        # 全部控件尺寸修正后统一再次布局（覆盖wxGTK首次布局使用的过期尺寸缓存）
        wx.CallAfter(self.tab_about.Layout)
        # 两列卡片等宽；工具描述按卡片可用宽度换行（容器尺寸变化时重新换行）
        self._tool_card_desc_labels = desc_labels
        self._tool_card_wrap_width = -1
        self.tab_about.Bind(wx.EVT_SIZE, self._on_about_cards_size)
        wx.CallAfter(self._rewrap_about_card_descriptions)
        self.notebook.AddPage(self.tab_about, translate('tab_about'))

    def on_tool_click(self, url):
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

class tdc_RoundedPanel(wx.Panel):
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

def create_tool(parent, user_setting_base_dir=None):
    return tdc_TabulexDocCreatorTool(parent)
