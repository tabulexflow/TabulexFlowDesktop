# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import sys
from pathlib import Path

_tool_dir = os.path.dirname(os.path.abspath(__file__))
if _tool_dir not in sys.path:
    sys.path.insert(0, _tool_dir)

from tfp_toolkit.tfp_i18n_manager import TFP_I18nManager as I18nManager, translate_list as _base_translate_list

DEFAULT_TRANSLATIONS = {
    "en": {
        "tool_name": "Tabulex Doc Creator",
        "tab_excel": "Excel",
        "tab_word": "Word",
        "tab_ppt": "PowerPoint",
        "tab_pdf": "PDF",
        "tab_about": "About",
        "label_operation_mode": "Mode:",
        "combo_operation_modes": ["Create Doc", "Get Doc Info"],
        "label_fill_method": "Fill:",
        "combo_excel_fill_methods": ["Placeholder", "Fill by Title"],
        "combo_word_fill_methods": ["Placeholder"],
        "combo_ppt_fill_methods": ["Placeholder"],
        "combo_pdf_fill_methods": ["Placeholder", "Insert Image", "Insert Text", "Insert Table", "Delete Table"],
        "label_table_cols": "Cols:",
        "label_table_rows": "Rows:",
        "label_tight": "Tight",
        "label_content_type": "Content Type:",
        "combo_content_types": ["Multi-line Text", "Local Table"],
        "label_fill_direction": "Fill Direction:",
        "combo_fill_directions": ["Down", "Right", "Coordinate"],
        "direction_down": "Down",
        "direction_right": "Right",
        "direction_coordinate": "Coordinate",
        "label_value_count": "Value Count:",
        "combo_value_counts": ["Single Value", "Multi Value", "Image"],
        "label_image_width": "Img Width:",
        "label_image_height": "Img Height:",
        "label_content_width": "Content Width(%):",
        "label_content_height": "Content Height(%):",
        "label_row_height": "Height:",
        "label_row_height_placeholder": "Height:",
        "label_row_height_text": "Text Total Width:",
        "label_row_height_table": "Height:",
        "label_row_height_image": "Width:",
        "label_insert_position": "Pos:",
        "combo_insert_positions": ["(All) Any Position", "(All) Bottom-Left", "(All) Bottom-Right", "(All) Top-Left", "(All) Top-Right", "(Inside) Any Position", "(Inside) Bottom-Left", "(Inside) Bottom-Right", "(Inside) Top-Left", "(Inside) Top-Right"],
        "btn_preview": "Preview",
        "btn_cancel": "Cancel",
        "btn_execute": "Execute",
        "btn_browse": "Browse...",
        "grid_col_id": "ID",
        "grid_col_source_file": "Source File",
        "grid_col_save_file": "Save File",
        "grid_col_target_page": "Target Page",
        "grid_col_result": "Result",
        "grid_col_insert_position": "Position",
        "grid_col_data": "Data",
        "grid_row_placeholder_label": "Placeholder",
        "grid_row_title_label": "Title",
        "grid_row_placeholder": "Placeholder",
        "grid_row_title": "Title",
        "grid_row_direction": "Direction",
        "grid_row_value_count": "Value Count",
        "grid_row_sheet": "Target Sheet",
        "grid_row_target_page": "Target Page",
        "grid_row_content_type": "Content Type",
        "menu_import": "Import",
        "menu_export": "Export",
        "menu_copy": "Copy",
        "menu_paste": "Paste",
        "menu_insert_row": "Insert Row",
        "menu_delete_row": "Delete Row",
        "menu_append_rows": "Append 100 Rows",
        "menu_clear_cells": "Clear Cells",
        "preview_title": "Preview Result",
        "preview_btn_close": "Close",
        "preview_btn_prev": "Previous",
        "preview_btn_next": "Next",
        "preview_label_file": "File:",
        "preview_current_cell": "Value: {}",
        "preview_slide_tab": "Slide {n}",
        "preview_page_tab": "Page {n}",
        "preview_load_failed": "Failed to load {tab} preview",
        "status_current_cell": "Value",
        "status_processing": "Processing: {current}/{total}",
        "msg_select_file": "Please select a file",
        "msg_no_data": "No data to process",
        "msg_operation_in_progress": "An operation is already in progress, please wait",
        "msg_output_conflict": "The following output files have conflicts (multiple rows writing to the same file). Continue?",
        "msg_warning": "Warning",
        "msg_processing": "Processing...",
        "msg_operation_cancelled": "Operation cancelled",
        "msg_completed": "Completed",
        "msg_info_failed_rows": "Failed to get document info for {count} row(s)",
        "msg_skipped_label": "skipped",
        "msg_skipped_already_success": "No file was generated: all {total} row(s) were skipped because the Result column already shows \"{success_text}\". To regenerate, select those cells in the Result column and press Delete to clear them first.",
        "msg_skipped_previous_error": "No file was generated: all {total} row(s) were skipped because the Result column is not empty ({errors} failed last time, {ok} already succeeded). Please fix the errors, then clear those cells in the Result column before executing again.",
        "msg_confirm_overwrite": "Confirm Overwrite",
        "result_success": "Success",
        "result_failed": "Failed",
        "result_no_valid_position": "Failed: No suitable position found",
        "result_no_space_text": "Failed: No space to insert text",
        "result_no_space_table": "Failed: No space to insert table",
        "result_no_space_image": "Failed: No space to insert image",
        "result_no_space_table_retry": "Failed: No space to insert table (tried smaller row heights)",
        "result_error_unknown": "Unknown error",
        "result_error_permission": "Permission denied",
        "result_error_not_found": "File not found",
        "result_error_invalid": "Invalid data",
        "result_error_invalid_target": "Invalid target: {value}",
        "result_error_timeout": "Timeout",
        "result_error_memory": "Memory error",
        "result_error_other": "Error",
        "result_error_doc_format": "Failed: .doc format is not supported, please use .docx",
        "result_error_ppt_format": "Failed: .ppt format is not supported, please use .pptx",
        "msg_wrong_tab_use_word": "This is a Word document, please use the Word tab",
        "msg_wrong_tab_use_excel": "This is an Excel file, please use the Excel tab",
        "msg_wrong_tab_use_ppt": "This is a PowerPoint file, please use the PowerPoint tab",
        "msg_error": "Error",
        "msg_file_not_found": "File not found",
        "msg_invalid_path": "Invalid file path",
        "msg_preview_error": "Preview failed",
        "msg_execute_success": "Execution successful",
        "msg_execute_error": "Execution failed",
        "msg_please_fill_data": "Please fill in data",
        "msg_file_exists": "File already exists. Overwrite?",
        "msg_mode_switch_clear_confirm": "Switching to \"Get Doc Info\" will clear all columns except ID / Source File / Save File / Result ({count} non-empty cells, including header rows). This cannot be undone. Continue?",
        "msg_file_too_large": "Failed: file too large (max {size}) to process",
        "msg_pdf_encrypted": "Failed: PDF is encrypted and cannot be edited",
        "msg_source_not_found": "Source file not found",
        "msg_image_not_found": "Image file not found",
         "msg_files_dropped": "Dropped {count} new path(s)",
        "msg_files_rejected": "Rejected {count} file(s) with unsupported extensions: {files}",
        "dialog_title_warning": "Warning",
        "pdf_info_page_count": "Page Count",
        "pdf_info_file_size": "File Size",
        "pdf_info_orientation": "Orientation",
        "pdf_info_page_size": "Page Size",
        "pdf_info_title": "Title",
        "pdf_info_author": "Author",
        "pdf_info_creation_date": "Creation Date",
        "pdf_info_modification_date": "Modification Date",
        "pdf_info_encrypted": "Encrypted",
        "pdf_info_yes": "Yes",
        "pdf_info_no": "No",
        "pdf_info_portrait": "Portrait",
        "pdf_info_landscape": "Landscape",
        "pdf_info_mixed": "Mixed",
        "pdf_info_not_available": "N/A",
        "word_page_count_unavailable": "N/A (docx cannot get exact page count)",
        "info_not_available": "N/A",
        "excel_info_file_size": "File Size",
        "excel_info_sheet_count": "Sheet Count",
        "excel_info_row_count": "Row Count",
        "excel_info_col_count": "Column Count",
        "excel_info_title": "Title",
        "excel_info_author": "Author",
        "excel_info_creation_date": "Creation Date",
        "excel_info_modification_date": "Modification Date",
        "excel_info_last_modified_by": "Last Modified By",
        "word_info_file_size": "File Size",
        "word_info_page_count": "Page Count",
        "word_info_word_count": "Word Count",
        "word_info_char_count": "Character Count",
        "word_info_title": "Title",
        "word_info_author": "Author",
        "word_info_creation_date": "Creation Date",
        "word_info_modification_date": "Modification Date",
        "word_info_last_modified_by": "Last Modified By",
        "ppt_info_file_size": "File Size",
        "ppt_info_slide_count": "Slide Count",
        "ppt_info_slide_size": "Slide Size",
        "ppt_info_title": "Title",
        "ppt_info_author": "Author",
        "ppt_info_creation_date": "Creation Date",
        "ppt_info_modification_date": "Modification Date",
        "ppt_info_last_modified_by": "Last Modified By",
        "label_title": "TabulexFlow - Bulk Document Creator",
        "label_intro": "Version: 1.0.0 | Developer: TabulexFlow Team | License: AGPL v3 (Open-source, free for individuals and enterprises)",
        "label_website": "Website: https://tabulexflow.com",
        "label_feedback": "Questions and Suggestions",
        "label_tools_title": "More Efficiency Tools",
        "label_tool1_name": "Tabulex File Operator",
        "label_tool1_desc": "Batch search, rename, move, copy, compress, delete and deduplicate files",
        "label_tool2_name": "TabulexBomComparator",
        "label_tool2_desc": "Compare and analyze BOM differences across multiple versions (Commercial Edition)",
        "label_tool3_name": "PalletLayout",
        "label_tool3_desc": "Optimize container loading with smart pallet arrangement algorithms (Commercial Edition)",
        "label_tool4_name": "Get More Tools",
        "label_tool4_desc": "Explore more efficiency tools to boost productivity",
        "tooltip_download": "Download",
        "message_open_link_error": "Unable to open link: {url}\nError: {error}",
        "dialog_title_error": "Error",
        "base_grid_copy": "Copy\tCtrl+C",
        "base_grid_paste": "Paste\tCtrl+V",
        "base_grid_undo": "Undo",
        "base_grid_redo": "Redo",
        "base_grid_delete_data": "Delete Data",
        "base_grid_add_rows": "Append 100 Rows",
        "base_grid_delete_selected_rows": "Delete Selected Rows",
        "base_grid_clear_selected_rows": "Delete Row Data",
        "base_grid_clear_selected_cols": "Delete Column Data",
    },
    "zh": {
        "tool_name": "灵表文档创建",
        "tab_excel": "Excel",
        "tab_word": "Word",
        "tab_ppt": "PowerPoint",
        "tab_pdf": "PDF",
        "tab_about": "关于",
        "label_operation_mode": "操作:",
        "combo_operation_modes": ["创建文档", "获取文档信息"],
        "label_fill_method": "填写:",
        "combo_excel_fill_methods": ["占位符替换", "按标题填写"],
        "combo_word_fill_methods": ["占位符替换"],
        "combo_ppt_fill_methods": ["占位符替换"],
        "combo_pdf_fill_methods": ["占位符替换", "插入图片", "插入文本", "插入表格", "删除表格"],
        "label_table_cols": "列数:",
        "label_table_rows": "行数:",
        "label_tight": "紧贴",
        "label_content_type": "内容形式:",
        "combo_content_types": ["多行文本", "局部表格"],
        "label_fill_direction": "填写方向:",
        "combo_fill_directions": ["向下", "向右", "坐标"],
        "direction_down": "向下",
        "direction_right": "向右",
        "direction_coordinate": "坐标",
        "label_value_count": "填写数量:",
        "combo_value_counts": ["单值", "多值", "图片"],
        "label_image_width": "图宽:",
        "label_image_height": "图高:",
        "label_content_width": "内容长度(%):",
        "label_content_height": "内容高度(%):",
        "label_row_height": "行高:",
        "label_row_height_placeholder": "行高:",
        "label_row_height_text": "文本总宽:",
        "label_row_height_table": "行高:",
        "label_row_height_image": "宽度:",
        "label_insert_position": "位置:",
        "combo_insert_positions": ["(全部)任意位置", "(全部)左下", "(全部)右下", "(全部)左上", "(全部)右上", "(图框内)任意位置", "(图框内)左下", "(图框内)右下", "(图框内)左上", "(图框内)右上"],
        "btn_preview": "预览",
        "btn_cancel": "取消",
        "btn_execute": "执行",
        "btn_browse": "浏览...",
        "grid_col_id": "编号ID",
        "grid_col_source_file": "待操作文件",
        "grid_col_save_file": "保存文件",
        "grid_col_target_page": "目标页",
        "grid_col_result": "执行结果",
        "grid_col_insert_position": "插入位置",
        "grid_col_data": "数据",
        "grid_row_placeholder_label": "待查找占位符",
        "grid_row_title_label": "待查找标题",
        "grid_row_placeholder": "占位符",
        "grid_row_title": "待查找标题",
        "grid_row_direction": "填写方向",
        "grid_row_value_count": "填写数量",
        "grid_row_sheet": "目标Sheet页",
        "grid_row_target_page": "目标页",
        "grid_row_content_type": "内容形式",
        "menu_import": "导入",
        "menu_export": "导出",
        "menu_copy": "复制",
        "menu_paste": "粘贴",
        "menu_insert_row": "插入行",
        "menu_delete_row": "删除行",
        "menu_append_rows": "追加100行",
        "menu_clear_cells": "清空单元格",
        "preview_title": "预览结果",
        "preview_btn_close": "关闭",
        "preview_btn_prev": "上一个",
        "preview_btn_next": "下一个",
        "preview_label_file": "文件:",
        "preview_current_cell": "内容：{}",
        "preview_slide_tab": "幻灯片 {n}",
        "preview_page_tab": "页 {n}",
        "preview_load_failed": "加载 {tab} 预览失败",
        "status_current_cell": "内容",
        "status_processing": "处理中: {current}/{total}",
        "msg_select_file": "请选择文件",
        "msg_no_data": "没有数据可处理",
        "msg_operation_in_progress": "操作正在进行中，请稍候",
        "msg_output_conflict": "以下输出文件存在冲突（多行数据写入同一文件），是否继续？",
        "msg_warning": "警告",
        "msg_processing": "处理中...",
        "msg_operation_cancelled": "操作已取消",
        "msg_completed": "处理完成",
        "msg_info_failed_rows": "{count} 行未能获取文档信息",
        "msg_skipped_label": "已跳过",
        "msg_skipped_already_success": "未生成文件：全部 {total} 行因“执行结果”列已标记为“{success_text}”而被跳过。如需重新生成，请先选中这些“执行结果”单元格并按 Delete 清空后再执行。",
        "msg_skipped_previous_error": "未生成文件：全部 {total} 行因“执行结果”列非空而被跳过（其中 {errors} 行上次执行失败，{ok} 行已成功）。请先修正错误，并清空这些“执行结果”单元格后再执行。",
        "msg_confirm_overwrite": "确认覆盖",
        "result_success": "成功",
        "result_failed": "失败",
        "result_no_valid_position": "失败：未找到合适的插入位置",
        "result_no_space_text": "失败：无空间插入文本",
        "result_no_space_table": "失败：无空间插入表格",
        "result_no_space_image": "失败：无空间插入图片",
        "result_no_space_table_retry": "失败：无空间插入表格（已尝试更小行高）",
        "result_error_unknown": "未知错误",
        "result_error_permission": "权限不足",
        "result_error_not_found": "文件不存在",
        "result_error_invalid": "数据无效",
        "result_error_invalid_target": "无效的目标：{value}",
        "result_error_timeout": "超时",
        "result_error_memory": "内存错误",
        "result_error_other": "错误",
        "result_error_doc_format": "失败：不支持 .doc 格式，请使用 .docx",
        "result_error_ppt_format": "失败：不支持 .ppt 格式，请使用 .pptx",
        "msg_wrong_tab_use_word": "这是 Word 文档，请在 Word 标签页操作",
        "msg_wrong_tab_use_excel": "这是 Excel 文件，请在 Excel 标签页操作",
        "msg_wrong_tab_use_ppt": "这是 PowerPoint 文件，请在 PowerPoint 标签页操作",
        "msg_error": "错误",
        "msg_file_not_found": "文件不存在",
        "msg_invalid_path": "无效的文件路径",
        "msg_preview_error": "预览失败",
        "msg_execute_success": "执行成功",
        "msg_execute_error": "执行失败",
        "msg_please_fill_data": "请填写数据",
        "msg_file_exists": "文件已存在，是否覆盖？",
        "msg_mode_switch_clear_confirm": "切换为“获取文档信息”将清空 编号ID/待操作文件/保存文件/执行结果 四列之外的所有列内容（含表头行，共 {count} 个非空单元格），且不可撤销。是否继续？",
        "msg_file_too_large": "失败：文件过大（最大 {size}），无法处理",
        "msg_pdf_encrypted": "失败：PDF 文件已加密，无法编辑",
        "msg_source_not_found": "源文件不存在",
        "msg_image_not_found": "图片文件不存在",
         "msg_files_dropped": "已拖入 {count} 个新路径",
        "msg_files_rejected": "已拒绝 {count} 个不支持的文件类型: {files}",
        "dialog_title_warning": "警告",
        "pdf_info_page_count": "页数",
        "pdf_info_file_size": "文件大小",
        "pdf_info_orientation": "页面方向",
        "pdf_info_page_size": "页面尺寸",
        "pdf_info_title": "标题",
        "pdf_info_author": "作者",
        "pdf_info_creation_date": "创建日期",
        "pdf_info_modification_date": "修改日期",
        "pdf_info_encrypted": "加密状态",
        "pdf_info_yes": "是",
        "pdf_info_no": "否",
        "pdf_info_portrait": "竖版",
        "pdf_info_landscape": "横版",
        "pdf_info_mixed": "混合",
        "pdf_info_not_available": "无",
        "word_page_count_unavailable": "无(python-docx无法精确获取页数)",
        "info_not_available": "无",
        "excel_info_file_size": "文件大小",
        "excel_info_sheet_count": "工作表数",
        "excel_info_row_count": "行数",
        "excel_info_col_count": "列数",
        "excel_info_title": "标题",
        "excel_info_author": "作者",
        "excel_info_creation_date": "创建日期",
        "excel_info_modification_date": "修改日期",
        "excel_info_last_modified_by": "最后修改者",
        "word_info_file_size": "文件大小",
        "word_info_page_count": "页数",
        "word_info_word_count": "字数",
        "word_info_char_count": "字符数",
        "word_info_title": "标题",
        "word_info_author": "作者",
        "word_info_creation_date": "创建日期",
        "word_info_modification_date": "修改日期",
        "word_info_last_modified_by": "最后修改者",
        "ppt_info_file_size": "文件大小",
        "ppt_info_slide_count": "幻灯片数",
        "ppt_info_slide_size": "幻灯片尺寸",
        "ppt_info_title": "标题",
        "ppt_info_author": "作者",
        "ppt_info_creation_date": "创建日期",
        "ppt_info_modification_date": "修改日期",
        "ppt_info_last_modified_by": "最后修改者",
        "label_title": "灵表矩阵 - 灵表文档创建",
        "label_intro": "版本: 1.0.0 | 开发者: TabulexFlow Team | 开源协议: AGPL v3 (开源，个人和企业免费使用)",
        "label_website": "官方网站: https://tabulexflow.com",
        "label_feedback": "问题与建议",
        "label_tools_title": "更多效率工具",
        "label_tool1_name": "灵表文件处理",
        "label_tool1_desc": "批量搜索、重命名、移动、复制、压缩、删除和去重文件",
        "label_tool2_name": "灵表BOM比对",
        "label_tool2_desc": "多版本BOM差异比对与分析（商业版）",
        "label_tool3_name": "装柜计算器",
        "label_tool3_desc": "智能算法优化集装箱装柜排列方案（商业版）",
        "label_tool4_name": "获取更多工具",
        "label_tool4_desc": "探索更多效率工具，提升工作效率",
        "tooltip_download": "下载",
        "message_open_link_error": "无法打开链接: {url}\n错误信息: {error}",
        "dialog_title_error": "错误",
        "base_grid_copy": "复制\tCtrl+C",
        "base_grid_paste": "粘贴\tCtrl+V",
        "base_grid_undo": "撤销",
        "base_grid_redo": "重做",
        "base_grid_delete_data": "删除数据",
        "base_grid_add_rows": "追加100行",
        "base_grid_delete_selected_rows": "删除选中的行",
        "base_grid_clear_selected_rows": "删除行数据",
        "base_grid_clear_selected_cols": "删除列数据",
    }
}


