# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
import os
import shutil
import threading
import re
from tfo_utils.tfo_i18n_manager import translate, i18n
from tfo_utils.tfo_file_utils import validate_file_operation, backup_file_or_dir, finalize_apply_new_path_only
from tfo_utils.tfo_logger import log_error, log_info, log_warning, log_file_operation
from tfo_utils.tfo_worker_mode import WorkerMode
from tfo_CustomGrid import tfo_CustomGrid

class tfo_CopyWorker(threading.Thread):
    def __init__(self, tool_instance, preview_mode=True, worker_mode=None):
        super().__init__()
        self.tool_instance = tool_instance
        if worker_mode is not None:
            self.worker_mode = worker_mode
        else:
            self.worker_mode = WorkerMode.PREVIEW if preview_mode else WorkerMode.EXECUTE
        self._stop_flag = threading.Event()
        self.progress_info = (0, 0, 0, 0)
        # __init__/start 均在 UI 线程执行：快照行数据，Worker 线程内不再跨线程读取 Grid
        self._snapshot_from_grid()

    def _snapshot_from_grid(self):
        """在 UI 线程快照 Grid 行数据（线程安全）。

        Worker 线程内不再跨线程读取 Grid，避免线程运行期间用户编辑表格导致读取到不一致数据。
        """
        grid = self.tool_instance.file_grid
        self.snapshot_rows_total = grid.GetNumberRows()
        self.snapshot_old_paths = [grid.GetCellValue(r, tfo_CustomGrid.COL_OLD_PATH).strip() for r in range(self.snapshot_rows_total)]
        self.snapshot_new_paths = [grid.GetCellValue(r, tfo_CustomGrid.COL_NEW_PATH).strip() for r in range(self.snapshot_rows_total)]
        self.snapshot_match_names = [grid.GetCellValue(r, tfo_CustomGrid.COL_MATCH_NAME).strip() for r in range(self.snapshot_rows_total)]

    def start(self):
        """启动前在 UI 线程重新快照 Grid，确保 Worker 使用启动时的最新行数据。

        Preview/Execute 不再修改 New Path（不会自动执行 Apply），但仍可能紧随用户编辑/导入之后
        启动；在 UI 线程重新快照可避免 Worker 线程跨线程读取 Grid 及读到构造时的过期数据。
        """
        self._snapshot_from_grid()
        super().start()

    def run(self):
        log_info(f"[CopyWorker] 开始执行, 模式: {self.worker_mode.name}")
        try:
            rows_total = self.snapshot_rows_total
            # 先清空整个"执行结果"列，避免残留上一次操作的结果
            for _clear_row in range(rows_total):
                self.tool_instance.file_grid.queue_cell_value(_clear_row, tfo_CustomGrid.COL_RESULT, "")
            count_total = 0
            for row_idx in range(rows_total):
                old_path = self.snapshot_old_paths[row_idx]
                new_path = self.snapshot_new_paths[row_idx]
                if old_path or new_path:
                    count_total += 1
            if count_total == 0:
                log_info("[CopyWorker] 没有需要处理的文件")
                return
            
            log_info(f"[CopyWorker] 待处理文件数: {count_total}")
            
            count_finished = 0
            count_ok = 0
            modified_paths_set = set()
            modified_paths_info = {}
            # 记录每一行在第一遍检查中的判定结果（will_be=正常执行，merge=合并目录）
            # 供第二遍（EXECUTE）直接使用，避免依赖通过 wx.CallAfter 异步写入的
            # Result 列文本造成竞态（直接点"执行"时可能读取到尚未写入的预览结果）。
            self.row_outcome = {}
            
            file_conflict_selection = self.tool_instance.combo_file_conflict0402.GetSelection()
            dir_conflict_selection = self.tool_instance.combo_dir_conflict0402.GetSelection()
            # 文件冲突方式（下拉框：0=跳过, 1=覆盖），供目录合并时按用户选择处理同名文件
            file_conflict_method = "overwrite" if file_conflict_selection == 1 else "skip"
            
            log_info(f"[CopyWorker] 文件冲突策略: {file_conflict_selection}, 目录冲突策略: {dir_conflict_selection}")
            
            for row in range(rows_total):
                modified_path = self.snapshot_new_paths[row]

                if modified_path:
                    if modified_path not in modified_paths_info:
                        modified_paths_info[modified_path] = {'count': 0, 'rows': []}
                    modified_paths_info[modified_path]['count'] += 1
                    modified_paths_info[modified_path]['rows'].append(row)
            
            # 第二遍：处理每一行
            for row_idx in range(rows_total):
                if self._stop_flag.is_set(): break
                old_path = self.snapshot_old_paths[row_idx]
                new_path = self.snapshot_new_paths[row_idx]
                if not old_path and not new_path:
                    continue
                if not old_path and new_path:
                    self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("warning_old_path_not_set"))
                    count_finished += 1
                    self.progress_info = (count_finished, count_total, count_ok, 0)
                    continue
                elif old_path and not new_path:
                    self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("warning_new_path_not_set"))
                    count_finished += 1
                    self.progress_info = (count_finished, count_total, count_ok, 0)
                    continue
                _validation_error_map = {
                    'source_invalid': 'error_old_path_invalid',
                    'source_not_exist': 'error_old_path_not_exist',
                    'target_invalid': 'error_new_path_invalid',
                    'target_path_too_long': 'warning_path_too_long',
                    'source_no_permission': 'error_old_path_no_permission',
                    'source_locked': 'warning_file_locked',
                    'target_no_permission': 'error_new_path_no_permission',
                    'same_path': 'warning_same_filename',
                }
                validation_errors = validate_file_operation(old_path, new_path, self.tool_instance.is_valid_path)
                if validation_errors:
                    error_code, error_param = validation_errors[0]
                    error_key = _validation_error_map.get(error_code, error_code)
                    if error_param:
                        self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate(error_key, size=error_param, length=error_param))
                    else:
                        self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate(error_key))
                    count_finished += 1
                    if error_code == 'same_path':
                        count_ok += 1
                    self.progress_info = (count_finished, count_total, count_ok, 0)
                    continue
                
                # 注意：复制操作允许Old Path重复（同一个文件可以复制到多个不同目标路径）
                # 所以不需要检查Old Path是否重复
                
                # 判断新路径是否重复
                path_info = modified_paths_info.get(new_path, {'count': 0, 'rows': []})
                is_duplicate = (path_info['count'] > 1)
                
                if is_duplicate:
                    current_row_index = path_info['rows'].index(row_idx) if row_idx in path_info['rows'] else -1
                    is_last_occurrence = (current_row_index == path_info['count'] - 1)
                    # 目标在磁盘上是否已存在（且非本行源路径）
                    dst_on_disk = (os.path.exists(new_path)
                                   and os.path.normcase(new_path) != os.path.normcase(old_path))
                    if os.path.isdir(old_path):
                        if dir_conflict_selection == 0:
                            # 跳过：仅第一个源执行；目标已在磁盘上时全部跳过
                            if current_row_index == 0 and not dst_on_disk:
                                self._set_will_be_result(row_idx)
                                count_ok += 1
                            else:
                                self.row_outcome[row_idx] = 'skip'
                                self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("warning_will_be_skipped"))
                        elif dir_conflict_selection == 1:
                            # 合并：所有重复行统一走 merge_directories，
                            # 避免最后一行按普通复制把源目录嵌套进已存在的目标目录
                            self.row_outcome[row_idx] = 'merge'
                            self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("warning_will_be_merged"))
                            count_ok += 1
                        elif dir_conflict_selection == 2:
                            # 替换：所有重复行都执行替换（按行序逐个替换目标），
                            # 避免靠前的源目录被跳过而不复制
                            self.row_outcome[row_idx] = 'replace'
                            count_ok += 1
                            if is_last_occurrence:
                                self._set_will_be_text(row_idx)
                            else:
                                self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("warning_will_be_replaced"))
                    else:
                        if file_conflict_selection == 0:
                            # 跳过：仅第一个源执行；目标已在磁盘上时全部跳过
                            if current_row_index == 0 and not dst_on_disk:
                                self._set_will_be_result(row_idx)
                                count_ok += 1
                            else:
                                self.row_outcome[row_idx] = 'skip'
                                self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("warning_will_be_skipped"))
                        elif file_conflict_selection == 1:
                            # 覆盖：所有重复行都执行（按行序依次覆盖）
                            self.row_outcome[row_idx] = 'will_be'
                            count_ok += 1
                            if is_last_occurrence:
                                self._set_will_be_text(row_idx)
                            else:
                                self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("warning_will_be_overwritten"))
                    count_finished += 1
                    self.progress_info = (count_finished, count_total, count_ok, 0)
                    continue
                else:
                    modified_paths_set.add(new_path)
                
                # 所有检查通过；若目标已存在于磁盘，按冲突策略决定本行处理方式
                if self._apply_disk_conflict(row_idx, old_path, new_path,
                                             file_conflict_selection, dir_conflict_selection):
                    count_ok += 1
                count_finished += 1
                self.progress_info = (count_finished, count_total, count_ok, 0)
            
            # 如果是执行模式，进行实际操作
            if self.worker_mode == WorkerMode.EXECUTE:
                # 操作级撤销/重做：获取当前操作条目和备份目录
                op_entry = getattr(self.tool_instance, '_current_op_entry', None)
                op_history_mgr = getattr(self.tool_instance, '_op_history_manager', None)
                backup_dir = None
                if op_entry is not None and op_history_mgr is not None:
                    backup_dir = op_history_mgr.ensure_backup_dir(op_entry)
                backup_idx = 0

                count_operated = 0
                for row_idx in range(rows_total):
                    if self._stop_flag.is_set(): break
                    old_path = self.snapshot_old_paths[row_idx]
                    new_path = self.snapshot_new_paths[row_idx]

                    if not old_path or not new_path:
                        continue

                    match_name = self.snapshot_match_names[row_idx]
                    outcome = self.row_outcome.get(row_idx)
                    if outcome == 'skip':
                        # 执行模式：跳过行的最终结果不能停留在预览态的"将被跳过"，覆盖为最终态"已跳过"
                        self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("warning_skipped"))
                        log_file_operation(translate("operation_copy"), old_path, new_path, match_name,
                                           skipped=True, row_index=row_idx)
                    elif outcome in ('will_be', 'merge', 'replace'):
                        target_dir = os.path.dirname(new_path)
                        if target_dir and not os.path.exists(target_dir):
                            try:
                                os.makedirs(target_dir, exist_ok=True)
                            except Exception as e:
                                log_file_operation(translate("operation_copy"), old_path, new_path, match_name,
                                                   success=False, error=e, row_index=row_idx)
                                self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("failure_cannot_create_directory"))
                                continue

                        try:
                            is_dir = os.path.isdir(old_path)
                            newpath_exists = os.path.exists(new_path)
                            dst_backup = None

                            # 操作级撤销/重做：备份目标（若已存在且与源不同）
                            if newpath_exists and backup_dir and os.path.normcase(new_path) != os.path.normcase(old_path):
                                category = "dir_conflicts" if is_dir else "file_conflicts"
                                dst_backup, _ = backup_file_or_dir(new_path, backup_dir, category, backup_idx)
                                backup_idx += 1

                            if outcome == 'replace':
                                # 替换冲突：备份后删除已存在的目标，再按普通复制处理
                                try:
                                    if os.path.isdir(new_path):
                                        shutil.rmtree(new_path)
                                    elif os.path.exists(new_path):
                                        os.remove(new_path)
                                except Exception as e:
                                    log_file_operation(translate("operation_copy"), old_path, new_path, match_name,
                                                       success=False, error=e, row_index=row_idx)
                                    self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("failure_operation_with_error", operation=translate("operation_copy"), error=str(e)))
                                    continue
                                outcome = 'will_be'

                            if outcome == 'merge':
                                if is_dir:
                                    # 复制合并目录：源目录不删除，仅需备份目标目录
                                    self.tool_instance.merge_directories(old_path, new_path, is_move=False, file_conflict=file_conflict_method)
                                    self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("success_operation_merged", operation=translate("operation_copy")))
                                    # 记录 merge_dirs 操作（src_dir_backup=None，因为源不被删除）
                                    if op_history_mgr and op_entry:
                                        op_history_mgr.append_file_op(op_entry, {
                                            "op": "merge_dirs",
                                            "src_dir": old_path,
                                            "dst_dir": new_path,
                                            "src_dir_backup": None,
                                            "dst_dir_backup": dst_backup,
                                            "is_move": False,
                                            "file_conflict": file_conflict_method,
                                            "success": True,
                                            "error": None,
                                        })
                                else:
                                    shutil.copy2(old_path, new_path)
                                    self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("success_operation_merged", operation=translate("operation_copy")))
                                    # 记录 copy 操作
                                    if op_history_mgr and op_entry:
                                        dst_mtime_after = None
                                        try:
                                            dst_mtime_after = os.path.getmtime(new_path)
                                        except OSError:
                                            pass
                                        op_history_mgr.append_file_op(op_entry, {
                                            "op": "copy",
                                            "src": old_path,
                                            "dst": new_path,
                                            "dst_backup": dst_backup,
                                            "dst_mtime_after": dst_mtime_after,
                                            "success": True,
                                            "error": None,
                                        })
                                count_operated += 1
                            else:
                                if is_dir:
                                    shutil.copytree(old_path, new_path, symlinks=True)
                                else:
                                    shutil.copy2(old_path, new_path)
                                self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("success_operation", operation=translate("operation_copy")))
                                count_operated += 1
                                # 记录 copy 操作
                                if op_history_mgr and op_entry:
                                    dst_mtime_after = None
                                    try:
                                        dst_mtime_after = os.path.getmtime(new_path)
                                    except OSError:
                                        pass
                                    op_history_mgr.append_file_op(op_entry, {
                                        "op": "copy",
                                        "src": old_path,
                                        "dst": new_path,
                                        "dst_backup": dst_backup,
                                        "dst_mtime_after": dst_mtime_after,
                                        "success": True,
                                        "error": None,
                                    })
                            # 操作成功：记录旧路径/新路径/匹配名，便于复现与定位
                            log_file_operation(translate("operation_copy"), old_path, new_path, match_name,
                                               success=True, row_index=row_idx)
                        except FileNotFoundError:
                            log_file_operation(translate("operation_copy"), old_path, new_path, match_name,
                                               success=False, error="file not found", row_index=row_idx)
                            self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("failure_file_not_exist"))
                        except PermissionError:
                            if not os.access(old_path, os.R_OK):
                                log_file_operation(translate("operation_copy"), old_path, new_path, match_name,
                                                   success=False, error="no read permission", row_index=row_idx)
                                self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("failure_no_read_permission"))
                            elif not os.access(os.path.dirname(new_path) if os.path.dirname(new_path) else '.', os.W_OK):
                                log_file_operation(translate("operation_copy"), old_path, new_path, match_name,
                                                   success=False, error="no write permission", row_index=row_idx)
                                self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("failure_no_write_permission"))
                            else:
                                log_file_operation(translate("operation_copy"), old_path, new_path, match_name,
                                                   success=False, error="permission error", row_index=row_idx)
                                self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("failure_operation", operation=translate("operation_copy")))
                        except Exception as e:
                            log_file_operation(translate("operation_copy"), old_path, new_path, match_name,
                                               success=False, error=e, row_index=row_idx)
                            self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("failure_operation_with_error", operation=translate("operation_copy"), error=str(e)))
                
                self.progress_info = (count_finished, count_total, count_ok, count_operated)
            log_info(f"[CopyWorker] 执行完成, 成功: {count_ok}/{count_total}")
        except Exception as e:
            log_error(f"[CopyWorker] 复制操作错误: {e}")

    def _set_will_be_result(self, row_idx):
        self.row_outcome[row_idx] = 'will_be'
        self._set_will_be_text(row_idx)

    def _set_will_be_text(self, row_idx):
        """仅写入普通"将执行"文案，不改变 row_outcome（供已显式设定 outcome 的行复用）"""
        self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("correct_will_be_copied"))

    def _apply_disk_conflict(self, row_idx, old_path, new_path, file_conflict_selection, dir_conflict_selection):
        """目标已存在于磁盘时，按冲突策略决定本行结果（预览与执行共用）

        返回 True 表示本行继续执行（will_be/merge/replace），False 表示跳过。
        目标不存在或与源路径相同时按普通执行处理。文件/目录冲突策略索引：
            文件：0=跳过, 1=覆盖；目录：0=跳过, 1=合并, 2=替换
        """
        if (not new_path or not os.path.exists(new_path)
                or os.path.normcase(new_path) == os.path.normcase(old_path)):
            self._set_will_be_result(row_idx)
            return True

        src_is_dir = os.path.isdir(old_path)
        dst_is_dir = os.path.isdir(new_path)
        if src_is_dir and dst_is_dir:
            if dir_conflict_selection == 1:
                self.row_outcome[row_idx] = 'merge'
                self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("warning_will_be_merged"))
                return True
            elif dir_conflict_selection == 2:
                self.row_outcome[row_idx] = 'replace'
                self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("warning_will_be_replaced"))
                return True
            else:
                self.row_outcome[row_idx] = 'skip'
                self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("warning_will_be_skipped"))
                return False
        else:
            if file_conflict_selection == 0:
                self.row_outcome[row_idx] = 'skip'
                self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("warning_will_be_skipped"))
                return False
            else:
                self.row_outcome[row_idx] = 'will_be'
                self.tool_instance.file_grid.queue_cell_value(row_idx, tfo_CustomGrid.COL_RESULT, translate("warning_will_be_overwritten"))
                return True

    def _get_operation_name(self):
        return translate("operation_copy")

    def stop(self):
        self._stop_flag.set()

    def is_stopped(self):
        return self._stop_flag.is_set()

    def get_progress_info(self):
        """获取进度信息"""
        return self.progress_info

    def apply_path(self):
        """应用路径变更（Apply）：仅修改 New Path 列（见 Note 13.0 / 6.1）。

        按行计算目标路径写入 New Path；New Path 发生变化的行清空该行 Result，
        未变化的行 Result 保持不变；不写入任何 Result 文案，也不修改其它列。
        """
        input_source_path03 = self.tool_instance.input_source_path03.GetValue().strip()
        input_dest_path03 = self.tool_instance.input_dest_path03.GetValue().strip()
        # 来源/目标输入框为空时无法计算新路径，直接返回（避免下方空串索引 ""[-1] 崩溃）
        if not input_source_path03 or not input_dest_path03:
            return
        create_folder_val = None
        folder_key = self.tool_instance.get_combo_box_method(
            self.tool_instance.combo_create_folder03, self.tool_instance.create_folder_mapping)
        if folder_key == 'single_level_subdirectories':
            create_folder_val = 'single'
        elif folder_key == 'multi_level_subdirectories':
            create_folder_val = 'recursive'
        elif folder_key == 'remove_parent_directory':
            create_folder_val = 'remove_parent'
        elif folder_key == 'flatten_all_files':
            create_folder_val = 'flatten'
        
        if len(input_source_path03) > 3 and input_source_path03[-1] == os.sep:
            source_path_val = input_source_path03.rstrip(os.sep)
        elif len(input_source_path03) <= 3 and input_source_path03[-1] == os.sep:
            source_path_val = input_source_path03
        else:
            source_path_val = input_source_path03

        if len(input_dest_path03) > 3 and input_dest_path03[-1] == os.sep:
            dest_path_val = input_dest_path03.rstrip(os.sep)
        elif len(input_dest_path03) <= 3 and input_dest_path03[-1] == os.sep:
            dest_path_val = input_dest_path03
        else:
            dest_path_val = input_dest_path03
        
        grid = self.tool_instance.file_grid
        rows = grid.GetNumberRows()
        cols = grid.GetNumberCols()
        before = [[grid.GetCellValue(r, c) for c in range(cols)] for r in range(rows)]
        total_count = 0
        
        for row in range(rows):
            current_old_path = grid.GetCellValue(row, tfo_CustomGrid.COL_OLD_PATH).strip()
            current_new_path = grid.GetCellValue(row, tfo_CustomGrid.COL_NEW_PATH).strip()

            if not current_old_path:
                # 无旧路径的行：Apply 不做任何修改
                continue
            
            total_count += 1
            # 旧路径无效/不存在，或已填新路径非法：视为无有效目标 → 清空 New Path
            if (not self.tool_instance.is_valid_path(current_old_path)
                    or not os.path.exists(current_old_path)
                    or (current_new_path and not self.tool_instance.is_valid_path(current_new_path))):
                grid.SetCellValue(row, tfo_CustomGrid.COL_NEW_PATH, "")
                continue
            
            try:
                source_path_norm = os.path.normpath(source_path_val)
                old_path_norm = os.path.normpath(current_old_path)
                
                if not old_path_norm.startswith(source_path_norm + os.sep):
                    grid.SetCellValue(row, tfo_CustomGrid.COL_NEW_PATH, "")
                    continue
                
                try:
                    relative_path = os.path.relpath(old_path_norm, source_path_norm)
                except ValueError:
                    # 无法计算相对路径：保持 New Path 不变
                    continue
                
                invalid_chars = '<>:"/\\|?*'
                match_name_original = self.tool_instance.file_grid.GetCellValue(row, tfo_CustomGrid.COL_MATCH_NAME).strip()
                match_name_cleaned = ''.join(c for c in match_name_original if c not in invalid_chars).strip()
                
                if not current_new_path:
                    original_basename = os.path.basename(current_old_path)
                    if create_folder_val == 'remove_parent':
                        # 消除父目录：去掉相对路径中目标文件/目录的父目录层级，保留目标本身
                        relative_dir = os.path.dirname(relative_path)
                        grand_relative_dir = os.path.dirname(relative_dir)
                        if grand_relative_dir:
                            new_path = os.path.join(dest_path_val, grand_relative_dir, original_basename)
                        else:
                            new_path = os.path.join(dest_path_val, original_basename)
                    elif create_folder_val == 'flatten':
                        # 展平所有文件：无论目标在来源路径的第几层，都直接放到目标路径第一层
                        new_path = os.path.join(dest_path_val, original_basename)
                    elif create_folder_val is None or not match_name_cleaned:
                        new_path = os.path.join(dest_path_val, relative_path)
                    else:
                        if create_folder_val == 'single':
                            new_path = os.path.join(dest_path_val, match_name_cleaned, original_basename)
                        elif create_folder_val == 'recursive':
                            new_path = os.path.join(dest_path_val, match_name_cleaned, relative_path)
                else:
                    new_basename = os.path.basename(current_new_path)
                    relative_dir = os.path.dirname(relative_path)
                    if create_folder_val == 'remove_parent':
                        # 消除父目录：对已有New Path去掉紧邻的父目录层级，保留目标本身；
                        # 新路径已直接位于目标路径根下（无父目录可消除）或路径本身无父目录（如 / 、C:/）时保持原路径不变
                        new_path_norm = os.path.normpath(current_new_path)
                        dest_norm = os.path.normpath(dest_path_val)
                        new_parent_dir = os.path.dirname(new_path_norm)
                        if new_parent_dir == dest_norm or not new_parent_dir or not os.path.dirname(new_parent_dir):
                            new_path = new_path_norm
                        else:
                            new_path = os.path.join(os.path.dirname(new_parent_dir), os.path.basename(new_path_norm))
                    elif create_folder_val == 'flatten':
                        new_path = os.path.join(dest_path_val, new_basename)
                    elif create_folder_val is None or not match_name_cleaned:
                        if relative_dir:
                            new_path = os.path.join(dest_path_val, relative_dir, new_basename)
                        else:
                            new_path = os.path.join(dest_path_val, new_basename)
                    else:
                        if create_folder_val == 'single':
                            new_path = os.path.join(dest_path_val, match_name_cleaned, new_basename)
                        elif create_folder_val == 'recursive':
                            if relative_dir:
                                new_path = os.path.join(dest_path_val, match_name_cleaned, relative_dir, new_basename)
                            else:
                                new_path = os.path.join(dest_path_val, match_name_cleaned, new_basename)
                
                grid.SetCellValue(row, tfo_CustomGrid.COL_NEW_PATH, new_path)
            except Exception as e:
                log_error(f"复制操作错误: {e}")
        
        modified_count = finalize_apply_new_path_only(grid, rows, cols, before,
                                                      tfo_CustomGrid.COL_NEW_PATH, tfo_CustomGrid.COL_RESULT)
        grid.ForceRefresh()
        grid.Update()
        wx.Yield()
        self.tool_instance.status_bar.SetStatusText(translate("worker_status_path_changed", total_count=total_count, modified_count=modified_count), 0)
