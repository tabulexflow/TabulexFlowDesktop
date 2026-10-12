# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import zipfile
import threading
import wx
from collections import defaultdict
from tdc_i18n_manager import translate, get_all_translations
from tdc_logger import log_info, log_error

# B3-2 安全修复：解析前源文件大小上限 200MB（防 zip bomb / 超大文档造成内存耗尽）
MAX_SOURCE_FILE_SIZE = 200 * 1024 * 1024

# OOXML（zip 包）主部件 → 文档类型
_OOXML_MAIN_PARTS = {
    'word': 'word/document.xml',
    'excel': 'xl/workbook.xml',
    'ppt': 'ppt/presentation.xml',
}
# OLE2（复合文档）旧版 Office 各类型共用一个文件头，按扩展名区分
_OLE2_EXT_KIND = {'.doc': 'word', '.xls': 'excel', '.ppt': 'ppt'}


def check_source_file_size(file_path, max_size=MAX_SOURCE_FILE_SIZE):
    """解析前源文件大小预检（B3-2 安全修复）

    限制被解析的源文件（xlsx/pdf/图片等）大小不超过 200MB，
    防止解析库对超大/畸形文档解压时资源耗尽。返回 True=通过；False=超限或不可读。
    """
    try:
        return os.path.getsize(file_path) <= max_size
    except OSError:
        return False


def detect_document_kind(file_path):
    """按文件内容（OOXML 主部件）或扩展名（OLE2）判断文档类型。

    返回 'word' / 'excel' / 'ppt'，无法判断时返回 None。
    用于识别“文件类型与当前 Tab 不符”的情况，给出明确提示而不是解析器的模糊报错。
    """
    try:
        with open(file_path, 'rb') as f:
            header = f.read(8)
    except OSError:
        return None
    if header == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        return _OLE2_EXT_KIND.get(os.path.splitext(file_path)[1].lower())
    if header[:2] == b'PK':
        try:
            with zipfile.ZipFile(file_path) as zf:
                names = set(zf.namelist())
        except Exception:
            return None
        for kind, part in _OOXML_MAIN_PARTS.items():
            if part in names:
                return kind
    return None


# 文件类型与当前 Tab 不符时的提示 i18n 键
WRONG_TAB_MESSAGE_KEYS = {
    'word': 'msg_wrong_tab_use_word',
    'excel': 'msg_wrong_tab_use_excel',
    'ppt': 'msg_wrong_tab_use_ppt',
}


def document_kind_mismatch_message(source_file, expected_kind):
    """若 source_file 的实际类型与 expected_kind 不符，返回提示文本；否则返回 None。"""
    actual = detect_document_kind(source_file)
    if actual and actual != expected_kind:
        return translate(WRONG_TAB_MESSAGE_KEYS[actual])
    return None


