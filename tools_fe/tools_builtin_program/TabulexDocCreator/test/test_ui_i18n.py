# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""TabulexDocCreator UI/i18n 回归测试

覆盖：Mode 选项改名（Create Doc / Get Doc Info）、Excel 首行标签 Target Sheet、
Create Doc 必填星号、Get Doc Info 数据列浅灰只读。
依赖缺失或无图形环境时自动跳过 UI 用例。
"""
import os
import sys
import json

import pytest

_TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)


def test_locale_operation_modes_all_languages():
    """六种语言的 Mode 选项应为 Create Doc / Get Doc Info 的本地化文案"""
    locales_dir = os.path.join(_TOOL_DIR, 'locales')
    expected = {
        'en': ['Create Doc', 'Get Doc Info'],
        'zh': ['创建文档', '获取文档信息'],
        'ru': ['Создать Документ', 'Получить Инфо Документа'],
        'fr': ['Créer Document', 'Obtenir Info Document'],
        'es': ['Crear Documento', 'Obtener Info Documento'],
        'ar': ['إنشاء مستند', 'الحصول على معلومات المستند'],
    }
    for lang, values in expected.items():
        with open(os.path.join(locales_dir, f'{lang}.json'), encoding='utf-8') as f:
            data = json.load(f)
        assert data['combo_operation_modes'] == values, lang


def test_locale_grid_row_sheet_not_plain_sheet():
    locales_dir = os.path.join(_TOOL_DIR, 'locales')
    expected = {
        'en': 'Target Sheet', 'zh': '目标Sheet页', 'ru': 'Целевой Лист',
        'fr': 'Feuille Cible', 'es': 'Hoja Destino', 'ar': 'ورقة الهدف',
    }
    for lang, value in expected.items():
        with open(os.path.join(locales_dir, f'{lang}.json'), encoding='utf-8') as f:
            data = json.load(f)
        assert data['grid_row_sheet'] == value, lang


def test_base_translations_updated():
    from tdc_i18n_manager import DEFAULT_TRANSLATIONS
    assert DEFAULT_TRANSLATIONS['en']['combo_operation_modes'] == ['Create Doc', 'Get Doc Info']
    assert DEFAULT_TRANSLATIONS['zh']['combo_operation_modes'] == ['创建文档', '获取文档信息']
    assert DEFAULT_TRANSLATIONS['en']['grid_row_sheet'] == 'Target Sheet'
    assert DEFAULT_TRANSLATIONS['zh']['grid_row_sheet'] == '目标Sheet页'


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
    return app, frame, tool


def test_preview_disabled_in_get_doc_info_mode():
    app, frame, tool = _make_tool()
    try:
        for dt in ('excel', 'word', 'ppt', 'pdf'):
            combo = tool.operation_modes[dt]
            combo.SetSelection(1)  # Get Doc Info
            tool._on_operation_mode_changed(dt, None)
            assert tool.preview_buttons[dt].IsEnabled() is False, dt
            # 执行/预览结束后的全局启用也需保持禁用
            tool._enable_after_execute()
            assert tool.preview_buttons[dt].IsEnabled() is False, dt
            tool._enable_after_preview()
            assert tool.preview_buttons[dt].IsEnabled() is False, dt
            # 切回 Create Doc 后恢复可用
            combo.SetSelection(0)
            tool._on_operation_mode_changed(dt, None)
            assert tool.preview_buttons[dt].IsEnabled() is True, dt
    finally:
        app.Destroy()


def test_on_preview_is_noop_in_get_doc_info_mode(monkeypatch):
    app, frame, tool = _make_tool()
    try:
        calls = []
        import wx
        monkeypatch.setattr(wx, 'MessageBox', lambda *a, **k: calls.append(a))
        dt = 'excel'
        combo = tool.operation_modes[dt]
        combo.SetSelection(1)  # Get Doc Info
        tool._on_operation_mode_changed(dt, None)
        tool._on_preview(dt)
        assert calls == []
    finally:
        app.Destroy()


def test_status_progress_uses_i18n_template():
    app, frame, tool = _make_tool()
    from tdc_i18n_manager import i18n
    restore = i18n.current_language
    try:
        i18n.set_language('zh')
        tool.update_progress('excel', 2, 5, 'f.xlsx')
        left = tool.status_labels_left['excel'].GetLabel()
        right = tool.status_labels_right['excel'].GetLabel()
        assert left.startswith('处理中: 2/5'), left
        assert 'f.xlsx' in left
        assert right == '40%'
    finally:
        i18n.set_language(restore)
        app.Destroy()


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


def test_excel_row0_label_and_create_stars():
    app, frame, grid = _make_excel_grid()
    try:
        assert grid.GetRowLabelValue(0) == 'Target Sheet'
        grid.set_operation_mode('create_from_template')
        assert grid.GetColLabelValue(grid.COL_SOURCE_FILE).endswith('*')
        assert grid.GetColLabelValue(grid.COL_SAVE_FILE).endswith('*')
        assert grid.GetRowLabelValue(grid.HEADER_ROW_PLACEHOLDER).endswith('*')
    finally:
        app.Destroy()


def test_info_mode_source_star_gray_readonly():
    app, frame, grid = _make_excel_grid()
    try:
        grid.set_operation_mode('get_file_info')
        # Get Doc Info 模式：Source File 列同样为必填并显示星号（不再使用 "Source File for Info"）
        assert grid.GetColLabelValue(grid.COL_SOURCE_FILE) == 'Source File*'
        assert not grid.GetRowLabelValue(grid.HEADER_ROW_PLACEHOLDER).endswith('*')
        attr = grid.GetOrCreateCellAttr(grid.DATA_ROW_START, grid.COL_DATA_START)
        assert attr.IsReadOnly() is True
        assert attr.GetBackgroundColour() == grid.read_only_bg_color
        # 待获取信息文件列仍可编辑
        assert grid.GetOrCreateCellAttr(grid.DATA_ROW_START, grid.COL_SOURCE_FILE).IsReadOnly() is False
        # 切回创建模式恢复可编辑
        grid.set_operation_mode('create_from_template')
        assert grid.GetOrCreateCellAttr(grid.DATA_ROW_START, grid.COL_DATA_START).IsReadOnly() is False
    finally:
        app.Destroy()
