# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""执行结果列已有值时跳过并给出明确提示的回归测试"""
import os
import sys

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


def make_row(source, save, items, result=''):
    return {'row_index': 4, 'id': '1', 'source_file': source, 'save_file': save,
            'target_page': '', 'data': items, 'is_inherited': False,
            'multi_value_offset': 1, 'result': result}


def _make_xlsx(path):
    openpyxl = pytest.importorskip('openpyxl')
    wb = openpyxl.Workbook()
    wb.active['A1'] = '{{x}}'
    wb.save(path)


def _worker(rows):
    from tdc_ExcelWorker import tdc_ExcelWorker
    return tdc_ExcelWorker(StubTool(), rows, 'create_from_template', 'placeholder', {})


def test_nonempty_error_result_skips_group(tmp_path):
    missing = str(tmp_path / 'missing.xlsx')
    dst = str(tmp_path / 'out.xlsx')
    rows = [make_row(missing, dst, [make_item('{{x}}', 'V')], result='Failed: Error')]
    worker = _worker(rows)
    worker.execute()
    assert worker.results == []
    assert worker._total_groups == 1
    assert worker._skipped_error == 1
    msg = worker._build_completion_message(0, 0)
    assert 'failed last time' in msg


def test_success_result_skips_group_and_message(tmp_path):
    missing = str(tmp_path / 'missing.xlsx')
    dst = str(tmp_path / 'out.xlsx')
    rows = [make_row(missing, dst, [make_item('{{x}}', 'V')], result='Success')]
    worker = _worker(rows)
    worker.execute()
    assert worker.results == []
    assert worker._skipped_success == 1
    msg = worker._build_completion_message(0, 0)
    assert 'Success' in msg and 'Delete' in msg


def test_empty_result_still_processes(tmp_path):
    src = str(tmp_path / 'src.xlsx')
    dst = str(tmp_path / 'out.xlsx')
    _make_xlsx(src)
    rows = [make_row(src, dst, [make_item('{{x}}', 'V')], result='')]
    worker = _worker(rows)
    worker.execute()
    assert worker.results and worker.results[0]['success'] is True
    assert worker._skipped_success == 0 and worker._skipped_error == 0


def test_all_translations_include_locales():
    from tdc_i18n_manager import get_all_translations
    values = get_all_translations('result_success')
    for expected in ('Success', '成功', 'Успешно', 'Réussi', 'Correcto', 'نجح'):
        assert expected in values, (expected, values)


def test_localized_success_values_detected():
    from tdc_BaseDocWorker import tdc_BaseDocWorker
    worker = tdc_BaseDocWorker(None, [], 'create_from_template', 'placeholder', {})
    for value in ('Success', '成功', 'Успешно', 'Réussi', 'Correcto', 'نجح'):
        skip, has_error = worker._get_group_result_state([{'result': value}])
        assert skip is True and has_error is False, value
    assert worker._get_group_result_state([{'result': 'Failed: Error'}]) == (True, True)
    assert worker._get_group_result_state([{'result': ''}]) == (False, False)


def test_failure_result_localized_across_languages():
    from tdc_i18n_manager import i18n, translate
    expected = {
        'ru': {'result_failed': 'Ошибка', 'result_error_not_found': 'Файл не найден'},
        'fr': {'result_failed': 'Échec', 'result_error_not_found': 'Fichier introuvable'},
        'es': {'result_failed': 'Fallido', 'result_error_not_found': 'Archivo no encontrado'},
        'ar': {'result_failed': 'فشل', 'result_error_not_found': 'الملف غير موجود'},
    }
    restore = i18n.current_language
    try:
        for lang, mapping in expected.items():
            i18n.set_language(lang)
            for key, value in mapping.items():
                assert translate(key) == value, (lang, key)
        for key in ('result_failed', 'result_error_unknown', 'result_error_permission',
                    'result_error_not_found', 'result_error_invalid', 'result_error_timeout',
                    'result_error_memory', 'result_error_other', 'result_error_doc_format',
                    'result_no_space_text', 'result_no_space_table', 'result_no_space_image',
                    'result_no_space_table_retry', 'result_no_valid_position'):
            for lang in ('en', 'zh', 'ru', 'fr', 'es', 'ar'):
                i18n.set_language(lang)
                value = translate(key)
                assert value and value != key, (lang, key)
    finally:
        i18n.set_language(restore)


def test_result_written_localized(tmp_path):
    src = str(tmp_path / 'src.xlsx')
    dst = str(tmp_path / 'out.xlsx')
    _make_xlsx(src)
    from tdc_i18n_manager import i18n
    captured = {}

    class Grid(StubGrid):
        def set_result(self, save_file, text):
            captured['text'] = text

    class Tool:
        def __init__(self):
            self.grids = {'excel': Grid()}

    from tdc_ExcelWorker import tdc_ExcelWorker
    restore = i18n.current_language
    try:
        i18n.set_language('ru')
        worker = tdc_ExcelWorker(Tool(), [make_row(src, dst, [make_item('{{x}}', 'V')])],
                                 'create_from_template', 'placeholder', {})
        worker.execute()
        assert captured.get('text') == 'Успешно'
    finally:
        i18n.set_language(restore)


def test_invalid_target_message_localized(tmp_path):
    openpyxl = pytest.importorskip('openpyxl')
    from tdc_ExcelWorker import tdc_ExcelWorker
    from tdc_i18n_manager import i18n
    src = str(tmp_path / 'src.xlsx')
    dst = str(tmp_path / 'out.xlsx')
    _make_xlsx(src)
    rows = [make_row(src, dst, [make_item('{{x}}', 'V', sheet='Nope')])]
    restore = i18n.current_language
    try:
        i18n.set_language('en')
        worker = _worker(rows)
        worker.execute()
        assert worker.results[0]['warning'] == 'Invalid target: Nope'
        i18n.set_language('zh')
        worker2 = _worker(rows)
        worker2.execute()
        assert worker2.results[0]['warning'] == '无效的目标：Nope'
    finally:
        i18n.set_language(restore)


def test_popup_message_reflects_skip(tmp_path, monkeypatch):
    missing = str(tmp_path / 'missing.xlsx')
    dst = str(tmp_path / 'out.xlsx')
    calls = []
    import wx
    monkeypatch.setattr(wx, 'MessageBox', lambda *a, **k: calls.append(a))
    rows = [make_row(missing, dst, [make_item('{{x}}', 'V')], result='Failed: Error')]
    worker = _worker(rows)
    worker.execute()
    assert calls
    assert 'failed last time' in calls[0][0]
