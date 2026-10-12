# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Grid 粘贴：剪贴板首行为“列标题行”时应跳过（与导入一致），普通数据行不跳过"""
import os
import sys

import pytest

_TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)


class _FakeTool:
    TFP_DPI_SCALE_FACTOR = 1.0


def _setup():
    wx = pytest.importorskip('wx')
    try:
        app = wx.App(False)
    except Exception:
        pytest.skip('no GUI display available')
    if not wx.TheClipboard.Open():
        pytest.skip('clipboard unavailable')
    return wx, app


def _new_grid(wx):
    from tdc_CustomGrid import tdc_CustomGrid
    frame = wx.Frame(None)
    return tdc_CustomGrid(frame, _FakeTool(), doc_type='word', fill_method='placeholder')


def _paste(wx, grid, text, row, col):
    wx.TheClipboard.SetData(wx.TextDataObject(text))
    wx.TheClipboard.Close()
    grid.SetGridCursor(row, col)
    grid.ClearSelection()
    grid._paste_from_clipboard()


def _set_html_clipboard(wx, rows):
    trs = ''
    for row in rows:
        tds = ''.join(f'<td><font>{cell if cell else "<br>"}</font></td>' for cell in row)
        trs += f'<tr>{tds}</tr>'
    wx.TheClipboard.SetData(wx.HTMLDataObject(f'<html><body><table>{trs}</table></body></html>'))
    wx.TheClipboard.Close()


def _paste_current(wx, grid, row, col):
    grid.SetGridCursor(row, col)
    grid.ClearSelection()
    grid._paste_from_clipboard()


def test_paste_html_flavor_preserves_leading_empty_rows():
    """纯文本 flavor 会丢首尾空行；HTML flavor 必须保留，粘贴到 Grid 后行不丢失"""
    wx, app = _setup()
    try:
        grid = _new_grid(wx)
        rows = [['', '', '', '', '', '', ''],
                ['', '', '', '', '', '', ''],
                ['', '', '', '', '{p1}', '{p2}', '{p3}'],
                ['', '', '', '', '', '', 'Image'],
                ['1', 'S1', 'D1', '', 'V1', 'V2', 'P1'],
                ['2', 'S2', 'D2', '', 'V11', 'V22', 'P2']]
        _set_html_clipboard(wx, rows)
        _paste_current(wx, grid, 0, 0)
        assert grid.GetCellValue(2, grid.COL_DATA_START) == '{p1}'      # 第 3 行落到 Grid 第 2 行
        assert grid.GetCellValue(grid.DATA_ROW_START, grid.COL_ID) == '1'
        assert grid.GetCellValue(grid.DATA_ROW_START + 1, grid.COL_ID) == '2'
    finally:
        app.Destroy()


def test_paste_html_flavor_with_label_column_skips_it():
    wx, app = _setup()
    try:
        grid = _new_grid(wx)
        rows = [['', '', '', '', '', '', '', ''],                       # A2 行（全空）
                ['', '', '', '', '', '', '', ''],                       # A3 行（全空）
                ['Direction', '', '', '', '', '{p1}', '{p2}', '{p3}'],  # A4
                ['Value Count', '', '', '', '', '', '', 'Image'],       # A5
                ['1', 'ID1', 'src1.docx', 'out1.docx', '', 'V1', '', ''],  # A6
                ['2', 'ID2', 'src2.docx', 'out2.docx', '', 'V2', '', '']]  # A7
        _set_html_clipboard(wx, rows)
        _paste_current(wx, grid, 0, 0)
        assert grid.GetCellValue(2, grid.COL_DATA_START) == '{p1}'      # 标签列已跳过
        assert grid.GetCellValue(grid.DATA_ROW_START, grid.COL_ID) == 'ID1'
        assert grid.GetCellValue(grid.DATA_ROW_START, grid.COL_SOURCE_FILE) == 'src1.docx'
        assert grid.GetCellValue(grid.DATA_ROW_START, grid.COL_SAVE_FILE) == 'out1.docx'
    finally:
        app.Destroy()


def test_paste_export_format_skips_header_row_and_label_col():
    wx, app = _setup()
    try:
        grid = _new_grid(wx)
        text = ("\tID\tSource File*\tSave File*\tResult\tData1\n"
                "Target Page\t\t\t\t\t\n"
                "Placeholder*\t\t\t\t\t{p1}\n"
                "Direction\t\t\t\t\t\n"
                "Value Count\t\t\t\t\t\n"
                "1\tID1\tsrc1.docx\tout1.docx\t\tV1")
        _paste(wx, grid, text, 0, 0)
        assert grid.GetCellValue(1, grid.COL_DATA_START) == '{p1}'
        assert grid.GetCellValue(grid.DATA_ROW_START, grid.COL_ID) == 'ID1'
        assert grid.GetCellValue(grid.DATA_ROW_START, grid.COL_SOURCE_FILE) == 'src1.docx'
        assert grid.GetCellValue(grid.DATA_ROW_START, grid.COL_SAVE_FILE) == 'out1.docx'
        assert grid.GetCellValue(grid.DATA_ROW_START, grid.COL_DATA_START) == 'V1'
    finally:
        app.Destroy()


def test_paste_title_row_without_label_col_skips_only_first_row():
    wx, app = _setup()
    try:
        grid = _new_grid(wx)
        text = ("ID\tSource File*\tSave File*\tResult\tData1\n"
                "\t\t\t\t\n"
                "\t\t\t\t{p1}\n"
                "\t\t\t\t\n"
                "\t\t\t\t\n"
                "ID1\tsrc1.docx\tout1.docx\t\tV1")
        _paste(wx, grid, text, 0, 0)
        assert grid.GetCellValue(1, grid.COL_DATA_START) == '{p1}'
        assert grid.GetCellValue(grid.DATA_ROW_START, grid.COL_ID) == 'ID1'
        assert grid.GetCellValue(grid.DATA_ROW_START, grid.COL_SOURCE_FILE) == 'src1.docx'
    finally:
        app.Destroy()


def test_paste_plain_data_first_row_not_skipped():
    wx, app = _setup()
    try:
        grid = _new_grid(wx)
        text = "FIRST\tr1a\tr1b\nSECOND\tr2a\tr2b"
        _paste(wx, grid, text, grid.DATA_ROW_START, grid.COL_SOURCE_FILE)
        assert grid.GetCellValue(grid.DATA_ROW_START, grid.COL_SOURCE_FILE) == 'FIRST'
        assert grid.GetCellValue(grid.DATA_ROW_START, grid.COL_SAVE_FILE) == 'r1a'
        assert grid.GetCellValue(grid.DATA_ROW_START + 1, grid.COL_SOURCE_FILE) == 'SECOND'
    finally:
        app.Destroy()
