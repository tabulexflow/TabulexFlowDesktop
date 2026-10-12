# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Excel：畸形 docProps XML（根元素后残留多余内容）的自动修复回归测试"""
import os
import sys
import zipfile

import pytest

_TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)


class StubGrid:
    COL_DATA_START = 4

    def SetCellValue(self, row, col, value):
        pass

    def set_result(self, save_file, text):
        pass


class StubTool:
    def __init__(self):
        self.grids = {'excel': StubGrid()}


def make_item(placeholder, value, value_count='Single Value', direction='Down', sheet=''):
    return {'placeholder': placeholder, 'direction': direction,
            'value_count': value_count, 'value': value, 'sheet': sheet}


def make_row(source, save, items):
    return {'row_index': 4, 'id': '1', 'source_file': source, 'save_file': save,
            'target_page': '', 'data': items, 'is_inherited': False,
            'multi_value_offset': 1, 'result': ''}


def _corrupt_core_xml(path):
    """在 docProps/core.xml 根元素后追加多余内容，制造 openpyxl 解析失败"""
    tmp = path + '.tmp'
    with zipfile.ZipFile(path, 'r') as zin, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == 'docProps/core.xml':
                data = data + b'<stray/>tail'
            zout.writestr(item, data)
    os.replace(tmp, path)


def _make_corrupted_template(tmp_path):
    openpyxl = pytest.importorskip('openpyxl')
    src = str(tmp_path / 'tpl.xlsx')
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Sheet1'
    ws['A1'] = 'Title'
    wb.save(src)
    _corrupt_core_xml(src)
    return src


def test_corrupted_template_fails_direct_load(tmp_path):
    openpyxl = pytest.importorskip('openpyxl')
    src = _make_corrupted_template(tmp_path)
    with pytest.raises(Exception):
        openpyxl.load_workbook(src)


def test_execute_repairs_corrupted_template(tmp_path):
    openpyxl = pytest.importorskip('openpyxl')
    from tdc_ExcelWorker import tdc_ExcelWorker
    src = _make_corrupted_template(tmp_path)
    dst = str(tmp_path / 'out.xlsx')
    worker = tdc_ExcelWorker(StubTool(),
                             [make_row(src, dst, [make_item('Title', 'NEW', direction='Down')])],
                             'create_from_template', 'title_fill', {})
    assert worker.execute()
    assert worker.results[0]['success'] is True
    out = openpyxl.load_workbook(dst)['Sheet1']
    assert out['A2'].value == 'NEW'


def test_preview_repairs_corrupted_template(tmp_path):
    openpyxl = pytest.importorskip('openpyxl')
    from tdc_ExcelWorker import tdc_ExcelWorker
    src = _make_corrupted_template(tmp_path)
    dst = str(tmp_path / 'out.xlsx')
    rows = [make_row(src, dst, [make_item('Title', 'NEW', direction='Down')])]
    worker = tdc_ExcelWorker(StubTool(), rows, 'create_from_template', 'title_fill', {})
    preview = worker.preview(rows)
    assert preview is not None and preview.get('data') is not None


def test_get_info_repairs_corrupted_template(tmp_path):
    openpyxl = pytest.importorskip('openpyxl')
    from tdc_ExcelWorker import tdc_ExcelWorker
    src = _make_corrupted_template(tmp_path)
    rows = [make_row(src, '', [])]
    worker = tdc_ExcelWorker(StubTool(), rows, 'get_file_info', 'placeholder', {})
    assert worker.execute()
