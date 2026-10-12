# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""切换操作模式时：清空 ID/Source File/Save File/Result 四列之外所有列的内容"""
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


def _fill_all_columns(grid, row):
    """填写固定四列 + 数据列（含表头行与数据行各一行样本）"""
    grid.SetCellValue(row, grid.COL_ID, 'id-1')
    grid.SetCellValue(row, grid.COL_SOURCE_FILE, 'src.xlsx')
    grid.SetCellValue(row, grid.COL_SAVE_FILE, 'out.xlsx')
    grid.SetCellValue(row, grid.COL_RESULT, 'Success')
    # 表头行（占位符/方向/数量）
    grid.SetCellValue(grid.HEADER_ROW_PLACEHOLDER, grid.COL_DATA_START, '{{name}}')
    grid.SetCellValue(grid.HEADER_ROW_DIRECTION, grid.COL_DATA_START, 'down')
    grid.SetCellValue(grid.HEADER_ROW_VALUE_COUNT, grid.COL_DATA_START, 'single')
    # 数据行
    grid.SetCellValue(row, grid.COL_DATA_START, 'value-1')
    grid.SetCellValue(row, grid.COL_DATA_START + 1, 'value-2')


def _assert_data_columns_empty(grid, rows):
    for row in rows:
        for col in range(grid.COL_DATA_START, grid.GetNumberCols()):
            assert grid.GetCellValue(row, col) == '', (row, col)


def _assert_fixed_columns_kept(grid, row):
    assert grid.GetCellValue(row, grid.COL_ID) == 'id-1'
    assert grid.GetCellValue(row, grid.COL_SOURCE_FILE) == 'src.xlsx'
    assert grid.GetCellValue(row, grid.COL_SAVE_FILE) == 'out.xlsx'
    assert grid.GetCellValue(row, grid.COL_RESULT) == 'Success'


def test_mode_switch_clears_data_columns_keeps_fixed():
    app, grid = _make_grid()
    try:
        row = grid.DATA_ROW_START
        _fill_all_columns(grid, row)
        grid.set_operation_mode('get_file_info')
        # 数据列（表头行 + 数据行）全部清空，固定四列保留
        _assert_data_columns_empty(grid, [grid.HEADER_ROW_PLACEHOLDER,
                                          grid.HEADER_ROW_DIRECTION,
                                          grid.HEADER_ROW_VALUE_COUNT,
                                          row])
        _assert_fixed_columns_kept(grid, row)
    finally:
        app.Destroy()


def test_mode_switch_back_also_clears():
    app, grid = _make_grid()
    try:
        row = grid.DATA_ROW_START
        grid.set_operation_mode('get_file_info')
        grid.SetCellValue(row, grid.COL_DATA_START, 'info-1')
        grid.SetCellValue(row, grid.COL_DATA_START + 1, 'info-2')
        grid.set_operation_mode('create_from_template')
        _assert_data_columns_empty(grid, [row])
    finally:
        app.Destroy()


def test_same_mode_does_not_clear():
    app, grid = _make_grid()
    try:
        row = grid.DATA_ROW_START
        # 重复设置当前模式（如下拉框重复选中同一项）不应清空已填内容
        grid.set_operation_mode('create_from_template')
        grid.SetCellValue(row, grid.COL_DATA_START, 'value-1')
        grid.set_operation_mode('create_from_template')
        assert grid.GetCellValue(row, grid.COL_DATA_START) == 'value-1'
    finally:
        app.Destroy()


def test_mode_switch_clears_undo_history():
    app, grid = _make_grid()
    try:
        row = grid.DATA_ROW_START
        grid.SetCellValue(row, grid.COL_DATA_START, 'value-1')
        grid.set_operation_mode('get_file_info')
        # 破坏性清空后撤销历史已清空，Ctrl+Z 不能恢复与新状态不符的旧值
        grid._undo()
        assert grid.GetCellValue(row, grid.COL_DATA_START) == ''
    finally:
        app.Destroy()


def test_mode_switch_clears_pdf_data_columns():
    app, grid = _make_grid(doc_type='pdf')
    try:
        row = grid.DATA_ROW_START
        _fill_all_columns(grid, row)
        grid.set_operation_mode('get_file_info')
        _assert_data_columns_empty(grid, [row])
        _assert_fixed_columns_kept(grid, row)
    finally:
        app.Destroy()


