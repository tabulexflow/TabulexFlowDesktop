# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""平台用户状态栏用户名打码 + 单元格状态栏 i18n 键守护测试

覆盖范围：
- mask_display_name（tfp_auth_manager）：1~2 字保留 1 字，3~5 字保留 2 字，>5 字保留 3 字
- TabulexFileOperator locales：status_cell_value / status_cell_empty 六语言齐全且含占位符
- TabulexDocCreator locales：status_current_cell / preview_current_cell 已改为 Value/内容 措辞

注：与 TabulexBomComparator 侧 mask_display_name 的 AST 一致性对比已迁至
后端仓 tests/test_tbc_mask_display_name_consistency.py（闭源侧文件不随公开仓分发）。
"""
import json
from pathlib import Path

import pytest

from tfp_auth.tfp_auth_manager import mask_display_name

FE_ROOT = Path(__file__).resolve().parent.parent
BUILTIN_PROGRAMS = FE_ROOT / "tools_fe" / "tools_builtin_program"
TFO_LOCALES = BUILTIN_PROGRAMS / "TabulexFileOperator" / "locales"
TDC_LOCALES = BUILTIN_PROGRAMS / "TabulexDocCreator" / "locales"
LANGUAGES = ("en", "zh", "fr", "es", "ru", "ar")


# ============================================================
# mask_display_name 打码规则
# ============================================================

@pytest.mark.parametrize("name,expected", [
    ("", ""),
    ("王", "王*"),
    ("张三", "张*"),
    ("张三丰", "张三*"),
    ("张三丰四", "张三**"),
    ("张三丰四五", "张三***"),
    ("Alexander", "Ale******"),
    ("abc", "ab*"),
    ("abcdef", "abc***"),
])
def test_mask_rules(name, expected):
    assert mask_display_name(name) == expected


def test_mask_hides_full_name():
    masked = mask_display_name("AlexanderHamilton")
    assert masked.startswith("Ale")
    assert "*" in masked
    assert "Hamilton" not in masked


# ============================================================
# TabulexFileOperator：status_cell_value / status_cell_empty
# ============================================================

@pytest.mark.parametrize("lang", LANGUAGES)
def test_tfo_cell_status_keys_exist(lang):
    data = json.loads((TFO_LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    assert "status_cell_value" in data, f"BFM {lang}.json 缺少 status_cell_value"
    assert "status_cell_empty" in data, f"BFM {lang}.json 缺少 status_cell_empty"
    assert "{value}" in data["status_cell_value"], f"BFM {lang}.json status_cell_value 缺少 {{value}} 占位符"


def test_tfo_cell_status_format():
    en = json.loads((TFO_LOCALES / "en.json").read_text(encoding="utf-8"))
    zh = json.loads((TFO_LOCALES / "zh.json").read_text(encoding="utf-8"))
    assert en["status_cell_value"].format(value="xxx") == "Value: xxx"
    assert zh["status_cell_value"].format(value="xxx") == "内容：xxx"


# ============================================================
# TabulexDocCreator：status_current_cell / preview_current_cell 措辞
# ============================================================

TDC_EXPECTED = {
    "en": ("Value", "Value: {}"),
    "zh": ("内容", "内容：{}"),
    "fr": ("Valeur", "Valeur: {}"),
    "es": ("Valor", "Valor: {}"),
    "ru": ("Значение", "Значение: {}"),
    "ar": ("القيمة", "القيمة: {}"),
}


@pytest.mark.parametrize("lang", LANGUAGES)
def test_tdc_cell_status_wording(lang):
    data = json.loads((TDC_LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    expected_status, expected_preview = TDC_EXPECTED[lang]
    assert data["status_current_cell"] == expected_status
    assert data["preview_current_cell"] == expected_preview


def test_tdc_default_translations_wording():
    """tdc_i18n_manager 内置 en/zh 回退翻译也必须同步为新措辞"""
    import sys
    tdc_dir = str(BUILTIN_PROGRAMS / "TabulexDocCreator")
    if tdc_dir not in sys.path:
        sys.path.insert(0, tdc_dir)
    import tdc_i18n_manager
    assert tdc_i18n_manager.DEFAULT_TRANSLATIONS["en"]["status_current_cell"] == "Value"
    assert tdc_i18n_manager.DEFAULT_TRANSLATIONS["en"]["preview_current_cell"] == "Value: {}"
    assert tdc_i18n_manager.DEFAULT_TRANSLATIONS["zh"]["status_current_cell"] == "内容"
    assert tdc_i18n_manager.DEFAULT_TRANSLATIONS["zh"]["preview_current_cell"] == "内容：{}"
