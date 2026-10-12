# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
import os
import shutil
import threading
import re
import regex
import tempfile
import datetime
from tfo_utils.tfo_i18n_manager import translate, i18n
from tfo_utils.tfo_file_utils import validate_file_operation, backup_file_or_dir, finalize_apply_new_path_only
from tfo_utils.tfo_logger import log_error, log_info, log_warning, log_file_operation
from tfo_utils.tfo_match_utils import validate_regex_complexity
from tfo_utils.tfo_worker_mode import WorkerMode
from tfo_CustomGrid import tfo_CustomGrid

try:
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3NoHeaderError
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

# Windows 保留设备名（不区分大小写，含带扩展名形式如 CON.txt），不能用作文件/文件夹名
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

class tfo_RenameMoveWorker(threading.Thread):
    def __init__(self, tool_instance, is_rename=True, preview_mode=True, worker_mode=None):
        super().__init__()
        self.tool_instance = tool_instance
        self.is_rename = is_rename
        if worker_mode is not None:
            self.worker_mode = worker_mode
        else:
            self.worker_mode = WorkerMode.PREVIEW if preview_mode else WorkerMode.EXECUTE
        self._stop_flag = threading.Event()
        self.progress_info = (0, 0, 0, 0)
        self.naming_method = ""
        # __init__/start 均在 UI 线程执行：在此快照行数据与冲突下拉框选项，Worker 线程内不再跨线程读取 Grid/控件
        self._snapshot_from_grid()

    def _snapshot_from_grid(self):
        """在 UI 线程快照 Grid 行数据与冲突下拉框选项（线程安全）。"""
        grid = self.tool_instance.file_grid
        self.snapshot_rows_total = grid.GetNumberRows()
        self.snapshot_old_paths = [grid.GetCellValue(r, grid.COL_OLD_PATH).strip() for r in range(self.snapshot_rows_total)]
        self.snapshot_new_paths = [grid.GetCellValue(r, grid.COL_NEW_PATH).strip() for r in range(self.snapshot_rows_total)]
        self.snapshot_match_names = [grid.GetCellValue(r, grid.COL_MATCH_NAME).strip() for r in range(self.snapshot_rows_total)]
        if self.is_rename:
            self.snapshot_file_conflict_selection = self.tool_instance.combo_file_conflict0202.GetSelection()
            self.snapshot_dir_conflict_selection = self.tool_instance.combo_dir_conflict0202.GetSelection()
        else:
            self.snapshot_file_conflict_selection = self.tool_instance.combo_file_conflict0302.GetSelection()
            self.snapshot_dir_conflict_selection = self.tool_instance.combo_dir_conflict0302.GetSelection()

    def start(self):
        """启动前在 UI 线程重新快照 Grid，确保 Worker 使用启动时的最新行数据。

        Preview/Execute 不再修改 New Path（不会自动执行 Apply），但仍可能紧随用户编辑/导入之后
        启动；在 UI 线程重新快照可避免 Worker 线程跨线程读取 Grid 及读到构造时的过期数据。
        """
        self._snapshot_from_grid()
        super().start()
    
    def run(self):
        operation_name = "RenameWorker" if self.is_rename else "MoveWorker"
        log_info(f"[{operation_name}] 开始执行, 模式: {self.worker_mode.name}")
        try:
            # 计算总数：只计算至少有一个路径非空的行（行数来自 UI 线程快照）
            rows_total = self.snapshot_rows_total
            # 先清空整个"执行结果"列，避免残留上一次操作的结果
            for _clear_row in range(rows_total):
                self.tool_instance.file_grid.queue_cell_value(_clear_row, self.tool_instance.file_grid.COL_RESULT, "")
            count_total = 0
            for row_idx in range(rows_total):
                old_path = self.snapshot_old_paths[row_idx]
                new_path = self.snapshot_new_paths[row_idx]
                if old_path or new_path:
                    count_total += 1
            # 如果没有需要处理的项目
            if count_total == 0:
                log_info(f"[{operation_name}] 没有需要处理的文件")
                return
            
            log_info(f"[{operation_name}] 待处理文件数: {count_total}")
            
            count_finished = 0
            count_ok = 0
            # 建立集合和计数器
            old_paths_set = set()
            modified_paths_set = set()
            modified_paths_info = {}
            # 记录每一行在第一遍检查中的判定结果（will_be=正常执行，merge=合并目录）
            # 供第二遍（EXECUTE）直接使用，避免依赖通过 wx.CallAfter 异步写入的
            # Result 列文本造成竞态（直接点"执行"时可能读取到尚未写入的预览结果）。
            self.row_outcome = {}
            
            # 冲突下拉框选项已在 __init__ 按 is_rename 从对应 Tab 快照（重命名=Tab02 的 0202，移动=Tab03 的 0302）
            file_conflict_selection = self.snapshot_file_conflict_selection
            dir_conflict_selection = self.snapshot_dir_conflict_selection
            # 文件冲突方式（下拉框：0=跳过, 1=覆盖），供目录合并时按用户选择处理同名文件
            file_conflict_method = "overwrite" if file_conflict_selection == 1 else "skip"
            
            log_info(f"[{operation_name}] 文件冲突策略: {file_conflict_selection}, 目录冲突策略: {dir_conflict_selection}")
            
            # 第一遍：收集所有新路径的信息
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
                # 第一步：获取旧路径，和获取新路径路径（来自 UI 线程快照）
                old_path = self.snapshot_old_paths[row_idx]
                new_path = self.snapshot_new_paths[row_idx]
                # 检查路径是否都为空，两个路径都为空则跳过不处理
                if not old_path and not new_path:
                    continue
                # 检查路径是否有一个为空一个非空
                if not old_path and new_path:
                    self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("warning_old_path_not_set"))
                    count_finished += 1
                    self.progress_info = (count_finished, count_total, count_ok, 0)
                    continue
                elif old_path and not new_path:
                    self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("warning_new_path_not_set"))
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
                        self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate(error_key, size=error_param, length=error_param))
                    else:
                        self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate(error_key))
                    count_finished += 1
                    if error_code == 'same_path':
                        count_ok += 1
                    self.progress_info = (count_finished, count_total, count_ok, 0)
                    continue
                
                # 判断旧路径是否重复（重命名和移动不允许重复）
                if old_path in old_paths_set:
                    self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("error_duplicate_old_path"))
                    count_finished += 1
                    self.progress_info = (count_finished, count_total, count_ok, 0)
                    continue
                else:
                    old_paths_set.add(old_path)
                
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
                            # 避免最后一行按普通移动把源目录嵌套进已存在的目标目录
                            self.row_outcome[row_idx] = 'merge'
                            self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("warning_will_be_merged"))
                            count_ok += 1
                        elif dir_conflict_selection == 2:
                            # 替换：所有重复行都执行替换（按行序逐个替换目标），
                            # 避免靠前的源目录既不移动也不删除而残留
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
                            # 覆盖：所有重复行都执行（按行序依次覆盖），
                            # 避免靠前的源文件既不移动也不删除而残留
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
                    # 路径与匹配名来自 UI 线程快照
                    old_path = self.snapshot_old_paths[row_idx]
                    new_path = self.snapshot_new_paths[row_idx]

                    if not old_path or not new_path:
                        continue

                    match_name = self.snapshot_match_names[row_idx]
                    outcome = self.row_outcome.get(row_idx)
                    if outcome == 'skip':
                        # 执行模式：跳过行的最终结果不能停留在预览态的"将被跳过"，
                        # 覆盖为最终态"已跳过"
                        self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("warning_skipped"))
                        log_file_operation(self._get_operation_name(), old_path, new_path, match_name,
                                           skipped=True, row_index=row_idx)
                    elif outcome in ('will_be', 'merge', 'replace'):
                        # 防御：预览后磁盘状态可能变化，源为文件而目标已是目录时绝不执行，
                        # 否则 shutil.move 会把文件移入目标目录内部
                        if not os.path.isdir(old_path) and os.path.isdir(new_path):
                            self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("error_source_file_target_dir"))
                            continue
                        target_dir = os.path.dirname(new_path)
                        if target_dir and not os.path.exists(target_dir):
                            try:
                                os.makedirs(target_dir, exist_ok=True)
                            except Exception as e:
                                log_file_operation(self._get_operation_name(), old_path, new_path, match_name,
                                                   success=False, error=e, row_index=row_idx)
                                self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("failure_cannot_create_directory"))
                                continue

                        try:
                            is_dir = os.path.isdir(old_path)
                            newpath_exists = os.path.exists(new_path)
                            dst_backup = None
                            src_backup = None

                            # 操作级撤销/重做：备份目标（若已存在且与源不同）
                            if newpath_exists and backup_dir and os.path.normcase(new_path) != os.path.normcase(old_path):
                                category = "dir_conflicts" if is_dir else "file_conflicts"
                                dst_backup, _ = backup_file_or_dir(new_path, backup_dir, category, backup_idx)
                                backup_idx += 1

                            if outcome == 'replace':
                                # 替换冲突：备份后删除已存在的目标，再按普通移动/复制处理
                                try:
                                    if os.path.isdir(new_path):
                                        shutil.rmtree(new_path)
                                    elif os.path.exists(new_path):
                                        os.remove(new_path)
                                except Exception as e:
                                    log_file_operation(self._get_operation_name(), old_path, new_path, match_name,
                                                       success=False, error=e, row_index=row_idx)
                                    self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("failure_operation_with_error", operation=self._get_operation_name(), error=str(e)))
                                    continue
                                outcome = 'will_be'

                            if outcome == 'merge':
                                if is_dir:
                                    # 合并目录：额外备份源目录
                                    if backup_dir:
                                        src_backup, _ = backup_file_or_dir(old_path, backup_dir, "dir_conflicts", backup_idx)
                                        backup_idx += 1
                                    self.tool_instance.merge_directories(old_path, new_path, is_move=True, file_conflict=file_conflict_method)
                                    self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("success_operation_merged", operation=self._get_operation_name()))
                                    # 记录 merge_dirs 操作
                                    if op_history_mgr and op_entry:
                                        op_history_mgr.append_file_op(op_entry, {
                                            "op": "merge_dirs",
                                            "src_dir": old_path,
                                            "dst_dir": new_path,
                                            "src_dir_backup": src_backup,
                                            "dst_dir_backup": dst_backup,
                                            "is_move": True,
                                            "file_conflict": file_conflict_method,
                                            "success": True,
                                            "error": None,
                                        })
                                else:
                                    shutil.move(old_path, new_path)
                                    self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("success_operation_merged", operation=self._get_operation_name()))
                                    # 记录 move 操作
                                    if op_history_mgr and op_entry:
                                        dst_mtime_after = None
                                        try:
                                            dst_mtime_after = os.path.getmtime(new_path)
                                        except OSError:
                                            pass
                                        op_history_mgr.append_file_op(op_entry, {
                                            "op": "move",
                                            "src": old_path,
                                            "dst": new_path,
                                            "src_backup": src_backup,
                                            "dst_backup": dst_backup,
                                            "dst_mtime_after": dst_mtime_after,
                                            "success": True,
                                            "error": None,
                                        })
                                count_operated += 1
                            else:
                                shutil.move(old_path, new_path)
                                self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("success_operation", operation=self._get_operation_name()))
                                count_operated += 1
                                # 记录 move 操作
                                if op_history_mgr and op_entry:
                                    dst_mtime_after = None
                                    try:
                                        dst_mtime_after = os.path.getmtime(new_path)
                                    except OSError:
                                        pass
                                    op_history_mgr.append_file_op(op_entry, {
                                        "op": "move",
                                        "src": old_path,
                                        "dst": new_path,
                                        "src_backup": src_backup,
                                        "dst_backup": dst_backup,
                                        "dst_mtime_after": dst_mtime_after,
                                        "success": True,
                                        "error": None,
                                    })
                            # 操作成功：记录旧路径/新路径/匹配名，便于复现与定位
                            log_file_operation(self._get_operation_name(), old_path, new_path, match_name,
                                               success=True, row_index=row_idx)
                        except FileNotFoundError:
                            log_file_operation(self._get_operation_name(), old_path, new_path, match_name,
                                               success=False, error="file not found", row_index=row_idx)
                            self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("failure_file_not_exist"))
                        except PermissionError:
                            if not os.access(old_path, os.R_OK):
                                log_file_operation(self._get_operation_name(), old_path, new_path, match_name,
                                                   success=False, error="no read permission", row_index=row_idx)
                                self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("failure_no_read_permission"))
                            elif not os.access(os.path.dirname(new_path) if os.path.dirname(new_path) else '.', os.W_OK):
                                log_file_operation(self._get_operation_name(), old_path, new_path, match_name,
                                                   success=False, error="no write permission", row_index=row_idx)
                                self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("failure_no_write_permission"))
                            else:
                                log_file_operation(self._get_operation_name(), old_path, new_path, match_name,
                                                   success=False, error="permission error", row_index=row_idx)
                                self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("failure_operation", operation=self._get_operation_name()))
                        except Exception as e:
                            log_file_operation(self._get_operation_name(), old_path, new_path, match_name,
                                               success=False, error=e, row_index=row_idx)
                            self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("failure_operation_with_error", operation=self._get_operation_name(), error=str(e)))
                
                # 最终更新进度信息，并添加实际操作数量
                self.progress_info = (count_finished, count_total, count_ok, count_operated)
            log_info(f"[{operation_name}] 执行完成, 成功: {count_ok}/{count_total}")
        except Exception as e:
            log_error(f"[{operation_name}] 重命名/移动操作错误: {e}")

    def _set_will_be_result(self, row_idx):
        self.row_outcome[row_idx] = 'will_be'
        self._set_will_be_text(row_idx)

    def _set_will_be_text(self, row_idx):
        """仅写入普通"将执行"文案，不改变 row_outcome（供已显式设定 outcome 的行复用）"""
        if self.is_rename:
            self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("correct_will_be_renamed"))
        else:
            self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("correct_will_be_moved"))

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
        if not src_is_dir and dst_is_dir:
            # 源为文件而目标已是目录：继续执行会把文件移入目录内部，按错误处理
            self.row_outcome[row_idx] = 'error'
            self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("error_source_file_target_dir"))
            return False
        if src_is_dir and dst_is_dir:
            if dir_conflict_selection == 1:
                self.row_outcome[row_idx] = 'merge'
                self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("warning_will_be_merged"))
                return True
            elif dir_conflict_selection == 2:
                self.row_outcome[row_idx] = 'replace'
                self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("warning_will_be_replaced"))
                return True
            else:
                self.row_outcome[row_idx] = 'skip'
                self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("warning_will_be_skipped"))
                return False
        else:
            if file_conflict_selection == 0:
                self.row_outcome[row_idx] = 'skip'
                self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("warning_will_be_skipped"))
                return False
            else:
                self.row_outcome[row_idx] = 'will_be'
                self.tool_instance.file_grid.queue_cell_value(row_idx, 3, translate("warning_will_be_overwritten"))
                return True

    def _get_operation_name(self):
        return translate("operation_rename") if self.is_rename else translate("operation_move")

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
                if os.name == 'nt' and match_name_cleaned:
                    # Windows 文件夹名补充清理：去除尾部点/空格；保留名（CON/NUL/COM1…，
                    # 含带扩展名形式）加下划线前缀，避免创建失败或指向设备
                    match_name_cleaned = match_name_cleaned.rstrip('. ')
                    if match_name_cleaned.split('.')[0].upper() in WINDOWS_RESERVED_NAMES:
                        match_name_cleaned = '_' + match_name_cleaned

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
                log_error(f"移动操作路径计算错误: {e}")

        modified_count = self._finalize_apply(grid, rows, cols, before)
        grid.ForceRefresh()
        grid.Update()
        wx.Yield()
        self.tool_instance.status_bar.SetStatusText(translate("worker_status_path_changed", total_count=total_count, modified_count=modified_count), 0)

    def apply_naming(self):
        """应用重命名（Apply）：仅修改 New Path 列（见 Note 13.0 / 6.1）。

        按行计算新文件名写入 New Path；New Path 发生变化的行清空该行 Result，
        未变化的行 Result 保持不变；不写入任何 Result 文案，也不修改其它列。
        """
        # 第一步：检查重命名参数（排除不需要参数的情况）
        naming_method = self.tool_instance.get_combo_box_method(
            self.tool_instance.combo_naming_method02, self.tool_instance.naming_method_mapping)
        current_method = naming_method

        # 解析合并方式的子模式（由第一个参数单选框决定）
        if current_method == "replace":
            effective_method = "replace_by_position" if self.tool_instance.radio_replace_mode_position02.GetValue() else "replace_by_text"
        elif current_method == "add_affix":
            effective_method = "add_prefix" if self.tool_instance.radio_affix_mode_prefix02.GetValue() else "add_suffix"
        elif current_method == "change_case":
            if self.tool_instance.radio_case_mode_lower02.GetValue():
                effective_method = "all_lowercase"
            elif self.tool_instance.radio_case_mode_camel02.GetValue():
                effective_method = "camel_case"
            elif self.tool_instance.radio_case_mode_capitalize02.GetValue():
                effective_method = "first_letter_uppercase"
            else:
                effective_method = "all_uppercase"
        else:
            effective_method = current_method

        is_rename_param_valid = True
        regex_error = None
        if effective_method not in ["original_name", "add_number", "rename_mp3"]:
            if effective_method == "replace_by_text":
                if not self.tool_instance.input_naming_oldtext.GetValue().strip():
                    is_rename_param_valid = False
            elif effective_method == "replace_by_position":
                position = self.tool_instance.input_naming_position02.GetValue().strip()
                length = self.tool_instance.input_length02.GetValue().strip()
                text = self.tool_instance.input_naming_text02.GetValue().strip()
                if not position or not position.isdigit() or int(position) < 0:
                    is_rename_param_valid = False
                if not length or not length.isdigit() or int(length) < 0:
                    is_rename_param_valid = False
                if not text:
                    is_rename_param_valid = False
            elif effective_method == "insert_by_position":
                position = self.tool_instance.input_naming_position02.GetValue().strip()
                text = self.tool_instance.input_naming_text02.GetValue().strip()
                if not position or not position.isdigit() or int(position) < 0:
                    is_rename_param_valid = False
                if not text:
                    is_rename_param_valid = False
            elif effective_method == "delete_by_position":
                position = self.tool_instance.input_naming_position02.GetValue().strip()
                length = self.tool_instance.input_length02.GetValue().strip()
                if not position or not position.isdigit() or int(position) < 0:
                    is_rename_param_valid = False
                if not length or not length.isdigit() or int(length) <= 0:
                    is_rename_param_valid = False
            elif effective_method in ["add_prefix", "add_suffix"]:
                if not self.tool_instance.input_naming_text02.GetValue().strip():
                    is_rename_param_valid = False
            elif effective_method == "regex_replace":
                pattern = self.tool_instance.input_naming_oldtext.GetValue().strip()
                if not pattern:
                    is_rename_param_valid = False
                else:
                    complexity_error = validate_regex_complexity(pattern)
                    if complexity_error:
                        is_rename_param_valid = False
                        regex_error = complexity_error
                    else:
                        try:
                            regex.compile(pattern)
                        except regex.error as e:
                            is_rename_param_valid = False
                            regex_error = str(e)
            elif effective_method == "convert_by_placeholder":
                if not self.tool_instance.input_naming_text02.GetValue().strip():
                    is_rename_param_valid = False
        
        if not is_rename_param_valid:
            if regex_error is not None:
                wx.MessageBox(translate("error_regex_invalid", error=regex_error), translate("dialog_title_error"), wx.OK | wx.ICON_ERROR)
                return
            wx.MessageBox(translate("worker_message_missing_rename_params"), translate("dialog_title_info"), wx.OK | wx.ICON_WARNING)
            return
        
        grid = self.tool_instance.file_grid
        rows = grid.GetNumberRows()
        cols = grid.GetNumberCols()
        before = [[grid.GetCellValue(r, c) for c in range(cols)] for r in range(rows)]
        total_count = 0
        serial_counter = 1
        self._position_out_of_range_count = 0
        
        if current_method == "add_number":
            # 参数：编号分组（单选：不分组/按父目录/按匹配名）+ 编号位置（勾选 Before=加到文件名前，不勾选=加到文件名末尾，默认末尾）
            scope_by_dir = self.tool_instance.radio_number_scope_dir02.GetValue()
            scope_by_match = self.tool_instance.radio_number_scope_match02.GetValue()
            add_at_start = self.tool_instance.check_number_pos_start02.GetValue()
            add_at_end = not add_at_start
            group_dict = {}
            for row in range(rows):
                new_path = self.tool_instance.file_grid.GetCellValue(row, self.tool_instance.file_grid.COL_NEW_PATH).strip()
                if not new_path:
                    old_path = self.tool_instance.file_grid.GetCellValue(row, self.tool_instance.file_grid.COL_OLD_PATH).strip()
                    if old_path:
                        new_path = old_path
                        self.tool_instance.file_grid.SetCellValue(row, self.tool_instance.file_grid.COL_NEW_PATH, new_path)
                    else:
                        for col in range(self.tool_instance.file_grid.GetNumberCols()):
                            self.tool_instance.file_grid.SetCellValue(row, col, "")
                        continue
                
                if scope_by_dir:
                    group_key = os.path.dirname(new_path)
                elif scope_by_match:
                    group_key = self.tool_instance.file_grid.GetCellValue(row, self.tool_instance.file_grid.COL_MATCH_NAME).strip()
                else:
                    group_key = "all"
                
                if group_key not in group_dict:
                    group_dict[group_key] = []
                group_dict[group_key].append((row, new_path))
            
            for group_key, items in group_dict.items():
                min_digits = max(2, len(str(len(items))))
                for idx, (row, new_path) in enumerate(items, start=1):
                    try:
                        old_path = self.tool_instance.file_grid.GetCellValue(row, self.tool_instance.file_grid.COL_OLD_PATH).strip()
                        if not old_path: continue
                        
                        total_count += 1
                        if not self.tool_instance.is_valid_path(old_path):
                            for col in range(self.tool_instance.file_grid.COL_RESULT, self.tool_instance.file_grid.GetNumberCols()):
                                self.tool_instance.file_grid.SetCellValue(row, col, "")
                            self.tool_instance.file_grid.SetCellValue(row, self.tool_instance.file_grid.COL_RESULT, translate("error_old_path_invalid"))
                            continue
                        
                        if not os.path.exists(old_path):
                            for col in range(self.tool_instance.file_grid.COL_RESULT, self.tool_instance.file_grid.GetNumberCols()):
                                self.tool_instance.file_grid.SetCellValue(row, col, "")
                            self.tool_instance.file_grid.SetCellValue(row, self.tool_instance.file_grid.COL_RESULT, translate("error_old_path_not_exist"))
                            continue
                        
                        current_new_path = self.tool_instance.file_grid.GetCellValue(row, self.tool_instance.file_grid.COL_NEW_PATH).strip()
                        
                        if current_new_path and not self.tool_instance.is_valid_path(current_new_path):
                            self.tool_instance.file_grid.SetCellValue(row, self.tool_instance.file_grid.COL_RESULT, translate("error_new_path_invalid"))
                            continue
                        
                        current_new_path = new_path
                        is_file = self._is_path_file(old_path, new_path)
                        dir_part = os.path.dirname(new_path)
                        base_part = os.path.basename(new_path)
                        cleaned_base = self._remove_existing_serial(base_part, is_file, add_at_start)
                        serial_str = f"{idx:0{min_digits}d}"
                        
                        if is_file:
                            name_part, ext_part = os.path.splitext(cleaned_base)
                        else:
                            name_part, ext_part = cleaned_base, ""
                        if add_at_start:
                            name_part = f"{serial_str}_" + name_part
                        if add_at_end:
                            name_part = name_part + f"_{serial_str}"
                        new_base = name_part + ext_part
                        
                        new_full_path = os.path.join(dir_part, new_base)
                        
                        self.tool_instance.file_grid.SetCellValue(row, self.tool_instance.file_grid.COL_NEW_PATH, new_full_path)
                    except Exception as e:
                        log_error(f"添加序号失败: {e}")
                        self.tool_instance.file_grid.SetCellValue(row, self.tool_instance.file_grid.COL_RESULT, translate("error_add_serial_number"))
        else:
            for row in range(rows):
                old_path = self.tool_instance.file_grid.GetCellValue(row, self.tool_instance.file_grid.COL_OLD_PATH).strip()
                if not old_path:
                    for col in range(self.tool_instance.file_grid.GetNumberCols()):
                        self.tool_instance.file_grid.SetCellValue(row, col, "")
                    continue
                
                total_count += 1
                if not self.tool_instance.is_valid_path(old_path):
                    for col in range(self.tool_instance.file_grid.COL_RESULT, self.tool_instance.file_grid.GetNumberCols()):
                        self.tool_instance.file_grid.SetCellValue(row, col, "")
                    self.tool_instance.file_grid.SetCellValue(row, self.tool_instance.file_grid.COL_RESULT, translate("error_old_path_invalid"))
                    continue
                
                if not os.path.exists(old_path):
                    for col in range(self.tool_instance.file_grid.COL_RESULT, self.tool_instance.file_grid.GetNumberCols()):
                        self.tool_instance.file_grid.SetCellValue(row, col, "")
                    self.tool_instance.file_grid.SetCellValue(row, self.tool_instance.file_grid.COL_RESULT, translate("error_old_path_not_exist"))
                    continue
                
                current_new_path = self.tool_instance.file_grid.GetCellValue(row, self.tool_instance.file_grid.COL_NEW_PATH).strip()

                if current_new_path and not self.tool_instance.is_valid_path(current_new_path):
                    self.tool_instance.file_grid.SetCellValue(row, self.tool_instance.file_grid.COL_RESULT, translate("error_new_path_invalid"))
                    continue
                
                try:
                    if effective_method == "original_name" or effective_method == "set_to_old_name":
                        original_basename = os.path.basename(old_path)
                        original_basename = self._clean_filename(original_basename)
                        if current_new_path:
                            dirname = os.path.dirname(current_new_path)
                            new_full_path = os.path.join(dirname, original_basename)
                        else:
                            new_full_path = old_path
                    elif effective_method == "rename_mp3":
                        if not HAS_MUTAGEN:
                            self.tool_instance.file_grid.SetCellValue(row, self.tool_instance.file_grid.COL_RESULT, translate("error_missing_mutagen_library"))
                            continue
                        
                        old_ext = os.path.splitext(old_path)[1].lower()
                        if old_ext != '.mp3':
                            continue
                        
                        if current_new_path:
                            dirname = os.path.dirname(current_new_path)
                        else:
                            dirname = os.path.dirname(old_path)
                        
                        artist, title = self._get_mp3_metadata(old_path)
                        if self.tool_instance.radio_mp3_title_first02.GetValue():
                            mp3_format = "title_artist"
                        elif self.tool_instance.radio_mp3_title_only02.GetValue():
                            mp3_format = "title_only"
                        else:
                            mp3_format = "artist_title"

                        if mp3_format == "title_only":
                            if title:
                                new_basename = f"{title}.mp3"
                            else:
                                new_basename = os.path.basename(old_path)
                        elif mp3_format == "title_artist":
                            if title and artist:
                                new_basename = f"{title} - {artist}.mp3"
                            elif title:
                                new_basename = f"{title}.mp3"
                            elif artist:
                                new_basename = f"{artist}.mp3"
                            else:
                                new_basename = os.path.basename(old_path)
                        else:  # artist_title（默认）
                            if artist and title:
                                new_basename = f"{artist} - {title}.mp3"
                            elif title:
                                new_basename = f"{title}.mp3"
                            elif artist:
                                new_basename = f"{artist}.mp3"
                            else:
                                new_basename = os.path.basename(old_path)
                        
                        new_basename = self._clean_filename(new_basename)
                        new_full_path = os.path.join(dirname, new_basename)
                    elif effective_method in ["replace_by_text", "replace_by_position", "insert_by_position", "delete_by_position", "add_prefix", "add_suffix", "all_uppercase", "first_letter_uppercase", "camel_case", "all_lowercase", "regex_replace"]:
                        if current_new_path:
                            dirname = os.path.dirname(current_new_path)
                            basename = os.path.basename(current_new_path)
                        else:
                            dirname = os.path.dirname(old_path)
                            basename = os.path.basename(old_path)
                        
                        if '.' in basename and not os.path.isdir(old_path) and not os.path.isdir(current_new_path if current_new_path else old_path):
                            name_part, ext_part = os.path.splitext(basename)
                        else:
                            name_part = basename
                            ext_part = ""
                        
                        new_name_part = self._get_new_name_part(name_part, effective_method)
                        if new_name_part is None:
                            continue
                        
                        if ext_part:
                            new_basename = new_name_part + ext_part
                        else:
                            new_basename = new_name_part
                        
                        new_basename = self._clean_filename(new_basename)
                        new_full_path = os.path.join(dirname, new_basename)
                    elif effective_method == "convert_by_placeholder":
                        format_text = self.tool_instance.input_naming_text02.GetValue().strip()
                        match_name = self.tool_instance.file_grid.GetCellValue(row, self.tool_instance.file_grid.COL_MATCH_NAME).strip()
                        old_dir = os.path.dirname(old_path)
                        old_parent = os.path.basename(old_dir) if old_dir else ""
                        old_base = os.path.basename(old_path)
                        
                        if current_new_path:
                            new_dir = os.path.dirname(current_new_path)
                        else:
                            new_dir = old_dir
                        
                        try:
                            stat_info = os.stat(old_path)
                            create_dt = datetime.datetime.fromtimestamp(stat_info.st_ctime)
                            modify_dt = datetime.datetime.fromtimestamp(stat_info.st_mtime)
                            create_date = create_dt.strftime("%Y%m%d")
                            modify_date = modify_dt.strftime("%Y%m%d")
                            create_time = create_dt.strftime("%H%M%S")
                            modify_time = modify_dt.strftime("%H%M%S")
                        except (ValueError, AttributeError):
                            create_date = "00000000"
                            modify_date = "00000000"
                            create_time = "000000"
                            modify_time = "000000"
                        
                        replaced_text = format_text
                        replaced_text = replaced_text.replace("{{SERIAL_NUMBER}}", str(serial_counter))
                        replaced_text = replaced_text.replace("{{CREATE_DATE}}", create_date)
                        replaced_text = replaced_text.replace("{{MODIFY_DATE}}", modify_date)
                        replaced_text = replaced_text.replace("{{CREATE_TIME}}", create_time)
                        replaced_text = replaced_text.replace("{{MODIFY_TIME}}", modify_time)
                        replaced_text = replaced_text.replace("{{MATCH_NAME}}", match_name if match_name else "")
                        replaced_text = replaced_text.replace("{{NEW_DIR}}", new_dir if new_dir else "")
                        replaced_text = replaced_text.replace("{{OLD_PARENT}}", old_parent if old_parent else "")
                        replaced_text = replaced_text.replace("{{OLD_DIR}}", old_dir if old_dir else "")
                        replaced_text = replaced_text.replace("{{OLD_BASE}}", old_base if old_base else "")
                        
                        has_dir_placeholder = "{{NEW_DIR}}" in format_text or "{{OLD_DIR}}" in format_text
                        is_absolute = False
                        if os.name == 'nt':
                            if len(replaced_text) >= 3 and replaced_text[1] == ':' and replaced_text[2] == os.sep:
                                is_absolute = True
                        else:
                            if replaced_text.startswith('/'):
                                is_absolute = True
                        
                        if not has_dir_placeholder and not is_absolute:
                            if not current_new_path:
                                new_full_path = os.path.join(old_dir, replaced_text)
                            else:
                                if new_dir and self.tool_instance.is_valid_path(new_dir):
                                    new_full_path = os.path.join(new_dir, replaced_text)
                                else:
                                    self.tool_instance.file_grid.SetCellValue(row, self.tool_instance.file_grid.COL_RESULT, translate("error_new_path_invalid"))
                                    self.tool_instance.file_grid.SetCellValue(row, self.tool_instance.file_grid.COL_NEW_PATH, replaced_text)
                                    continue
                        else:
                            if is_absolute:
                                new_full_path = replaced_text
                            else:
                                if os.path.isdir(old_path):
                                    new_full_path = replaced_text
                                else:
                                    _, old_ext = os.path.splitext(old_path)
                                    new_full_path = replaced_text + old_ext
                        
                        new_full_path = self._clean_path(new_full_path)
                        serial_counter += 1
                    else:
                        new_full_path = current_new_path
                    
                    grid.SetCellValue(row, self.tool_instance.file_grid.COL_NEW_PATH, new_full_path)
                except Exception as e:
                    log_error(f"重命名失败: {e}")
                    continue
        
        modified_count = self._finalize_apply(grid, rows, cols, before)
        grid.ForceRefresh()
        grid.Update()
        wx.Yield()
        status_msg = translate("worker_status_rename_applied", total_count=total_count, modified_count=modified_count)
        if self._position_out_of_range_count > 0:
            status_msg += " " + translate("worker_status_position_out_of_range", count=self._position_out_of_range_count)
        self.tool_instance.status_bar.SetStatusText(status_msg, 0)

    def _get_new_name_part(self, name_part, naming_method):
        """根据重命名方式处理name_part（不含扩展名的部分）"""
        current_method = naming_method
        pattern = ""
        try:
            if current_method == "replace_by_text":
                oldtext = self.tool_instance.input_naming_oldtext.GetValue().strip()
                newtext = self.tool_instance.input_naming_text02.GetValue().strip()
                return name_part.replace(oldtext, newtext)
            elif current_method == "replace_by_position":
                position = int(self.tool_instance.input_naming_position02.GetValue().strip())
                length = int(self.tool_instance.input_length02.GetValue().strip())
                text = self.tool_instance.input_naming_text02.GetValue().strip()
                if position >= len(name_part):
                    self._position_out_of_range_count += 1
                    return name_part
                if position + length > len(name_part):
                    length = len(name_part) - position
                return name_part[:position] + text + name_part[position+length:]
            elif current_method == "insert_by_position":
                position = int(self.tool_instance.input_naming_position02.GetValue().strip())
                text = self.tool_instance.input_naming_text02.GetValue().strip()
                if position > len(name_part):
                    position = len(name_part)
                return name_part[:position] + text + name_part[position:]
            elif current_method == "delete_by_position":
                position = int(self.tool_instance.input_naming_position02.GetValue().strip())
                length = int(self.tool_instance.input_length02.GetValue().strip())
                if position >= len(name_part):
                    self._position_out_of_range_count += 1
                    return name_part
                if position + length > len(name_part):
                    length = len(name_part) - position
                return name_part[:position] + name_part[position+length:]
            elif current_method == "add_prefix":
                prefix = self.tool_instance.input_naming_text02.GetValue().strip()
                return prefix + name_part
            elif current_method == "add_suffix":
                suffix = self.tool_instance.input_naming_text02.GetValue().strip()
                return name_part + suffix
            elif current_method == "all_uppercase":
                return name_part.upper()
            elif current_method == "first_letter_uppercase":
                return name_part.capitalize()
            elif current_method == "camel_case":
                # 使用正则表达式分割但保留分隔符
                parts = re.split(r'([_\s:-]+)', name_part)
                result = ""
                for i, part in enumerate(parts):
                    if i % 2 == 0:  # 单词部分
                        result += part.capitalize()
                    else:  # 分隔符部分
                        result += part
                return result
            elif current_method == "all_lowercase":
                return name_part.lower()
            elif current_method == "regex_replace":
                pattern = self.tool_instance.input_naming_oldtext.GetValue().strip()
                replacement = self.tool_instance.input_naming_text02.GetValue()
                # 用 regex 库的原生超时防止 ReDoS（Apply 在主线程执行，避免界面卡死）
                return regex.sub(pattern, replacement, name_part, timeout=2)
            else:
                return name_part
        except TimeoutError:
            log_error(f"正则替换超时: {pattern}")
            return None
        except Exception as e:
            log_error(f"重命名失败: {e}")
            return None

    def _is_path_file(self, old_path, new_path):
        """判断路径是文件还是目录"""
        if new_path and os.path.exists(new_path):
            return not os.path.isdir(new_path)
        if old_path and os.path.exists(old_path):
            return not os.path.isdir(old_path)
        
        basename_to_check = os.path.basename(new_path) if new_path else ""
        if not basename_to_check and old_path:
            basename_to_check = os.path.basename(old_path)
        
        if basename_to_check:
            pattern = r'\.[a-zA-Z]{2,7}$'
            if re.search(pattern, basename_to_check):
                return True
        return False

    def _remove_existing_serial(self, basename, is_file, remove_prefix):
        """移除指定位置已存在的编号，用于重复应用"添加编号"时保持幂等。

        remove_prefix=True（Before 勾选，添加前置编号）时仅清除已有前缀编号 `NN_`，
        保留已有后缀编号；remove_prefix=False（Before 不勾选，添加后置编号）时仅清除
        已有后缀编号 `_NN`，保留已有前缀编号。
        """
        if is_file:
            name_part, ext_part = os.path.splitext(basename)
        else:
            name_part, ext_part = basename, ""
        if remove_prefix:
            name_part = re.sub(r'^\d+_', '', name_part)
        else:
            name_part = re.sub(r'_\d+$', '', name_part)
        return name_part + ext_part

    def _get_mp3_metadata(self, mp3_path):
        """获取MP3文件的歌手和歌名"""
        try:
            audio = MP3(mp3_path)
            artist = ""
            title = ""
            
            if "TPE1" in audio:
                artist = str(audio["TPE1"])
            elif "TPE2" in audio:
                artist = str(audio["TPE2"])
            
            if "TIT2" in audio:
                title = str(audio["TIT2"])
            
            return artist.strip(), title.strip()
        except ID3NoHeaderError:
            return "", ""
        except Exception as e:
            log_error(f"读取MP3元数据失败: {e}")
            return "", ""

    def _clean_filename(self, filename):
        """剔除文件名中的非法字符"""
        if os.name == 'nt':
            invalid_chars = r'<>:"\\|?*/'
            for char in invalid_chars:
                filename = filename.replace(char, '_')
        else:
            # POSIX 文件名仅 '/' 和空字节非法；()[]{};$&' 等都是合法字符，
            # 不应替换，否则"原名称"等命名方式会产生意外改名
            filename = filename.replace('/', '_').replace('\x00', '_')
        return filename

    def _clean_path(self, path):
        """剔除路径中文件名部分的非法字符，保留路径分隔符"""
        dirname, basename = os.path.split(path)
        if basename:
            cleaned_basename = self._clean_filename(basename)
            return os.path.join(dirname, cleaned_basename) if dirname else cleaned_basename
        return path

    def _finalize_apply(self, grid, rows, cols, before):
        """Apply 收尾（见 Note 13.0 / 6.1）：委托共用实现，返回 New Path 变化行数。"""
        return finalize_apply_new_path_only(grid, rows, cols, before,
                                            tfo_CustomGrid.COL_NEW_PATH, tfo_CustomGrid.COL_RESULT)