class tdc_I18nManager(I18nManager):

    def __init__(self, default_language='en'):
        super().__init__(default_language=default_language, default_translations=DEFAULT_TRANSLATIONS)

    def _find_locales_dir(self):
        tool_dir_name = Path(__file__).parent.name
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
            base = Path(__file__).parent
            locales = base / 'locales'
            if locales.exists():
                return str(locales)
        except OSError:
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
            base = Path(__file__).parent.parent.parent.parent
            possible_paths.append(base / 'locales')
        except OSError:
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
                            print(f"Error loading main app {lang}.json: {e}")
                break

    def _find_language_config_file(self):
        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            config_file = exe_dir / 'config' / 'language_settings.json'
            if config_file.exists():
                return config_file
        try:
            base = Path(__file__).parent.parent.parent.parent
            config_file = base / 'config' / 'language_settings.json'
            if config_file.exists():
                return config_file
        except OSError:
            pass
        return None


i18n = tdc_I18nManager()
translate = i18n.get


def translate_list(key):
    return _base_translate_list(i18n, key)


def get_all_translations(key):
    """返回某键在所有已知语言下的翻译值（含内置默认表与运行时加载的 locales）。

    用于跨语言状态判定，例如判断“执行结果”列是否为“成功”，
    不能只扫描内置的 en/zh 默认表，否则用户语言为 ru/fr/es/ar 时会漏判。
    """
    result = []
    for lang_translations in DEFAULT_TRANSLATIONS.values():
        value = lang_translations.get(key) if isinstance(lang_translations, dict) else None
        if value and value not in result:
            result.append(value)
    for lang_translations in getattr(i18n, 'translations', {}).values():
        value = lang_translations.get(key) if isinstance(lang_translations, dict) else None
        if value and value not in result:
            result.append(value)
    return result
