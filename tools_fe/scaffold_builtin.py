#!/usr/bin/env python3
# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""BuiltinProgram 工具脚手架生成器

用法：
    python scaffold_builtin.py <tool_ident> <tool_title_zh> <tool_title_en>

示例：
    python scaffold_builtin.py MyTool 我的工具 My Tool

将在 tools_fe/tools_builtin_program/{tool_ident}/ 下生成完整的工具目录结构。
"""

import os
import sys
import json
import shutil
from pathlib import Path

# 项目根目录（脚本所在目录的上级）
_SCRIPT_DIR = Path(__file__).parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
_TOOLS_DIR = _PROJECT_ROOT / "tools_fe" / "tools_builtin_program"
_DEFAULT_ICON = _PROJECT_ROOT / "config" / "default_icon.ico"


def generate_tool_main(tool_ident: str, tool_title_zh: str, tool_title_en: str) -> str:
    """生成 tool_main.py 模板"""
    class_name = f"{tool_ident}Tool"
    i18n_class = f"{tool_ident}_I18nManager"

    template = f'''# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""{tool_title_en} - BuiltinProgram Tool"""

import wx
from pathlib import Path

from tfp_toolkit.tfp_base_tool import TFP_BuiltinProgramTool
from tfp_toolkit.tfp_i18n_manager import TFP_I18nManager as I18nManager, translate_list as _base_translate_list
from tfp_toolkit.tfp_dpi import spx_calc

DEFAULT_TRANSLATIONS = {{
    "en": {{"tool_name": "{tool_title_en}"}},
    "zh": {{"tool_name": "{tool_title_zh}"}}
}}

_TOOL_DIR = Path(__file__).parent


class {i18n_class}(I18nManager):

    def __init__(self, default_language='en'):
        super().__init__(default_language=default_language, default_translations=DEFAULT_TRANSLATIONS)

    def _find_locales_dir(self):
        return str(_TOOL_DIR / 'locales') if (_TOOL_DIR / 'locales').exists() else None

    def _load_main_app_translations(self):
        # 由SDK基类处理
        pass

    def _find_language_config_file(self):
        # 由SDK基类处理
        return None


i18n = {i18n_class}()
translate = i18n.get


class {class_name}(TFP_BuiltinProgramTool):
    """{tool_title_en} 工具类"""

    @property
    def tool_ident(self) -> str:
        return "{tool_ident}"

    @property
    def tool_name(self) -> str:
        return translate("tool_name")

    def create_embedded_interface(self, parent_panel, parent_sizer):
        """创建嵌入式界面（实现TFP_BuiltinProgramTool抽象方法）"""
        self.panel = wx.Panel(parent_panel)
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(self.panel, label=translate("tool_name"))
        sizer.Add(label, 0, wx.ALL, spx_calc(10))
        self.panel.SetSizer(sizer)
        parent_sizer.Add(self.panel, 1, wx.EXPAND)
        return self.panel

    def show_interface(self):
        """显示界面"""
        if self.panel:
            self.panel.Show()


def create_tool(parent, user_setting_base_dir=None):
    """工具工厂函数，由主程序调用"""
    return {class_name}(parent)
