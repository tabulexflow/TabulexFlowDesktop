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
TabulexFlow 共享Grid基类（SDK权威源）

提供所有Grid的公共行为：
- Delete 键：未编辑时清空选中单元格内容，编辑时删字符
- Ctrl+C/V：复制/粘贴（Tab 分隔，兼容 Excel）
- Ctrl+A：全选
- Ctrl+Z/Y：撤销/重做（最多 max_undo 步，默认20）
- Enter：向下移动光标
- Tab/Shift+Tab：向右/向左移动光标（含换行）
- 行标签右键菜单：追加10行 / 删除选中的行 / 删除行数据
- 列标签右键菜单：删除列数据
- 只读模式：可复制不可粘贴/清空
- 提示 Label：选中单元格时显示列提示
- 列对齐辅助方法：set_column_alignment()

子类可通过重写以下 hook 方法扩展行为：
- on_cells_cleared(cells): 单元格被清空后调用
- on_cells_pasted(cells): 单元格被粘贴后调用
- on_rows_added(count): 行被添加后调用
- on_rows_deleted(rows): 行被删除后调用

子类若重写 _on_key_down，应先处理自身特殊按键，
然后对未处理的按键调用 super()._on_key_down(event)。

注意：此文件是SDK的权威源。各子工具的BaseGrid（tfo_BaseGrid、tdc_BaseGrid、tbc_BaseGrid）
应改为继承此类，移除与TFP_BaseGrid重复的方法，仅保留各工具特有的功能。
"""

import wx
import wx.grid
import logging

logger = logging.getLogger(__name__)


class _UndoEntry:
    """撤销/重做条目（增量 Delta）"""

    def __init__(self):
        self.cell_changes = []      # [(row, col, old_value, new_value), ...]
        self.rows_added = None      # (start_row, count) 或 None
        self.rows_deleted = None    # [(row, [cell_values]), ...] 降序排列，或 None
        self.selection = None       # 操作前的选区状态（由 _capture_selection 返回）


class TFP_BaseGrid(wx.grid.Grid):
    """TabulexFlow 共享Grid基类

    提供所有Grid的公共行为：键盘快捷键、复制/粘贴、撤销/重做、
    右键菜单、只读模式、提示Label、列对齐等。

    子类可通过重写 hook 方法扩展行为，也可重写 _on_key_down
    处理自身特殊按键（对未处理的按键应调用 super()._on_key_down(event)）。

    Args:
        max_undo: 撤销/重做最大步数，默认20。子类可通过构造参数自定义
                  （如BDC=50，BFM=20，BC=20）。
    """

    MAX_UNDO = 20  # 默认值，子类可通过 __init__ 的 max_undo 参数覆盖

    def __init__(self, *args, max_undo=None, **kwargs):
        super().__init__(*args, **kwargs)
        if max_undo is not None:
            self.MAX_UNDO = max_undo
        self._read_only = False
        self._hint_label = None
        self._column_hints = {}
        # Undo/Redo 状态
        self._undo_stack = []
        self._redo_stack = []
        self._applying_undo = False      # 防止 undo/redo 操作本身被记录
        self._setup_common_behaviors()

    def _setup_common_behaviors(self):
        """绑定公共事件"""
        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self.Bind(wx.grid.EVT_GRID_LABEL_RIGHT_CLICK, self._on_label_right_click)
        self.Bind(wx.grid.EVT_GRID_CELL_RIGHT_CLICK, self._on_cell_right_click)
        self.Bind(wx.grid.EVT_GRID_SELECT_CELL, self._on_cell_select)
        # 仅绑定 CHANGING（不绑定 CHANGED），避免与子类的 CHANGED 绑定冲突
        # 使用 wx.CallAfter 在值已改变后记录 Undo 条目
        self.Bind(wx.grid.EVT_GRID_CELL_CHANGING, self._on_cell_changing)

    def _translate(self, key, **kwargs):
        """翻译i18n键为当前语言的值

        基类使用SDK默认的i18n单例进行翻译。
        子类应重写此方法，使用自己的i18n管理器进行翻译，
        以确保能找到子工具locales目录下的翻译键。
        """
        from tfp_toolkit.tfp_i18n_manager import translate
        return translate(key, **kwargs)

    # ================================================================
    #  键盘事件处理
    # ================================================================

    def _on_key_down(self, event):
        """公共键盘事件处理

        子类重写时，对未处理的按键应调用 super()._on_key_down(event)。
        """
        key_code = event.GetKeyCode()
        modifiers = event.GetModifiers()

        if key_code == wx.WXK_DELETE:
            if self.IsCellEditControlShown():
                event.Skip()
            else:
                self._clear_selected_cells()

        elif modifiers == wx.MOD_CONTROL and key_code == ord('C'):
            self._copy_selection()

        elif modifiers == wx.MOD_CONTROL and key_code == ord('V'):
            if not self._read_only:
                self._paste_from_clipboard()

        elif modifiers == wx.MOD_CONTROL and key_code == ord('A'):
            self.SelectAll()

        elif modifiers == wx.MOD_CONTROL and key_code == ord('Z'):
            if not self.IsCellEditControlShown():
                self._undo()

        elif modifiers == wx.MOD_CONTROL and key_code == ord('Y'):
            if not self.IsCellEditControlShown():
                self._redo()

        elif key_code == wx.WXK_RETURN:
            if self.IsCellEditControlShown():
                event.Skip()
            else:
                self._move_cursor_down()

        elif key_code == wx.WXK_TAB:
            if self.IsCellEditControlShown():
                event.Skip()
            else:
                if event.ShiftDown():
                    self._move_cursor_prev()
                else:
                    self._move_cursor_next()

        else:
            event.Skip()

    def _move_cursor_down(self):
        """Enter 键：向下移动一行"""
        row = self.GetGridCursorRow()
        col = self.GetGridCursorCol()
        if row < self.GetNumberRows() - 1:
            self.SetGridCursor(row + 1, col)
            self.MakeCellVisible(row + 1, col)

    def _move_cursor_next(self):
        """Tab 键：向右移动一列，到末列换到下一行首列"""
        row = self.GetGridCursorRow()
        col = self.GetGridCursorCol()
        last_col = self.GetNumberCols() - 1
        last_row = self.GetNumberRows() - 1
        if col < last_col:
            self.SetGridCursor(row, col + 1)
        elif row < last_row:
            self.SetGridCursor(row + 1, 0)
        self.MakeCellVisible(self.GetGridCursorRow(), self.GetGridCursorCol())

    def _move_cursor_prev(self):
        """Shift+Tab：向左移动一列，到首列换到上一行末列"""
        row = self.GetGridCursorRow()
        col = self.GetGridCursorCol()
        last_col = self.GetNumberCols() - 1
        if col > 0:
            self.SetGridCursor(row, col - 1)
        elif row > 0:
            self.SetGridCursor(row - 1, last_col)
        self.MakeCellVisible(self.GetGridCursorRow(), self.GetGridCursorCol())

    # ================================================================
    #  单元格编辑事件（用于 Undo 记录）
    # ================================================================

    def _on_cell_changing(self, event):
        """单元格值即将改变前：暂存旧值，安排 CallAfter 记录 Undo"""
        if self._applying_undo or self._read_only:
            event.Skip()
            return
        row = event.GetRow()
        col = event.GetCol()
        old_value = self.GetCellValue(row, col)
        selection = self._capture_selection()
        # 在值已改变后（事件处理完毕）记录 Undo 条目
        wx.CallAfter(self._record_cell_edit, row, col, old_value, selection)
        event.Skip()

    def _record_cell_edit(self, row, col, old_value, selection):
        """在单元格编辑完成后记录 Undo 条目（由 CallAfter 调用）"""
        if self._applying_undo or self._read_only:
            return
        new_value = self.GetCellValue(row, col)
        if old_value != new_value:
            entry = _UndoEntry()
            entry.cell_changes = [(row, col, old_value, new_value)]
            entry.selection = selection
            self._push_undo(entry)

    # ================================================================
    #  Undo / Redo 栈管理
    # ================================================================

    def _capture_selection(self):
        """捕获当前选区状态"""
        blocks_tl = self.GetSelectionBlockTopLeft()
        blocks_br = self.GetSelectionBlockBottomRight()
        return {
            'cursor_row': self.GetGridCursorRow(),
            'cursor_col': self.GetGridCursorCol(),
            'selected_rows': list(self.GetSelectedRows()),
            'selected_cols': list(self.GetSelectedCols()),
            'selection_blocks': [
                (tl[0], tl[1], br[0], br[1])
                for tl, br in zip(blocks_tl, blocks_br)
            ],
        }

    def _restore_selection(self, sel):
        """恢复选区状态并滚动到可见位置"""
        self.ClearSelection()
        cursor_row = sel.get('cursor_row', 0)
        cursor_col = sel.get('cursor_col', 0)

        for tl_row, tl_col, br_row, br_col in sel.get('selection_blocks', []):
            self.SelectBlock(tl_row, tl_col, br_row, br_col, addToSelected=True)
        for row in sel.get('selected_rows', []):
            self.SelectRow(row, addToSelected=True)
        for col in sel.get('selected_cols', []):
            self.SelectCol(col, addToSelected=True)

        self.SetGridCursor(cursor_row, cursor_col)
        self.MakeCellVisible(cursor_row, cursor_col)

    def _push_undo(self, entry):
        """推入撤销栈，清空重做栈"""
        self._undo_stack.append(entry)
        if len(self._undo_stack) > self.MAX_UNDO:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _undo(self):
        """撤销"""
        if not self._undo_stack or self._read_only:
            return
        entry = self._undo_stack.pop()
        self._applying_undo = True
        self.BeginBatch()
        try:
            # 1. 撤销行删除（升序插入并恢复数据）
            if entry.rows_deleted:
                for row, values in reversed(entry.rows_deleted):
                    self.InsertRows(row)
                    for col_idx, val in enumerate(values):
                        if col_idx < self.GetNumberCols():
                            self.SetCellValue(row, col_idx, val)

            # 2. 撤销单元格变化（恢复旧值）
            for row, col, old_val, _new_val in entry.cell_changes:
                self.SetCellValue(row, col, old_val)

            # 3. 撤销行追加（删除追加的行）
            if entry.rows_added:
                start_row, count = entry.rows_added
                for _ in range(count):
                    self.DeleteRows(start_row)
        finally:
            self.EndBatch()
            self._applying_undo = False

        self._redo_stack.append(entry)

        # 触发 hook 以更新子类验证状态
        if entry.cell_changes:
            cells = [(r, c) for r, c, _, _ in entry.cell_changes]
            self.on_cells_cleared(cells)
        if entry.rows_deleted:
            self.on_rows_added(len(entry.rows_deleted))
        if entry.rows_added:
            self.on_rows_deleted(list(range(entry.rows_added[0],
                                            entry.rows_added[0] + entry.rows_added[1])))

        # 恢复选区并滚动到可见位置
        if entry.selection:
            self._restore_selection(entry.selection)

    def _redo(self):
        """重做"""
        if not self._redo_stack or self._read_only:
            return
        entry = self._redo_stack.pop()
        self._applying_undo = True
        self.BeginBatch()
        try:
            # 1. 重做行追加
            if entry.rows_added:
                start_row, count = entry.rows_added
                self.AppendRows(count)

            # 2. 重做单元格变化（应用新值）
            for row, col, _old_val, new_val in entry.cell_changes:
                self.SetCellValue(row, col, new_val)

            # 3. 重做行删除（降序删除）
            if entry.rows_deleted:
                for row, _values in entry.rows_deleted:
                    self.DeleteRows(row)
        finally:
            self.EndBatch()
            self._applying_undo = False

        self._undo_stack.append(entry)

        # 触发 hook
        if entry.cell_changes:
            cells = [(r, c) for r, c, _, _ in entry.cell_changes]
            self.on_cells_cleared(cells)
        if entry.rows_added:
            self.on_rows_added(entry.rows_added[1])
        if entry.rows_deleted:
            self.on_rows_deleted([r for r, _ in entry.rows_deleted])

        # 恢复选区并滚动到可见位置
        if entry.selection:
            self._restore_selection(entry.selection)

    # ================================================================
    #  清空 / Delete
    # ================================================================

    def _clear_selected_cells(self):
        """清空所有选中单元格的内容（跳过只读单元格）"""
        if self._read_only:
            return

        selection = self._capture_selection()
        cleared_cells = []
        undo_changes = []

        self.BeginBatch()
        try:
            selected_rows = self.GetSelectedRows()
            selected_cols = self.GetSelectedCols()
            blocks_tl = self.GetSelectionBlockTopLeft()
            blocks_br = self.GetSelectionBlockBottomRight()

            if selected_rows:
                for row in selected_rows:
                    for col in range(self.GetNumberCols()):
                        if not self.IsReadOnly(row, col):
                            old_val = self.GetCellValue(row, col)
                            self.SetCellValue(row, col, "")
                            cleared_cells.append((row, col))
                            undo_changes.append((row, col, old_val, ""))
            elif selected_cols:
                for col in selected_cols:
                    for row in range(self.GetNumberRows()):
                        if not self.IsReadOnly(row, col):
                            old_val = self.GetCellValue(row, col)
                            self.SetCellValue(row, col, "")
                            cleared_cells.append((row, col))
                            undo_changes.append((row, col, old_val, ""))
            elif blocks_tl:
                for i in range(len(blocks_tl)):
                    tl = blocks_tl[i]
                    br = blocks_br[i]
                    for row in range(tl[0], br[0] + 1):
                        for col in range(tl[1], br[1] + 1):
                            if not self.IsReadOnly(row, col):
                                old_val = self.GetCellValue(row, col)
                                self.SetCellValue(row, col, "")
                                cleared_cells.append((row, col))
                                undo_changes.append((row, col, old_val, ""))
            else:
                row = self.GetGridCursorRow()
                col = self.GetGridCursorCol()
                if 0 <= row < self.GetNumberRows() and 0 <= col < self.GetNumberCols():
                    if not self.IsReadOnly(row, col):
                        old_val = self.GetCellValue(row, col)
                        self.SetCellValue(row, col, "")
                        cleared_cells.append((row, col))
                        undo_changes.append((row, col, old_val, ""))
        finally:
            self.EndBatch()

        if cleared_cells:
            entry = _UndoEntry()
            entry.cell_changes = undo_changes
            entry.selection = selection
            self._push_undo(entry)
            self.on_cells_cleared(cleared_cells)

    # ================================================================
    #  复制 / Ctrl+C
    # ================================================================

    def _copy_selection(self):
        """复制选中单元格到剪贴板（Tab 分隔，兼容 Excel）"""
        selected_rows = self.GetSelectedRows()
        selected_cols = self.GetSelectedCols()
        blocks_tl = self.GetSelectionBlockTopLeft()
        blocks_br = self.GetSelectionBlockBottomRight()

        lines = []

        if selected_rows:
            sorted_rows = sorted(selected_rows)
            for row in sorted_rows:
                row_values = [self.GetCellValue(row, col)
                              for col in range(self.GetNumberCols())]
                lines.append('\t'.join(row_values))
        elif selected_cols:
            sorted_cols = sorted(selected_cols)
            for row in range(self.GetNumberRows()):
                row_values = [self.GetCellValue(row, col) for col in sorted_cols]
                lines.append('\t'.join(row_values))
        elif blocks_tl:
            for i in range(len(blocks_tl)):
                tl = blocks_tl[i]
                br = blocks_br[i]
                for row in range(tl[0], br[0] + 1):
                    row_values = [self.GetCellValue(row, col)
                                  for col in range(tl[1], br[1] + 1)]
                    lines.append('\t'.join(row_values))
        else:
            row = self.GetGridCursorRow()
            col = self.GetGridCursorCol()
            if 0 <= row < self.GetNumberRows() and 0 <= col < self.GetNumberCols():
                lines.append(self.GetCellValue(row, col))

        if lines:
            text = '\n'.join(lines)
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(text))
                wx.TheClipboard.Close()

    # ================================================================
    #  粘贴 / Ctrl+V
    # ================================================================

    def _paste_from_clipboard(self):
        """从剪贴板粘贴数据到当前焦点单元格位置

        以 GetGridCursorRow/Col 为起点，按 Tab 分隔列、换行分隔行粘贴。
        超出 Grid 行列数的部分跳过，只读单元格跳过。
        """
        if not wx.TheClipboard.Open():
            return

        target_row = self.GetGridCursorRow()
        target_col = self.GetGridCursorCol()

        if target_row < 0 or target_col < 0:
            wx.TheClipboard.Close()
            return

        selection = self._capture_selection()
        pasted_cells = []
        undo_changes = []

        try:
            text_data = wx.TextDataObject()
            if wx.TheClipboard.GetData(text_data):
                text = text_data.GetText()
                lines = text.split('\n')

                self.BeginBatch()
                try:
                    for row_offset, line in enumerate(lines):
                        if line.endswith('\r'):
                            line = line[:-1]
                        if not line.strip():
                            continue
                        grid_row = target_row + row_offset
                        if grid_row >= self.GetNumberRows():
                            break

                        values = line.split('\t')
                        for col_offset, value in enumerate(values):
                            grid_col = target_col + col_offset
                            if grid_col >= self.GetNumberCols():
                                break
                            if not self.IsReadOnly(grid_row, grid_col):
                                old_val = self.GetCellValue(grid_row, grid_col)
                                new_val = value.strip()
                                self.SetCellValue(grid_row, grid_col, new_val)
                                pasted_cells.append((grid_row, grid_col))
                                undo_changes.append((grid_row, grid_col, old_val, new_val))
                finally:
                    self.EndBatch()
        finally:
            wx.TheClipboard.Close()

        if pasted_cells:
            entry = _UndoEntry()
            entry.cell_changes = undo_changes
            entry.selection = selection
            self._push_undo(entry)
            self.on_cells_pasted(pasted_cells)

    # ================================================================
    #  单元格右键菜单
    # ================================================================

    def _on_cell_right_click(self, event):
        """单元格右键菜单：复制/粘贴/撤销/重做/删除数据

        子类可重写此方法以添加自定义菜单项，但建议调用
        super()._on_cell_right_click(event) 或使用 _add_default_cell_menu_items(menu)
        来保持公共菜单项的一致性。
        """
        if self.IsCellEditControlShown():
            event.Skip()
            return

        self.SetGridCursor(event.GetRow(), event.GetCol())

        menu = wx.Menu()
        self._add_default_cell_menu_items(menu)

        self.PopupMenu(menu)
        menu.Destroy()

    def _add_default_cell_menu_items(self, menu):
        """向菜单添加公共单元格操作项：复制/粘贴/撤销/重做/删除数据

        供子类在自定义右键菜单中调用，以保持菜单项的一致性。
        """
        copy_item = menu.Append(wx.ID_ANY, self._translate("base_grid_copy"))
        self.Bind(wx.EVT_MENU, lambda e: self._copy_selection(), copy_item)

        if not self._read_only:
            paste_item = menu.Append(wx.ID_ANY, self._translate("base_grid_paste"))
            self.Bind(wx.EVT_MENU, lambda e: self._paste_from_clipboard(), paste_item)

            menu.AppendSeparator()

            undo_item = menu.Append(wx.ID_ANY, self._translate("base_grid_undo"))
            self.Bind(wx.EVT_MENU, lambda e: self._undo(), undo_item)
            undo_item.Enable(self.can_undo())

            redo_item = menu.Append(wx.ID_ANY, self._translate("base_grid_redo"))
            self.Bind(wx.EVT_MENU, lambda e: self._redo(), redo_item)
            redo_item.Enable(self.can_redo())

            menu.AppendSeparator()

            delete_item = menu.Append(wx.ID_ANY, self._translate("base_grid_delete_data"))
            self.Bind(wx.EVT_MENU, lambda e: self._clear_selected_cells(), delete_item)

    # ================================================================
    #  行/列标签右键菜单
    # ================================================================

    def _on_label_right_click(self, event):
        """行/列标签右键菜单"""
        row = event.GetRow()
        col = event.GetCol()

        if row >= 0 and col == -1:
            selected_rows = self.GetSelectedRows()
            if row not in selected_rows:
                self.SelectRow(row)
                selected_rows = [row]
            has_selected_rows = len(selected_rows) > 0

            menu = wx.Menu()

            add_item = menu.Append(wx.ID_ANY, self._translate("base_grid_add_rows"))
            self.Bind(wx.EVT_MENU, lambda e: self._add_rows(10), add_item)

            delete_item = menu.Append(wx.ID_ANY, self._translate("base_grid_delete_selected_rows"))
            self.Bind(wx.EVT_MENU, lambda e: self._delete_selected_rows(), delete_item)
            delete_item.Enable(has_selected_rows)

            if not self._read_only:
                menu.AppendSeparator()
                clear_item = menu.Append(wx.ID_ANY, self._translate("base_grid_clear_selected_rows"))
                self.Bind(wx.EVT_MENU, lambda e: self._clear_selected_rows(), clear_item)
                clear_item.Enable(has_selected_rows)

            self.PopupMenu(menu)
            menu.Destroy()

        elif col >= 0 and row == -1:
            selected_cols = self.GetSelectedCols()
            if col not in selected_cols:
                self.SelectCol(col)
                selected_cols = [col]
            has_selected_cols = len(selected_cols) > 0

            if not self._read_only:
                menu = wx.Menu()

                clear_item = menu.Append(wx.ID_ANY, self._translate("base_grid_clear_selected_cols"))
                self.Bind(wx.EVT_MENU, lambda e: self._clear_selected_cols(), clear_item)
                clear_item.Enable(has_selected_cols)

                self.PopupMenu(menu)
                menu.Destroy()

    # ================================================================
    #  行/列操作方法
    # ================================================================

    def _add_rows(self, count=10):
        """追加指定数量的空行"""
        selection = self._capture_selection()
        start_row = self.GetNumberRows()
        self.AppendRows(count)

        entry = _UndoEntry()
        entry.rows_added = (start_row, count)
        entry.selection = selection
        self._push_undo(entry)

        self.on_rows_added(count)

    def _delete_selected_rows(self):
        """删除选中的行（若无选中则删除当前焦点行）"""
        selection = self._capture_selection()
        selected_rows = list(self.GetSelectedRows())
        if not selected_rows:
            row = self.GetGridCursorRow()
            if row >= 0:
                selected_rows = [row]

        if not selected_rows:
            return

        # 降序排序，从大到小删除以避免索引偏移
        selected_rows.sort(reverse=True)

        # 保存被删除行的完整数据（降序）
        saved_rows = []
        for row in selected_rows:
            row_data = [self.GetCellValue(row, col) for col in range(self.GetNumberCols())]
            saved_rows.append((row, row_data))

        self.BeginBatch()
        try:
            for row in selected_rows:
                self.DeleteRows(row)
        finally:
            self.EndBatch()

        entry = _UndoEntry()
        entry.rows_deleted = saved_rows
        entry.selection = selection
        self._push_undo(entry)

        self.on_rows_deleted(selected_rows)

    def _clear_selected_rows(self):
        """清空选中行内所有单元格的内容（跳过只读单元格）"""
        if self._read_only:
            return

        selection = self._capture_selection()
        selected_rows = list(self.GetSelectedRows())
        if not selected_rows:
            row = self.GetGridCursorRow()
            if row >= 0:
                selected_rows = [row]

        if not selected_rows:
            return

        cleared_cells = []
        undo_changes = []

        self.BeginBatch()
        try:
            for row in selected_rows:
                for col in range(self.GetNumberCols()):
                    if not self.IsReadOnly(row, col):
                        old_val = self.GetCellValue(row, col)
                        self.SetCellValue(row, col, "")
                        cleared_cells.append((row, col))
                        undo_changes.append((row, col, old_val, ""))
        finally:
            self.EndBatch()

        if cleared_cells:
            entry = _UndoEntry()
            entry.cell_changes = undo_changes
            entry.selection = selection
            self._push_undo(entry)
            self.on_cells_cleared(cleared_cells)

    def _clear_selected_cols(self):
        """清空选中列内所有单元格的内容（跳过只读单元格）"""
        if self._read_only:
            return

        selection = self._capture_selection()
        selected_cols = list(self.GetSelectedCols())
        if not selected_cols:
            col = self.GetGridCursorCol()
            if col >= 0:
                selected_cols = [col]

        if not selected_cols:
            return

        cleared_cells = []
        undo_changes = []

        self.BeginBatch()
        try:
            for col in selected_cols:
                for row in range(self.GetNumberRows()):
                    if not self.IsReadOnly(row, col):
                        old_val = self.GetCellValue(row, col)
                        self.SetCellValue(row, col, "")
                        cleared_cells.append((row, col))
                        undo_changes.append((row, col, old_val, ""))
        finally:
            self.EndBatch()

        if cleared_cells:
            entry = _UndoEntry()
            entry.cell_changes = undo_changes
            entry.selection = selection
            self._push_undo(entry)
            self.on_cells_cleared(cleared_cells)

    # ================================================================
    #  单元格选中提示
    # ================================================================

    def _on_cell_select(self, event):
        """单元格选中事件：更新提示 Label（如果已设置）"""
        if self._hint_label is not None:
            col = event.GetCol()
            hint = self._column_hints.get(col, "")
            self._hint_label.SetLabel(hint)
        event.Skip()

    # ================================================================
    #  公共 API
    # ================================================================

    def set_read_only(self, read_only=True):
        """设置只读模式：禁用编辑，但仍可复制和选择"""
        self._read_only = read_only
        self.EnableEditing(not read_only)

    def set_hint_label(self, label):
        """设置提示 Label 控件引用（选中单元格时更新其文本）"""
        self._hint_label = label

    def set_column_hints(self, hints_dict):
        """设置列提示字典 {列索引: 提示文字}"""
        self._column_hints = hints_dict

    def set_column_alignment(self, col, horiz=wx.ALIGN_CENTER, vert=wx.ALIGN_CENTER):
        """设置整列的对齐方式"""
        attr = wx.grid.GridCellAttr()
        attr.SetAlignment(horiz, vert)
        self.SetColAttr(col, attr)

    def set_column_read_only(self, col, read_only=True):
        """设置整列为只读"""
        attr = wx.grid.GridCellAttr()
        attr.SetReadOnly(read_only)
        self.SetColAttr(col, attr)

    def can_undo(self):
        """是否可以撤销"""
        return len(self._undo_stack) > 0 and not self._read_only

    def can_redo(self):
        """是否可以重做"""
        return len(self._redo_stack) > 0 and not self._read_only

    def clear_undo_history(self):
        """清空撤销/重做历史"""
        self._undo_stack.clear()
        self._redo_stack.clear()

    # ================================================================
    #  Hook 方法（子类可重写）
    # ================================================================

    def on_cells_cleared(self, cells):
        """单元格被清空后的回调

        Args:
            cells: 被清空的 (row, col) 元组列表
        """
        pass

    def on_cells_pasted(self, cells):
        """单元格被粘贴后的回调

        Args:
            cells: 被粘贴的 (row, col) 元组列表
        """
        pass

    def on_rows_added(self, count):
        """行被添加后的回调

        Args:
            count: 添加的行数
        """
        pass

    def on_rows_deleted(self, rows):
        """行被删除后的回调

        Args:
            rows: 被删除的行号列表（降序）
        """
        pass
