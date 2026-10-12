# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
import os
import shutil
import threading
from tfo_utils.tfo_i18n_manager import translate, i18n
from tfo_utils.tfo_recycle_bin import delete_to_recycle
from tfo_utils.tfo_file_utils import backup_file_or_dir
from tfo_utils.tfo_logger import log_error, log_info, log_warning, log_file_operation
from tfo_utils.tfo_worker_mode import WorkerMode

"""删除工作线程"""
class tfo_DeleteWorker(threading.Thread):
    def __init__(self, tool_instance, delete_original, paths_info, execute=True, delete_filter="delete_all", filter_params=None, preview_mode=False, worker_mode=None):
        super().__init__()
        self.tool_instance = tool_instance
        self.delete_original = delete_original
        self.paths_info = paths_info
        if worker_mode is not None:
            self.worker_mode = worker_mode
        else:
            if not execute:
                self.worker_mode = WorkerMode.APPLY
            elif preview_mode:
                self.worker_mode = WorkerMode.PREVIEW
            else:
                self.worker_mode = WorkerMode.EXECUTE
        self.delete_filter = delete_filter
        self.filter_params = filter_params if filter_params else {}
        self._stop_flag = threading.Event()
        self.progress_info = (0, 0, 0, 0)
        self.path_info = {}
        self.to_delete_count = 0
        # __init__ 在 UI 线程执行：在此快照行数据与行数，Worker 线程内不再跨线程读取 Grid
        grid = tool_instance.file_grid
        self.snapshot_rows_total = grid.GetNumberRows()
        self.snapshot_old_paths = [grid.GetCellValue(r, grid.COL_OLD_PATH).strip() for r in range(self.snapshot_rows_total)]
        self.snapshot_new_paths = [grid.GetCellValue(r, grid.COL_NEW_PATH).strip() for r in range(self.snapshot_rows_total)]
        self.snapshot_match_names = [grid.GetCellValue(r, grid.COL_MATCH_NAME).strip() for r in range(self.snapshot_rows_total)]

    @staticmethod
    def _get_creation_time(path):
        """获取创建时间：优先 st_birthtime（macOS 提供真实创建时间），

        无该属性时回退 st_ctime（Windows 上即创建时间；Linux 上是元数据变更
        时间，作为平台限制下的近似值）。
        """
        stat = os.stat(path)
        birth = getattr(stat, 'st_birthtime', None)
        return birth if birth is not None else stat.st_ctime

    def run(self):
        log_info(f"[DeleteWorker] 开始执行, 模式: {self.worker_mode.name}, 删除筛选: {self.delete_filter}")
        try:
            # 定义一个空的删除结果字典
            delete_result_dict = {}
            to_delete_paths = set()
            
            rows_total = len(self.paths_info)
            log_info(f"[DeleteWorker] 待处理项目数: {rows_total}")
            # 先清空整个"执行结果"列，避免残留上一次操作的结果
            for _clear_row in range(self.snapshot_rows_total):
                self.tool_instance.file_grid.queue_cell_value(_clear_row, self.tool_instance.file_grid.COL_RESULT, "")

            finished_count = 0
            ok_files_count = 0
            ok_dirs_count = 0

            # 操作级撤销/重做：获取当前操作条目和备份目录
            op_entry = getattr(self.tool_instance, '_current_op_entry', None)
            op_history_mgr = getattr(self.tool_instance, '_op_history_manager', None)
            backup_dir = None
            if op_entry is not None and op_history_mgr is not None:
                backup_dir = op_history_mgr.ensure_backup_dir(op_entry)
            backup_idx = 0

            for row_idx, delete_path, path_type in self.paths_info:
                if self._stop_flag.is_set(): break

                # 该行旧路径/新路径/匹配名（用于执行结果日志）
                row_old_path = self.snapshot_old_paths[row_idx]
                row_new_path = self.snapshot_new_paths[row_idx]
                match_name = self.snapshot_match_names[row_idx]

                # 清空结果列
                self.tool_instance.file_grid.queue_cell_value(row_idx, 3, "")
                
                # 若该路径去除首尾空格后为空则什么都不做
                if not delete_path:
                    self.tool_instance.file_grid.queue_cell_value(row_idx, 3, "")
                    continue
                
                # 判断是否是合法的路径
                is_valid_path = True
                try:
                    os.path.normpath(delete_path)
                except Exception:
                    is_valid_path = False
                
                if not is_valid_path:
                    result_text = translate("failure_path_type_invalid", path_type=path_type)
                    self.tool_instance.file_grid.queue_cell_value(row_idx, 3, result_text)
                    continue
                
                # 检查该路径是否存在
                path_exists = os.path.exists(delete_path)
                
                # 检查去除首尾空格后的路径是否在删除结果字典里，若在则直接把对应值写入结果列
                if delete_path in delete_result_dict:
                    result_text, was_success, was_dir = delete_result_dict[delete_path]
                    self.tool_instance.file_grid.queue_cell_value(row_idx, 3, result_text)
                    if was_success:
                        if was_dir:
                            ok_dirs_count += 1
                        else:
                            ok_files_count += 1
                    finished_count += 1
                    self.progress_info = (finished_count, rows_total, ok_files_count, ok_dirs_count)
                    continue
                
                # 若不存在则检查该路径是否存在
                if not path_exists:
                    # 路径不存在
                    result_text = translate("success_path_type_not_exist", path_type=path_type)
                    self.tool_instance.file_grid.queue_cell_value(row_idx, 3, result_text)
                    delete_result_dict[delete_path] = (result_text, True, False)
                    if self.worker_mode == WorkerMode.EXECUTE:
                        log_file_operation(translate("tab_delete"), row_old_path, row_new_path, match_name,
                                           skipped=True, row_index=row_idx)
                    finished_count += 1
                    self.progress_info = (finished_count, rows_total, ok_files_count, ok_dirs_count)
                    continue
                
                # 判断是否符合删除过滤设置
                matches_filter = True
                current_filter = self.delete_filter
                
                if current_filter == "delete_all":
                    # 全部删除，无需过滤
                    pass
                elif current_filter == "name_contains":
                    # 检查文件名是否包含指定文本
                    text = self.filter_params.get("text", "")
                    if text:
                        filename = os.path.basename(delete_path)
                        if text not in filename:
                            matches_filter = False
                elif current_filter == "name_not_contains":
                    # 检查文件名是否不包含指定文本
                    text = self.filter_params.get("text", "")
                    if text:
                        filename = os.path.basename(delete_path)
                        if text in filename:
                            matches_filter = False
                elif current_filter == "size_less_than":
                    if os.path.isfile(delete_path):
                        file_size = os.path.getsize(delete_path)
                        size_limit = self.filter_params.get("size_max", 0)
                        if file_size >= size_limit:
                            matches_filter = False
                    else:
                        # 目录不参与大小过滤
                        matches_filter = False
                elif current_filter == "size_greater_than":
                    # 检查文件大小是否大于指定值
                    if os.path.isfile(delete_path):
                        file_size = os.path.getsize(delete_path)
                        size_limit = self.filter_params.get("size_min", 0)
                        if file_size <= size_limit:
                            matches_filter = False
                    else:
                        # 目录不参与大小过滤
                        matches_filter = False
                elif current_filter == "size_between":
                    # 检查文件大小是否介于指定值之间
                    if os.path.isfile(delete_path):
                        file_size = os.path.getsize(delete_path)
                        size_min = self.filter_params.get("size_min", 0)
                        size_max = self.filter_params.get("size_max", float('inf'))
                        if not (size_min <= file_size <= size_max):
                            matches_filter = False
                    else:
                        # 目录不参与大小过滤
                        matches_filter = False
                elif current_filter == "create_time_before":
                    # 检查创建时间是否早于指定时间
                    target_date = self.filter_params.get("date_to")
                    if target_date is None:
                        # 未提供上界日期：显式跳过该边界（视为无上限，不做过滤）
                        pass
                    else:
                        try:
                            create_time = self._get_creation_time(delete_path)
                            if create_time >= target_date.timestamp():
                                matches_filter = False
                        except Exception as e:
                            log_error(f"检查创建时间(before)失败: {e}")
                            matches_filter = False
                elif current_filter == "create_time_after":
                    # 检查创建时间是否晚于指定时间
                    target_date = self.filter_params.get("date_from")
                    if target_date is None:
                        # 未提供下界日期：显式跳过该边界（视为无下限，不做过滤）
                        pass
                    else:
                        try:
                            create_time = self._get_creation_time(delete_path)
                            if create_time <= target_date.timestamp():
                                matches_filter = False
                        except Exception as e:
                            log_error(f"检查创建时间(after)失败: {e}")
                            matches_filter = False
                elif current_filter == "create_time_between":
                    # 检查创建时间是否介于指定时间之间；任一边界为 None 时跳过该边界
                    try:
                        create_time = self._get_creation_time(delete_path)
                        time_from = self.filter_params.get("date_from")
                        time_to = self.filter_params.get("date_to")
                        if time_from is not None and create_time < time_from.timestamp():
                            matches_filter = False
                        if time_to is not None and create_time > time_to.timestamp():
                            matches_filter = False
                    except Exception as e:
                        log_error(f"检查创建时间(between)失败: {e}")
                        matches_filter = False
                elif current_filter == "modify_time_before":
                    # 检查修改时间是否早于指定时间
                    target_date = self.filter_params.get("date_to")
                    if target_date is None:
                        # 未提供上界日期：显式跳过该边界（视为无上限，不做过滤）
                        pass
                    else:
                        try:
                            mod_time = os.path.getmtime(delete_path)
                            if mod_time >= target_date.timestamp():
                                matches_filter = False
                        except Exception as e:
                            log_error(f"检查修改时间(before)失败: {e}")
                            matches_filter = False
                elif current_filter == "modify_time_after":
                    # 检查修改时间是否晚于指定时间
                    target_date = self.filter_params.get("date_from")
                    if target_date is None:
                        # 未提供下界日期：显式跳过该边界（视为无下限，不做过滤）
                        pass
                    else:
                        try:
                            mod_time = os.path.getmtime(delete_path)
                            if mod_time <= target_date.timestamp():
                                matches_filter = False
                        except Exception as e:
                            log_error(f"检查修改时间(after)失败: {e}")
                            matches_filter = False
                elif current_filter == "modify_time_between":
                    # 检查修改时间是否介于指定时间之间；任一边界为 None 时跳过该边界
                    try:
                        mod_time = os.path.getmtime(delete_path)
                        time_from = self.filter_params.get("date_from")
                        time_to = self.filter_params.get("date_to")
                        if time_from is not None and mod_time < time_from.timestamp():
                            matches_filter = False
                        if time_to is not None and mod_time > time_to.timestamp():
                            matches_filter = False
                    except Exception as e:
                        log_error(f"检查修改时间(between)失败: {e}")
                        matches_filter = False
                
                if not matches_filter:
                    finished_count += 1
                    self.progress_info = (finished_count, rows_total, ok_files_count, ok_dirs_count)
                    continue
                
                # 判断是否有删除权限
                has_permission = True
                try:
                    # 检查是否有写权限（删除需要写权限）
                    if os.path.isfile(delete_path):
                        # 对于文件，检查其父目录是否有写权限
                        parent_dir = os.path.dirname(delete_path)
                        if not os.access(parent_dir, os.W_OK):
                            has_permission = False
                    else:
                        # 对于目录，检查其本身是否有写权限
                        if not os.access(delete_path, os.W_OK):
                            has_permission = False
                except Exception as e:
                    log_error(f"检查删除权限失败: {e}")
                    has_permission = False
                
                if not has_permission:
                    result_text = translate("failure_cannot_delete_path_type_permission", path_type=path_type)
                    self.tool_instance.file_grid.queue_cell_value(row_idx, 3, result_text)
                    delete_result_dict[delete_path] = (result_text, False, False)
                    if self.worker_mode == WorkerMode.EXECUTE:
                        log_file_operation(translate("tab_delete"), row_old_path, row_new_path, match_name,
                                           success=False, error="no permission", row_index=row_idx)
                    finished_count += 1
                    self.progress_info = (finished_count, rows_total, ok_files_count, ok_dirs_count)
                    continue
                
                if self.worker_mode == WorkerMode.APPLY:
                    # 标记写入"执行结果"列，绝不覆盖"新路径"列（删除目标为新路径时需保留其原值）
                    self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("result_will_delete"))
                    to_delete_paths.add(delete_path)
                
                if self.worker_mode != WorkerMode.APPLY:
                    if self.worker_mode == WorkerMode.PREVIEW:
                        is_dir = os.path.isdir(delete_path)
                        if is_dir:
                            result_text = translate("preview_will_delete_dir", path_type=path_type)
                        else:
                            result_text = translate("preview_will_delete_file", path_type=path_type)
                        
                        self.tool_instance.file_grid.queue_cell_value(row_idx, 3, result_text)
                        delete_result_dict[delete_path] = (result_text, False, is_dir)
                        finished_count += 1
                        self.progress_info = (finished_count, rows_total, ok_files_count, ok_dirs_count)
                    else:
                        try:
                            is_dir = os.path.isdir(delete_path)

                            # 操作级撤销/重做：删除前备份文件/目录
                            path_backup = None
                            if backup_dir:
                                category = "deleted_dirs" if is_dir else "deleted_files"
                                path_backup, _ = backup_file_or_dir(delete_path, backup_dir, category, backup_idx)
                                backup_idx += 1

                            result = delete_to_recycle(delete_path)
                            if result == 0:
                                if is_dir:
                                    result_text = translate("success_deleted_dir_to_recycle_bin", path_type=path_type)
                                    ok_dirs_count += 1
                                else:
                                    result_text = translate("success_deleted_file_to_recycle_bin", path_type=path_type)
                                    ok_files_count += 1
                                delete_result_dict[delete_path] = (result_text, True, is_dir)
                                log_file_operation(translate("tab_delete"), row_old_path, row_new_path, match_name,
                                                   success=True, row_index=row_idx)
                                # 操作级撤销/重做：记录 delete_to_recycle 操作
                                if op_history_mgr and op_entry:
                                    op_history_mgr.append_file_op(op_entry, {
                                        "op": "delete_to_recycle",
                                        "path": delete_path,
                                        "path_backup": path_backup,
                                        "success": True,
                                        "error": None,
                                    })
                            else:
                                log_error(f"删除{path_type}路径到回收站失败, 错误码: {result}")
                                result_text = translate("failure_cannot_delete_path_type_to_recycle_bin", path_type=path_type, error_code=result)
                                delete_result_dict[delete_path] = (result_text, False, is_dir)
                                log_file_operation(translate("tab_delete"), row_old_path, row_new_path, match_name,
                                                   success=False, error=f"recycle error_code={result}", row_index=row_idx)
                            self.tool_instance.file_grid.queue_cell_value(row_idx, 3, result_text)
                            finished_count += 1
                            self.progress_info = (finished_count, rows_total, ok_files_count, ok_dirs_count)
                            
                        except PermissionError:
                            result_text = translate("failure_cannot_delete_path_type_permission", path_type=path_type)
                            self.tool_instance.file_grid.queue_cell_value(row_idx, 3, result_text)
                            delete_result_dict[delete_path] = (result_text, False, False)
                            log_file_operation(translate("tab_delete"), row_old_path, row_new_path, match_name,
                                               success=False, error="permission error", row_index=row_idx)
                            finished_count += 1
                            self.progress_info = (finished_count, rows_total, ok_files_count, ok_dirs_count)
                        except Exception as e:
                            log_error(f"删除{path_type}路径失败: {e}")
                            result_text = translate("failure_cannot_delete_path_type_unknown_error", path_type=path_type)
                            self.tool_instance.file_grid.queue_cell_value(row_idx, 3, result_text)
                            delete_result_dict[delete_path] = (result_text, False, False)
                            log_file_operation(translate("tab_delete"), row_old_path, row_new_path, match_name,
                                               success=False, error=e, row_index=row_idx)
                            finished_count += 1
                            self.progress_info = (finished_count, rows_total, ok_files_count, ok_dirs_count)
                else:
                    # 仅过滤模式，不执行删除
                    finished_count += 1
                    self.progress_info = (finished_count, rows_total, ok_files_count, ok_dirs_count)
            
            # 计算待删除数量（用于过滤模式）
            self.to_delete_count = len(to_delete_paths)
            
            # 最终更新进度信息
            self.progress_info = (finished_count, rows_total, ok_files_count, ok_dirs_count)
            log_info(f"[DeleteWorker] 执行完成, 文件: {ok_files_count}, 目录: {ok_dirs_count}")
        except Exception as e:
            log_error(f"[DeleteWorker] 删除操作错误: {e}")
    
    def stop(self):
        self._stop_flag.set()

    def is_stopped(self):
        return self._stop_flag.is_set()
    
    def get_progress_info(self):
        return self.progress_info
    
    def get_to_delete_count(self):
        return self.to_delete_count
