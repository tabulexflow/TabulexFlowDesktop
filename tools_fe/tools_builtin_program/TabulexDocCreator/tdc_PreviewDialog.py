# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import sys
import os
_tool_dir = os.path.dirname(os.path.abspath(__file__))
if _tool_dir not in sys.path:
    sys.path.insert(0, _tool_dir)

import wx
import wx.grid
import io
from tdc_i18n_manager import translate
from tdc_logger import log_info, log_error, log_warning, log_debug

try:
    import wx.richtext
    HAS_RICHTEXT = True
except ImportError:
    HAS_RICHTEXT = False

class tdc_BorderCellRenderer(wx.grid.GridCellStringRenderer):
    def __init__(self, border_info=None, bg_color=None, alignment=None, font_color=None):
        super().__init__()
        self.border_info = border_info or {}
        self.bg_color = bg_color
        self.alignment = alignment or {}
        self.font_color = font_color
    
    def Draw(self, grid, attr, dc, rect, row, col, isSelected):
        if attr is None:
            attr = wx.grid.GridCellAttr()
        if self.bg_color:
            attr.SetBackgroundColour(self.bg_color)
        else:
            attr.SetBackgroundColour(wx.WHITE)
        if self.font_color:
            try:
                if isinstance(self.font_color, str) and len(self.font_color) >= 6:
                    r = int(self.font_color[-6:-4], 16)
                    g = int(self.font_color[-4:-2], 16)
                    b = int(self.font_color[-2:], 16)
                    attr.SetTextColour(wx.Colour(r, g, b))
            except (ValueError, TypeError):
                pass
        super().Draw(grid, attr, dc, rect, row, col, isSelected)
        dc.SetPen(wx.Pen(wx.BLACK, 1))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        has_top = self.border_info.get('top')
        has_bottom = self.border_info.get('bottom')
        has_left = self.border_info.get('left')
        has_right = self.border_info.get('right')
        if has_top:
            dc.DrawLine(rect.x, rect.y, rect.x + rect.width + 1, rect.y)
        if has_left:
            dc.DrawLine(rect.x, rect.y, rect.x, rect.y + rect.height + 1)
        if has_bottom:
            dc.DrawLine(rect.x, rect.y + rect.height, rect.x + rect.width, rect.y + rect.height)
        if has_right:
            dc.DrawLine(rect.x + rect.width, rect.y, rect.x + rect.width, rect.y + rect.height)

