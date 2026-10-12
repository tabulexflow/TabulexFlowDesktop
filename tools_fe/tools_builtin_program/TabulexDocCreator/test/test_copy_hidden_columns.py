# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Grid 复制：隐藏列（宽度为0）不应出现在复制结果中，避免粘贴到 Excel 时多出空列"""
import os
import sys

import pytest

_TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)


def _make_grid(doc_type='excel'):
    wx = pytest.importorskip('wx')
    try:
        app = wx.App(False)
    except Exception:
        pytest.skip('no GUI display available')
    from tdc_CustomGrid import tdc_CustomGrid

    class FakeTool:
        TFP_DPI_SCALE_FACTOR = 1.0

    frame = wx.Frame(None)
    grid = tdc_CustomGrid(frame, FakeTool(), doc_type=doc_type, fill_method='placeholder')
    return app, grid


def _read_clipboard():
    wx = pytest.importorskip('wx')
    if not wx.TheClipboard.Open():
        pytest.skip('clipboard unavailable')
    data = wx.TextDataObject()
    wx.TheClipboard.GetData(data)
    wx.TheClipboard.Close()
    return data.GetText()


def test_column_layout_has_no_target_page_column():
    app, grid = _make_grid()
    try:
        assert grid.COL_SAVE_FILE == 2
        assert grid.COL_RESULT == 3
        assert grid.COL_DATA_START == 4
        assert not hasattr(grid, 'COL_TARGET_PAGE')
    finally:
        app.Destroy()


def test_copy_skips_hidden_columns():
    app, grid = _make_grid()
    try:
        row = grid.DATA_ROW_START
        # Get Doc Info 模式隐藏 保存文件 与 执行结果 两列
        grid.set_operation_mode('get_file_info')
        grid.SetCellValue(row, grid.COL_ID, '1')
        grid.SetCellValue(row, grid.COL_SOURCE_FILE, 'src.xlsx')
        grid.SetCellValue(row, grid.COL_SAVE_FILE, 'hidden-save')
        grid.SetCellValue(row, grid.COL_RESULT, 'hidden-result')
        grid.SetCellValue(row, grid.COL_DATA_START, 'info1')
        grid.SetCellValue(row, grid.COL_DATA_START + 1, 'info2')

        grid.ClearSelection()
        grid.SelectBlock(row, 0, row, grid.COL_DATA_START + 1)
        grid._copy_selection()

        assert _read_clipboard().split('\t') == ['1', 'src.xlsx', 'info1', 'info2']
    finally:
        app.Destroy()