# ---------------------------------------------------------------------------
# Create Doc → Get Doc Info 切换确认框（>3 个非空单元格弹框，取消则回退下拉框）
# ---------------------------------------------------------------------------

def _make_tool():
    wx = pytest.importorskip('wx')
    try:
        app = wx.App(False)
    except Exception:
        pytest.skip('no GUI display available')
    from tool_main import create_tool
    frame = wx.Frame(None)
    panel = wx.Panel(frame)
    sizer = wx.BoxSizer(wx.VERTICAL)
    tool = create_tool(frame)
    tool.create_embedded_interface(panel, sizer)
    return app, tool


def _fill_cells(grid, count):
    """在数据列填入 count 个非空单元格（先表头行后数据行）"""
    row = grid.DATA_ROW_START
    for i in range(count):
        if i == 0:
            grid.SetCellValue(grid.HEADER_ROW_PLACEHOLDER, grid.COL_DATA_START, f'p{i}')
        else:
            grid.SetCellValue(row, grid.COL_DATA_START + i - 1, f'v{i}')


def test_create_to_get_confirm_yes_clears(monkeypatch):
    import wx
    app, tool = _make_tool()
    try:
        dt = 'excel'
        grid = tool.grids[dt]
        _fill_cells(grid, 4)  # 4 个非空 > 阈值 3 → 弹框
        asked = []
        monkeypatch.setattr(wx, 'MessageBox', lambda *a, **k: (asked.append(a), wx.YES)[1])
        tool.operation_modes[dt].SetSelection(1)
        tool._on_operation_mode_changed(dt, None)
        assert len(asked) == 1
        assert '4' in asked[0][0]  # 提示中包含非空单元格数量
        # 确认后正常切换并清空
        assert grid.operation_mode == 'get_file_info'
        _assert_data_columns_empty(grid, [grid.DATA_ROW_START])
    finally:
        app.Destroy()


def test_create_to_get_confirm_no_reverts(monkeypatch):
    import wx
    app, tool = _make_tool()
    try:
        dt = 'excel'
        grid = tool.grids[dt]
        _fill_cells(grid, 4)
        monkeypatch.setattr(wx, 'MessageBox', lambda *a, **k: wx.NO)
        tool.operation_modes[dt].SetSelection(1)
        tool._on_operation_mode_changed(dt, None)
        # 取消：模式不变、内容保留、下拉框回退到 Create Doc
        assert grid.operation_mode == 'create_from_template'
        assert grid.GetCellValue(grid.DATA_ROW_START, grid.COL_DATA_START) == 'v1'
        assert tool.operation_modes[dt].GetSelection() == 0
    finally:
        app.Destroy()


def test_create_to_get_few_cells_no_confirm(monkeypatch):
    import wx
    app, tool = _make_tool()
    try:
        dt = 'excel'
        grid = tool.grids[dt]
        _fill_cells(grid, 3)  # 3 个非空 ≤ 阈值 → 不弹框直接清空
        asked = []
        monkeypatch.setattr(wx, 'MessageBox', lambda *a, **k: (asked.append(a), wx.YES)[1])
        tool.operation_modes[dt].SetSelection(1)
        tool._on_operation_mode_changed(dt, None)
        assert asked == []
        assert grid.operation_mode == 'get_file_info'
        _assert_data_columns_empty(grid, [grid.DATA_ROW_START])
    finally:
        app.Destroy()


def test_get_to_create_never_confirms(monkeypatch):
    import wx
    app, tool = _make_tool()
    try:
        dt = 'excel'
        grid = tool.grids[dt]
        # 先切到 Get Doc Info（≤3 个非空，无弹框）
        tool.operation_modes[dt].SetSelection(1)
        tool._on_operation_mode_changed(dt, None)
        _fill_cells(grid, 10)  # Get Doc Info 下填大量信息列
        asked = []
        monkeypatch.setattr(wx, 'MessageBox', lambda *a, **k: (asked.append(a), wx.YES)[1])
        tool.operation_modes[dt].SetSelection(0)
        tool._on_operation_mode_changed(dt, None)
        # Get→Create 方向不弹框，直接清空
        assert asked == []
        assert grid.operation_mode == 'create_from_template'
        _assert_data_columns_empty(grid, [grid.DATA_ROW_START])
    finally:
        app.Destroy()