class tdc_PreviewDialog(wx.Dialog):
    def __init__(self, parent, tool_instance, doc_type, data, current_index):
        # DPI缩放支持
        self.TFP_DPI_SCALE_FACTOR = getattr(tool_instance, 'TFP_DPI_SCALE_FACTOR', 1.0)
        super().__init__(parent, title=translate('preview_title'), size=(int(900 * self.TFP_DPI_SCALE_FACTOR), int(700 * self.TFP_DPI_SCALE_FACTOR)), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX)
        self.tool_instance = tool_instance
        self.doc_type = doc_type
        self.data = data
        self.current_index = current_index
        self.preview_cache = {}
        self.save_file_indices = []
        self.current_file_index = 0
        self._init_ui()
        self._load_preview()
    
    def _get_params(self):
        if hasattr(self.tool_instance, 'get_all_params'):
            return self.tool_instance.get_all_params(self.doc_type)
        return {}
    
    def _init_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_toolbar = wx.BoxSizer(wx.HORIZONTAL)
        self.label_file = wx.StaticText(self, label=translate('preview_label_file'))
        self.text_file = wx.StaticText(self, label='', style=wx.ST_NO_AUTORESIZE)
        self.text_file.SetFont(wx.Font(int(10 * self.TFP_DPI_SCALE_FACTOR), wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self._populate_file_list()
        current_save_file = None
        for row in self.data:
            if row.get('row_index') == self.current_index:
                current_save_file = row.get('save_file', '')
                break
        if not current_save_file:
            for row in self.data:
                save_file = row.get('save_file', '')
                if save_file and save_file.strip():
                    current_save_file = save_file
                    break
        initial_file_index = 0
        if current_save_file and self.save_file_indices:
            for i, idx in enumerate(self.save_file_indices):
                if self.data[idx].get('save_file', '') == current_save_file:
                    initial_file_index = i
                    self.current_index = idx
                    break
        self.current_file_index = initial_file_index
        self._update_file_display()
        btn_prev = wx.Button(self, label=translate('preview_btn_prev'))
        btn_prev.Bind(wx.EVT_BUTTON, self._on_prev)
        btn_next = wx.Button(self, label=translate('preview_btn_next'))
        btn_next.Bind(wx.EVT_BUTTON, self._on_next)
        sizer_toolbar.Add(self.label_file, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, int(5 * self.TFP_DPI_SCALE_FACTOR))
        sizer_toolbar.Add(self.text_file, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, int(10 * self.TFP_DPI_SCALE_FACTOR))
        sizer_toolbar.Add(btn_prev, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, int(5 * self.TFP_DPI_SCALE_FACTOR))
        sizer_toolbar.Add(btn_next, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(sizer_toolbar, 0, wx.EXPAND | wx.ALL, int(10 * self.TFP_DPI_SCALE_FACTOR))
        self.preview_panel = wx.Panel(self)
        self.preview_sizer = wx.BoxSizer(wx.VERTICAL)
        self.preview_panel.SetSizer(self.preview_sizer)
        sizer.Add(self.preview_panel, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, int(10 * self.TFP_DPI_SCALE_FACTOR))
        sizer_btn = wx.BoxSizer(wx.HORIZONTAL)
        self.label_current_cell = wx.StaticText(self, label=translate('preview_current_cell').format(''))
        sizer_btn.Add(self.label_current_cell, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer_btn.AddStretchSpacer()
        btn_close = wx.Button(self, label=translate('preview_btn_close'))
        btn_close.Bind(wx.EVT_BUTTON, self._on_close)
        sizer_btn.Add(btn_close, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(sizer_btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, int(10 * self.TFP_DPI_SCALE_FACTOR))
        self.SetSizer(sizer)
        self.Centre()
    
    def _populate_file_list(self):
        save_files = []
        save_file_indices = []
        for i, row in enumerate(self.data):
            save_file = row.get('save_file', '')
            if save_file and save_file.strip() and save_file not in save_files:
                save_files.append(save_file)
                save_file_indices.append(i)
        self.save_file_indices = save_file_indices
        self.save_files = save_files
    
    def _update_file_display(self):
        if self.save_files and 0 <= self.current_file_index < len(self.save_files):
            display_name = os.path.basename(self.save_files[self.current_file_index])
            self.text_file.SetLabel(display_name)
    
    def _on_prev(self, event):
        if self.current_file_index > 0:
            self.current_file_index -= 1
            self.current_index = self.save_file_indices[self.current_file_index]
            self._update_file_display()
            self._load_preview()
    
    def _on_next(self, event):
        if self.current_file_index < len(self.save_file_indices) - 1:
            self.current_file_index += 1
            self.current_index = self.save_file_indices[self.current_file_index]
            self._update_file_display()
            self._load_preview()
    
    def _on_close(self, event):
        self.EndModal(wx.ID_CLOSE)
    
    def _clear_preview(self):
        for child in self.preview_panel.GetChildren():
            child.Destroy()
        self.preview_panel.Layout()
    
    def _load_preview(self):
        self._clear_preview()
        if self.current_index < 0 or self.current_index >= len(self.data):
            return
        self.label_current_cell.SetLabel(translate('preview_current_cell').format(''))
        row_data = self.data[self.current_index]
        target_save_file = row_data.get('save_file', '')
        target_source_file = row_data.get('source_file', '')
        if not target_save_file or not target_save_file.strip():
            for i in range(self.current_index, -1, -1):
                r_save = self.data[i].get('save_file', '')
                if r_save and r_save.strip():
                    target_save_file = r_save
                    target_source_file = self.data[i].get('source_file', '')
                    break
        if not target_save_file or not target_save_file.strip():
            return
        related_rows = []
        for r in self.data:
            r_save = r.get('save_file', '')
            r_source = r.get('source_file', '')
            if r_save and r_save.strip():
                if r_save == target_save_file:
                    related_rows.append(r)
            else:
                inherited_save = None
                inherited_source = None
                row_idx = r.get('row_index', 0)
                for i in range(len(self.data) - 1, -1, -1):
                    check_row = self.data[i]
                    check_idx = check_row.get('row_index', 0)
                    if check_idx < row_idx:
                        check_save = check_row.get('save_file', '')
                        check_source = check_row.get('source_file', '')
                        if check_save and check_save.strip():
                            inherited_save = check_save
                            inherited_source = check_source
                            break
                if inherited_save == target_save_file:
                    related_rows.append(r)
        if self.doc_type == 'excel':
            self._load_excel_preview(related_rows)
        elif self.doc_type == 'word':
            self._load_word_preview(related_rows)
        elif self.doc_type == 'ppt':
            self._load_ppt_preview(related_rows)
        elif self.doc_type == 'pdf':
            self._load_pdf_preview(related_rows)
        self.preview_panel.Layout()
    
    def _load_excel_preview(self, rows_data):
        try:
            from tdc_ExcelWorker import tdc_ExcelWorker
            fill_method = self._get_current_fill_method()
            params = self._get_params()
            worker = tdc_ExcelWorker(self.tool_instance, rows_data, 0, fill_method, params)
            preview_data = worker.preview(rows_data)
            if preview_data and preview_data.get('data'):
                grid = wx.grid.Grid(self.preview_panel)
                data = preview_data['data']
                max_rows = min(len(data), 50)
                max_cols = max(len(row) for row in data) if data else 0
                max_cols = min(max_cols, 30)
                grid.CreateGrid(max_rows, max_cols)
                for row_idx, row in enumerate(data[:max_rows]):
                    for col_idx, value in enumerate(row[:max_cols]):
                        if value is not None:
                            grid.SetCellValue(row_idx, col_idx, str(value))
                grid.SetColLabelSize(int(20 * self.TFP_DPI_SCALE_FACTOR))
                grid.SetRowLabelSize(int(40 * self.TFP_DPI_SCALE_FACTOR))
                grid.EnableEditing(False)
                grid.Bind(wx.grid.EVT_GRID_SELECT_CELL, self._on_grid_cell_selected)
                format_info = preview_data.get('format', {})
                self._apply_excel_format(grid, format_info, max_rows, max_cols)
                self.preview_sizer.Add(grid, 1, wx.EXPAND)
            elif preview_data and preview_data.get('error'):
                # 文件类型与当前 Tab 不符等已知原因：直接显示明确提示
                self._show_error_message(preview_data['error'], show_prefix=False)
            else:
                self._show_error_message(translate('preview_load_failed', tab=translate('tab_excel')))
        except Exception as e:
            import traceback
            log_error(traceback.format_exc())
            self._show_error_message(str(e))
    
    def _on_grid_cell_selected(self, event):
        grid = event.GetEventObject()
        row = event.GetRow()
        col = event.GetCol()
        value = grid.GetCellValue(row, col) if row >= 0 and col >= 0 else ''
        self.label_current_cell.SetLabel(translate('preview_current_cell').format(value if value else ''))
        event.Skip()
    
    def _apply_excel_format(self, grid, format_info, max_rows, max_cols):
        row_heights = format_info.get('row_heights', {})
        for row_idx, height in row_heights.items():
            row_idx = int(row_idx)
            grid_row = row_idx - 1
            if 0 <= grid_row < max_rows:
                scaled_height = max(int(height * 1.2 * self.TFP_DPI_SCALE_FACTOR), int(20 * self.TFP_DPI_SCALE_FACTOR))
                grid.SetRowSize(grid_row, scaled_height)
        col_widths = format_info.get('col_widths', {})
        for col_idx, width in col_widths.items():
            col_idx = int(col_idx)
            grid_col = col_idx - 1
            if 0 <= grid_col < max_cols:
                scaled_width = max(int(width * 7.5 * self.TFP_DPI_SCALE_FACTOR), int(20 * self.TFP_DPI_SCALE_FACTOR))
                grid.SetColSize(grid_col, scaled_width)
        hidden_rows = format_info.get('hidden_rows', [])
        for row_idx in hidden_rows:
            grid_row = row_idx - 1
            if 0 <= grid_row < max_rows:
                grid.HideRow(grid_row)
        hidden_cols = format_info.get('hidden_cols', [])
        for col_idx in hidden_cols:
            grid_col = col_idx - 1
            if 0 <= grid_col < max_cols:
                grid.HideCol(grid_col)
        cell_backgrounds = format_info.get('cell_backgrounds', {})
        cell_borders = format_info.get('cell_borders', {})
        cell_alignments = format_info.get('cell_alignments', {})
        cell_font_colors = format_info.get('cell_font_colors', {})
        merged_cells = format_info.get('merged_cells', [])
        merged_positions = set()
        merge_start_positions = {}
        merge_borders = {}
        for merge_info in merged_cells:
            min_row = merge_info['min_row'] - 1
            max_row = merge_info['max_row'] - 1
            min_col = merge_info['min_col'] - 1
            max_col = merge_info['max_col'] - 1
            for r in range(min_row, max_row + 1):
                for c in range(min_col, max_col + 1):
                    if r != min_row or c != min_col:
                        merged_positions.add((r, c))
            merge_start_positions[(min_row, min_col)] = (max_row - min_row + 1, max_col - min_col + 1)
            merged_border = {'top': False, 'bottom': False, 'left': False, 'right': False}
            for r in range(min_row, max_row + 1):
                left_key = f'{r + 1},{min_col + 1}'
                if cell_borders.get(left_key, {}).get('left'):
                    merged_border['left'] = True
                right_key = f'{r + 1},{max_col + 1}'
                if cell_borders.get(right_key, {}).get('right'):
                    merged_border['right'] = True
            for c in range(min_col, max_col + 1):
                top_key = f'{min_row + 1},{c + 1}'
                if cell_borders.get(top_key, {}).get('top'):
                    merged_border['top'] = True
                bottom_key = f'{max_row + 1},{c + 1}'
                if cell_borders.get(bottom_key, {}).get('bottom'):
                    merged_border['bottom'] = True
            merge_borders[(min_row, min_col)] = merged_border
        for grid_row in range(max_rows):
            for grid_col in range(max_cols):
                row_idx = grid_row + 1
                col_idx = grid_col + 1
                key = f'{row_idx},{col_idx}'
                bg_color = cell_backgrounds.get(key)
                border_info = cell_borders.get(key, {})
                align_info = cell_alignments.get(key, {})
                font_color_str = cell_font_colors.get(key)
                font_color = None
                if font_color_str:
                    font_color = self._parse_excel_color(font_color_str)
                color = None
                if bg_color:
                    color = self._parse_excel_color(bg_color)
                if (grid_row, grid_col) in merged_positions:
                    attr = wx.grid.GridCellAttr()
                    attr.SetBackgroundColour(wx.WHITE)
                    grid.SetAttr(grid_row, grid_col, attr)
                    continue
                if (grid_row, grid_col) in merge_borders:
                    border_info = merge_borders[(grid_row, grid_col)].copy()
                else:
                    border_info = cell_borders.get(key, {}).copy()
                if grid_col > 0:
                    left_key = f'{row_idx},{col_idx - 1}'
                    left_border = cell_borders.get(left_key, {})
                    if left_border.get('right') and not border_info.get('left'):
                        border_info['left'] = left_border['right']
                if grid_row > 0:
                    top_key = f'{row_idx - 1},{col_idx}'
                    top_border = cell_borders.get(top_key, {})
                    if top_border.get('bottom') and not border_info.get('top'):
                        border_info['top'] = top_border['bottom']
                attr = wx.grid.GridCellAttr()
                if color:
                    attr.SetBackgroundColour(color)
                else:
                    attr.SetBackgroundColour(wx.WHITE)
                if font_color:
                    attr.SetTextColour(font_color)
                if border_info:
                    renderer = tdc_BorderCellRenderer(border_info, color, align_info, font_color_str)
                    attr.SetRenderer(renderer)
                h_align = align_info.get('h', '')
                v_align = align_info.get('v', '')
                wx_h_align = wx.ALIGN_LEFT
                wx_v_align = wx.ALIGN_CENTER
                if h_align == 'center':
                    wx_h_align = wx.ALIGN_CENTER
                elif h_align == 'right':
                    wx_h_align = wx.ALIGN_RIGHT
                if v_align == 'top':
                    wx_v_align = wx.ALIGN_TOP
                elif v_align == 'bottom':
                    wx_v_align = wx.ALIGN_BOTTOM
                attr.SetAlignment(wx_h_align, wx_v_align)
                grid.SetAttr(grid_row, grid_col, attr)
        for (min_row, min_col), (num_rows, num_cols) in merge_start_positions.items():
            if 0 <= min_row < max_rows and 0 <= min_col < max_cols:
                if num_rows > 1 or num_cols > 1:
                    grid.SetCellSize(min_row, min_col, num_rows, num_cols)
    
    def _parse_excel_color(self, color_str):
        try:
            if isinstance(color_str, str):
                if color_str.startswith('00') and len(color_str) == 8:
                    r = int(color_str[2:4], 16)
                    g = int(color_str[4:6], 16)
                    b = int(color_str[6:8], 16)
                    return wx.Colour(r, g, b)
                elif len(color_str) == 6:
                    r = int(color_str[0:2], 16)
                    g = int(color_str[2:4], 16)
                    b = int(color_str[4:6], 16)
                    return wx.Colour(r, g, b)
                elif len(color_str) == 8:
                    r = int(color_str[2:4], 16)
                    g = int(color_str[4:6], 16)
                    b = int(color_str[6:8], 16)
                    return wx.Colour(r, g, b)
        except Exception:
            pass
        return None
    
    def _load_word_preview(self, rows_data):
        try:
            from tdc_WordWorker import tdc_WordWorker
            params = self._get_params()
            worker = tdc_WordWorker(self.tool_instance, rows_data, 0, 'placeholder', params)
            preview_data = worker.preview(rows_data)
            if preview_data and preview_data.get('text'):
                if HAS_RICHTEXT:
                    richtext = wx.richtext.RichTextCtrl(self.preview_panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.VSCROLL)
                    richtext.SetValue(preview_data['text'])
                else:
                    richtext = wx.TextCtrl(self.preview_panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.VSCROLL)
                    richtext.SetValue(preview_data['text'])
                self.preview_sizer.Add(richtext, 1, wx.EXPAND)
            elif preview_data and preview_data.get('error'):
                # .doc 等已知不支持的情况：直接显示 Worker 返回的明确原因，不再叠加通用前缀
                self._show_error_message(preview_data['error'], show_prefix=False)
            else:
                self._show_error_message(translate('preview_load_failed', tab=translate('tab_word')))
        except Exception as e:
            log_error(f'Word preview error: {e}')
            self._show_error_message(str(e))
    
    def _load_ppt_preview(self, rows_data):
        try:
            from tdc_PowerPointWorker import tdc_PowerPointWorker
            params = self._get_params()
            worker = tdc_PowerPointWorker(self.tool_instance, rows_data, 0, 'placeholder', params)
            preview_data = worker.preview(rows_data)
            if preview_data and preview_data.get('slides'):
                slides_text = preview_data['slides']
                notebook = wx.Notebook(self.preview_panel)
                for i, slide_text in enumerate(slides_text):
                    page = wx.Panel(notebook)
                    sizer = wx.BoxSizer(wx.VERTICAL)
                    text_ctrl = wx.TextCtrl(page, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.VSCROLL)
                    text_ctrl.SetValue(slide_text)
                    sizer.Add(text_ctrl, 1, wx.EXPAND)
                    page.SetSizer(sizer)
                    notebook.AddPage(page, f'Slide {i+1}')
                self.preview_sizer.Add(notebook, 1, wx.EXPAND)
            elif preview_data and preview_data.get('error'):
                # .ppt 等已知不支持的情况：直接显示 Worker 返回的明确原因，不再叠加通用前缀
                self._show_error_message(preview_data['error'], show_prefix=False)
            else:
                self._show_error_message(translate('preview_load_failed', tab=translate('tab_ppt')))
        except Exception as e:
            log_error(f'PowerPoint preview error: {e}')
            self._show_error_message(str(e))
    
    def _load_pdf_preview(self, rows_data):
        try:
            from tdc_PDFWorker import tdc_PDFWorker
            fill_method = self._get_current_fill_method()
            params = self._get_params()
            log_debug(f'Loading PDF preview with fill_method: {fill_method}')
            worker = tdc_PDFWorker(self.tool_instance, rows_data, 0, fill_method, params)
            preview_data = worker.preview(rows_data)
            log_debug(f'Preview data returned: {type(preview_data)}')
            if preview_data and preview_data.get('images'):
                images = preview_data['images']
                log_debug(f'Number of images: {len(images)}')
                notebook = wx.Notebook(self.preview_panel)
                for i, img_data in enumerate(images):
                    log_debug(f'Image {i} type: {type(img_data)}, size: {len(img_data) if img_data else 0}')
                    page_panel = wx.Panel(notebook)
                    sizer = wx.BoxSizer(wx.VERTICAL)
                    scroll = wx.ScrolledWindow(page_panel)
                    scroll_sizer = wx.BoxSizer(wx.VERTICAL)
                    img_stream = io.BytesIO(img_data)
                    img = wx.Image(img_stream, wx.BITMAP_TYPE_PNG)
                    if not img.IsOk():
                        log_error(f'Failed to create image for page {i}')
                        continue
                    bitmap = wx.Bitmap(img)
                    static_bitmap = wx.StaticBitmap(scroll, bitmap=bitmap)
                    scroll_sizer.Add(static_bitmap, 0, wx.ALIGN_CENTER)
                    scroll.SetSizer(scroll_sizer)
                    scroll.SetScrollbars(1, 1, bitmap.GetWidth(), bitmap.GetHeight())
                    sizer.Add(scroll, 1, wx.EXPAND)
                    page_panel.SetSizer(sizer)
                    notebook.AddPage(page_panel, translate('preview_page_tab', n=i + 1))
                self.preview_sizer.Add(notebook, 1, wx.EXPAND)
            else:
                log_error(f'PDF preview returned no data. preview_data={preview_data}')
                self._show_error_message(translate('preview_load_failed', tab=translate('tab_pdf')))
        except Exception as e:
            import traceback
            log_error(f'PDF preview error: {e}')
            log_error(traceback.format_exc())
            self._show_error_message(str(e))
    
    def _get_current_fill_method(self):
        if self.tool_instance and hasattr(self.tool_instance, 'get_fill_method'):
            return self.tool_instance.get_fill_method(self.doc_type)
        return 'placeholder'
    
    def _show_error_message(self, message, show_prefix=True):
        label = f'{translate("msg_preview_error")}: {message}' if show_prefix else message
        static_text = wx.StaticText(self.preview_panel, label=label)
        static_text.SetForegroundColour(wx.RED)
        self.preview_sizer.Add(static_text, 1, wx.ALIGN_CENTER)
