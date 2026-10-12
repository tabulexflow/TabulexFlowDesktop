# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import sys
import logging

logger = logging.getLogger(__name__)
from pathlib import Path

from tfp_toolkit.tfp_i18n_manager import TFP_I18nManager as I18nManager, translate_list as _base_translate_list

DEFAULT_TRANSLATIONS = {
    "en": {
        "tool_name": "Tabulex File Operator",
        "combo_match_methods": [
            "Contains Full Name", "Contains All Fragments", "Contains Any Fragment",
            "Equals Name", "Starts with Name", "Ends with Name",
            "Images (Preset)", "Documents (Preset)", "Compressed (Preset)", "Text (Preset)",
            "Exclude Full Names", "Exclude Wildcards", "Matches Wildcard", "Matches Regex"
        ],
        "combo_naming_methods": [
            "Original Name", "Replace by Text", "Replace by Position",
            "Insert by Position", "Delete by Position", "Add Prefix", "Add Suffix",
            "All Uppercase", "First Letter Uppercase", "Camel Case", "All Lowercase",
            "Number Without Grouping", "Number by Directory", "Number by Match Name",
            "Convert by Placeholder", "Rename MP3"
        ],
        "combo_file_conflict": ["Skip Duplicates", "Overwrite Duplicates"],
        "combo_dir_conflict": ["Skip Duplicates", "Merge Duplicates", "Replace Duplicates"],
        "combo_create_folder": ["Keep Structure", "Match-Name Subfolder Only", "Match-Name Subfolder + Original Structure", "Remove Parent Folder", "Flatten All Files"],
        "combo_delete_filters": [
            "Delete All", "Name Contains", "Name Not Contains",
            "Size Less Than", "Size Greater Than", "Size Between",
            "Created Before", "Created After", "Created Between",
            "Modified Before", "Modified After", "Modified Between"
        ],
        "combo_size_unit": ["B", "KB", "MB", "GB"],
        "combo_duplicate_algorithms": ["By Name", "Name + Size", "File Fingerprint", "File Hash"],
        "combo_duplicate_rules": [
            "Keep Latest Creation", "Keep Earliest Creation",
            "Keep Latest Modification", "Keep Earliest Modification",
            "Keep Longest Name", "Keep Shortest Name",
            "Keep Longest Path", "Keep Shortest Path"
        ],
        "menu_reset": "Reset",
        "menu_reset_confirm": "Reset all inputs to their initial values and clear the table?\nThe current search results and form settings will be discarded.",
        "menu_reset_done": "All inputs have been reset to their initial values",
        "menu_reset_failed": "Reset failed: {error}",
        "filetype_excel": "Excel files",
        "filetype_text": "Text files",
        "status_table_cleared": "Table cleared",
        "search_dialog_current": "Found {count} results, currently at {index}",
        "status_all_paths_exist": "All paths already exist, no new paths added",
        "status_dropped_paths": "Dropped {count} new path(s)",
        "result_invalid_path": "[Invalid Path]",
        "result_nonexistent_path": "[Nonexistent Path]",
        "result_not_file": "[Not File]",
        "result_no_permission": "[No Permission]",
        "result_will_delete": "[WILL DELETE]",
        "result_will_retain": "[WILL RETAIN]",
        "result_no_duplicate": "[NO DUPLICATE]",
        "result_error": "[Error: {error}]",
        "help_title_match_method": "Match Method",
        "help_title_rename": "Rename",
    },
    "zh": {
        "tool_name": "灵表文件处理",
        "combo_match_methods": [
            "包含任意匹配名整体", "包含匹配名所有片段", "包含匹配名任意片段",
            "等于匹配名", "以匹配名开头", "以匹配名结尾",
            "图片文件(预置)", "办公文档(预置)", "压缩文件(预置)", "文本文件(预置)",
            "排除所有匹配名整体", "排除所有通配符整体", "符合匹配名的通配符", "符合匹配名的正则式"
        ],
        "combo_naming_methods": [
            "原来的名字", "按文本替换", "按位置替换",
            "按位置插入", "按位置删除", "添加前缀", "添加后缀",
            "全部大写", "首字大写", "驼峰形式", "全部小写",
            "不分组加编号", "按父目录编号", "按匹配名编号",
            "按占位符转换", "对MP3重命名"
        ],
        "combo_file_conflict": ["跳过重名文件", "覆盖重名文件"],
        "combo_dir_conflict": ["跳过重名目录", "合并重名目录", "替换重名目录"],
        "combo_create_folder": ["保留结构", "只建匹配名子目录", "匹配名子目录+原结构", "消除父目录", "展平所有文件"],
        "combo_delete_filters": [
            "删除全部文件", "文件名包含", "文件名不含",
            "体积小于", "体积大于", "体积介于",
            "创建时间早于", "创建时间晚于", "创建时间介于",
            "修改时间早于", "修改时间晚于", "修改时间介于"
        ],
        "combo_size_unit": ["B", "KB", "MB", "GB"],
        "combo_duplicate_algorithms": ["按文件名", "文件名+大小", "文件指纹法", "文件哈希法"],
        "combo_duplicate_rules": [
            "保留创建时间最晚的", "保留创建时间最早的",
            "保留修改时间最晚的", "保留修改时间最早的",
            "保留文件名最长的", "保留文件名最短的",
            "保留路径最长的", "保留路径最短的"
        ],
        "menu_reset": "重置",
        "menu_reset_confirm": "确定要重置所有输入为初始值并清空表格吗？\n当前搜索结果和表单设置将被清除。",
        "menu_reset_done": "已将所有输入重置为初始值",
        "menu_reset_failed": "重置失败: {error}",
        "filetype_excel": "Excel 文件",
        "filetype_text": "文本文件",
        "status_table_cleared": "表格已清空",
        "search_dialog_current": "找到 {count} 个结果，当前是第 {index} 个",
        "status_all_paths_exist": "所有路径已存在，无新路径添加",
        "status_dropped_paths": "已拖入 {count} 个新路径",
        "result_invalid_path": "[无效路径]",
        "result_nonexistent_path": "[路径不存在]",
        "result_not_file": "[不是文件]",
        "result_no_permission": "[无权限]",
        "result_will_delete": "[将删除]",
        "result_will_retain": "[将保留]",
        "result_no_duplicate": "[无重复]",
        "result_error": "[错误: {error}]",
        "help_title_match_method": "匹配方法",
        "help_title_rename": "重命名",
    }
}