class tdc_BaseDocWorker:
    worker_type = ''

    OLE2_SIGNATURE = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'

    @staticmethod
    def is_ole2_file(file_path):
        """判断是否为 OLE2 旧版二进制 Office 文件（.doc/.xls/.ppt）"""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(8)
            return header == tdc_BaseDocWorker.OLE2_SIGNATURE
        except Exception:
            return False

    def __init__(self, tool_instance, data, operation_mode, fill_method, params=None):
        self.tool_instance = tool_instance
        self.data = data
        self.operation_mode = operation_mode
        self.fill_method = fill_method
        self.results = []
        self.cancelled = False
        self.params = params or {}
        # 执行统计：用于向用户解释“因执行结果列已有值而跳过”的情况
        self._total_groups = 0
        self._skipped_success = 0
        self._skipped_error = 0
        # 方案6：进度更新合并（仅保留最新进度、按事件循环节拍刷新），避免逐文件 CallAfter 淹没事件队列
        self._progress_lock = threading.Lock()
        self._progress_latest = None
        self._progress_flush_scheduled = False

    def cancel(self):
        self.cancelled = True

    def _group_data_by_save_file(self):
        grouped = defaultdict(list)
        current_save_file = None
        current_source_file = None
        for row in self.data:
            save_file = row.get('save_file', '')
            source_file = row.get('source_file', '')
            data_items = row.get('data', [])
            has_data1 = False
            if data_items and len(data_items) > 0:
                first_data = data_items[0].get('value', '')
                has_data1 = bool(first_data and first_data.strip())
            if save_file and save_file.strip():
                if not os.path.dirname(save_file) and source_file:
                    source_dir = os.path.dirname(source_file)
                    if source_dir:
                        save_file = os.path.join(source_dir, save_file)
                current_save_file = save_file
                current_source_file = source_file
            elif has_data1 and current_save_file:
                row['save_file'] = current_save_file
                row['source_file'] = current_source_file
                grouped[current_save_file].append(row)
                continue
            if current_save_file:
                row['save_file'] = current_save_file
                row['source_file'] = current_source_file
                grouped[current_save_file].append(row)
        return grouped

    def _describe_rows(self, rows):
        """把一组行数据整理为可日志输出的结构，便于复现和定位问题

        包含：行号/编号/源文件/保存文件/目标页/是否继承，以及每个数据项的
        占位符、填写方向、填写数量、Sheet/目标页与实际值。
        """
        described = []
        for row in rows or []:
            entry = {
                'row_index': row.get('row_index'),
                'id': row.get('id'),
                'source_file': row.get('source_file'),
                'save_file': row.get('save_file'),
                'target_page': row.get('target_page'),
                'is_inherited': row.get('is_inherited'),
                'result': row.get('result'),
                'data': [],
            }
            for item in row.get('data', []):
                item_entry = {
                    'placeholder': item.get('placeholder'),
                    'direction': item.get('direction'),
                    'value_count': item.get('value_count'),
                    'value': item.get('value'),
                }
                if item.get('sheet') is not None:
                    item_entry['sheet'] = item.get('sheet')
                if item.get('target_page') is not None:
                    item_entry['target_page'] = item.get('target_page')
                entry['data'].append(item_entry)
            described.append(entry)
        return described
    
    def log_group_result(self, save_file, rows, success, error=None):
        """按 Source File 组记录处理数据与结果（失败含出错信息，成功也记录）"""
        payload = self._describe_rows(rows)
        if success:
            log_info(f'[{self.worker_type}] GROUP SUCCESS file={save_file} rows={payload}')
        else:
            log_error(f'[{self.worker_type}] GROUP FAILED file={save_file} error={error!r} rows={payload}')
    
    def log_info_row_failure(self, row_data, error):
        """Get Doc Info 模式：记录未成功获取信息的行数据与出错信息（成功不记录）"""
        log_error(f'[{self.worker_type}] GET INFO FAILED error={error!r} row={self._describe_rows([row_data])}')
    
    def _get_group_result_state(self, rows):
        """判断某个 Source File 组是否应因“执行结果”列已有值而跳过。

        返回 (should_skip, has_error)：
        - 执行结果列全部为空 → (False, False)，正常处理；
        - 存在任意非空值（Success 或错误信息）→ (True, 是否包含非 Success 值)。
        """
        success_values = get_all_translations('result_success')
        results = [(row.get('result') or '').strip() for row in rows]
        if not any(results):
            return False, False
        has_error = not any(r in success_values for r in results if r)
        return True, has_error
    
    def _record_skip(self, is_error):
        """累计被跳过的组数（按 Success / 上次出错分类）"""
        if is_error:
            self._skipped_error += 1
        else:
            self._skipped_success += 1
    
    def _build_completion_message(self, success_count, processed_count):
        """生成执行完成提示语；全部被跳过时给出明确原因与处理建议"""
        skipped = self._skipped_success + self._skipped_error
        total = self._total_groups or (processed_count + skipped)
        if processed_count == 0 and skipped > 0:
            if self._skipped_error > 0:
                return translate('msg_skipped_previous_error', total=total,
                                 errors=self._skipped_error, ok=self._skipped_success)
            return translate('msg_skipped_already_success', total=total,
                             success_text=translate('result_success'))
        if skipped > 0:
            return (f'{translate("msg_completed")}: {success_count}/{processed_count}'
                    f' ({translate("msg_skipped_label")}: {skipped})')
        return f'{translate("msg_completed")}: {success_count}/{processed_count}'
    
    def _show_error(self, message):
        def _do_show():
            wx.MessageBox(f'{translate("msg_error")}: {message}', translate('msg_error'), wx.OK | wx.ICON_ERROR)
        wx.CallAfter(_do_show)

    def _update_progress(self, current, total, filename=''):
        """更新进度：仅保留最新一次进度并按事件循环节拍合并刷新（线程安全）。

        逐文件直接 wx.CallAfter 会在文件数很多时淹没事件队列，导致界面/进度刷新被拖慢；
        改为"最新值 + 仅一次待处理刷新"的合并模式。
        """
        with self._progress_lock:
            self._progress_latest = (current, total, filename)
            if self._progress_flush_scheduled:
                return
            self._progress_flush_scheduled = True
        wx.CallAfter(self._flush_progress)

    def _flush_progress(self):
        with self._progress_lock:
            payload = self._progress_latest
            self._progress_flush_scheduled = False
        if payload is None:
            return
        current, total, filename = payload
        if self.tool_instance and hasattr(self.tool_instance, 'update_progress'):
            self.tool_instance.update_progress(self.worker_type, current, total, filename)

    def _clear_progress(self):
        def _do_clear():
            if self.tool_instance and hasattr(self.tool_instance, 'clear_progress'):
                self.tool_instance.clear_progress(self.worker_type)
        wx.CallAfter(_do_clear)