'''
    return template


def generate_manifest(tool_ident: str, tool_title_zh: str, tool_title_en: str) -> dict:
    """生成 tool_manifest.json 内容"""
    return {
        "tool_ident": tool_ident,
        "tool_title": {
            "en": tool_title_en,
            "zh": tool_title_zh,
            "fr": tool_title_en,
            "ru": tool_title_en,
            "es": tool_title_en,
            "ar": tool_title_en
        },
        "tool_type": "BuiltinProgram",
        "tool_version": "1.0.0",
        "tool_description": {
            "en": f"{tool_title_en} - A TabulexFlow built-in tool",
            "zh": f"{tool_title_zh} - TabulexFlow 内置工具"
        },
        "tool_is_free": True,
        "tool_is_open_source": True,
        "tool_is_local": True,
        "tool_need_ai": False,
        "tool_folder_path": f"tools_builtin_program/{tool_ident}",
        "tool_need_version": "1.0.0",
        "tool_dependencies": [],
        "tool_window_width": 800,
        "tool_window_height": 500,
        "tool_icon_path": "app_icon.ico",
        "tool_author": "TabulexFlow Team",
        "tool_license": "AGPL-3.0",
        "tool_tags": [],
        "tool_min_frontend_version": "1.0.0"
    }


def generate_locale_en(tool_title_en: str) -> dict:
    """生成英文locale文件"""
    return {
        "tool_name": tool_title_en
    }


def generate_locale_zh(tool_title_zh: str) -> dict:
    """生成中文locale文件"""
    return {
        "tool_name": tool_title_zh
    }


def main():
    if len(sys.argv) < 4:
        print("Usage: python scaffold_builtin.py <tool_ident> <tool_title_zh> <tool_title_en>")
        print("Example: python scaffold_builtin.py MyTool 我的工具 My Tool")
        sys.exit(1)

    tool_ident = sys.argv[1]
    tool_title_zh = sys.argv[2]
    tool_title_en = " ".join(sys.argv[3:])

    # 验证tool_ident格式（仅允许字母、数字、下划线）
    if not tool_ident.replace("_", "").replace("-", "").isalnum():
        print(f"Error: tool_ident '{tool_ident}' contains illegal characters; only letters, digits, underscores and hyphens are allowed")
        sys.exit(1)

    # 检查工具是否已存在
    tool_dir = _TOOLS_DIR / tool_ident
    if tool_dir.exists():
        print(f"Error: tool directory already exists: {tool_dir}")
        sys.exit(1)

    # 创建目录结构
    locales_dir = tool_dir / "locales"
    locales_dir.mkdir(parents=True, exist_ok=True)

    # 生成 tool_main.py
    tool_main_content = generate_tool_main(tool_ident, tool_title_zh, tool_title_en)
    tool_main_path = tool_dir / "tool_main.py"
    with open(tool_main_path, 'w', encoding='utf-8') as f:
        f.write(tool_main_content)
    print(f"Generated: {tool_main_path}")

    # 生成 tool_manifest.json
    manifest = generate_manifest(tool_ident, tool_title_zh, tool_title_en)
    manifest_path = tool_dir / "tool_manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=4)
    print(f"Generated: {manifest_path}")

    # 复制默认图标
    icon_dest = tool_dir / "app_icon.ico"
    if _DEFAULT_ICON.exists():
        shutil.copy2(str(_DEFAULT_ICON), str(icon_dest))
        print(f"Copied: {icon_dest}")
    else:
        print(f"Warning: default icon not found ({_DEFAULT_ICON}), skipping icon copy")

    # 生成 locale 文件
    en_locale = generate_locale_en(tool_title_en)
    en_path = locales_dir / "en.json"
    with open(en_path, 'w', encoding='utf-8') as f:
        json.dump(en_locale, f, ensure_ascii=False, indent=2)
    print(f"Generated: {en_path}")

    zh_locale = generate_locale_zh(tool_title_zh)
    zh_path = locales_dir / "zh.json"
    with open(zh_path, 'w', encoding='utf-8') as f:
        json.dump(zh_locale, f, ensure_ascii=False, indent=2)
    print(f"Generated: {zh_path}")

    # 输出总结
    print()
    print(f"=== BuiltinProgram tool '{tool_ident}' created successfully ===")
    print(f"Directory: {tool_dir}")
    print()
    print("Generated files:")
    print(f"  {tool_main_path.name}    - Tool main program")
    print(f"  {manifest_path.name} - Tool manifest")
    print(f"  app_icon.ico        - Tool icon")
    print(f"  locales/en.json     - English translation")
    print(f"  locales/zh.json     - Chinese translation")
    print()
    print("Next steps:")
    print(f"  1. Edit {tool_main_path.name} to implement the tool functionality")
    print(f"  2. Edit locales/*.json to add more translations")
    print(f"  3. Replace app_icon.ico with a custom icon")
    print(f"  4. Launch the main program; the tool will be auto-discovered and loaded")


if __name__ == "__main__":
    main()
