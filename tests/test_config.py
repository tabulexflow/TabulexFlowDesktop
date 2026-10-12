# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""测试 tfp_utils.tfp_main_menu 模块"""
import pytest
import sys
import os

_fe_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _fe_root not in sys.path:
    sys.path.insert(0, _fe_root)

try:
    from tfp_utils.tfp_main_menu import TFP_MainMenu
    HAS_MENU = True
except ImportError:
    HAS_MENU = False


class TestTFMainMenu:
    """测试主菜单"""

    @pytest.mark.skipif(not HAS_MENU, reason="tfp_main_menu 模块不可用")
    def test_menu_class_exists(self):
        """测试菜单类存在"""
        assert TFP_MainMenu is not None


class TestMenuConfig:
    """测试菜单配置"""

    def test_menu_config_exists(self):
        """测试菜单配置文件存在"""
        config_path = os.path.join(_fe_root, 'config', 'menu_config.json')
        assert os.path.exists(config_path), "menu_config.json 应存在"

    def test_menu_config_is_valid_json(self):
        """测试菜单配置是有效 JSON"""
        import json
        config_path = os.path.join(_fe_root, 'config', 'menu_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert isinstance(data, dict)


class TestToolListConfig:
    """测试工具列表配置"""

    def test_internal_tool_list_exists(self):
        """测试内置工具列表配置存在"""
        config_path = os.path.join(_fe_root, 'config', 'tool_list_builtin.json')
        assert os.path.exists(config_path), "tool_list_builtin.json 应存在"

    def test_internal_tool_list_is_valid_json(self):
        """测试内置工具列表配置是有效 JSON"""
        import json
        config_path = os.path.join(_fe_root, 'config', 'tool_list_builtin.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert isinstance(data, (dict, list))

    def test_builtin_tools_have_required_fields(self):
        """测试内置工具列表包含必需字段"""
        import json
        config_path = os.path.join(_fe_root, 'config', 'tool_list_builtin.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            tools = json.load(f)

        required_fields = ['tool_ident', 'tool_title', 'tool_type', 'tool_version']
        for category, tool_list in tools.items():
            if isinstance(tool_list, list):
                for tool in tool_list:
                    for field in required_fields:
                        assert field in tool, f"工具 {tool.get('tool_ident', 'unknown')} 缺少字段 {field}"


class TestLanguageSettings:
    """测试语言设置"""

    def test_language_settings_exists(self):
        """测试语言设置文件存在"""
        config_path = os.path.join(_fe_root, 'config', 'language_settings.json')
        assert os.path.exists(config_path), "language_settings.json 应存在"

    def test_language_settings_is_valid_json(self):
        """测试语言设置是有效 JSON"""
        import json
        config_path = os.path.join(_fe_root, 'config', 'language_settings.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert isinstance(data, dict)