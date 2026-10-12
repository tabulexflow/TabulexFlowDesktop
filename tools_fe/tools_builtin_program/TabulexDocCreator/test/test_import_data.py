# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Grid 导入：首行/首列不应被无条件跳过（仅工具导出的带标题行文件才跳过）"""
import os
import sys

import pytest

_TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)


class _FakeFileDialog:
    path = ''

    def __init__(self, *args, **kwargs):
        pass

    def ShowModal(self):
        return __import__('wx').ID_OK

    def GetPath(self):
        return _FakeFileDialog.path

    def Destroy(self):
        pass


class _FakeTool:
    TFP_DPI_SCALE_FACTOR = 1.0

    def get_operation_mode_display(self, doc_type):
        return 'Create Doc'

    def get_fill_method_display(self, doc_type):
        return 'Placeholder'


def _setup_wx():
    wx = pytest.importorskip('wx')
    try:
        app = wx.App(False)
    except Exception:
        pytest.skip('no GUI display available')
    import tdc_CustomGrid as M
    M.wx.FileDialog = _FakeFileDialog
    M.wx.MessageBox = lambda *a, **k: 0
    return wx, app


def _new_grid(wx, app):
    from tdc_CustomGrid import tdc_CustomGrid
    frame = wx.Frame(None)
    return tdc_CustomGrid(frame, _FakeTool(), doc_type='word', fill_method='placeholder')


def _fill_rows(grid, start, values):
    for i, row in enumerate(values):
        r = start + i
        grid.SetCellValue(r, grid.COL_ID, row[0])
        grid.SetCellValue(r, grid.COL_SOURCE_FILE, row[1])
        grid.SetCellValue(r, grid.COL_SAVE_FILE, row[2])
        grid.SetCellValue(r, grid.COL_DATA_START, row[3])


def test_export_import_round_trip_keeps_all_rows():
    wx, app = _setup_wx()
    try:
        g1 = _new_grid(wx, app)
        g1.SetCellValue(g1.HEADER_ROW_PLACEHOLDER, g1.COL_DATA_START, '{p1}')
        _fill_rows(g1, g1.DATA_ROW_START, [['ID1', 'src1.docx', 'out1.docx', 'V1'],
                                           ['ID2', 'src2.docx', 'out2.docx', 'V2']])
        import tempfile
        export_path = os.path.join(tempfile.mkdtemp(), 'export.xlsx')
        _FakeFileDialog.path = export_path
        g1._export_data()
        assert os.path.exists(export_path)

        g2 = _new_grid(wx, app)
        _FakeFileDialog.path = export_path
        g2._import_data()
        assert g2.GetCellValue(g2.HEADER_ROW_PLACEHOLDER, g2.COL_DATA_START) == '{p1}'
        assert g2.GetCellValue(g2.DATA_ROW_START, g2.COL_ID) == 'ID1'
        assert g2.GetCellValue(g2.DATA_ROW_START, g2.COL_SOURCE_FILE) == 'src1.docx'
        assert g2.GetCellValue(g2.DATA_ROW_START + 1, g2.COL_ID) == 'ID2'
    finally:
        app.Destroy()


def test_import_without_label_row_keeps_first_row(tmp_path):
    """文件没有标题行时，第一行必须导入到 Grid 第一行，不能被跳过"""
    openpyxl = pytest.importorskip('openpyxl')
    wx, app = _setup_wx()
    try:
        grid = _new_grid(wx, app)
        wb = openpyxl.Workbook()
        ws = wb.active
        # 无标题行/标签列：行与 Grid 行一一对应，列与 Grid 列一一对应
        ws.append(['', '', '', '', ''])          # grid row 0（目标页行）
        ws.append(['', '', '', '', '{p1}'])      # grid row 1（占位符行）
        ws.append(['', '', '', '', ''])          # grid row 2（填写方向）
        ws.append(['', '', '', '', ''])          # grid row 3（填写数量）
        ws.append(['1', 'src1.docx', 'out1.docx', '', 'V1'])  # grid row 4（首行数据）
        path = str(tmp_path / 'no_label.xlsx')
        wb.save(path)
        _FakeFileDialog.path = path
        grid._import_data()
        assert grid.GetCellValue(1, grid.COL_DATA_START) == '{p1}'   # 第二行仍在第二行
        assert grid.GetCellValue(grid.DATA_ROW_START, grid.COL_ID) == '1'
        assert grid.GetCellValue(grid.DATA_ROW_START, grid.COL_SOURCE_FILE) == 'src1.docx'
    finally:
        app.Destroy()


def test_import_plain_first_row_not_dropped(tmp_path):
    """普通数据表（无标题行）的第一行不能被跳过"""
    openpyxl = pytest.importorskip('openpyxl')
    wx, app = _setup_wx()
    try:
        grid = _new_grid(wx, app)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(['FIRST', 'r1a', 'r1b'])
        ws.append(['SECOND', 'r2a', 'r2b'])
        path = str(tmp_path / 'plain.xlsx')
        wb.save(path)
        _FakeFileDialog.path = path
        grid._import_data()
        assert grid.GetCellValue(0, grid.COL_ID) == 'FIRST'
        assert grid.GetCellValue(1, grid.COL_ID) == 'SECOND'
    finally:
        app.Destroy()
