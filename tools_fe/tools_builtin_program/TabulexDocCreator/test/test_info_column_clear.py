# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Get Doc Info 模式：清空 Source File 时联动清空该行只读信息列"""
import os
import sys

import pytest

_TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)


class _FakeEvent:
    def __init__(self, row, col):
        self._row = row
        self._col = col

    def GetRow(self):
        return self._row

    def GetCol(self):
        return self._col

    def Skip(self):
        pass


def _make_excel_grid():
    wx = pytest.importorskip('wx')
    try:
        app = wx.App(False)
    except Exception:
        pytest.skip('no GUI display available')
    from tdc_CustomGrid import tdc_CustomGrid

    class FakeTool:
        TFP_DPI_SCALE_FACTOR = 1.0

    frame = wx.Frame(None)
    grid = tdc_CustomGrid(frame, FakeTool(), doc_type='excel', fill_method='placeholder')
    return app, frame, grid


def _fill_row(grid, row, source='src.xlsx'):
    grid.SetCellValue(row, grid.COL_SOURCE_FILE, source)
    for col in range(grid.COL_DATA_START, grid.COL_DATA_START + 3):
        grid.SetCellValue(row, col, f'info-{col}')


def _assert_info_empty(grid, row):
    for col in range(grid.COL_DATA_START, grid.COL_DATA_START + 3):
        assert grid.GetCellValue(row, col) == '', (row, col)


def test_delete_key_clears_info_columns():
    app, frame, grid = _make_excel_grid()
    try:
        row = grid.DATA_ROW_START
        grid.set_operation_mode('get_file_info')
        _fill_row(grid, row)
        grid.SetGridCursor(row, grid.COL_SOURCE_FILE)
        grid._clear_selected_cells()
        assert grid.GetCellValue(row, grid.COL_SOURCE_FILE) == ''
        _assert_info_empty(grid, row)
    finally:
        app.Destroy()


def test_direct_edit_to_empty_clears_info_columns():
    app, frame, grid = _make_excel_grid()
    try:
        row = grid.DATA_ROW_START
        grid.set_operation_mode('get_file_info')
        _fill_row(grid, row)
        grid.SetCellValue(row, grid.COL_SOURCE_FILE, '')
        grid._on_cell_changed(_FakeEvent(row, grid.COL_SOURCE_FILE))
        _assert_info_empty(grid, row)
    finally:
        app.Destroy()


def test_paste_source_clears_info_columns():
    app, frame, grid = _make_excel_grid()
    try:
        row = grid.DATA_ROW_START
        grid.set_operation_mode('get_file_info')
        _fill_row(grid, row)
        grid.on_cells_pasted([(row, grid.COL_SOURCE_FILE)])
        _assert_info_empty(grid, row)
    finally:
        app.Destroy()


def test_create_mode_keeps_info_columns():
    app, frame, grid = _make_excel_grid()
    try:
        row = grid.DATA_ROW_START
        grid.set_operation_mode('create_from_template')
        _fill_row(grid, row)
        grid.SetCellValue(row, grid.COL_SOURCE_FILE, '')
        grid._on_cell_changed(_FakeEvent(row, grid.COL_SOURCE_FILE))
        # 非 Get Doc Info 模式不应联动清空
        assert grid.GetCellValue(row, grid.COL_DATA_START) == f'info-{grid.COL_DATA_START}'
    finally:
        app.Destroy()


def test_multiple_rows_cleared_on_delete():
    app, frame, grid = _make_excel_grid()
    try:
        r1, r2 = grid.DATA_ROW_START, grid.DATA_ROW_START + 1
        grid.set_operation_mode('get_file_info')
        _fill_row(grid, r1)
        _fill_row(grid, r2)
        grid.on_cells_cleared([(r1, grid.COL_SOURCE_FILE), (r2, grid.COL_SOURCE_FILE)])
        _assert_info_empty(grid, r1)
        _assert_info_empty(grid, r2)
    finally:
        app.Destroy()
