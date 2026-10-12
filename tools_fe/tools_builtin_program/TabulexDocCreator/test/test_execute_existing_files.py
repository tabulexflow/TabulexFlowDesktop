# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""执行前过滤：执行结果列已有值的组不应参与“覆盖确认”（此前会先问覆盖、再说全部跳过）"""
import os
import sys

import pytest

_TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)


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
    return wx, app, tool


def _add_row(grid, row, source, save, result=''):
    grid.SetCellValue(grid.HEADER_ROW_PLACEHOLDER, grid.COL_DATA_START, '{p1}')
    grid.SetCellValue(row, grid.COL_SOURCE_FILE, source)
    grid.SetCellValue(row, grid.COL_SAVE_FILE, save)
    grid.SetCellValue(row, grid.COL_DATA_START, 'V')
    grid.SetCellValue(row, grid.COL_RESULT, result)


def test_all_success_rows_are_filtered_out():
    wx, app, tool = _make_tool()
    try:
        grid = tool.grids['word']
        _add_row(grid, grid.DATA_ROW_START, 'src1.docx', 'out1.docx', result='Success')
        _add_row(grid, grid.DATA_ROW_START + 1, 'src2.docx', 'out2.docx', result='Success')
        data = grid.get_data_rows()
        assert tool._get_unskipped_rows(data) == []
    finally:
        app.Destroy()


def test_partial_success_filters_only_marked_groups():
    wx, app, tool = _make_tool()
    try:
        grid = tool.grids['word']
        _add_row(grid, grid.DATA_ROW_START, 'src1.docx', 'out1.docx', result='Success')
        _add_row(grid, grid.DATA_ROW_START + 1, 'src2.docx', 'out2.docx', result='')
        data = grid.get_data_rows()
        unskipped = tool._get_unskipped_rows(data)
        saves = [r.get('save_file') for r in unskipped]
        assert saves == ['out2.docx']
    finally:
        app.Destroy()


def test_inherited_rows_follow_parent_group():
    """同一保存文件的继承行：父行已成功时，整组（含继承行）都应被过滤"""
    wx, app, tool = _make_tool()
    try:
        grid = tool.grids['word']
        _add_row(grid, grid.DATA_ROW_START, 'src.docx', 'out.docx', result='Success')
        # 继承行：只有数据列
        grid.SetCellValue(grid.DATA_ROW_START + 1, grid.COL_DATA_START, 'V2')
        data = grid.get_data_rows()
        assert tool._get_unskipped_rows(data) == []
    finally:
        app.Destroy()


def test_execute_all_skipped_does_not_prompt_overwrite(tmp_path, monkeypatch):
    """全部组已成功时，不应再弹“File already exists. Overwrite?”，直接执行并给出跳过提示"""
    wx, app, tool = _make_tool()
    try:
        grid = tool.grids['word']
        out1 = str(tmp_path / 'out1.docx')
        out2 = str(tmp_path / 'out2.docx')
        for path in (out1, out2):
            with open(path, 'w', encoding='utf-8') as f:
                f.write('x')
        _add_row(grid, grid.DATA_ROW_START, str(tmp_path / 'src1.docx'), out1, result='Success')
        _add_row(grid, grid.DATA_ROW_START + 1, str(tmp_path / 'src2.docx'), out2, result='Success')

        messages = []
        monkeypatch.setattr(wx, 'MessageBox',
                            lambda msg, *a, **k: messages.append(msg) or wx.YES)
        executed = []
        tool._validate_data = lambda doc_type, data: []
        tool._execute_operation = lambda *a: executed.append(a)

        tool._on_execute('word')

        assert executed, 'worker should still run (and show the skip message)'
        assert not any('File already exists' in str(m) for m in messages), messages
    finally:
        app.Destroy()

