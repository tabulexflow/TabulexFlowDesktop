# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""诊断日志回归测试

- Create Doc：成功与失败都记录该 Source File 组的全部行数据（失败另含出错信息）。
- Get Doc Info：仅失败时记录该行的数据与出错信息，成功不记录组数据。
"""
import os
import sys

import pytest

_TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)

import tdc_BaseDocWorker as base  # noqa: E402


class StubGrid:
    COL_DATA_START = 4

    def SetCellValue(self, row, col, value):
        pass

    def set_result(self, save_file, text):
        pass


class StubTool:
    def __init__(self):
        self.grids = {'excel': StubGrid()}


def make_item(placeholder, value, value_count='Single Value', direction='Down'):
    return {'placeholder': placeholder, 'direction': direction,
            'value_count': value_count, 'value': value}


def make_row(source, save, items, result=''):
    return {'row_index': 4, 'id': '1', 'source_file': source, 'save_file': save,
            'target_page': '', 'data': items, 'is_inherited': False,
            'multi_value_offset': 1, 'result': result}


def _capture(monkeypatch):
    infos, errors = [], []
    monkeypatch.setattr(base, 'log_info', lambda m: infos.append(m))
    monkeypatch.setattr(base, 'log_error', lambda m: errors.append(m))
    return infos, errors


def _make_xlsx(path):
    openpyxl = pytest.importorskip('openpyxl')
    wb = openpyxl.Workbook()
    wb.active['A1'] = '{{x}}'
    wb.save(path)


def test_create_success_logs_group(monkeypatch, tmp_path):
    openpyxl = pytest.importorskip('openpyxl')
    from tdc_ExcelWorker import tdc_ExcelWorker
    src = str(tmp_path / 'src.xlsx')
    dst = str(tmp_path / 'dst.xlsx')
    _make_xlsx(src)
    infos, errors = _capture(monkeypatch)
    worker = tdc_ExcelWorker(StubTool(), [make_row(src, dst, [make_item('{{x}}', 'VAL')])],
                             'create_from_template', 'placeholder', {})
    worker.execute()
    success_logs = [m for m in infos if 'GROUP SUCCESS' in m]
    assert success_logs, infos
    log = success_logs[0]
    assert src in log and 'VAL' in log and 'placeholder' in log


def test_create_failure_logs_group_and_error(monkeypatch, tmp_path):
    from tdc_ExcelWorker import tdc_ExcelWorker
    missing = str(tmp_path / 'missing.xlsx')
    dst = str(tmp_path / 'dst.xlsx')
    infos, errors = _capture(monkeypatch)
    worker = tdc_ExcelWorker(StubTool(), [make_row(missing, dst, [make_item('{{x}}', 'VAL')])],
                             'create_from_template', 'placeholder', {})
    worker.execute()
    fail_logs = [m for m in errors if 'GROUP FAILED' in m]
    assert fail_logs, errors
    assert missing in fail_logs[0]


def test_get_info_failure_logs_row(monkeypatch, tmp_path):
    from tdc_ExcelWorker import tdc_ExcelWorker
    missing = str(tmp_path / 'missing.xlsx')
    infos, errors = _capture(monkeypatch)
    worker = tdc_ExcelWorker(StubTool(), [make_row(missing, '', [])],
                             'get_file_info', 'placeholder', {})
    worker.execute()
    fail_logs = [m for m in errors if 'GET INFO FAILED' in m]
    assert fail_logs, errors
    assert missing in fail_logs[0]
    assert not [m for m in infos if 'GROUP SUCCESS' in m]


def test_get_info_success_no_group_log(monkeypatch, tmp_path):
    openpyxl = pytest.importorskip('openpyxl')
    from tdc_ExcelWorker import tdc_ExcelWorker
    src = str(tmp_path / 'src.xlsx')
    _make_xlsx(src)
    infos, errors = _capture(monkeypatch)
    worker = tdc_ExcelWorker(StubTool(), [make_row(src, '', [])],
                             'get_file_info', 'placeholder', {})
    worker.execute()
    assert not [m for m in errors if 'GET INFO FAILED' in m]
    assert not [m for m in infos if 'GROUP SUCCESS' in m]


def test_preview_success_logs_group(monkeypatch, tmp_path):
    openpyxl = pytest.importorskip('openpyxl')
    from tdc_ExcelWorker import tdc_ExcelWorker
    src = str(tmp_path / 'src.xlsx')
    dst = str(tmp_path / 'dst.xlsx')
    _make_xlsx(src)
    infos, errors = _capture(monkeypatch)
    worker = tdc_ExcelWorker(StubTool(), [make_row(src, dst, [make_item('{{x}}', 'VAL')])],
                             'create_from_template', 'placeholder', {})
    worker.preview([make_row(src, dst, [make_item('{{x}}', 'VAL')])])
    assert [m for m in infos if 'GROUP SUCCESS' in m]
