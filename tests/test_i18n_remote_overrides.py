# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""T8.3.2 验证：主程序 i18n 远程覆盖层合并语义。

合并语义：后端有&本地有→后端值覆盖；后端有&本地无→补充新增；
后端无&本地有→保留本地；未知 locale/非字典/非字符串值忽略。
"""

import pytest

from tfp_utils.tfp_i18n_manager import TFP_I18nManager

# 键名带任务前缀，避免与真实 locales/*.json 内置键冲突
_K_OVERRIDE = 't83_greet'
_K_LOCAL_ONLY = 't83_only_local'
_K_NEW = 't83_brand_new'


@pytest.fixture
def mgr(monkeypatch):
    monkeypatch.setattr(TFP_I18nManager, '_find_language_config_file', lambda self: None)
    return TFP_I18nManager(
        default_language='en',
        default_translations={
            'en': {_K_OVERRIDE: 'Hello', _K_LOCAL_ONLY: 'Local only'},
            'zh': {_K_OVERRIDE: '你好'},
        })


def test_override_existing_key(mgr):
    """后端有 & 本地有 → 后端值覆盖本地值。"""
    assert mgr.apply_remote_overrides({'zh': {_K_OVERRIDE: '您好'}}) == 1
    mgr.set_language('zh')
    assert mgr.get(_K_OVERRIDE) == '您好'


def test_add_new_key(mgr):
    """后端有 & 本地无 → 补充新增。"""
    assert mgr.apply_remote_overrides({'en': {_K_NEW: 'Brand new'}}) == 1
    assert mgr.get(_K_NEW) == 'Brand new'


def test_local_only_key_preserved(mgr):
    """后端无 & 本地有 → 保留本地值（不删除、不回退）。"""
    mgr.apply_remote_overrides({'en': {_K_OVERRIDE: 'Hi'}})
    assert mgr.get(_K_LOCAL_ONLY) == 'Local only'


def test_unknown_locale_ignored(mgr):
    """不在 SUPPORTED_LANGUAGES 内的 locale 整体忽略。"""
    assert mgr.apply_remote_overrides({'xx': {_K_OVERRIDE: '??'}}) == 0
    assert mgr.get(_K_OVERRIDE) == 'Hello'


def test_non_dict_overrides_ignored(mgr):
    """非字典载荷（None/列表/字符串/数字）整体忽略，不抛异常。"""
    for bad in (None, [], 'x', 3):
        assert mgr.apply_remote_overrides(bad) == 0
    assert mgr.get(_K_OVERRIDE) == 'Hello'


def test_non_string_values_skipped(mgr):
    """值非字符串的键跳过，同 locale 其余字符串键正常合入。"""
    applied = mgr.apply_remote_overrides(
        {'en': {_K_OVERRIDE: 'Hi', 't83_num': 3, 't83_obj': {'a': 1}}})
    assert applied == 1
    assert mgr.get(_K_OVERRIDE) == 'Hi'
    assert mgr.get('t83_num') == 't83_num'  # 未合入，get 回退返回键名


def test_apply_before_language_switch(mgr):
    """合并不受当前语言限制：对非当前 locale 的覆盖在切换语言后生效。"""
    mgr.set_language('en')
    mgr.apply_remote_overrides({'zh': {_K_OVERRIDE: '您好'}})
    assert mgr.get(_K_OVERRIDE) == 'Hello'  # 当前 en 不受 zh 覆盖影响
    mgr.set_language('zh')
    assert mgr.get(_K_OVERRIDE) == '您好'
