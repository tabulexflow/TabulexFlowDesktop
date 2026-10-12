# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""测试 tfp_utils.tfp_i18n_manager 模块"""
import pytest
import sys
import os

_fe_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _fe_root not in sys.path:
    sys.path.insert(0, _fe_root)

from tfp_utils.tfp_i18n_manager import TFP_I18nManager, SUPPORTED_LANGUAGES, translate


class TestTFI18nManagerInit:
    """测试 I18nManager 初始化"""

    def test_independent_instances(self):
        """测试每个实例独立（非单例模式）"""
        mgr1 = TFP_I18nManager(default_language='en')
        mgr2 = TFP_I18nManager(default_language='zh')
        # 两个实例应该是不同的对象
        assert mgr1 is not mgr2
        # 各自的翻译字典独立
        mgr1.set_language('en')
        mgr2.set_language('zh')
        assert mgr1.current_language == 'en'
        assert mgr2.current_language == 'zh'
        # 修改一个不影响另一个
        mgr1.set_language('fr')
        assert mgr1.current_language == 'fr'
        assert mgr2.current_language == 'zh'

    def test_default_language(self, monkeypatch):
        """测试默认语言（隔离仓库 config/language_settings.json，验证无保存设置时使用 default_language）"""
        monkeypatch.setattr(TFP_I18nManager, '_find_language_config_file', lambda self: None)
        mgr = TFP_I18nManager(default_language='zh')
        assert mgr.current_language == 'zh'

    def test_supported_languages_list(self):
        """测试支持的语言列表"""
        assert 'en' in SUPPORTED_LANGUAGES
        assert 'zh' in SUPPORTED_LANGUAGES
        assert len(SUPPORTED_LANGUAGES) >= 2


class TestTFI18nManagerTranslate:
    """测试翻译功能"""

    @pytest.fixture
    def i18n(self):
        translations = {
            'en': {'greeting': 'Hello', 'farewell': 'Goodbye'},
            'zh': {'greeting': '你好', 'farewell': '再见'},
        }
        mgr = TFP_I18nManager(
            default_language='en',
            default_translations=translations
        )
        mgr.set_language('en')
        yield mgr

    def test_get_known_key(self, i18n):
        """测试获取已知键"""
        assert i18n.get('greeting') == 'Hello'

    def test_get_unknown_key(self, i18n):
        """测试获取未知键返回键本身"""
        assert i18n.get('unknown_key') == 'unknown_key'

    def test_switch_language(self, i18n):
        """测试切换语言"""
        i18n.set_language('zh')
        assert i18n.current_language == 'zh'
        assert i18n.get('greeting') == '你好'

    def test_get_language_code(self, i18n):
        """测试获取当前语言代码"""
        assert i18n.get_language_code() == 'en'

    def test_get_available_languages(self, i18n):
        """测试获取可用语言列表"""
        langs = i18n.get_available_languages()
        assert 'en' in langs
        assert 'zh' in langs


class TestTFI18nManagerLanguageSwitch:
    """测试语言切换"""

    @pytest.fixture
    def i18n(self):
        translations = {
            'en': {'key': 'Value'},
            'zh': {'key': '值'},
            'fr': {'key': 'Valeur'},
        }
        mgr = TFP_I18nManager(
            default_language='en',
            default_translations=translations
        )
        mgr.set_language('en')
        yield mgr

    def test_switch_to_supported_language(self, i18n):
        """测试切换到支持的语言"""
        for lang in ['en', 'zh', 'fr']:
            i18n.set_language(lang)
            assert i18n.current_language == lang

    def test_switch_to_unsupported_language(self, i18n):
        """测试切换到不支持的语言保持当前"""
        current = i18n.current_language
        i18n.set_language('jp')
        assert i18n.current_language == current

    def test_get_with_formatting(self, i18n):
        """测试带格式化的翻译"""
        assert i18n.get('key') == 'Value'
        i18n.set_language('zh')
        assert i18n.get('key') == '值'


class TestTranslateFunction:
    """测试 translate 便捷函数"""

    def test_translate_returns_string(self):
        """测试 translate 返回字符串"""
        result = translate('nav.home')
        assert isinstance(result, str)

    def test_translate_unknown_key(self):
        """测试翻译未知键返回键本身"""
        result = translate('unknown.key.xyz12345')
        assert result == 'unknown.key.xyz12345'