_TOOL_DIR = Path(__file__).parent.parent


class tfo_I18nManager(I18nManager):

    def __init__(self, default_language='en'):
        super().__init__(default_language=default_language, default_translations=DEFAULT_TRANSLATIONS)

    def _find_locales_dir(self):
        tool_dir_name = _TOOL_DIR.name

        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base = Path(sys._MEIPASS)
            locales = base / 'tools_fe' / 'tools_builtin_program' / tool_dir_name / 'locales'
            if locales.exists():
                return str(locales)
            locales = base / tool_dir_name / 'locales'
            if locales.exists():
                return str(locales)

        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            locales = exe_dir / 'tools_fe' / 'tools_builtin_program' / tool_dir_name / 'locales'
            if locales.exists():
                return str(locales)

        try:
            locales = _TOOL_DIR / 'locales'
            if locales.exists():
                return str(locales)
        except Exception:
            pass

        return None

    def _load_main_app_translations(self):
        possible_paths = []

        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base = Path(sys._MEIPASS)
            possible_paths.append(base / 'locales')

        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            possible_paths.append(exe_dir / 'locales')

        try:
            base = _TOOL_DIR.parent.parent.parent
            possible_paths.append(base / 'locales')
        except Exception:
            pass

        for locales_dir in possible_paths:
            if locales_dir and locales_dir.exists():
                from tfp_toolkit.tfp_i18n_manager import SUPPORTED_LANGUAGES
                for lang in SUPPORTED_LANGUAGES:
                    lang_file = locales_dir / f'{lang}.json'
                    if lang_file.exists():
                        try:
                            import json
                            with open(lang_file, 'r', encoding='utf-8') as f:
                                main_app_translations = json.load(f)
                                if lang not in self.translations:
                                    self.translations[lang] = {}
                                self.translations[lang].update(main_app_translations)
                        except Exception as e:
                            logger.error(f"Failed to load main app locale {lang}.json: {e}")
                break

    def _find_language_config_file(self):
        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            config_file = exe_dir / 'config' / 'language_settings.json'
            if config_file.exists():
                return config_file

        try:
            base = _TOOL_DIR.parent.parent.parent
            config_file = base / 'config' / 'language_settings.json'
            if config_file.exists():
                return config_file
        except Exception:
            pass
        return None


i18n = tfo_I18nManager()
translate = i18n.get


def translate_list(key):
    return _base_translate_list(i18n, key)
