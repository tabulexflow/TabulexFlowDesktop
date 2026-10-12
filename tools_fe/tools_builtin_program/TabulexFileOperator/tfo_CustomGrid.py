# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
import wx.grid
import os
import re
import ctypes
import datetime
import subprocess
import threading
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter
import openpyxl
from tfo_utils.tfo_i18n_manager import translate, i18n
from tfo_utils.tfo_logger import log_info, log_error, log_warning, log_debug
from tfo_utils.tfo_base_grid import tfo_BaseGrid
from tfp_toolkit.tfp_dpi import spx_calc

# 可执行/可运行代码的扩展名：通过"打开此项"打开前必须二次确认（A5-1 安全修复）
# 路径来自可编辑表格，可能被粘贴恶意路径，直接交给系统关联程序执行存在风险
_EXECUTABLE_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".scr", ".msi", ".ps1",
    ".com", ".pif", ".vbs", ".js", ".jse", ".wsf", ".wsh", ".msc",
    ".jar", ".app", ".dmg", ".sh", ".bin", ".run", ".reg", ".lnk",
}

class tfo_CustomGrid(tfo_BaseGrid):
    """TabulexFileOperator 自定义 Grid，继承 tfo_BaseGrid 基类

    基类提供：键盘快捷键（Ctrl+C/V/A/Z/Y, Delete, Enter, Tab）、复制/粘贴、
    撤销/重做（增量 Delta 机制）、行/列标签右键菜单、单元格右键菜单、只读模式等。

    本类保留 BFM 特有的业务逻辑：
    - 列定义（旧路径、新路径、匹配名等 13 列）
    - 粘贴后处理（process_after_paste：联动清空非编辑列、去重、调整行数）
    - 清空单元格联动（清空新路径列时联动清空非编辑列）
    - 排序、搜索、导入/导出、拖放等
    - 自定义右键菜单（打开文件、复制路径、导入导出、搜索等）
    """

    COL_OLD_PATH = 0
    COL_NEW_PATH = 1
    COL_MATCH_NAME = 2
    COL_RESULT = 3
    COL_PARENT_DIR = 4
    COL_FILE_NAME = 5
    COL_LEVEL = 6
    COL_TYPE = 7
    COL_SIZE = 8
    COL_CREATE_TIME = 9
    COL_MODIFY_TIME = 10
    COL_HIDDEN = 11
    COL_READONLY = 12
    COL_COUNT = 13

    def __init__(self, parent, frame, callbacks=None, editable=True):
        super().__init__(parent)
        self.frame = frame
        self.callbacks = callbacks or {}
        self.editable = editable
        # 方案6/3（进度可见性）：执行期间的网格写回节流 + 当前执行行高亮。
        # Worker 线程逐行写结果若直接 wx.CallAfter，会为每一行投递一个事件，行数大时
        # 淹没事件队列，导致状态栏/网格进度刷新被"饿死"（观感上完全看不到进度）。
        # queue_cell_value 改为写入合并队列，由主线程按事件循环节拍批量落盘，
        # 同名 (row,col) 只保留最后一次值；同时把最近写入"执行结果"列的行整行高亮。
        self._pending_writes = {}
        self._pending_lock = threading.Lock()
        self._flush_scheduled = False
        self._progress_active = False
        self._pending_highlight_row = -1
        self._highlight_row = -1
        # DPI缩放支持
        self.TFP_DPI_SCALE_FACTOR = getattr(frame, 'TFP_DPI_SCALE_FACTOR', 1.0)
        self._spx = lambda v: spx_calc(v) if v != -1 else -1
        read_only_bg_color = wx.Colour(247, 247, 247)
        # 搜索相关变量
        self.search_dialog = None
        self.search_text = ""
        self.search_results = []
        self.current_search_index = -1
        self.last_search_text = ""
        # 定义列名、默认宽度，是否可编辑，对齐方式（调整后顺序）
        self.default_col_labels = [translate("grid_col_old_path"), translate("grid_col_new_path"), translate("grid_col_match_name"), translate("grid_col_result"), translate("grid_col_parent_dir"), translate("grid_col_file_name"), translate("grid_col_level"),
                translate("grid_col_type"), translate("grid_col_size"), translate("grid_col_create_time"), translate("grid_col_modify_time"), translate("grid_col_hidden"), translate("grid_col_readonly")]
        self.default_col_widths = [self._spx(220), self._spx(220), self._spx(85), self._spx(180), self._spx(110), self._spx(190), self._spx(50), self._spx(60), self._spx(80), self._spx(140), self._spx(140), self._spx(60), self._spx(60)]  # 调整宽度
        self.default_export_widths = [45, 45, 12, 13, 15, 28, 4, 7, 12, 11, 11, 4, 5]  # 调整导出宽度
        # 注意：第3列（匹配名）现在为只读（False），第0列（文件或目录名）保持只读
        self.default_col_editables = [True, True, True, False, False, False, False, False, False, False, False, False, False]
        self.default_col_aligns = [wx.ALIGN_RIGHT, wx.ALIGN_RIGHT, wx.ALIGN_CENTER, wx.ALIGN_LEFT,
                wx.ALIGN_CENTER, wx.ALIGN_LEFT, wx.ALIGN_CENTER, wx.ALIGN_CENTER, wx.ALIGN_RIGHT, wx.ALIGN_CENTER,
                wx.ALIGN_CENTER, wx.ALIGN_CENTER, wx.ALIGN_CENTER]
        self.default_export_aligns = [wx.ALIGN_LEFT, wx.ALIGN_LEFT, wx.ALIGN_CENTER, wx.ALIGN_LEFT,
                wx.ALIGN_CENTER, wx.ALIGN_LEFT, wx.ALIGN_CENTER, wx.ALIGN_CENTER, wx.ALIGN_RIGHT, wx.ALIGN_LEFT,
                wx.ALIGN_LEFT, wx.ALIGN_CENTER, wx.ALIGN_CENTER]
        self.default_import_need = [True, True, True, False, False, False, False, False, False, False, False, False, False]
        self.default_export_format = ['General', 'General', '@', '@', '@', '@', '0', '@', '#,##0.00', 'yyyy-mm-dd', 'yyyy-mm-dd', '@', '@']
        self.default_col_overflow = [True, True, True, False, False, True, False, False, False, False, False, False, False]
        # 创建表格
        self.CreateGrid(20, len(self.default_col_labels))
        for col in range(len(self.default_col_labels)):
            self.SetColLabelValue(col, self.default_col_labels[col])
            self.SetColSize(col, self.default_col_widths[col])
            attr = wx.grid.GridCellAttr()
            attr.SetReadOnly(not self.default_col_editables[col])
            attr.SetAlignment(self.default_col_aligns[col], wx.ALIGN_CENTER)
            if not self.default_col_editables[col]: attr.SetBackgroundColour(read_only_bg_color)
            # attr.SetRenderer(wx.grid.GridCellAutoWrapStringRenderer())
            attr.SetOverflow(False)
            self.SetColAttr(col, attr)
        # 存储原始列名
        self.original_col_labels = {}
        for col in range(len(self.default_col_labels)):
            self.original_col_labels[col] = self.GetColLabelValue(col)
        # 表格设置
        self.EnableEditing(editable)
        self.DisableDragRowSize()
        self.SetSelectionMode(wx.grid.Grid.GridSelectCells)
        # 事件ID（增加搜索相关ID）
        self.ID_OPEN_ITEM = wx.NewIdRef()
        self.ID_OPEN_CONTAINING_DIR = wx.NewIdRef()
        self.ID_COPY_PATH = wx.NewIdRef()
        self.ID_IMPORT = wx.NewIdRef()
        self.ID_EXPORT = wx.NewIdRef()
        self.ID_INSERT_ROW = wx.NewIdRef()
        self.ID_DELETE_ROW = wx.NewIdRef()
        self.ID_SORT_ASC = wx.NewIdRef()
        self.ID_SORT_DESC = wx.NewIdRef()
        self.ID_COPY_ROW = wx.NewIdRef()
        self.ID_DELETE_ROW_DATA = wx.NewIdRef()
        self.ID_COPY_COLUMN = wx.NewIdRef()
        self.ID_DELETE_COLUMN = wx.NewIdRef()
        self.ID_SEARCH = wx.NewIdRef()
        self.ID_DESELECT_ALL = wx.NewIdRef()
        # 绑定额外事件
        self.Bind(wx.grid.EVT_GRID_COL_AUTO_SIZE, self.on_col_auto_size)
        # 绑定单元格选择事件，用于在状态栏显示内容
        self.Bind(wx.grid.EVT_GRID_SELECT_CELL, self.on_select_cell)
        # 初始化单元格为空
        for row in range(20):
            for col in range(len(self.default_col_labels)):
                self.SetCellValue(row, col, "")
        # 设置拖放目标
        self.SetDropTarget(tfo_FileDropTargetGrid(self))

    # ================================================================
    #  重写基类键盘事件：添加 BFM 特有快捷键
    # ================================================================

    def _on_key_down(self, event):
        """BFM 键盘事件处理：先处理特有快捷键，其余委托基类"""
        key_code = event.GetKeyCode()
        modifiers = event.GetModifiers()

        if modifiers == wx.MOD_CONTROL and key_code == ord('F'):
            self.on_search_grid(None)
        elif modifiers == wx.MOD_CONTROL and key_code == ord('I'):
            self.on_import_grid(None)
        elif modifiers == wx.MOD_CONTROL and key_code == ord('E'):
            self.on_export_grid(None)
        elif key_code == wx.WXK_ESCAPE:
            self.ClearSelection()
        else:
            super()._on_key_down(event)

    # ================================================================
    #  重写基类粘贴：保留 BFM 特殊粘贴逻辑
    # ================================================================

    def _paste_from_clipboard(self):
        """BFM 粘贴：支持单值多选、粘贴后处理"""
        try:
            # 第一步：从剪贴板获取文本数据
            clipboard_text = ""
            if wx.TheClipboard.Open():
                data_obj = wx.TextDataObject()
                if wx.TheClipboard.GetData(data_obj): clipboard_text = data_obj.GetText()
                wx.TheClipboard.Close()
            if not clipboard_text: return
            # 第二步：确定粘贴的起始位置和选中区域
            selection = self.GetSelectedBlocks()
            selected_cells = self.GetSelectedCells()
            # 获取所有选中的单元格
            all_selected_cells = set()
            # 添加单个选中的单元格
            for cell in selected_cells:
                all_selected_cells.add(cell)
            # 添加块选中的单元格
            for block in selection:
                top_left = block.GetTopLeft()
                bottom_right = block.GetBottomRight()
                for row in range(top_left.GetRow(), bottom_right.GetRow() + 1):
                    for col in range(top_left.GetCol(), bottom_right.GetCol() + 1):
                        all_selected_cells.add((row, col))
            # 第三步：处理剪贴板文本，按行分割
            lines = clipboard_text.strip().splitlines()
            data_matrix = []
            for line in lines:
                if not line.strip():
                    # 空行不丢弃：生成全空行占位，保持与剪贴板行号一一对应，避免后续行整体上移错位
                    data_matrix.append([''])
                else:
                    data_matrix.append(line.split('\t'))
            num_rows = len(data_matrix)
            if num_rows == 0: return
            num_cols = max(len(row) for row in data_matrix) if data_matrix else 0
            # 第四步：判断是否为单值粘贴到多个单元格
            is_single_value = (num_rows == 1 and num_cols == 1)
            has_multiple_selection = len(all_selected_cells) > 1

            # 捕获选区用于 Undo
            undo_selection = self._capture_selection()
            undo_changes = []

            if is_single_value and has_multiple_selection:
                # 单值粘贴到多个选中单元格
                single_value = data_matrix[0][0]
                pasted_rows = set()
                self.BeginBatch()
                try:
                    for row, col in all_selected_cells:
                        if row >= 0 and col >= 0 and row < self.GetNumberRows() and col < self.GetNumberCols():
                            if col < len(self.default_col_editables) and self.default_col_editables[col]:
                                old_val = self.GetCellValue(row, col)
                                self.SetCellValue(row, col, single_value)
                                undo_changes.append((row, col, old_val, single_value))
                                pasted_rows.add(row)
                finally:
                    self.EndBatch()
                if pasted_rows:
                    # 联动副作用（清空只读列/按旧路径回填/清重复行/行增删）与粘贴写入合并为同一条撤销记录
                    link_changes, rows_added, rows_deleted = self.process_after_paste(list(pasted_rows), min([c for r, c in all_selected_cells]))
                    # 记录 Undo
                    from tfp_toolkit.tfp_base_grid import _UndoEntry
                    entry = _UndoEntry()
                    entry.cell_changes = undo_changes + link_changes
                    entry.rows_added = rows_added
                    entry.rows_deleted = rows_deleted
                    entry.selection = undo_selection
                    self._push_undo(entry)
                    self.update_status(translate("status_pasted_value_to_cells", value=single_value, count=len(all_selected_cells)))
                return
            # 第七步：正常的多值粘贴逻辑
            if selection:
                block_list = list(selection)
                if block_list:
                    block = block_list[0]
                    start_row = block.GetTopLeft().GetRow()
                    start_col = block.GetTopLeft().GetCol()
                else:
                    start_row = self.GetGridCursorRow()
                    start_col = self.GetGridCursorCol()
            elif selected_cells:
                start_row = selected_cells[0][0]
                start_col = selected_cells[0][1]
            else:
                start_row = self.GetGridCursorRow()
                start_col = self.GetGridCursorCol()
            if start_row < 0 or start_col < 0:
                start_row = 0
                start_col = 0
            # 第八步：扩展表格（如果需要）
            required_rows = start_row + num_rows
            required_cols = start_col + num_cols
            total_row_count = self.GetNumberRows()
            current_cols = self.GetNumberCols()
            expand_added = None
            if required_rows > total_row_count:
                self.AppendRows(required_rows - total_row_count)
                # 粘贴扩展的行纳入撤销记录（末尾追加），撤销粘贴时一并删除
                expand_added = (total_row_count, required_rows - total_row_count)
            if required_cols > current_cols:
                num_cols = min(num_cols, current_cols - start_col)
            # 第九步：执行粘贴
            pasted_rows = []
            self.BeginBatch()
            try:
                for i, row_data in enumerate(data_matrix):
                    target_row = start_row + i
                    if target_row >= self.GetNumberRows(): break
                    pasted_rows.append(target_row)
                    for j in range(min(len(row_data), num_cols)):
                        target_col = start_col + j
                        if target_col >= self.GetNumberCols(): break
                        # 只读列跳过写入（与基类粘贴行为一致）
                        if target_col < len(self.default_col_editables) and not self.default_col_editables[target_col]: continue
                        cell_value = row_data[j]
                        old_val = self.GetCellValue(target_row, target_col)
                        self.SetCellValue(target_row, target_col, cell_value)
                        undo_changes.append((target_row, target_col, old_val, cell_value))
            finally:
                self.EndBatch()
            # 第十步：处理粘贴后的数据（联动副作用一并收集进撤销记录）
            link_changes, adjust_added, rows_deleted = self.process_after_paste(pasted_rows, start_col)
            # 合并粘贴扩展与行数调整的追加记录（均为末尾追加）
            rows_added = expand_added
            if adjust_added is not None:
                if rows_added is not None and rows_added[0] + rows_added[1] == adjust_added[0]:
                    rows_added = (rows_added[0], rows_added[1] + adjust_added[1])
                else:
                    rows_added = adjust_added
            if undo_changes or link_changes or rows_added or rows_deleted:
                from tfp_toolkit.tfp_base_grid import _UndoEntry
                entry = _UndoEntry()
                entry.cell_changes = undo_changes + link_changes
                entry.rows_added = rows_added
                entry.rows_deleted = rows_deleted
                entry.selection = undo_selection
                self._push_undo(entry)
            # 第十一步：更新状态栏
            rows_pasted = min(num_rows, self.GetNumberRows() - start_row)
            cols_pasted = min(num_cols, self.GetNumberCols() - start_col)
            self.update_status(translate("status_pasted_rows_cols", rows=rows_pasted, cols=cols_pasted))
        except Exception as e:
            log_error(f"粘贴数据失败: {e}")
            wx.MessageBox(translate("dialog_paste_failed", error=str(e)), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)

    # ================================================================
    #  重写基类清空：保留 BFM 联动清空逻辑
    # ================================================================

    def _clear_selected_cells(self):
        """BFM 清空：清空可编辑列，联动清空非编辑列"""
        if self._read_only:
            return

        selection = self._capture_selection()
        cleared_cells = []
        undo_changes = []
        rows_with_deleted_new_path = set()

        self.BeginBatch()
        try:
            # 收集需要清空的单元格
            cells_to_clear = set()
            selected_rows = self.GetSelectedRows()
            selected_cols = self.GetSelectedCols()
            blocks_tl = self.GetSelectionBlockTopLeft()
            blocks_br = self.GetSelectionBlockBottomRight()

            if selected_rows:
                for row in selected_rows:
                    for col in range(self.GetNumberCols()):
                        cells_to_clear.add((row, col))
            elif selected_cols:
                for col in selected_cols:
                    for row in range(self.GetNumberRows()):
                        cells_to_clear.add((row, col))
            elif blocks_tl:
                for i in range(len(blocks_tl)):
                    tl = blocks_tl[i]
                    br = blocks_br[i]
                    for row in range(tl[0], br[0] + 1):
                        for col in range(tl[1], br[1] + 1):
                            cells_to_clear.add((row, col))
            else:
                row = self.GetGridCursorRow()
                col = self.GetGridCursorCol()
                if 0 <= row < self.GetNumberRows() and 0 <= col < self.GetNumberCols():
                    cells_to_clear.add((row, col))

            # 清空可编辑列
            for row, col in cells_to_clear:
                if col >= 0 and col < len(self.default_col_editables) and self.default_col_editables[col]:
                    old_val = self.GetCellValue(row, col)
                    self.SetCellValue(row, col, "")
                    cleared_cells.append((row, col))
                    undo_changes.append((row, col, old_val, ""))
                    if col == self.COL_NEW_PATH:
                        rows_with_deleted_new_path.add(row)

            # 联动：清空新路径列时，若旧路径也为空，则清空非编辑列
            for row in rows_with_deleted_new_path:
                if not self.GetCellValue(row, self.COL_OLD_PATH).strip():
                    for col in range(self.GetNumberCols()):
                        if col >= 0 and col < len(self.default_col_editables) and not self.default_col_editables[col]:
                            old_val = self.GetCellValue(row, col)
                            if old_val:
                                self.SetCellValue(row, col, "")
                                cleared_cells.append((row, col))
                                undo_changes.append((row, col, old_val, ""))
        finally:
            self.EndBatch()

        if cleared_cells:
            from tfp_toolkit.tfp_base_grid import _UndoEntry
            entry = _UndoEntry()
            entry.cell_changes = undo_changes
            entry.selection = selection
            self._push_undo(entry)
            self.on_cells_cleared(cleared_cells)

    # ================================================================
    #  重写基类右键菜单：添加 BFM 特有菜单项
    # ================================================================

    def _on_cell_right_click(self, event):
        """BFM 单元格右键菜单：基类菜单 + BFM 特有项"""
        if self.IsCellEditControlShown():
            event.Skip()
            return

        row_grid = event.GetRow()
        col_grid = event.GetCol()
        self.SetGridCursor(row_grid, col_grid)

        if row_grid < 0 or col_grid < 0:
            event.Skip()
            return

        menu = wx.Menu()
        # 基类菜单项：复制/粘贴/撤销/重做/删除数据
        self._add_default_cell_menu_items(menu)

        menu.AppendSeparator()

        # BFM 特有：取消选择
        deselect_all_item = menu.Append(self.ID_DESELECT_ALL, translate("context_menu_deselect_all"))
        self.Bind(wx.EVT_MENU, lambda e: self.ClearSelection(), deselect_all_item)

        menu.AppendSeparator()

        # BFM 特有：打开文件/目录、复制路径
        can_copy_path = False
        can_open_item = False
        can_open_dir = False
        if row_grid >= 0 and col_grid >= 0 and row_grid < self.GetNumberRows() and col_grid < self.GetNumberCols():
            # 按被右键的列确定操作路径：
            # Old Path 列取旧路径，New Path 列取新路径，其他列不允许路径相关操作
            if col_grid == self.COL_OLD_PATH:
                target_path = self.GetCellValue(row_grid, self.COL_OLD_PATH).strip()
            elif col_grid == self.COL_NEW_PATH:
                target_path = self.GetCellValue(row_grid, self.COL_NEW_PATH).strip()
            else:
                target_path = ""
            if target_path:
                can_copy_path = True
                if os.path.exists(target_path): can_open_item = True
            # "打开包含目录"仅在被右键路径列可用（Old Path / New Path），其他列禁用
            can_open_dir = bool(target_path)
        open_item = menu.Append(self.ID_OPEN_ITEM, translate("context_menu_open_item"))
        open_item.Enable(can_open_item)
        open_containing_dir_item = menu.Append(self.ID_OPEN_CONTAINING_DIR, translate("context_menu_open_dir"))
        open_containing_dir_item.Enable(can_open_dir)
        copy_path_item = menu.Append(self.ID_COPY_PATH, translate("context_menu_copy_path"))
        copy_path_item.Enable(can_copy_path)
        self.Bind(wx.EVT_MENU, self.on_open_item, open_item)
        self.Bind(wx.EVT_MENU, lambda e, cp=target_path: self.on_open_containing_dir(e, cp), open_containing_dir_item)
        self.Bind(wx.EVT_MENU, self.on_copy_path, copy_path_item)

        menu.AppendSeparator()

        # BFM 特有：导入、导出、搜索
        import_item = menu.Append(self.ID_IMPORT, translate("context_menu_import"))
        export_item = menu.Append(self.ID_EXPORT, translate("context_menu_export"))
        search_item = menu.Append(self.ID_SEARCH, translate("context_menu_search"))
        self.Bind(wx.EVT_MENU, self.on_import_grid, import_item)
        self.Bind(wx.EVT_MENU, self.on_export_grid, export_item)
        self.Bind(wx.EVT_MENU, self.on_search_grid, search_item)

        self.PopupMenu(menu)
        menu.Destroy()

    def _on_label_right_click(self, event):
        """BFM 行/列标签右键菜单：基类菜单 + BFM 特有项（排序、插入行等）

        方法名必须与基类 tfp_base_grid.py 绑定的 _on_label_right_click 一致，
        否则绑定失效、行/列标签右键菜单与排序功能整体不可用。
        """
        row_label = event.GetRow()
        col_label = event.GetCol()
        if row_label == -1 and col_label >= 0:
            # 列标签右键
            self.current_sort_col = col_label
            menu = wx.Menu()
            sort_asc_item = menu.Append(self.ID_SORT_ASC, translate("context_menu_sort_asc"))
            sort_desc_item = menu.Append(self.ID_SORT_DESC, translate("context_menu_sort_desc"))
            menu.AppendSeparator()
            copy_col_data_item = menu.Append(self.ID_COPY_COLUMN, translate("context_menu_copy_col_data"))
            if col_label >= 0 and col_label < len(self.default_col_editables) and self.default_col_editables[col_label]:
                delete_col_data_item = menu.Append(self.ID_DELETE_COLUMN, translate("context_menu_delete_col_data"))
                self.Bind(wx.EVT_MENU, lambda e: self.on_delete_column_data(e, None), delete_col_data_item)
            self.Bind(wx.EVT_MENU, self.on_sort_asc, sort_asc_item)
            self.Bind(wx.EVT_MENU, self.on_sort_desc, sort_desc_item)
            self.Bind(wx.EVT_MENU, lambda e: self.on_copy_column_data(e, None), copy_col_data_item)
            self.PopupMenu(menu)
            menu.Destroy()
        elif row_label >= 0 and col_label == -1:
            # 行标签右键
            self.current_right_click_row = row_label
            menu = wx.Menu()
            insert_row_item = menu.Append(self.ID_INSERT_ROW, translate("context_menu_insert_row"))
            delete_row_item = menu.Append(self.ID_DELETE_ROW, translate("context_menu_delete_row"))
            menu.AppendSeparator()
            copy_row_data_item = menu.Append(self.ID_COPY_ROW, translate("context_menu_copy_row_data"))
            delete_row_data_item = menu.Append(self.ID_DELETE_ROW_DATA, translate("context_menu_delete_row_data"))
            self.Bind(wx.EVT_MENU, self.on_insert_row, insert_row_item)
            self.Bind(wx.EVT_MENU, self.on_delete_row, delete_row_item)
            self.Bind(wx.EVT_MENU, lambda e, row=row_label: self.on_copy_row_data(e, row), copy_row_data_item)
            self.Bind(wx.EVT_MENU, lambda e: self.on_delete_row_data(e, None), delete_row_data_item)
            self.PopupMenu(menu)
            menu.Destroy()
        else:
            event.Skip()

    # ================================================================
    #  Hook 方法重写
    # ================================================================

    def on_cells_cleared(self, cells):
        """单元格被清空后：更新状态栏"""
        if cells:
            self.update_status(translate("status_deleted_cells", count=len(cells)))

    def on_cells_pasted(self, cells):
        """单元格被粘贴后：由 _paste_from_clipboard 自行处理 process_after_paste"""
        pass

    def on_rows_added(self, count):
        """行被添加后：更新状态栏"""
        self.update_status(translate("status_inserted_rows", count=count))

    def on_rows_deleted(self, rows):
        """行被删除后：调整行数"""
        self.update_status(translate("status_deleted_rows", count=len(rows)))
        self.adjust_table_rows()

    # ==================== 回调方法 ====================
    """更新状态栏的回调方法"""
    def update_status(self, text):
        if 'update_status' in self.callbacks:
            self.callbacks['update_status'](text)

    """禁用控件的回调方法"""
    def disable_controls(self):
        if 'disable_controls' in self.callbacks:
            self.callbacks['disable_controls']()

    """恢复控件的回调方法"""
    def restore_controls(self):
        if 'restore_controls' in self.callbacks:
            self.callbacks['restore_controls']()

    """获取搜索文件夹的回调方法"""
    def get_search_folder(self):
        if 'get_search_folder' in self.callbacks:
            return self.callbacks['get_search_folder']()
        return ""

    """设置搜索文件夹的回调方法"""
    def set_search_folder(self, folder_path, need_raise_event=False):
        if 'set_search_folder' in self.callbacks:
            return self.callbacks['set_search_folder'](folder_path, need_raise_event)
        return ""

    """调整表格行数的回调方法"""
    def adjust_table_rows_callback(self):
        if 'adjust_table_rows' in self.callbacks:
            self.callbacks['adjust_table_rows']()

    """刷新布局的回调方法"""
    def layout_frame(self):
        if 'layout_frame' in self.callbacks:
            self.callbacks['layout_frame']()

    # ==================== 执行进度：节流写回 + 当前行高亮 ====================
    # 当前执行行高亮色（浅黄）；恢复默认背景时只读列用灰底，其余用白底，与 __init__ 一致。
    _HIGHLIGHT_COLOUR = wx.Colour(255, 245, 157)

    def begin_operation_progress(self):
        """操作开始时调用（主线程）：进入进度高亮模式。可重复调用。"""
        with self._pending_lock:
            self._progress_active = True
            self._pending_highlight_row = -1
        self._flush_progress()

    def end_operation_progress(self):
        """操作结束时调用（主线程）：同步落盘全部挂起写入并清除当前行高亮。

        必须同步落盘：操作完成后 tool_main 会读取网格内容做统计/展示，
        若仍有挂起写入未落盘会读到旧值。
        """
        with self._pending_lock:
            self._progress_active = False
        self._apply_pending_writes()
        self._clear_highlight()

    def queue_cell_value(self, row, col, value):
        """Worker 线程调用：把单元格结果放入合并队列，由主线程批量落盘（线程安全）。

        替代 Worker 中逐行 `wx.CallAfter(grid.SetCellValue, ...)`：只在无待处理 flush
        时投递一次 flush 事件，避免事件队列被逐行写入淹没。
        """
        with self._pending_lock:
            self._pending_writes[(row, col)] = value
            if not self._flush_scheduled:
                self._flush_scheduled = True
                wx.CallAfter(self._flush_progress)

    def _flush_progress(self):
        """主线程：按时拍批量落盘挂起写入，并更新当前行高亮。"""
        self._apply_pending_writes()
        self._refresh_highlight()

    def _apply_pending_writes(self):
        """主线程：批量落盘挂起写入；记录最近一次"执行结果"列写入的行用于高亮。"""
        with self._pending_lock:
            items = list(self._pending_writes.items())
            self._pending_writes.clear()
            self._flush_scheduled = False
        if not items:
            return
        rows = self.GetNumberRows()
        cols = self.GetNumberCols()
        self.BeginBatch()
        try:
            for (row, col), value in items:
                if 0 <= row < rows and 0 <= col < cols:
                    self.SetCellValue(row, col, value)
                if (col == self.COL_RESULT and self._progress_active
                        and isinstance(value, str) and value):
                    with self._pending_lock:
                        self._pending_highlight_row = row
        finally:
            self.EndBatch()

    def _refresh_highlight(self):
        with self._pending_lock:
            target = self._pending_highlight_row if self._progress_active else -1
        if target != self._highlight_row:
            self._set_highlight_row(target)

    def _set_highlight_row(self, row):
        previous = self._highlight_row
        if previous == row:
            return
        self._highlight_row = row
        if 0 <= previous < self.GetNumberRows():
            self._paint_row_background(previous, None)
        if 0 <= row < self.GetNumberRows():
            self._paint_row_background(row, self._HIGHLIGHT_COLOUR)

    def _clear_highlight(self):
        with self._pending_lock:
            self._pending_highlight_row = -1
        self._set_highlight_row(-1)

    def _paint_row_background(self, row, colour):
        """整行设背景色；colour=None 时恢复各列默认背景。"""
        for col in range(self.GetNumberCols()):
            self.SetCellBackgroundColour(
                row, col, self._default_cell_bg(col) if colour is None else colour)
        self.RefreshBlock(row, 0, row, self.GetNumberCols() - 1)

    def _default_cell_bg(self, col):
        """列默认背景色（与 __init__ 中只读列灰底保持一致）。"""
        if col < len(self.default_col_editables) and not self.default_col_editables[col]:
            return wx.Colour(247, 247, 247)
        return wx.Colour(255, 255, 255)

    # ==================== 表格操作方法 ====================
    """设置指定列数据的对齐方式"""
    def set_column_data_alignment(self, col, alignment):
        attr = wx.grid.GridCellAttr()
        attr.SetAlignment(alignment, wx.ALIGN_CENTER)
        self.SetColAttr(col, attr)

    """列自动调整大小事件处理"""
    def on_col_auto_size(self, event):
        col = event.GetRowOrCol()
        event.Veto()
        self.toggle_col_width(col)

    """切换列宽"""
    def toggle_col_width(self, col):
        auto_width = self.calculate_auto_width(col)
        current_width = self.GetColSize(col)
        if abs(current_width - auto_width) <= 3:
            new_width = self.default_col_widths[col]
        else:
            new_width = auto_width
        self.SetColSize(col, new_width)

    """计算列的自适应宽度"""
    def calculate_auto_width(self, col, ret_type='UI_GRID'):
        if ret_type == "UI_GRID":
            if self.GetNumberRows() == 0:
                return self.default_col_widths[col]
            dc = wx.ClientDC(self)
            header_val = self.GetColLabelValue(col)
            dc.SetFont(self.GetLabelFont())
            header_width = dc.GetTextExtent(header_val)[0]
            max_content_width = 0
            for row in range(self.GetNumberRows()):
                cell_value = self.GetCellValue(row, col)
                if cell_value:
                    dc.SetFont(self.GetDefaultCellFont())
                    cell_width = dc.GetTextExtent(cell_value)[0]
                    if cell_width > max_content_width:
                        max_content_width = cell_width
            return max(header_width, max_content_width) + self._spx(15)
        elif ret_type == "EXPORT_EXCEL":
            if self.GetNumberRows() == 0:
                return self.default_export_widths[col]
            header_val = self.GetColLabelValue(col)
            header_width = 0
            for char in str(header_val):
                header_width = (header_width + 2) if ord(char) > 127 else (header_width + 1)
            max_content_width = 0
            for row in range(self.GetNumberRows()):
                cell_value = self.GetCellValue(row, col)
                if cell_value:
                    cell_width = 0
                    for char in str(cell_value):
                        cell_width = (cell_width + 2) if ord(char) > 127 else (cell_width + 1)
                    if cell_width > max_content_width:
                        max_content_width = cell_width
            return max(header_width, max_content_width) + 1
        else:
            return self.default_col_widths[col]

    """升序排列"""
    def on_sort_asc(self, event):
        if hasattr(self, 'current_sort_col'):
            self.sort_rows(self.current_sort_col, ascending=True)

    """降序排列"""
    def on_sort_desc(self, event):
        if hasattr(self, 'current_sort_col'):
            self.sort_rows(self.current_sort_col, ascending=False)

    """设置列名后的排序箭头"""
    def set_col_sort_indicator(self, col_idx=None, ascending=True):
        for col in range(self.GetNumberCols()):
            original_label = self.original_col_labels.get(col, "")
            self.SetColLabelValue(col, original_label)
        if col_idx is not None and 0 <= col_idx < self.GetNumberCols():
            original_label = self.original_col_labels.get(col_idx, "")
            arrow = " ↑" if ascending else " ↓"
            self.SetColLabelValue(col_idx, original_label + arrow)

    """按列排序行数据"""
    def sort_rows(self, col_idx, ascending=True):
        self.SetFocus()
        rows = self.GetNumberRows()
        if rows <= 1:
            self.set_col_sort_indicator(col_idx, ascending)
            col_name = self.original_col_labels.get(col_idx, self.GetColLabelValue(col_idx))
            order = translate("sort_ascending") if ascending else translate("sort_descending")
            self.update_status(translate("status_sorted_by_column", column=col_name, order=order))
            return
        # 收集所有非空白行的数据
        non_empty_data = []
        blank_rows = []
        for row in range(rows):
            is_blank = True
            for col in range(self.GetNumberCols()):
                if self.GetCellValue(row, col).strip():
                    is_blank = False
                    break
            if is_blank:
                blank_rows.append(row)
            else:
                row_data = []
                for col in range(self.GetNumberCols()):
                    row_data.append(self.GetCellValue(row, col))
                non_empty_data.append((row, row_data))
        if not non_empty_data:
            self.set_col_sort_indicator(col_idx, ascending)
            col_name = self.original_col_labels.get(col_idx, self.GetColLabelValue(col_idx))
            order = translate("sort_ascending") if ascending else translate("sort_descending")
            self.update_status(translate("status_sorted_by_column", column=col_name, order=order))
            return

        def sort_key(item):
            row_idx, row_data = item
            primary_value = row_data[col_idx]
            secondary_value = row_data[self.COL_OLD_PATH] if col_idx != self.COL_OLD_PATH else ""
            if col_idx == self.COL_LEVEL:
                try:
                    primary_value = int(primary_value) if primary_value else 0
                except (ValueError, TypeError):
                    primary_value = 0
            elif col_idx == self.COL_SIZE:
                try:
                    primary_value = float(primary_value) if primary_value else 0.0
                except (ValueError, TypeError):
                    primary_value = 0.0
            elif col_idx in (self.COL_CREATE_TIME, self.COL_MODIFY_TIME):
                primary_value = primary_value if primary_value else ""
            else:
                primary_value = primary_value if primary_value else ""
            if col_idx != self.COL_NEW_PATH:
                return (primary_value, secondary_value)
            else:
                return (primary_value,)
        non_empty_data.sort(key=sort_key, reverse=not ascending)
        self.DeleteRows(0, rows)
        for _, row_data in non_empty_data:
            row = self.GetNumberRows()
            self.AppendRows(1)
            for col, value in enumerate(row_data):
                self.SetCellValue(row, col, value)
        if blank_rows:
            self.AppendRows(len(blank_rows))
            for i in range(len(blank_rows)):
                row = self.GetNumberRows() - len(blank_rows) + i
                for col in range(self.GetNumberCols()):
                    self.SetCellValue(row, col, "")
        self.set_col_sort_indicator(col_idx, ascending)
        col_name = self.original_col_labels.get(col_idx, self.GetColLabelValue(col_idx))
        order = translate("sort_ascending") if ascending else translate("sort_descending")
        self.update_status(translate("status_sorted_by_column", column=col_name, order=order))
        if non_empty_data:
            self.SetGridCursor(0, col_idx)
            self.SelectBlock(0, col_idx, 0, col_idx)
            self.GoToCell(0, col_idx)
        # 排序后清空撤销历史（排序是破坏性操作，难以增量撤销）
        self.clear_undo_history()

    """复制当前激活的单元格"""
    def copy_active_cell(self):
        row = self.GetGridCursorRow()
        col = self.GetGridCursorCol()
        if row >= 0 and col >= 0:
            cell_value = self.GetCellValue(row, col)
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(cell_value))
                wx.TheClipboard.Close()
            self.update_status(translate("status_copied_current_cell"))

    """复制选中内容到剪贴板"""
    def on_copy_grid(self, event):
        self._copy_selection()

    """从剪贴板粘贴到表格"""
    def on_paste_grid(self, event):
        self._paste_from_clipboard()

    """删除选中单元格内容"""
    def on_delete_cells(self, event):
        self._clear_selected_cells()

    """选择全部菜单项处理"""
    def on_select_all(self, event):
        self.SelectAll()

    """取消选择菜单项处理"""
    def on_deselect_all(self, event):
        self.ClearSelection()

    """打开此项"""
    def _confirm_open_executable(self, path):
        """可执行文件打开前的二次确认（A5-1 安全修复）

        表格内路径可被用户粘贴编辑，来源不可信时直接执行可执行文件有风险，
        打开前弹出警告确认。返回 True=确认继续；False=取消。
        """
        dlg = wx.MessageDialog(
            self,
            translate("dialog_open_executable_warning", name=os.path.basename(path)),
            translate("dialog_title_warning"),
            wx.YES_NO | wx.ICON_WARNING
        )
        dlg.SetYesNoLabels(translate("dialog_btn_open_anyway"), translate("dialog_btn_cancel"))
        ret = dlg.ShowModal()
        dlg.Destroy()
        return ret == wx.ID_YES

    def on_open_item(self, event):
        rows = self.get_selected_rows()
        if not rows:
            row = self.GetGridCursorRow()
            if row >= 0:
                rows = [row]
        if rows:
            row = rows[0]
            old_path = self.GetCellValue(row, self.COL_OLD_PATH).strip()
            new_path = self.GetCellValue(row, self.COL_NEW_PATH).strip()
            path = old_path or new_path
            if path and os.path.exists(path):
                # A5-1：可执行扩展名打开前弹警告确认（保持列表参数形式、无 shell=True）
                ext = os.path.splitext(path)[1].lower()
                if ext in _EXECUTABLE_EXTENSIONS and not self._confirm_open_executable(path):
                    return
                try:
                    if os.name == 'nt':
                        os.startfile(path)
                    else:
                        subprocess.Popen(['xdg-open', path])
                except Exception as e:
                    wx.MessageBox(translate("dialog_open_failed", error=str(e)), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
            else:
                wx.MessageBox(translate("dialog_path_invalid"), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)

    """打开包含目录（右键 Old Path / New Path 列）：
    无论路径是文件还是目录，都打开其父目录并默认选中该路径项；
    仅当路径为根目录（如 Win 的 D:/、Linux 的 /，无父目录）时才打开目录自身；
    待打开的目标目录不存在时弹出警告。
    实际打开动作放入后台线程执行：D-Bus ShowItems 是同步调用，可能长时间阻塞，
    若在主线程执行会导致界面冻结数秒到数分钟、看起来像"点了没反应"。"""
    def on_open_containing_dir(self, event, target_path):
        if not target_path:
            return
        target_dir, select_item = self._get_target_dir_and_select(target_path)
        if not os.path.isdir(target_dir):
            wx.MessageBox(translate("dialog_path_invalid"), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
            return
        threading.Thread(
            target=self._open_containing_dir_worker,
            args=(target_dir, select_item),
            daemon=True,
        ).start()

    """后台线程中执行打开操作，避免同步调用阻塞 wx 主线程"""
    def _open_containing_dir_worker(self, target_dir, select_item):
        try:
            if os.name == 'nt':
                if select_item:
                    subprocess.Popen(['explorer.exe', '/select,', select_item])
                else:
                    os.startfile(target_dir)
            else:
                if select_item:
                    self._linux_open_and_select(select_item)
                else:
                    subprocess.Popen(['xdg-open', target_dir])
        except Exception as e:
            # 后台线程不能直接操作 wx 控件，统一切回主线程弹窗
            wx.CallAfter(
                wx.MessageBox,
                translate("dialog_open_dir_failed", error=str(e)),
                translate("dialog_title_error"),
                wx.OK | wx.ICON_ERROR,
            )

    """计算"打开包含目录"的目标目录与选中项：
    - 一般情况：返回 (父目录, 原路径)，即在父目录中选中原路径项；
    - 根目录（dirname 为空或等于自身，如 "/"、"D:/"）：返回 (目录自身, None)，仅打开目录。"""
    def _get_target_dir_and_select(self, path):
        parent = os.path.dirname(path)
        if not parent or parent == path:
            return path, None
        return parent, path

    """在 Linux 文件管理器中打开 item_path 的父目录并尽量选中它：
    智能按文件管理器选择实现（不再使用 FileManager1.ShowItems——
    Thunar 未完整实现该接口，属 XFCE 已知缺陷 bug#11024，会导致慢/打不开）：
    - Nautilus / Dolphin / Caja(1.26+)：用 --select 打开父目录并选中（可靠）；
    - Nemo：仅能选中文件，文件项用 nemo 选中，目录项改为打开父目录；
    - Thunar / PCManFM 等不支持选中：仅用 xdg-open 打开父目录。
    全程非阻塞，保证快速可靠。"""
    def _linux_open_and_select(self, item_path):
        import shutil
        parent = os.path.dirname(item_path)
        open_target = parent or item_path
        default_fm = self._get_default_file_manager()

        if default_fm in ("nautilus", "org.gnome.nautilus") and shutil.which("nautilus"):
            subprocess.Popen(["nautilus", "--select", item_path])
            return
        if default_fm in ("dolphin", "org.kde.dolphin") and shutil.which("dolphin"):
            subprocess.Popen(["dolphin", "--select", item_path])
            return
        if default_fm in ("caja", "org.mate.caja") and shutil.which("caja"):
            subprocess.Popen(["caja", "--select", item_path])
            return
        if default_fm in ("nemo", "org.nemo") and shutil.which("nemo") and os.path.isfile(item_path):
            subprocess.Popen(["nemo", item_path])
            return
        # Thunar/PCManFM 等不支持选中，或默认文件管理器未知/不可用：仅打开父目录
        subprocess.Popen(["xdg-open", open_target])

    """查询系统默认文件管理器（xdg-mime 中 inode/directory 的默认应用），
    返回其 desktop 文件名去掉 .desktop 后缀的小写名称；失败返回空串。"""
    def _get_default_file_manager(self):
        import shutil
        try:
            xdg_mime = shutil.which("xdg-mime")
            if xdg_mime:
                result = subprocess.run(
                    [xdg_mime, "query", "default", "inode/directory"],
                    capture_output=True, text=True, timeout=3,
                )
                if result.returncode == 0:
                    name = result.stdout.strip().lower()
                    if name.endswith(".desktop"):
                        name = name[:-8]
                    return name
        except Exception:
            pass
        return ""

    """复制路径"""
    def on_copy_path(self, event):
        rows = self.get_selected_rows()
        if not rows:
            row = self.GetGridCursorRow()
            if row >= 0:
                rows = [row]
        if rows:
            paths = []
            for row in rows:
                old_path = self.GetCellValue(row, self.COL_OLD_PATH).strip()
                new_path = self.GetCellValue(row, self.COL_NEW_PATH).strip()
                path = old_path or new_path
                if path:
                    paths.append(path)
            if paths:
                clipboard_text = '\n'.join(paths)
                if wx.TheClipboard.Open():
                    wx.TheClipboard.SetData(wx.TextDataObject(clipboard_text))
                    wx.TheClipboard.Close()
                    self.update_status(translate("status_copied_paths_to_clipboard", count=len(paths)))
            else:
                wx.MessageBox(translate("dialog_no_valid_paths"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)

    """插入行"""
    def on_insert_row(self, event):
        selected_rows = self.get_selected_rows()
        if not selected_rows:
            row = self.GetGridCursorRow()
            if row >= 0:
                selected_rows = [row]
        if selected_rows:
            insert_pos = selected_rows[0]
            num_rows = len(selected_rows)
            self.InsertRows(insert_pos, num_rows)
            read_only_bg_color = wx.Colour(247, 247, 247)
            for i in range(num_rows):
                row_idx = insert_pos + i
                for col in range(self.GetNumberCols()):
                    attr = wx.grid.GridCellAttr()
                    attr.SetReadOnly(not self.default_col_editables[col])
                    attr.SetAlignment(self.default_col_aligns[col], wx.ALIGN_CENTER)
                    if not self.default_col_editables[col]:
                        attr.SetBackgroundColour(read_only_bg_color)
                    self.SetRowAttr(row_idx, attr)
                    self.SetCellValue(row_idx, col, "")
            self.update_status(translate("status_inserted_rows", count=num_rows))
            # 插入行后清空撤销历史（插入行涉及行属性设置，难以增量撤销）
            self.clear_undo_history()

    """删除行"""
    def on_delete_row(self, event):
        selected_rows = self.get_selected_rows()
        if not selected_rows:
            row = self.GetGridCursorRow()
            if row >= 0:
                selected_rows = [row]
        if selected_rows:
            for row in sorted(selected_rows, reverse=True):
                self.DeleteRows(row, 1)
            self.update_status(translate("status_deleted_rows", count=len(selected_rows)))
            self.adjust_table_rows()
            # 删除行后清空撤销历史（DeleteRows 涉及行属性，难以增量撤销）
            self.clear_undo_history()

    """复制列数据"""
    def on_copy_column_data(self, event, col=None):
        try:
            selected_cols = []
            if col is not None:
                selected_cols = [col]
            else:
                selected_cols = self.get_selected_columns()
            if not selected_cols:
                wx.MessageBox(translate("dialog_select_column_first"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
                return
            all_data_lines = []
            for col_idx in selected_cols:
                if col_idx < 0 or col_idx >= self.GetNumberCols():
                    continue
                col_data = []
                for row in range(self.GetNumberRows()):
                    cell_value = self.GetCellValue(row, col_idx)
                    col_data.append(cell_value)
                all_data_lines.append(col_data)
            if all_data_lines:
                max_rows = max(len(col_data) for col_data in all_data_lines)
                clipboard_lines = []
                for row in range(max_rows):
                    row_data = []
                    for col_idx, col_data in enumerate(all_data_lines):
                        if row < len(col_data):
                            row_data.append(col_data[row])
                        else:
                            row_data.append("")
                    clipboard_lines.append('\t'.join(row_data))
                clipboard_data = '\n'.join(clipboard_lines)
                if wx.TheClipboard.Open():
                    wx.TheClipboard.SetData(wx.TextDataObject(clipboard_data))
                    wx.TheClipboard.Close()
                col_names = ", ".join([self.GetColLabelValue(col) for col in selected_cols])
                self.update_status(f"Copied data from {len(selected_cols)} columns to clipboard")
        except Exception as e:
            log_error(f"复制列数据失败: {e}")

    """删除列数据"""
    def on_delete_column_data(self, event, col=None):
        try:
            selected_cols = []
            if col is not None:
                selected_cols = [col]
            else:
                selected_cols = self.get_selected_columns()
            if not selected_cols:
                wx.MessageBox(translate("dialog_select_column_delete"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
                return
            contains_old_path_col = self.COL_OLD_PATH in selected_cols
            contains_new_path_col = self.COL_NEW_PATH in selected_cols

            selection = self._capture_selection()
            undo_changes = []

            self.BeginBatch()
            try:
                for col_idx in selected_cols:
                    if col_idx < 0 or col_idx >= self.GetNumberCols():
                        continue
                    if col_idx < len(self.default_col_editables) and self.default_col_editables[col_idx]:
                        for row in range(self.GetNumberRows()):
                            old_val = self.GetCellValue(row, col_idx)
                            if old_val:
                                self.SetCellValue(row, col_idx, "")
                                undo_changes.append((row, col_idx, old_val, ""))
                if contains_old_path_col:
                    for row in range(self.GetNumberRows()):
                        for col in range(self.GetNumberCols()):
                            if col >= 0 and col < len(self.default_col_editables) and not self.default_col_editables[col]:
                                old_val = self.GetCellValue(row, col)
                                if old_val:
                                    self.SetCellValue(row, col, "")
                                    undo_changes.append((row, col, old_val, ""))
                if contains_new_path_col:
                    for row in range(self.GetNumberRows()):
                        old_val = self.GetCellValue(row, self.COL_RESULT)
                        if old_val:
                            self.SetCellValue(row, self.COL_RESULT, "")
                            undo_changes.append((row, self.COL_RESULT, old_val, ""))
            finally:
                self.EndBatch()

            if undo_changes:
                from tfp_toolkit.tfp_base_grid import _UndoEntry
                entry = _UndoEntry()
                entry.cell_changes = undo_changes
                entry.selection = selection
                self._push_undo(entry)

            col_names = ", ".join([self.GetColLabelValue(col) for col in selected_cols])
            self.update_status(f"Deleted data from {len(selected_cols)} columns")
        except Exception as e:
            log_error(f"删除列数据失败: {e}")

    """复制行数据"""
    def on_copy_row_data(self, event, row=None):
        try:
            selected_rows = []
            if row is not None:
                selected_rows = [row]
            else:
                selected_rows = self.get_selected_rows()
            if not selected_rows:
                wx.MessageBox(translate("dialog_select_row_copy"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
                return
            data_lines = []
            for row_idx in selected_rows:
                if row_idx < 0 or row_idx >= self.GetNumberRows():
                    continue
                row_data = []
                for col in range(self.GetNumberCols()):
                    cell_value = self.GetCellValue(row_idx, col)
                    row_data.append(cell_value)
                data_lines.append('\t'.join(row_data))
            if data_lines:
                clipboard_data = '\n'.join(data_lines)
                if wx.TheClipboard.Open():
                    wx.TheClipboard.SetData(wx.TextDataObject(clipboard_data))
                    wx.TheClipboard.Close()
                self.update_status(f"Copied data from {len(selected_rows)} rows to clipboard")
        except Exception as e:
            log_error(f"复制行数据失败: {e}")

    """删除行数据"""
    def on_delete_row_data(self, event, row=None):
        try:
            selected_rows = []
            if row is not None:
                selected_rows = [row]
            else:
                selected_rows = self.get_selected_rows()
            if not selected_rows:
                wx.MessageBox(translate("dialog_select_row_delete"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
                return

            selection = self._capture_selection()
            undo_changes = []

            self.BeginBatch()
            try:
                for row_idx in selected_rows:
                    if row_idx < 0 or row_idx >= self.GetNumberRows():
                        continue
                    for col in range(self.GetNumberCols()):
                        if col >= 0 and col < len(self.default_col_editables) and self.default_col_editables[col]:
                            old_val = self.GetCellValue(row_idx, col)
                            if old_val:
                                self.SetCellValue(row_idx, col, "")
                                undo_changes.append((row_idx, col, old_val, ""))
            finally:
                self.EndBatch()

            if undo_changes:
                from tfp_toolkit.tfp_base_grid import _UndoEntry
                entry = _UndoEntry()
                entry.cell_changes = undo_changes
                entry.selection = selection
                self._push_undo(entry)

            self.update_status(translate("status_deleted_rows_data", count=len(selected_rows)))
        except Exception as e:
            log_error(f"删除行数据失败: {e}")

    """获取选中的列列表"""
    def get_selected_columns(self):
        cols = set()
        selected_cells = self.GetSelectedCells()
        for cell in selected_cells:
            row, col = cell
            cols.add(col)
        selected_blocks = self.GetSelectedBlocks()
        for block in selected_blocks:
            top_left = block.GetTopLeft()
            bottom_right = block.GetBottomRight()
            for col in range(top_left.GetCol(), bottom_right.GetCol() + 1):
                cols.add(col)
        rows = self.GetNumberRows()
        for col in range(self.GetNumberCols()):
            all_selected = True
            for row in range(rows):
                if not self.IsInSelection(row, col):
                    all_selected = False
                    break
            if all_selected:
                cols.add(col)
        return sorted(list(cols))

    """从旧路径获取文件信息并写入表格行：参数传入None则不填写该列，参数传入非None包括空字串则填写该列"""
    def write_row_by_old_path(self, grid_row_idx, old_path, new_path=None, match_name=None, execute_result=None, path_depth=None):
        if grid_row_idx is None or old_path is None:
            return
        if grid_row_idx < 0 or grid_row_idx >= self.GetNumberRows():
            log_error(f"行索引错误: {grid_row_idx}")
            return
        if old_path == "":
            for loop_col in range(len(self.default_col_labels)): self.SetCellValue(grid_row_idx, loop_col, "")
            if new_path is not None: self.SetCellValue(grid_row_idx, self.COL_NEW_PATH, new_path.strip())
            if match_name is not None: self.SetCellValue(grid_row_idx, self.COL_MATCH_NAME, match_name)
        else:
            if old_path is not None: self.SetCellValue(grid_row_idx, self.COL_OLD_PATH, old_path.strip())
            if new_path is not None: self.SetCellValue(grid_row_idx, self.COL_NEW_PATH, new_path.strip())
            if match_name is not None: self.SetCellValue(grid_row_idx, self.COL_MATCH_NAME, match_name)
            if execute_result is not None: self.SetCellValue(grid_row_idx, self.COL_RESULT, execute_result)
            if path_depth is not None: self.SetCellValue(grid_row_idx, self.COL_LEVEL, str(path_depth))
            try:
                self.SetCellValue(grid_row_idx, self.COL_FILE_NAME, os.path.basename(old_path))
                stat_info = os.stat(old_path)
                if os.path.isdir(old_path):
                    self.SetCellValue(grid_row_idx, self.COL_TYPE, translate("file_type_directory"))
                    dir_size = self.get_directory_size(old_path)
                    self.SetCellValue(grid_row_idx, self.COL_SIZE, f"{dir_size / 1024:.2f}")
                else:
                    _, ext = os.path.splitext(os.path.basename(old_path))
                    self.SetCellValue(grid_row_idx, self.COL_TYPE, ext.upper() if ext else translate("file_type_file"))
                    self.SetCellValue(grid_row_idx, self.COL_SIZE, f"{stat_info.st_size / 1024:.2f}")
                ctime_str = datetime.datetime.fromtimestamp(stat_info.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
                mtime_str = datetime.datetime.fromtimestamp(stat_info.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                self.SetCellValue(grid_row_idx, self.COL_CREATE_TIME, ctime_str)
                self.SetCellValue(grid_row_idx, self.COL_MODIFY_TIME, mtime_str)
                is_hidden = self.is_hidden_file(old_path)
                self.SetCellValue(grid_row_idx, self.COL_HIDDEN, translate("yes") if is_hidden else translate("no"))
                is_readonly = self.is_readonly_file(old_path)
                self.SetCellValue(grid_row_idx, self.COL_READONLY, translate("read_only") if is_readonly else translate("writable"))
                parent_dir = os.path.dirname(old_path)
                self.SetCellValue(grid_row_idx, self.COL_PARENT_DIR, os.path.basename(parent_dir))
            except Exception as e:
                log_error(f"获取文件属性失败 {old_path}: {e}")
                self.SetCellValue(grid_row_idx, self.COL_FILE_NAME, "")
                self.SetCellValue(grid_row_idx, self.COL_TYPE, translate("unknown"))
                self.SetCellValue(grid_row_idx, self.COL_SIZE, "0.00")
                self.SetCellValue(grid_row_idx, self.COL_CREATE_TIME, translate("unknown_time"))
                self.SetCellValue(grid_row_idx, self.COL_MODIFY_TIME, translate("unknown_time"))
                self.SetCellValue(grid_row_idx, self.COL_HIDDEN, translate("no"))
                self.SetCellValue(grid_row_idx, self.COL_READONLY, translate("unknown"))
                self.SetCellValue(grid_row_idx, self.COL_PARENT_DIR, "")

    """获取目录大小 - 递归计算目录内所有文件的总大小"""
    def get_directory_size(self, dir_path):
        total_size = 0
        try:
            for entry in os.scandir(dir_path):
                if entry.is_file():
                    total_size += entry.stat().st_size
                elif entry.is_dir():
                    total_size += self.get_directory_size(entry.path)
        except (PermissionError, OSError):
            pass
        return total_size

    """判断文件或目录是否为隐藏的（包括检查所有上层目录）"""
    def is_hidden_file(self, full_path):
        try:
            normalized_path = os.path.abspath(full_path)
            if os.name == 'nt':
                FILE_ATTRIBUTE_HIDDEN = 0x02
                root = os.path.splitdrive(normalized_path)[0] + "\\"
                current_path = normalized_path
                while True:
                    if current_path != root:
                        try:
                            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(current_path))
                            if attrs != -1 and bool(attrs & FILE_ATTRIBUTE_HIDDEN):
                                return True
                        except (AttributeError, OSError, WindowsError):
                            pass
                    parent_path = os.path.dirname(current_path)
                    if parent_path == current_path or parent_path == root:
                        break
                    current_path = parent_path
                return False
            else:
                parts = os.path.normpath(normalized_path).split(os.sep)
                for part in parts:
                    if part and part not in (".", "..") and part.startswith('.'):
                        return True
                return False
        except Exception:
            return False

    """判断文件是否为只读文件"""
    def is_readonly_file(self, full_path):
        try:
            if os.name == 'nt':
                FILE_ATTRIBUTE_READONLY = 0x01
                attrs = ctypes.windll.kernel32.GetFileAttributesW(str(full_path))
                return attrs != -1 and bool(attrs & FILE_ATTRIBUTE_READONLY)
            else:
                return not os.access(full_path, os.W_OK)
        except Exception:
            return False

    # 找到所有路径的共同前缀（保持原始大小写）
    def common_prefix(self, paths_list, need_exist=False):
        if not paths_list:
            return None
        if need_exist:
            valid_paths = [os.path.normpath(p) for p in paths_list if os.path.exists(p)]
            if not valid_paths: return None
            paths_to_process = valid_paths
        else:
            paths_to_process = [os.path.normpath(p) for p in paths_list]
        split_paths = [p.split(os.sep) for p in paths_to_process]
        reference_parts = split_paths[0]
        min_len = min(len(p) for p in split_paths)
        common_parts = []
        for i in range(min_len):
            current_part = split_paths[0][i]
            if all(p[i].lower() == current_part.lower() for p in split_paths):
                common_parts.append(reference_parts[i])
            else:
                break
        if common_parts:
            if os.name == 'nt' and len(common_parts) > 0:
                if len(common_parts[0]) == 2 and common_parts[0][1] == ':':
                    pass
                elif len(common_parts[0]) == 1 and common_parts[0].isalpha():
                    common_parts[0] = common_parts[0] + ':'
            common_path = os.sep.join(common_parts)
            if os.name == 'nt':
                if len(common_path) == 2 and common_path[1] == ':':
                    common_path = common_path + '\\'
                elif len(common_path) > 2 and common_path[1] == ':' and common_path[2] != '\\':
                    common_path = common_path[:2] + '\\' + common_path[2:]
            try:
                if os.path.exists(common_path) and os.path.isdir(common_path):
                    return common_path
                else:
                    while common_parts:
                        common_parts.pop()
                        if common_parts:
                            parent_path = os.sep.join(common_parts)
                            if os.name == 'nt' and len(parent_path) == 2 and parent_path[1] == ':':
                                parent_path = parent_path + '\\'
                            elif os.name == 'nt' and len(parent_path) == 1 and parent_path.isalpha():
                                parent_path = parent_path + ':' + '\\'
                            if os.path.exists(parent_path) and os.path.isdir(parent_path):
                                return parent_path
            except Exception:
                return None
        return None

    """导入表格数据"""
    def on_import_grid(self, event):
        log_info("开始导入表格数据")
        try:
            self.disable_controls()
            self.layout_frame()
            wx.Yield()
            dlg = wx.MessageDialog(
                self.frame,
                translate("dialog_import_requirements"),
                translate("dialog_title_confirm_import"),
                wx.OK | wx.CANCEL | wx.OK_DEFAULT | wx.ICON_WARNING
            )
            dlg.SetOKLabel(translate("dialog_btn_ok"))
            result = dlg.ShowModal()
            dlg.Destroy()
            if result != wx.ID_OK:
                log_info("用户取消导入操作")
                return
            with wx.FileDialog(self.frame, translate("dialog_import_excel"),
                             wildcard=f"{translate('filetype_excel')} (*.xlsx;*.xls)|*.xlsx;*.xls",
                             style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
                if fileDialog.ShowModal() == wx.ID_CANCEL:
                    log_info("用户取消选择文件")
                    return
                filepath = fileDialog.GetPath()
                log_info(f"选择导入文件: {filepath}")
                wb = openpyxl.load_workbook(filepath, data_only=True)
                ws = wb.active
                header_row = []
                max_col = ws.max_column
                for col in range(1, max_col + 1):
                    cell_value = ws.cell(row=1, column=col).value
                    header_row.append(str(cell_value) if cell_value is not None else "")
                column_mapping = {}
                for excel_col_idx, header_value in enumerate(header_row):
                    header_value = str(header_value).strip()
                    if not header_value: continue
                    for grid_col_idx in range(len(self.default_col_labels)):
                        if grid_col_idx < len(self.default_import_need) and self.default_import_need[grid_col_idx]:
                            grid_header = self.default_col_labels[grid_col_idx]
                            if grid_header == header_value:
                                column_mapping[excel_col_idx] = grid_col_idx
                                break
                if not column_mapping:
                    log_warning("没有找到可导入的列")
                    wx.MessageBox(
                        translate("dialog_no_importable_columns", columns=', '.join([self.default_col_labels[i] for i in range(len(self.default_col_labels)) if i < len(self.default_import_need) and self.default_import_need[i]])),
                        translate("dialog_title_error"), wx.OK | wx.ICON_ERROR
                    )
                    return
                all_paths = []
                data_rows = []
                for row in range(2, ws.max_row + 1):
                    row_data = {}
                    has_data = False
                    for excel_col_idx, grid_col_idx in column_mapping.items():
                        cell_value = ws.cell(row=row, column=excel_col_idx + 1).value
                        if cell_value is not None:
                            cell_str = str(cell_value).strip()
                            if cell_str:
                                row_data[grid_col_idx] = cell_str
                                if grid_col_idx == self.COL_OLD_PATH:
                                    all_paths.append(os.path.normpath(cell_str))
                                has_data = True
                    if has_data:
                        data_rows.append(row_data)
                if not data_rows:
                    log_warning("没有有效数据可导入")
                    self.update_status(translate("status_no_valid_data"))
                    wx.MessageBox(translate("dialog_no_valid_data"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
                    return
                if self.GetNumberRows() > 0: self.DeleteRows(0, self.GetNumberRows())
                if self.GetNumberRows() < len(data_rows): self.AppendRows(len(data_rows) - self.GetNumberRows())
                search_path = self.get_search_folder()
                if not search_path:
                    search_path = self.common_prefix(all_paths, True)
                    if search_path: self.set_search_folder(search_path)
                for row_idx, row_data in enumerate(data_rows):
                    old_path = row_data[self.COL_OLD_PATH] if self.COL_OLD_PATH in row_data else None
                    new_path = row_data[self.COL_NEW_PATH] if self.COL_NEW_PATH in row_data else None
                    match_name = row_data[self.COL_MATCH_NAME] if self.COL_MATCH_NAME in row_data else None
                    if old_path and search_path and os.path.normpath(old_path).startswith(os.path.normpath(search_path)):
                        path_depth = os.path.normpath(old_path).replace(os.path.normpath(search_path), '').count(os.sep)
                    else:
                        path_depth = ""
                    self.write_row_by_old_path(row_idx, old_path or "", new_path or "", match_name or "", "", path_depth)
                self.adjust_table_rows()
                self.update_status(translate("status_imported_rows", count=len(data_rows)))
                self.set_col_sort_indicator()
                log_info(f"成功导入 {len(data_rows)} 行数据")
                # 导入后清空撤销历史
                self.clear_undo_history()
        except Exception as e:
            log_error(f"导入表格失败: {str(e)}")
            wx.MessageBox(translate("error_import_excel", error=str(e)), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
        finally:
            self.restore_controls()
            self.layout_frame()

    """导出到Excel"""
    def on_export_grid(self, event):
        # 第一步：检查表格中是否有旧路径
        old_path_all_empty = True
        for row in range(self.GetNumberRows()):
            old_path = self.GetCellValue(row, self.COL_OLD_PATH)
            if old_path and old_path.strip():
                old_path_all_empty = False
                break
        # 获取搜索目录
        search_path = self.get_search_folder()
        if not search_path:
            if old_path_all_empty:
                search_path = None
            else:
                all_paths = []
                for row in range(self.GetNumberRows()):
                    old_path = self.GetCellValue(row, self.COL_OLD_PATH)
                    if old_path and old_path.strip():
                        try:
                            all_paths.append(os.path.normpath(old_path.strip()))
                        except Exception:
                            continue
                search_path = self.common_prefix(all_paths, True)
                if search_path: self.set_search_folder(search_path)
        # 显示对话框，选择导出方式（单选按钮组，默认选中"导出数据表格"）
        dlg = wx.Dialog(self.frame, title=translate("export_table_dialog_title"), size=(self._spx(520), self._spx(300)))
        title_sizer = wx.BoxSizer(wx.HORIZONTAL)
        icon = wx.StaticBitmap(dlg, bitmap=wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, wx.ART_OTHER, (32, 32)))
        title = wx.StaticText(dlg, label=translate("export_table_dialog_title"))
        font = title.GetFont()
        font.SetPointSize(int(font.GetPointSize() + 1))
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(font)
        title_sizer.Add(icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self._spx(10))
        title_sizer.Add(title, 0, wx.ALIGN_CENTER_VERTICAL)
        info_text = wx.StaticText(dlg, label=translate("export_table_dialog_info"))
        info_text.Wrap(self._spx(460))
        # 三个导出方式通过单选按钮组选择；默认选中"导出数据表格"
        radio_tree = wx.RadioButton(dlg, label=translate("export_dir_tree_text"), style=wx.RB_GROUP)
        radio_tree.SetMinSize((-1, self._spx(26)))
        radio_data = wx.RadioButton(dlg, label=translate("export_data_table"))
        radio_data.SetMinSize((-1, self._spx(26)))
        radio_template = wx.RadioButton(dlg, label=translate("export_template_table"))
        radio_template.SetMinSize((-1, self._spx(26)))
        # 表格中没有旧路径时，目录树与数据表格导出不可用（模板始终可用），默认选中模板
        if old_path_all_empty:
            radio_tree.Disable()
            radio_data.Disable()
            radio_data.SetValue(False)
            radio_template.SetValue(True)
        else:
            radio_data.SetValue(True)
        btn_ok = wx.Button(dlg, label=translate("btn_export_grid"), id=wx.ID_OK)
        btn_ok.SetMinSize((-1, self._spx(28)))
        btn_cancel = wx.Button(dlg, label=translate("cancel"), id=wx.ID_CANCEL)
        btn_cancel.SetMinSize((-1, self._spx(28)))
        btn_cancel.SetFocus()
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(title_sizer, 0, wx.ALL | wx.EXPAND, self._spx(10))
        sizer.Add(info_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, self._spx(10))
        radio_sizer = wx.BoxSizer(wx.VERTICAL)
        radio_sizer.Add(radio_tree, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, self._spx(20))
        radio_sizer.Add(radio_data, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, self._spx(20))
        radio_sizer.Add(radio_template, 0, wx.LEFT | wx.RIGHT, self._spx(20))
        sizer.Add(radio_sizer, 0, wx.EXPAND | wx.BOTTOM, self._spx(5))
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_cancel, 0, wx.ALL, self._spx(5))
        btn_sizer.Add(btn_ok, 0, wx.ALL, self._spx(5))
        btn_sizer.AddStretchSpacer()
        sizer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, self._spx(10))
        dlg.SetMinSize((self._spx(520), self._spx(300)))
        dlg.SetSizer(sizer)
        dlg.Fit()
        def on_confirm_export(event):
            if radio_tree.GetValue():
                dlg.EndModal(1)
            elif radio_data.GetValue():
                dlg.EndModal(2)
            else:
                dlg.EndModal(3)
        btn_ok.Bind(wx.EVT_BUTTON, on_confirm_export)
        result = dlg.ShowModal()
        if result == 1:
            self.export_data_to_tree(search_path)
        elif result == 2:
            self.export_data_or_tmpl(search_path, is_tmpl=False)
        elif result == 3:
            self.export_data_or_tmpl(search_path, is_tmpl=True)
        dlg.Destroy()

    """导出目录树文本"""
    def export_data_to_tree(self, search_path):
        log_info(f"开始导出目录树: {search_path}")
        if not search_path or not os.path.exists(search_path) or not os.path.isdir(search_path):
            log_error("无效的搜索路径")
            wx.MessageBox(translate("error_invalid_search_path_for_tree"), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
            return
        try:
            self.disable_controls()
            self.layout_frame()
            wx.Yield()
            default_filename = 'FolderTree'
            if search_path:
                default_filename = f"{os.path.basename(search_path)}_{default_filename}"
            default_path = os.path.dirname(search_path) if os.path.exists(search_path) else ""
            with wx.FileDialog(self.frame, translate("export_dir_tree_text"), defaultDir=default_path,
                             defaultFile=default_filename, wildcard="文本文件 (*.txt)|*.txt",
                             style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as fileDialog:
                if fileDialog.ShowModal() == wx.ID_CANCEL:
                    log_info("用户取消选择保存路径")
                    return
                filepath = fileDialog.GetPath()
                if not filepath.lower().endswith('.txt'):
                    filepath += '.txt'
                self.update_status(translate("status_exporting_dir_tree"))
                wx.Yield()
                valid_path_list = [search_path]
                valid_dir_count = 0
                valid_file_count = 0
                not_exist_count = 0
                not_child_count = 0
                for row in range(self.GetNumberRows()):
                    old_path = self.GetCellValue(row, self.COL_OLD_PATH).strip()
                    if not old_path:
                        continue
                    try:
                        normalized_path = os.path.normpath(old_path)
                    except Exception:
                        not_exist_count += 1
                        continue
                    if not os.path.exists(normalized_path):
                        not_exist_count += 1
                        continue
                    try:
                        real_search_path = os.path.realpath(search_path)
                        real_normalized_path = os.path.realpath(normalized_path)
                        if not real_normalized_path.startswith(real_search_path + os.sep):
                            not_child_count += 1
                            continue
                    except Exception:
                        not_child_count += 1
                        continue
                    if normalized_path not in valid_path_list:
                        valid_path_list.append(normalized_path)
                tree_structure = {}
                tree_structure[search_path] = {'dirs': [], 'files': []}
                for path in valid_path_list[1:]:
                    try:
                        rel_path = os.path.relpath(path, search_path)
                    except ValueError:
                        continue
                    if os.path.isdir(path):
                        valid_dir_count += 1
                    else:
                        valid_file_count += 1
                    parts = rel_path.split(os.sep)
                    for i in range(len(parts)):
                        if i == 0:
                            current_path = os.path.join(search_path, parts[0])
                        else:
                            current_path = os.path.join(search_path, *parts[:i+1])
                        parent_path = os.path.dirname(current_path) if i > 0 else search_path
                        if parent_path not in tree_structure:
                            tree_structure[parent_path] = {'dirs': [], 'files': []}
                        if i == len(parts) - 1:
                            if os.path.isdir(current_path):
                                if current_path not in tree_structure[parent_path]['dirs']:
                                    tree_structure[parent_path]['dirs'].append(current_path)
                            else:
                                if current_path not in tree_structure[parent_path]['files']:
                                    tree_structure[parent_path]['files'].append(current_path)
                        else:
                            if current_path not in tree_structure[parent_path]['dirs']:
                                tree_structure[parent_path]['dirs'].append(current_path)
                            if current_path not in tree_structure:
                                tree_structure[current_path] = {'dirs': [], 'files': []}
                for parent_path in tree_structure:
                    tree_structure[parent_path]['files'].sort()
                    tree_structure[parent_path]['dirs'].sort()
                tree_lines = []
                root_display = os.path.basename(search_path) if os.path.basename(search_path) else search_path
                if not root_display.endswith(os.sep):
                    root_display += os.sep
                tree_lines.append(root_display)

                def build_tree(parent_path, prefix="", is_last=True):
                    if parent_path not in tree_structure:
                        return []
                    result = []
                    children = tree_structure[parent_path]
                    file_count = len(children['files'])
                    dir_count = len(children['dirs'])
                    for i, file_path in enumerate(children['files']):
                        is_last_child = (i == file_count - 1) and (dir_count == 0)
                        file_name = os.path.basename(file_path)
                        connector = "└── " if is_last_child else "├── "
                        result.append(f"{prefix}{connector}{file_name}")
                    for i, dir_path in enumerate(children['dirs']):
                        is_last_child = i == dir_count - 1
                        dir_name = os.path.basename(dir_path)
                        if not dir_name.endswith(os.sep):
                            dir_name += os.sep
                        connector = "└── " if is_last_child else "├── "
                        result.append(f"{prefix}{connector}{dir_name}")
                        new_prefix = prefix + ("    " if is_last_child else "│   ")
                        result.extend(build_tree(dir_path, new_prefix, is_last_child))
                    return result
                tree_lines.extend(build_tree(search_path, "", True))
                if tree_lines:
                    tree_lines[0] = f"{tree_lines[0]} (合计：{valid_file_count}个子文件，{valid_dir_count}个子目录)"
                tree_lines.append("")
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(tree_lines))
                skip_info = ""
                if not_exist_count > 0 or not_child_count > 0:
                    skip_info = translate("skip_info_format", not_exist=not_exist_count, not_child=not_child_count)
                self.update_status(translate("dir_tree_saved_to", filepath=filepath, skip_info=skip_info))
                log_info(f"目录树已保存到: {filepath}")
        except PermissionError:
            log_error(f"文件被占用: {filepath}")
            wx.MessageBox(translate("error_file_in_use", filepath=filepath), translate("export_failed"), wx.OK | wx.ICON_ERROR)
        except Exception as e:
            log_error(f"导出目录树失败: {str(e)}")
            wx.MessageBox(translate("error_export_tree", error=str(e)), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
        finally:
            self.restore_controls()
            self.layout_frame()
            wx.Yield()

    """导出到Excel"""
    def export_data_or_tmpl(self, search_path, is_tmpl):
        log_info(f"开始导出Excel: is_tmpl={is_tmpl}")
        if self.GetNumberRows() == 0 and not is_tmpl:
            log_warning("没有数据可导出")
            wx.MessageBox(translate("dialog_no_data_to_export"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            self.disable_controls()
            self.layout_frame()
            wx.Yield()
            default_path = ""
            if is_tmpl:
                default_filename = "Template_OperateFiles"
            else:
                default_filename = "OperateFiles"
            if search_path:
                default_path = os.path.dirname(search_path) if os.path.exists(search_path) else ""
                if not is_tmpl: default_filename = f"{os.path.basename(search_path)}_{default_filename}"
            with wx.FileDialog(self.frame, translate("dialog_export_excel"), defaultDir=default_path,
                             defaultFile=default_filename, wildcard=f"{translate('filetype_excel')} (*.xlsx)|*.xlsx",
                             style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as fileDialog:
                if fileDialog.ShowModal() == wx.ID_CANCEL:
                    log_info("用户取消选择保存路径")
                    return
                filepath = fileDialog.GetPath()
                log_info(f"选择导出文件: {filepath}")
                if not filepath.lower().endswith('.xlsx'):
                    filepath += '.xlsx'
                self.update_status(translate("status_exporting_excel"))
                wx.Yield()
                wb = Workbook()
                ws = wb.active
                def clean_sheet_name(name):
                    if not name:
                        return "OperateFiles"
                    invalid_chars = ['\\', '/', '*', '?', ':', '[', ']']
                    for char in invalid_chars:
                        name = name.replace(char, '_')
                    name = name.replace("'", "")
                    if name and name[0].isdigit():
                        name = "Sheet_" + name
                    if len(name) > 31:
                        name = name[:31]
                    if not name:
                        name = "OperateFiles"
                    return name
                ws.title = clean_sheet_name("OperateFiles_" + os.path.basename(search_path) if search_path else "OperateFiles")
                gray_fill = PatternFill(start_color="D3D3D3", end_color="D3D3D3", fill_type="solid")
                thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
                left_alignment = Alignment(horizontal='left', vertical='center')
                center_alignment = Alignment(horizontal='center', vertical='center')
                right_alignment = Alignment(horizontal='right', vertical='center')
                if is_tmpl:
                    export_cols = [i for i, need in enumerate(self.default_import_need) if need]
                    if not export_cols:
                        wx.MessageBox(translate("dialog_no_columns_to_export"), translate("dialog_title_info"), wx.OK | wx.ICON_INFORMATION)
                        self.restore_controls()
                        self.layout_frame()
                        wx.Yield()
                        return
                    total_export_cols = len(export_cols) + 1
                    ws.column_dimensions['A'].width = 5
                    for excel_col_idx, grid_col in enumerate(export_cols, start=2):
                        column_letter = get_column_letter(excel_col_idx)
                        tool_window_width = self.default_export_widths[grid_col]
                        ws.column_dimensions[column_letter].width = tool_window_width
                    last_write_row_idx = 100
                    for row_excel in range(1, last_write_row_idx + 2):
                        cell = ws.cell(row=row_excel, column=1)
                        cell.border = thin_border
                        if row_excel == 1:
                            cell.value = '编号'
                            cell.fill = gray_fill
                            cell.alignment = center_alignment
                            cell.number_format = '@'
                        else:
                            cell.value = row_excel - 1
                            cell.alignment = center_alignment
                        for excel_col_idx, grid_col in enumerate(export_cols, start=2):
                            cell = ws.cell(row=row_excel, column=excel_col_idx)
                            cell.border = thin_border
                            if row_excel == 1:
                                cell.value = self.default_col_labels[grid_col]
                                cell.fill = gray_fill
                                cell.number_format = '@'
                            else:
                                cell.number_format = self.default_export_format[grid_col]
                            wx_alignment = self.default_export_aligns[grid_col]
                            if wx_alignment == wx.ALIGN_LEFT:
                                cell.alignment = left_alignment
                            elif wx_alignment == wx.ALIGN_CENTER:
                                cell.alignment = center_alignment
                            elif wx_alignment == wx.ALIGN_RIGHT:
                                cell.alignment = right_alignment
                    last_row = last_write_row_idx + 1
                    last_col = len(export_cols) + 1
                    ws.row_dimensions[1].height = 25
                    if last_row > 1:
                        ws.auto_filter.ref = f"A1:{get_column_letter(last_col)}{last_row}"
                    ws.freeze_panes = 'A2'
                else:
                    last_write_row_idx = self.GetNumberRows()
                    last_write_col_idx = len(self.default_col_labels)
                    readonly_fill = PatternFill(start_color="F7F7F7", end_color="F7F7F7", fill_type="solid")
                    for col_excel in range(1, last_write_col_idx + 2):
                        if col_excel == 1:
                            ws.column_dimensions['A'].width = 5
                        else:
                            tool_window_width = self.default_export_widths[col_excel - 2]
                            auto_width = self.calculate_auto_width(col_excel - 2, ret_type="EXPORT_EXCEL")
                            col_label = self.GetColLabelValue(col_excel - 2)
                            if col_label in [translate("col_old_path"), translate("col_new_path")]:
                                ws.column_dimensions[get_column_letter(col_excel)].width = min(tool_window_width, auto_width)
                            elif col_label in [translate("col_create_time"), translate("col_modify_time")]:
                                ws.column_dimensions[get_column_letter(col_excel)].width = tool_window_width
                            else:
                                ws.column_dimensions[get_column_letter(col_excel)].width = max(tool_window_width, auto_width)
                        for row_excel in range(1, last_write_row_idx + 2):
                            cell = ws.cell(row_excel, col_excel)
                            cell.border = thin_border
                            if row_excel == 1:
                                cell.fill = gray_fill
                                cell.number_format = '@'
                            else:
                                cell.number_format = self.default_export_format[col_excel - 2]
                            if col_excel == 1:
                                cell.alignment = center_alignment
                            else:
                                wx_alignment = self.default_export_aligns[col_excel - 2]
                                if wx_alignment == wx.ALIGN_LEFT:
                                    cell.alignment = left_alignment
                                elif wx_alignment == wx.ALIGN_CENTER:
                                    cell.alignment = center_alignment
                                elif wx_alignment == wx.ALIGN_RIGHT:
                                    cell.alignment = right_alignment
                            if row_excel >= 2 and not self.default_col_editables[col_excel - 2]:
                                cell.fill = readonly_fill
                    for row_excel in range(1, last_write_row_idx + 2):
                        for col_excel in range(1, last_write_col_idx + 2):
                            if row_excel == 1:
                                if col_excel == 1:
                                    ws.cell(row_excel, col_excel).value = '编号'
                                else:
                                    ws.cell(row_excel, col_excel).value = self.default_col_labels[col_excel - 2]
                            else:
                                if col_excel == 1:
                                    ws.cell(row_excel, col_excel).value = row_excel - 1
                                else:
                                    grid_cell_value = self.GetCellValue(row_excel - 2, col_excel - 2)
                                    if grid_cell_value:
                                        if self.default_export_format[col_excel - 2] in ['0', '#,##0.00']:
                                            try:
                                                converted_val = float(grid_cell_value)
                                                ws.cell(row_excel, col_excel).value = converted_val
                                            except ValueError:
                                                ws.cell(row_excel, col_excel).value = grid_cell_value
                                        elif self.default_export_format[col_excel - 2] in ['yyyy-mm-dd',]:
                                            try:
                                                converted_val = datetime.datetime.strptime(grid_cell_value, "%Y-%m-%d %H:%M:%S")
                                                ws.cell(row_excel, col_excel).value = converted_val
                                            except ValueError:
                                                ws.cell(row_excel, col_excel).value = grid_cell_value
                                        else:
                                            ws.cell(row_excel, col_excel).value = grid_cell_value
                    last_row = last_write_row_idx + 1
                    last_col = last_write_col_idx + 1
                    ws.row_dimensions[1].height = 25
                    if last_row > 1:
                        ws.auto_filter.ref = f"A1:{get_column_letter(last_col)}{last_row}"
                    ws.freeze_panes = 'A2'
                wb.save(filepath)
                if is_tmpl:
                    self.update_status(translate("template_saved_to", filepath=filepath))
                    log_info(f"模板已保存到: {filepath}")
                else:
                    self.update_status(translate("table_saved_to", filepath=filepath))
                    log_info(f"表格已保存到: {filepath}")
        except PermissionError:
            log_error(f"文件被占用: {filepath}")
            wx.MessageBox(translate("error_file_in_use", filepath=filepath), translate("export_failed"), wx.OK | wx.ICON_ERROR)
        except Exception as e:
            log_error(f"导出Excel失败: {str(e)}")
            wx.MessageBox(translate("error_export_excel", error=str(e)), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
        finally:
            self.restore_controls()
            self.layout_frame()
            wx.Yield()

    """清空表格按钮事件"""
    def on_clear_adjust_table(self, min_rows):
        total_row_count = self.GetNumberRows()
        if total_row_count > 0:
            self.DeleteRows(0, total_row_count)
        if total_row_count < min_rows:
            self.AppendRows(min_rows - total_row_count)
        elif total_row_count > min_rows:
            self.AppendRows(min_rows)
        if self.GetNumberRows() != min_rows:
            rows = self.GetNumberRows()
            if rows > 0: self.DeleteRows(0, rows)
            self.AppendRows(min_rows)
        for row in range(min_rows):
            for col in range(self.GetNumberCols()):
                self.SetCellValue(row, col, "")
        self.update_status("表格已清空")
        # 清空后清空撤销历史
        self.clear_undo_history()

    """获取选中的行列表"""
    def get_selected_rows(self):
        rows = set()
        selected_cells = self.GetSelectedCells()
        for cell in selected_cells:
            row, col = cell
            rows.add(row)
        selected_blocks = self.GetSelectedBlocks()
        for block in selected_blocks:
            top_left = block.GetTopLeft()
            bottom_right = block.GetBottomRight()
            for row in range(top_left.GetRow(), bottom_right.GetRow() + 1):
                rows.add(row)
        return sorted(list(rows))

    """判断指定行在"调整表格行数"语义下是否为空行

    非空判定检查 0/1/2 三列（旧路径/新路径/匹配名），任一列有内容即视为非空行。
    仅检查旧路径会把"仅新路径有数据"的行误判为空行而被静默删除。
    """
    def _is_row_empty_for_adjust(self, row):
        for col in (self.COL_OLD_PATH, self.COL_NEW_PATH, self.COL_MATCH_NAME):
            value = self.GetCellValue(row, col)
            if value and value.strip():
                return False
        return True

    """调整表格行数，确保最后一个非空行后面有5个空行，且只有5个空行"""
    def adjust_table_rows(self):
        total_rows = self.GetNumberRows()
        if total_rows == 0:
            self.AppendRows(20)
            return
        last_nonempty_row = -1
        for row in range(total_rows-1, -1, -1):
            if not self._is_row_empty_for_adjust(row):
                last_nonempty_row = row
                break
        if last_nonempty_row == -1:
            if total_rows > 20:
                self.DeleteRows(20, total_rows-20)
            elif total_rows < 20:
                self.AppendRows(20-total_rows)
            return
        empty_rows_after = 0
        for row in range(last_nonempty_row+1, total_rows):
            if self._is_row_empty_for_adjust(row):
                empty_rows_after += 1
            else:
                empty_rows_after = 0
                last_nonempty_row = row
        if empty_rows_after < 5:
            self.AppendRows(5 - empty_rows_after)
        elif empty_rows_after > 5:
            extra_rows_count = empty_rows_after - 5
            delete_start = total_rows - extra_rows_count
            if delete_start < last_nonempty_row + 1:
                delete_start = last_nonempty_row + 1
            self.DeleteRows(delete_start, extra_rows_count)
        total_rows = self.GetNumberRows()
        if total_rows < 20:
            self.AppendRows(20 - total_rows)

    """处理粘贴后的数据

    粘贴触发的联动副作用（清空只读列、按旧路径回填、清除重复旧行、调整表格行数）
    会收集为撤销变更返回，由调用方并入粘贴操作的撤销记录。
    返回 (cell_changes, rows_added, rows_deleted)。
    """
    def process_after_paste(self, pasted_rows, start_col):
        cell_changes = []

        def _collect_row_changes(row, before_values):
            # 对比操作前整行快照，收集实际发生变化的单元格（含只读列的联动写入）
            for col in range(self.GetNumberCols()):
                new_val = self.GetCellValue(row, col)
                if new_val != before_values[col]:
                    cell_changes.append((row, col, before_values[col], new_val))

        # 7.12: 检查粘贴区域是否包含"旧路径"列（列索引0）
        paste_contains_old_path = False
        for col in range(start_col, start_col + len(self.default_col_labels)):
            if col < self.GetNumberCols() and col == self.COL_OLD_PATH:
                paste_contains_old_path = True
                break
        if paste_contains_old_path:
            for row in pasted_rows:
                before_values = [self.GetCellValue(row, col) for col in range(self.GetNumberCols())]
                for col in range(self.GetNumberCols()):
                    if not self.default_col_editables[col]:
                        self.SetCellValue(row, col, "")
                old_path = self.GetCellValue(row, self.COL_OLD_PATH)
                if old_path and old_path.strip():
                    self.write_row_by_old_path(row, old_path.strip())
                _collect_row_changes(row, before_values)
        paste_area_paths = set()
        for row in pasted_rows:
            old_path = self.GetCellValue(row, self.COL_OLD_PATH)
            if old_path and old_path.strip():
                paste_area_paths.add(old_path.strip())
        for row in range(self.GetNumberRows()-1, 0, -1):
            if row not in pasted_rows:
                old_path = self.GetCellValue(row, self.COL_OLD_PATH)
                if old_path and old_path.strip() and old_path.strip() in paste_area_paths:
                    before_values = [self.GetCellValue(row, col) for col in range(self.GetNumberCols())]
                    for col in range(self.GetNumberCols()):
                        self.SetCellValue(row, col, "")
                    _collect_row_changes(row, before_values)
        # 调整表格行数：行追加/删除同样纳入撤销记录。
        # adjust_table_rows 只会从末尾删除"空行"（0/1/2 列为空），先快照末尾连续空行数据供撤销恢复
        rows_added = None
        rows_deleted = []
        tail_empty_rows = []  # [(row, [cell_values]), ...] 降序
        for row in range(self.GetNumberRows()-1, -1, -1):
            if not self._is_row_empty_for_adjust(row):
                break
            tail_empty_rows.append((row, [self.GetCellValue(row, col) for col in range(self.GetNumberCols())]))
        total_before = self.GetNumberRows()
        self.adjust_table_rows()
        total_after = self.GetNumberRows()
        if total_after > total_before:
            rows_added = (total_before, total_after - total_before)
        elif total_after < total_before:
            removed_count = total_before - total_after
            # tail_empty_rows 为降序，被删的是其中行号最大的 removed_count 行
            rows_deleted = tail_empty_rows[:removed_count]
        return (cell_changes, rows_added, rows_deleted)

    """搜索表格内容"""
    def on_search_grid(self, event):
        if self.search_dialog is None or not isinstance(self.search_dialog, wx.Dialog):
            last_search_text = getattr(self, 'last_search_text', '')
            self.search_dialog = tfo_SearchDialog(self.frame, self, last_search_text)

            def on_dialog_close(evt):
                if hasattr(self.search_dialog, 'search_text'):
                    self.last_search_text = self.search_dialog.search_text.GetValue()
                self.search_dialog = None
                evt.Skip()
            self.search_dialog.Bind(wx.EVT_CLOSE, on_dialog_close)
            self.search_dialog.Show()
        else:
            if not self.search_dialog.IsShown():
                self.search_dialog.Show()
            self.search_dialog.Raise()
            self.search_dialog.SetFocus()
            if hasattr(self, 'last_search_text') and self.last_search_text:
                self.search_dialog.search_text.SetValue(self.last_search_text)
                wx.CallAfter(self._search_text_move_cursor_to_end)

    """移动光标到搜索文本末尾"""
    def _search_text_move_cursor_to_end(self):
        if hasattr(self, 'search_dialog') and self.search_dialog and hasattr(self.search_dialog, 'search_text'):
            text_len = len(self.search_dialog.search_text.GetValue())
            self.search_dialog.search_text.SetInsertionPoint(text_len)
            self.search_dialog.search_text.SetFocus()

    """搜索上一个"""
    def search_previous(self):
        if not self.search_results:
            return False
        if self.current_search_index <= 0:
            return False
        self.current_search_index -= 1
        self.select_search_result()
        return True

    """搜索下一个"""
    def search_next(self):
        if not self.search_results:
            return False
        if self.current_search_index >= len(self.search_results) - 1:
            return False
        self.current_search_index += 1
        self.select_search_result()
        return True

    """执行搜索"""
    def perform_search(self, search_text):
        self.search_text = search_text.lower()
        self.search_results = []
        self.current_search_index = -1
        if not self.search_text:
            return 0
        for row in range(self.GetNumberRows()):
            for col in range(2):
                cell_value = self.GetCellValue(row, col)
                if self.search_text in cell_value.lower():
                    self.search_results.append((row, col))
        return len(self.search_results)

    def select_search_result(self):
        if 0 <= self.current_search_index < len(self.search_results):
            row, col = self.search_results[self.current_search_index]
            self.SetGridCursor(row, col)
            self.SelectBlock(row, col, row, col)
            self.GoToCell(row, col)
            self.SetFocus()
            if self.search_dialog:
                self.search_dialog.update_status(translate("search_dialog_current", count=len(self.search_results), index=self.current_search_index + 1))

    """单元格选择事件 - 在状态栏显示当前单元格内容"""
    def on_select_cell(self, event):
        row = event.GetRow()
        col = event.GetCol()
        if row >= 0 and col >= 0:
            cell_value = self.GetCellValue(row, col)
            col_name = self.GetColLabelValue(col) if col < self.GetNumberCols() else ""
            if cell_value:
                self.update_status(translate("status_cell_value", value=cell_value))
            else:
                self.update_status(translate("status_cell_empty"))
        event.Skip()

"""搜索对话框类"""
class tfo_SearchDialog(wx.Dialog):
    def __init__(self, parent, grid, last_search_text=''):
        self.TFP_DPI_SCALE_FACTOR = getattr(grid, 'TFP_DPI_SCALE_FACTOR', 1.0)
        self._spx = lambda v: spx_calc(v) if v != -1 else -1
        dialog_width = self._spx(450)
        dialog_height = self._spx(250)
        super().__init__(parent, title=translate("search_dialog_title"), size=(dialog_width, dialog_height))
        self.grid = grid
        self.last_search_text = last_search_text
        self._is_closing = False
        self._last_focus = None
        parent_size = parent.GetSize()
        parent_pos = parent.GetPosition()
        offset = self._spx(10)
        dialog_x = parent_pos.x + parent_size.width - dialog_width - offset
        dialog_y = parent_pos.y + parent_size.height - dialog_height - offset
        self.SetPosition(wx.Point(dialog_x, dialog_y))
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.status_label = wx.StaticText(panel, label=translate("search_dialog_prompt"))
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_label = wx.StaticText(panel, label=translate("search_dialog_label"))
        self.search_text = wx.TextCtrl(panel, size=(self._spx(200), -1))
        self.search_text.SetValue(last_search_text)
        search_sizer.Add(search_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self._spx(5))
        search_sizer.Add(self.search_text, 1, wx.EXPAND)
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_search_prev = wx.Button(panel, label=translate("search_dialog_btn_prev"))
        self.btn_search_next = wx.Button(panel, label=translate("search_dialog_btn_next"))
        self.btn_cancel = wx.Button(panel, label=translate("dialog_btn_cancel"), id=wx.ID_CANCEL)
        button_sizer.Add(self.btn_cancel, 0, wx.ALL, self._spx(5))
        button_sizer.AddStretchSpacer()
        button_sizer.Add(self.btn_search_prev, 0, wx.ALL, self._spx(5))
        button_sizer.Add(self.btn_search_next, 0, wx.ALL, self._spx(5))
        option_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.case_sensitive = wx.CheckBox(panel, label=translate("search_dialog_case_sensitive"))
        self.whole_word = wx.CheckBox(panel, label=translate("search_dialog_whole_word"))
        option_sizer.Add(self.case_sensitive, 0, wx.RIGHT, self._spx(10))
        option_sizer.Add(self.whole_word, 0, wx.RIGHT, self._spx(10))
        sizer.Add(self.status_label, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, self._spx(10))
        sizer.Add(search_sizer, 0, wx.EXPAND | wx.ALL, self._spx(10))
        sizer.Add(option_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self._spx(10))
        sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, self._spx(10))
        panel.SetSizer(sizer)
        self.Bind(wx.EVT_BUTTON, self.on_search_prev, self.btn_search_prev)
        self.Bind(wx.EVT_BUTTON, self.on_search_next, self.btn_search_next)
        self.Bind(wx.EVT_BUTTON, self.on_cancel, self.btn_cancel)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_ACTIVATE, self.on_activate)
        self.Bind(wx.EVT_SHOW, self.on_show)
        self.search_text.Bind(wx.EVT_SET_FOCUS, self.on_focus_change)
        self.search_text.Bind(wx.EVT_TEXT, self.on_text_changed)
        self.search_text.Bind(wx.EVT_KEY_UP, self.on_key_up)
        self.search_text.SetFocus()
        self.update_button_state()
        self.SetWindowStyle(wx.DEFAULT_DIALOG_STYLE)

    def on_show(self, event):
        if event.IsShown():
            self.search_text.SetFocus()
            wx.CallAfter(self.move_cursor_to_end)
            self._last_focus = self.search_text
        event.Skip()

    def move_cursor_to_end(self):
        text_len = len(self.search_text.GetValue())
        self.search_text.SetInsertionPoint(text_len)

    def on_activate(self, event):
        if event.GetActive():
            if self._last_focus and hasattr(self._last_focus, 'SetFocus'):
                self._last_focus.SetFocus()
                if self._last_focus == self.search_text:
                    wx.CallAfter(self.move_cursor_to_end)
            else:
                self.search_text.SetFocus()
                wx.CallAfter(self.move_cursor_to_end)
        event.Skip()

    def on_focus_change(self, event):
        self._last_focus = event.GetEventObject()
        event.Skip()

    def on_text_changed(self, event):
        search_text = self.search_text.GetValue().strip()
        self.update_button_state(search_text)

    def update_button_state(self, search_text=None):
        if search_text is None:
            search_text = self.search_text.GetValue().strip()
        has_search_text = bool(search_text)
        self.btn_search_prev.Enable(has_search_text)
        self.btn_search_next.Enable(has_search_text)

    def on_search_prev(self, event):
        search_text = self.search_text.GetValue().strip()
        if not search_text:
            self.update_status(translate("search_dialog_enter_text"))
            return
        if search_text != self.last_search_text:
            result_count = self.perform_search()
            if result_count == 0:
                self.update_status(translate("search_dialog_not_found", text=search_text))
                return
            self.last_search_text = search_text
            if self.grid.search_results:
                self.grid.current_search_index = len(self.grid.search_results) - 1
                self.grid.select_search_result()
                self.update_status(translate("search_dialog_found", count=result_count, index=self.grid.current_search_index + 1))
        else:
            if self.grid.search_previous():
                self.update_status(translate("search_dialog_found", count=len(self.grid.search_results), index=self.grid.current_search_index + 1))
            else:
                self.update_status(translate("search_dialog_first", count=len(self.grid.search_results)))
        self.activate_and_restore_focus()

    def on_search_next(self, event):
        search_text = self.search_text.GetValue().strip()
        if not search_text:
            self.update_status(translate("search_dialog_enter_text"))
            return
        if search_text != self.last_search_text:
            result_count = self.perform_search()
            if result_count == 0:
                self.update_status(translate("search_dialog_not_found", text=search_text))
                return
            self.last_search_text = search_text
            if self.grid.search_results:
                self.grid.current_search_index = 0
                self.grid.select_search_result()
                self.update_status(translate("search_dialog_found", count=result_count, index=self.grid.current_search_index + 1))
        else:
            if self.grid.search_next():
                self.update_status(translate("search_dialog_found", count=len(self.grid.search_results), index=self.grid.current_search_index + 1))
            else:
                self.update_status(translate("search_dialog_last", count=len(self.grid.search_results)))
        self.activate_and_restore_focus()

    def perform_search(self):
        search_text = self.search_text.GetValue()
        case_sensitive = self.case_sensitive.GetValue()
        whole_word = self.whole_word.GetValue()
        self.grid.search_text = search_text if case_sensitive else search_text.lower()
        self.grid.search_results = []
        self.grid.current_search_index = -1
        if not self.grid.search_text:
            return 0
        for row in range(self.grid.GetNumberRows()):
            for col in range(2):
                cell_value = self.grid.GetCellValue(row, col)
                if case_sensitive:
                    text_to_search = cell_value
                else:
                    text_to_search = cell_value.lower()
                if whole_word:
                    words = re.findall(r'\b\w+\b', text_to_search)
                    if any(self.grid.search_text == word for word in words):
                        self.grid.search_results.append((row, col))
                else:
                    if self.grid.search_text in text_to_search:
                        self.grid.search_results.append((row, col))
        return len(self.grid.search_results)

    def activate_and_restore_focus(self):
        self.Raise()
        self.SetFocus()
        if self._last_focus and hasattr(self._last_focus, 'SetFocus'):
            self._last_focus.SetFocus()
            if self._last_focus == self.search_text:
                wx.CallAfter(self.move_cursor_to_end)
        else:
            self.search_text.SetFocus()
            wx.CallAfter(self.move_cursor_to_end)

    def on_cancel(self, event):
        if not self._is_closing:
            self._is_closing = True
            self.Close()

    def on_close(self, event):
        if not self._is_closing:
            self._is_closing = True
        if hasattr(self, 'search_text'):
            if hasattr(self.grid, 'last_search_text'):
                self.grid.last_search_text = self.search_text.GetValue()
        self.grid.search_dialog = None
        self.Destroy()

    def on_key_up(self, event):
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
            if event.ShiftDown():
                self.on_search_prev(event)
            else:
                self.on_search_next(event)
            return
        elif keycode == wx.WXK_ESCAPE:
            if not self._is_closing:
                self._is_closing = True
                self.Close()
            return
        event.Skip()

    def update_status(self, text):
        self.status_label.SetLabel(text)
        self.status_label.Refresh()

"""文件拖放目标类 - 用于表格"""
class tfo_FileDropTargetGrid(wx.FileDropTarget):
    def __init__(self, grid):
        super().__init__()
        self.grid = grid

    def OnDragOver(self, x, y, default):
        return wx.DragLink

    def OnDropFiles(self, x, y, filenames):
        if not filenames:
            return False
        existing_paths = set()
        for row_idx in range(self.grid.GetNumberRows()):
            path = self.grid.GetCellValue(row_idx, self.grid.COL_OLD_PATH).strip()
            if path:
                existing_paths.add(os.path.normcase(path))
        new_paths = []
        for path in filenames:
            if os.path.isfile(path):
                _, ext = os.path.splitext(path)
                ext = ext.lower()
                if ext == '.lnk' or ext == '':
                    target_path = self.parse_shortcut(path)
                    if target_path and os.path.exists(target_path):
                        path = target_path
                    else:
                        parent_dir = os.path.dirname(path)
                        if os.path.isdir(parent_dir):
                            path = parent_dir
            if os.path.exists(path) and os.path.normcase(path) not in existing_paths:
                new_paths.append(path)
                existing_paths.add(os.path.normcase(path))
        if not new_paths:
            self.grid.update_status(translate("status_all_paths_exist"))
            return False
        last_nonempty_row = -1
        for i in range(self.grid.GetNumberRows()):
            if self.grid.GetCellValue(i, self.grid.COL_OLD_PATH).strip():
                last_nonempty_row = i
        insert_position = last_nonempty_row + 1
        if last_nonempty_row == -1:
            insert_position = 0
        total_row_count = self.grid.GetNumberRows()
        if insert_position + len(new_paths) > total_row_count:
            self.grid.AppendRows(insert_position + len(new_paths) - total_row_count)
        for i, path in enumerate(new_paths):
            row_idx = insert_position + i
            self.grid.SetCellValue(row_idx, self.grid.COL_OLD_PATH, path)
            for col in range(self.grid.GetNumberCols()):
                if col not in [self.grid.COL_OLD_PATH, self.grid.COL_NEW_PATH]:
                    self.grid.SetCellValue(row_idx, col, "")
        self.grid.adjust_table_rows()
        last_nonempty_row = -1
        for i in range(self.grid.GetNumberRows()-1, -1, -1):
            if self.grid.GetCellValue(i, self.grid.COL_OLD_PATH).strip():
                last_nonempty_row = i
                break
        if last_nonempty_row >= 0:
            self.grid.SetGridCursor(last_nonempty_row, self.grid.COL_NEW_PATH)
            self.grid.SelectBlock(last_nonempty_row, self.grid.COL_NEW_PATH, last_nonempty_row, self.grid.COL_NEW_PATH)
            self.grid.GoToCell(last_nonempty_row, self.grid.COL_NEW_PATH)
        self.grid.update_status(translate("status_dropped_paths", count=len(new_paths)))
        # 拖放后清空撤销历史
        self.grid.clear_undo_history()
        # 返回 True 告知拖放框架数据已被接受处理
        return True

    """解析Windows快捷方式(.lnk)文件"""
    def parse_shortcut(self, lnk_path):
        import ctypes
        try:
            class GUID(ctypes.Structure):
                _fields_ = [
                    ('Data1', ctypes.wintypes.DWORD),
                    ('Data2', ctypes.wintypes.WORD),
                    ('Data3', ctypes.wintypes.WORD),
                    ('Data4', ctypes.wintypes.BYTE * 8)
                ]
            IID_IShellLink = GUID(0x000214EE, 0x0000, 0x0000, (0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))
            CLSID_ShellLink = GUID(0x00021401, 0x0000, 0x0000, (0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))
            class IPersistFile(ctypes.c_void_p):
                pass
            class IShellLink(ctypes.c_void_p):
                pass
            ole32 = ctypes.windll.ole32
            ole32.CoInitialize(None)
            psl = ctypes.POINTER(IShellLink)()
            hr = ole32.CoCreateInstance(ctypes.byref(CLSID_ShellLink), None, 1, ctypes.byref(IID_IShellLink), ctypes.byref(psl))
            if hr != 0:
                ole32.CoUninitialize()
                return None
            ppf = ctypes.POINTER(IPersistFile)()
            hr = psl.QueryInterface(ctypes.byref(IID_IShellLink), ctypes.byref(ppf))
            if hr != 0:
                psl.Release()
                ole32.CoUninitialize()
                return None
            hr = ppf.Load(lnk_path, 0)
            if hr != 0:
                ppf.Release()
                psl.Release()
                ole32.CoUninitialize()
                return None
            buf = ctypes.create_unicode_buffer(260)
            psl.GetPath(buf, ctypes.sizeof(buf), None, 0)
            target_path = buf.value
            ppf.Release()
            psl.Release()
            ole32.CoUninitialize()
            return target_path if target_path else None
        except Exception:
            try:
                with open(lnk_path, 'rb') as f:
                    content = f.read()
                    path_pattern = r'[A-Za-z]:\\[^\x00]*'
                    matches = re.findall(path_pattern.encode('latin-1'), content)
                    for match in matches:
                        try:
                            potential_path = match.decode('utf-8', errors='ignore')
                            if os.path.exists(potential_path):
                                return potential_path
                        except Exception:
                            continue
            except Exception:
                pass
            return None
