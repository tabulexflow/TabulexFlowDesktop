# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
import os
import re
import sys
import threading
import ctypes
import signal
from tfo_utils.tfo_i18n_manager import translate, i18n
from tfo_utils.tfo_file_utils import MAX_SEARCH_DEPTH
from tfo_utils.tfo_logger import log_error, log_info, log_warning
from tfo_utils.tfo_match_utils import (
    check_name_match_list, check_name_match_part,
    validate_regex_complexity, regex_match_with_timeout,
    wildcard_to_regex, split_match_name_with_quotes,
    PRESET_METHODS, EXCLUDE_METHODS, METHODS_USING_ENDSWITH
)


"""搜索工作线程类"""
class tfo_SearchWorker(threading.Thread):
    def __init__(self, tool_instance, search_path, match_names, match_method,
                 recursive, search_filename, search_dirname,
                 search_hidden, is_match_all=False):
        super().__init__()
        self.tool_instance = tool_instance
        self.search_path = search_path
        self.match_names = match_names
        self.match_method = match_method
        self.recursive = recursive
        self.search_filename = search_filename
        self.search_dirname = search_dirname
        self.search_hidden = search_hidden
        self.is_match_all = is_match_all
        self.finished = 0
        self.total = 0
        self.current_path = ""
        self.matched_count = 0
        self.results = {}
        self.unmatched_match_names = []
        self._stop_flag = threading.Event()
        self._progress_lock = threading.Lock()
    
    def is_match_method(self, method_key):
        return self.match_method == method_key

    def stop(self):
        """停止线程"""
        self._stop_flag.set()

    @staticmethod
    def _on_walk_error(error):
        pass

    """检查是否已停止"""
    def is_stopped(self):
        return self._stop_flag.is_set()

    """获取进度信息"""
    def get_progress_info(self):
        with self._progress_lock:
            return (self.finished, self.total, self.matched_count,
                   self.current_path, self.results, self.unmatched_match_names)

    """线程主函数"""
    def run(self):
        log_info(f"[SearchWorker] 开始搜索, 路径: {self.search_path}, 匹配方法: {self.match_method}, 递归: {self.recursive}")
        try:
            # 初始化进度
            with self._progress_lock:
                self.finished = 0
                self.total = 0
                self.matched_count = 0
                self.current_path = ""
                self.results = {}
                self.unmatched_match_names = []
            # 执行搜索
            self._perform_search()
            log_info(f"[SearchWorker] 搜索完成, 匹配数: {self.matched_count}")
        except Exception as e:
            log_error(f"[SearchWorker] 搜索线程错误: {e}")
            # 在UI线程中显示错误
            wx.CallAfter(self.tool_instance.status_bar.SetStatusText, translate("worker_status_search_error", error=str(e)), 0)

    """执行搜索操作"""
    def _perform_search(self):
        if self.is_match_all:
            for match_name in self.match_names:
                self.results[match_name] = []
            # 添加所有文件和目录
            self._search_all()
        else:
            # 按匹配名搜索
            current_method_key = self.match_method
            if current_method_key in ["exclude_full_names", "exclude_wildcards"]:
                self.results["/".join(self.match_names)] = []
                self._search_by_exclude_names()
            else:
                for match_name in self.match_names:
                    self.results[match_name] = []
                self._search_by_contain_names()

    """搜索所有文件和目录"""
    def _search_all(self):
        match_name = ""  # 空字符串作为匹配名
        if self.recursive:
            for root, dirs, files in os.walk(self.search_path, onerror=self._on_walk_error):
                if self.is_stopped():
                    return
                current_depth = os.path.relpath(root, self.search_path).count(os.sep) + 1
                if current_depth > MAX_SEARCH_DEPTH:
                    dirs.clear()
                    continue
                with self._progress_lock:
                    self.current_path = root
                # 处理目录
                if self.search_dirname:
                    for dir_name in dirs:
                        if self.is_stopped():
                            return
                        loop_dir_path = os.path.join(root, dir_name)
                        # 检查隐藏属性
                        if not self.search_hidden and self._is_hidden_file(loop_dir_path): continue
                        path_depth = os.path.relpath(root, self.search_path).count(os.sep) + 1
                        self.results[match_name].append((loop_dir_path, match_name, True, path_depth))
                        with self._progress_lock:
                            self.matched_count += 1
                # 处理文件
                if self.search_filename:
                    for file_name in files:
                        if self.is_stopped():
                            return
                        loop_file_path = os.path.join(root, file_name)
                        # 检查隐藏属性
                        if not self.search_hidden and self._is_hidden_file(loop_file_path): continue
                        # 计算路径深度
                        path_depth = os.path.relpath(root, self.search_path).count(os.sep) + 1
                        self.results[match_name].append((loop_file_path, match_name, False, path_depth))
                        with self._progress_lock:
                            self.matched_count += 1
        else:
            # 非递归搜索
            try:
                items = os.listdir(self.search_path)
                with self._progress_lock:
                    self.current_path = self.search_path
                    self.total = len(items)
                for i, item in enumerate(items):
                    if self.is_stopped():
                        return
                    loop_item_path = os.path.join(self.search_path, item)
                    is_dir = os.path.isdir(loop_item_path)
                    # 检查隐藏属性
                    if not self.search_hidden and self._is_hidden_file(loop_item_path): continue
                    if is_dir and self.search_dirname:
                        self.results[match_name].append((loop_item_path, match_name, True, 1))
                        with self._progress_lock:
                            self.matched_count += 1
                    elif not is_dir and self.search_filename:
                        self.results[match_name].append((loop_item_path, match_name, False, 1))
                        with self._progress_lock:
                            self.matched_count += 1
                    with self._progress_lock:
                        self.finished = i + 1
            except PermissionError:
                pass

    """按排除名搜索"""
    def _search_by_exclude_names(self):
        if self.is_stopped(): return
        found_any = False
        if self.recursive:
            for root, dirs, files in os.walk(self.search_path, onerror=self._on_walk_error):
                if self.is_stopped(): return
                current_depth = os.path.relpath(root, self.search_path).count(os.sep) + 1
                if current_depth > MAX_SEARCH_DEPTH:
                    dirs.clear()
                    continue
                with self._progress_lock:
                    self.current_path = root
                # 处理目录
                if self.search_dirname:
                    for dir_name in dirs:
                        if self.is_stopped(): return
                        if self._check_match_name_all_list(dir_name, self.match_names, self.match_method) is not None:
                            loop_dir_path = os.path.join(root, dir_name)
                            # 检查隐藏属性
                            if not self.search_hidden and self._is_hidden_file(loop_dir_path): continue
                            path_depth = os.path.relpath(root, self.search_path).count(os.sep) + 1
                            self.results["/".join(self.match_names)].append((loop_dir_path, "/".join(self.match_names), True, path_depth))
                            found_any = True
                            with self._progress_lock:
                                self.matched_count += 1
                # 处理文件
                if self.search_filename:
                    for file_name in files:
                        if self.is_stopped(): return
                        if self._check_match_name_all_list(file_name, self.match_names, self.match_method) is not None:
                            loop_file_path = os.path.join(root, file_name)
                            # 检查隐藏属性
                            if not self.search_hidden and self._is_hidden_file(loop_file_path): continue
                            # 计算路径深度
                            path_depth = os.path.relpath(root, self.search_path).count(os.sep) + 1
                            self.results["/".join(self.match_names)].append((loop_file_path, "/".join(self.match_names), False, path_depth))
                            found_any = True
                            with self._progress_lock:
                                self.matched_count += 1
        else:
            # 非递归搜索
            try:
                items = os.listdir(self.search_path)
                with self._progress_lock:
                    self.current_path = self.search_path
                    self.total = len(items) * 1
                for i, item in enumerate(items):
                    if self.is_stopped(): return
                    loop_item_path = os.path.join(self.search_path, item)
                    is_dir = os.path.isdir(loop_item_path)
                    # 检查隐藏属性
                    if not self.search_hidden and self._is_hidden_file(loop_item_path): continue
                    if is_dir and self.search_dirname and self._check_match_name_all_list(item, self.match_names, self.match_method) is not None:
                        self.results["/".join(self.match_names)].append((loop_item_path, "/".join(self.match_names), True, 1))
                        found_any = True
                        with self._progress_lock:
                            self.matched_count += 1
                    elif not is_dir and self.search_filename and self._check_match_name_all_list(item, self.match_names, self.match_method) is not None:
                        self.results["/".join(self.match_names)].append((loop_item_path, "/".join(self.match_names), False, 1))
                        found_any = True
                        with self._progress_lock:
                            self.matched_count += 1
                    with self._progress_lock:
                        # 排除名搜索只跑一轮（total = len(items)），finished 不得超过 total；
                        # 原公式多加了一轮 len(items) 导致进度超出 100%
                        self.finished = i + 1
            except PermissionError:
                pass
        # 如果没有找到任何结果，添加到未匹配列表
        if not found_any:
            with self._progress_lock:
                self.unmatched_match_names.append("/".join(self.match_names))

    """按匹配名搜索"""
    def _search_by_contain_names(self):
        for match_idx, match_name in enumerate(self.match_names):
            if self.is_stopped(): return
            found_any = False
            if self.recursive:
                for root, dirs, files in os.walk(self.search_path, onerror=self._on_walk_error):
                    if self.is_stopped(): return
                    current_depth = os.path.relpath(root, self.search_path).count(os.sep) + 1
                    if current_depth > MAX_SEARCH_DEPTH:
                        dirs.clear()
                        continue
                    with self._progress_lock:
                        self.current_path = root
                    # 处理目录
                    if self.search_dirname:
                        for dir_name in dirs:
                            if self.is_stopped(): return
                            if self._check_match_name_all_part(dir_name, match_name, self.match_method) is not None:
                                loop_dir_path = os.path.join(root, dir_name)
                                # 检查隐藏属性
                                if not self.search_hidden and self._is_hidden_file(loop_dir_path): continue
                                path_depth = os.path.relpath(root, self.search_path).count(os.sep) + 1
                                self.results[match_name].append((loop_dir_path, match_name, True, path_depth))
                                found_any = True
                                with self._progress_lock:
                                    self.matched_count += 1
                    # 处理文件
                    if self.search_filename:
                        for file_name in files:
                            if self.is_stopped(): return
                            if self._check_match_name_all_part(file_name, match_name, self.match_method) is not None:
                                loop_file_path = os.path.join(root, file_name)
                                # 检查隐藏属性
                                if not self.search_hidden and self._is_hidden_file(loop_file_path): continue
                                # 计算路径深度
                                path_depth = os.path.relpath(root, self.search_path).count(os.sep) + 1
                                self.results[match_name].append((loop_file_path, match_name, False, path_depth))
                                found_any = True
                                with self._progress_lock:
                                    self.matched_count += 1
            else:
                # 非递归搜索
                try:
                    items = os.listdir(self.search_path)
                    with self._progress_lock:
                        self.current_path = self.search_path
                        self.total = len(items) * len(self.match_names)
                    for i, item in enumerate(items):
                        if self.is_stopped(): return
                        loop_item_path = os.path.join(self.search_path, item)
                        is_dir = os.path.isdir(loop_item_path)
                        # 检查隐藏属性
                        if not self.search_hidden and self._is_hidden_file(loop_item_path): continue
                        if is_dir and self.search_dirname and self._check_match_name_all_part(item, match_name, self.match_method) is not None:
                            self.results[match_name].append((loop_item_path, match_name, True, 1))
                            found_any = True
                            with self._progress_lock:
                                self.matched_count += 1
                        elif not is_dir and self.search_filename and self._check_match_name_all_part(item, match_name, self.match_method) is not None:
                            self.results[match_name].append((loop_item_path, match_name, False, 1))
                            found_any = True
                            with self._progress_lock:
                                self.matched_count += 1
                        with self._progress_lock:
                            self.finished = match_idx * len(items) + i + 1
                except PermissionError:
                    pass
            # 如果没有找到任何结果，添加到未匹配列表
            if not found_any:
                with self._progress_lock:
                    self.unmatched_match_names.append(match_name)

    def _check_match_name_all_list(self, file_dir_name, match_names, match_method):
        return check_name_match_list(file_dir_name, match_names, match_method)

    def _check_match_name_all_part(self, file_dir_name, match_name, match_method):
        return check_name_match_part(file_dir_name, match_name, match_method)

    def _split_match_name_with_quotes(self, match_name):
        return split_match_name_with_quotes(match_name)

    def _wildcard_to_regex(self, wildcard):
        return wildcard_to_regex(wildcard)

    """判断文件或目录是否为隐藏的"""
    def _is_hidden_file(self, full_file_path):
        try:
            # 规范化路径
            normalized_path = os.path.abspath(full_file_path)
            # Windows系统
            if os.name == 'nt':
                FILE_ATTRIBUTE_HIDDEN = 0x02
                # 获取Windows根路径（如C:\）
                root = os.path.splitdrive(normalized_path)[0] + "\\"
                # 检查当前路径及其所有父目录（但不包括根路径）
                current_path = normalized_path
                while True:
                    # 如果不是根路径，检查隐藏属性
                    if current_path != root:
                        try:
                            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(current_path))
                            if attrs != -1 and bool(attrs & FILE_ATTRIBUTE_HIDDEN):
                                return True
                        except (AttributeError, OSError, WindowsError):
                            pass  # 继续检查上层目录
                    # 移动到父目录
                    parent_path = os.path.dirname(current_path)
                    # 如果已经到达根路径或父路径等于当前路径，停止检查
                    if parent_path == current_path or parent_path == root:
                        break
                    current_path = parent_path
                return False
            else:
                # Unix/Linux/MacOS系统
                # 分割路径为各个组成部分
                parts = os.path.normpath(normalized_path).split(os.sep)
                # 检查每个目录名是否以点开头（跳过根目录的空字符串和"."、".."）
                for part in parts:
                    # 跳过空字符串（根目录）和"."、".."
                    if part and part not in (".", "..") and part.startswith('.'):
                        return True
                return False
        except Exception:
            # 发生任何异常都返回非隐藏
            return False
