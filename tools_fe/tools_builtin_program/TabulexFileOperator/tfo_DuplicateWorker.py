# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
import os
import threading
import hashlib
import shutil
from tfo_utils.tfo_i18n_manager import translate, i18n
from tfo_utils.tfo_recycle_bin import delete_to_recycle
from tfo_utils.tfo_file_utils import backup_file_or_dir
from tfo_utils.tfo_logger import log_error, log_info, log_warning, log_file_operation
from tfo_utils.tfo_worker_mode import WorkerMode

"""去重工作线程"""
class tfo_DuplicateWorker(threading.Thread):
    def __init__(self, tool_instance, algorithm, rule, execute_delete=False, preview_mode=False, worker_mode=None):
        super().__init__()
        self.tool_instance = tool_instance
        self.algorithm = algorithm
        self.rule = rule
        if worker_mode is not None:
            self.worker_mode = worker_mode
        else:
            if not execute_delete:
                self.worker_mode = WorkerMode.APPLY
            elif preview_mode:
                self.worker_mode = WorkerMode.PREVIEW
            else:
                self.worker_mode = WorkerMode.EXECUTE
        self._stop_flag = threading.Event()
        self.progress_info = (0, 0, 0, 0, 0)
        self.hash_progress_info = (0, 0)
        self.duplicate_groups = 0
        self.files_to_delete = 0
        self.deleted_count = 0
        self.delete_result_dict = {}
        # __init__ 在 UI 线程执行：在此快照行数据，Worker 线程内不再跨线程读取 Grid
        grid = tool_instance.file_grid
        self.snapshot_rows = grid.GetNumberRows()
        self.snapshot_old_paths = [grid.GetCellValue(r, grid.COL_OLD_PATH).strip() for r in range(self.snapshot_rows)]
        self.snapshot_match_names = [grid.GetCellValue(r, grid.COL_MATCH_NAME).strip() for r in range(self.snapshot_rows)]

    def run(self):
        log_info(f"[DuplicateWorker] 开始执行, 模式: {self.worker_mode.name}, 算法: {self.algorithm}, 规则: {self.rule}")
        try:
            # 预置：建立重复文件ID到重复文件路径Set集合的空字典
            duplicate_files = {}
            # 初始化重复文件组数和将被删除文件的数量
            duplicate_groups = 0
            files_to_delete = 0
            
            # 获取表格行数（来自 UI 线程快照）
            rows = self.snapshot_rows
            log_info(f"[DuplicateWorker] 待扫描文件数: {rows}")
            # 先清空整个"执行结果"列，避免残留上一次操作的结果
            for _clear_row in range(rows):
                self.tool_instance.file_grid.queue_cell_value(_clear_row, self.tool_instance.file_grid.COL_RESULT, "")

            # 如果是文件指纹法或文件哈希法，先收集所有文件大小
            current_algorithm_key = self.algorithm
            if current_algorithm_key in ["file_fingerprint", "file_hash"]:
                # 第一步：收集所有文件的大小和路径信息
                file_size_map = {}  # 文件大小 -> [行索引列表]
                file_path_map = {}  # 行索引 -> (路径, 大小)

                for row in range(rows):
                    old_path = self.snapshot_old_paths[row]
                    
                    self.tool_instance.file_grid.queue_cell_value(row, self.tool_instance.file_grid.COL_RESULT, "")
                    
                    if not old_path:
                        # 只有"应用"按钮才修改新路径列，此处不清空新路径
                        self.tool_instance.file_grid.queue_cell_value(row, self.tool_instance.file_grid.COL_MATCH_NAME, "")
                        self.tool_instance.file_grid.queue_cell_value(row, self.tool_instance.file_grid.COL_RESULT, "")
                        continue
                    
                    # 判断该单元格里的值是否是合法的路径
                    if not self.tool_instance.is_valid_path(old_path):
                        # 清空该行除"旧路径"外的其他单元格
                        self.tool_instance.file_grid.queue_cell_value(row, 2, "")
                        self.tool_instance.file_grid.queue_cell_value(row, 3, "")
                        # 在该行"执行结果"列里填入字串"[Invalid Path]"（i18n 标记）
                        self.tool_instance.file_grid.queue_cell_value(row, 3, translate("result_invalid_path"))
                        continue

                    # 判断该单元格里的路径是否存在
                    if not os.path.exists(old_path):
                        # 清空该行除"旧路径"外的其他单元格
                        self.tool_instance.file_grid.queue_cell_value(row, 2, "")
                        self.tool_instance.file_grid.queue_cell_value(row, 3, "")
                        # 在该行"执行结果"列里填入字串"[Nonexistent Path]"（i18n 标记）
                        self.tool_instance.file_grid.queue_cell_value(row, 3, translate("result_nonexistent_path"))
                        continue

                    # 判断该单元格里的路径是否是目录
                    if os.path.isdir(old_path):
                        # 在该行"执行结果"列里填入字串"[Not File]"（i18n 标记）
                        self.tool_instance.file_grid.queue_cell_value(row, 3, translate("result_not_file"))
                        continue

                    # 判断该单元格里的路径指向的文件是否有读权限
                    if not os.access(old_path, os.R_OK):
                        # 在该行"执行结果"列里填入字串"[No Permission]"（i18n 标记）
                        self.tool_instance.file_grid.queue_cell_value(row, 3, translate("result_no_permission"))
                        continue
                    
                    # 获取文件大小
                    try:
                        file_size = os.path.getsize(old_path)
                        file_path_map[row] = (old_path, file_size)
                        
                        if file_size not in file_size_map:
                            file_size_map[file_size] = []
                        file_size_map[file_size].append(row)
                    except Exception as e:
                        self.tool_instance.file_grid.queue_cell_value(row, 3, translate("result_error", error=str(e)))
                        continue
                
                # 第二步：根据选择的算法计算文件ID
                current_algorithm = self.algorithm
                
                if current_algorithm in ["file_fingerprint", "file_hash"]:
                    # 文件指纹法或哈希法：先按文件大小分组，然后对相同大小的文件计算指纹或哈希
                    hash_total = sum(len(row_list) for row_list in file_size_map.values() if len(row_list) > 1)
                    hash_current = 0
                    self.hash_progress_info = (0, hash_total)
                    for file_size, row_list in file_size_map.items():
                        if len(row_list) == 1:
                            row = row_list[0]
                            old_path = file_path_map[row][0]
                            file_id = f"unique_{old_path}"
                            duplicate_files[file_id] = {row}
                        else:
                            # 文件大小有重复，需要计算指纹或哈希
                            for row in row_list:
                                if self._stop_flag.is_set(): break
                                old_path = file_path_map[row][0]
                                hash_current += 1
                                self.hash_progress_info = (hash_current, hash_total)
                                try:
                                    if current_algorithm == "file_fingerprint":
                                        file_size = os.path.getsize(old_path)
                                        with open(old_path, 'rb') as f:
                                            header = f.read(min(1024, file_size))
                                            if file_size > 1024:
                                                f.seek(-min(1024, file_size - 1024), os.SEEK_END)
                                                footer = f.read(1024)
                                                file_id = f"{file_size}_{header.hex()}_{footer.hex()}"
                                            else:
                                                file_id = f"{file_size}_{header.hex()}"
                                    elif current_algorithm == "file_hash":
                                        file_size = os.path.getsize(old_path)
                                        md5_hash = hashlib.md5()
                                        with open(old_path, 'rb') as f:
                                            header = f.read(min(1024, file_size))
                                            md5_hash.update(header)
                                            if file_size > 1024:
                                                remaining = file_size - 1024
                                                footer_size = min(1024, remaining)
                                                body_size = remaining - footer_size
                                                chunk_size = 65536
                                                bytes_read = 0
                                                while bytes_read < body_size:
                                                    read_now = min(chunk_size, body_size - bytes_read)
                                                    chunk = f.read(read_now)
                                                    if not chunk:
                                                        break
                                                    md5_hash.update(chunk)
                                                    bytes_read += len(chunk)
                                                footer = f.read(footer_size)
                                                md5_hash.update(footer)
                                            file_id = f"{md5_hash.hexdigest()}_{header.hex()}"
                                    
                                    if file_id not in duplicate_files:
                                        duplicate_files[file_id] = set()
                                    duplicate_files[file_id].add(row)
                                except Exception as e:
                                    self.tool_instance.file_grid.queue_cell_value(row, 3, translate("result_error", error=str(e)))
                                    continue
            else:
                for row in range(rows):
                    old_path = self.snapshot_old_paths[row]

                    self.tool_instance.file_grid.queue_cell_value(row, self.tool_instance.file_grid.COL_RESULT, "")
                    
                    if not old_path:
                        # 只有"应用"按钮才修改新路径列，此处不清空新路径
                        self.tool_instance.file_grid.queue_cell_value(row, self.tool_instance.file_grid.COL_MATCH_NAME, "")
                        self.tool_instance.file_grid.queue_cell_value(row, self.tool_instance.file_grid.COL_RESULT, "")
                        continue
                    
                    if not self.tool_instance.is_valid_path(old_path):
                        self.tool_instance.file_grid.queue_cell_value(row, self.tool_instance.file_grid.COL_MATCH_NAME, "")
                        self.tool_instance.file_grid.queue_cell_value(row, self.tool_instance.file_grid.COL_RESULT, "")
                        self.tool_instance.file_grid.queue_cell_value(row, self.tool_instance.file_grid.COL_RESULT, translate("result_invalid_path"))
                        continue
                    
                    if not os.path.exists(old_path):
                        self.tool_instance.file_grid.queue_cell_value(row, self.tool_instance.file_grid.COL_MATCH_NAME, "")
                        self.tool_instance.file_grid.queue_cell_value(row, self.tool_instance.file_grid.COL_RESULT, "")
                        self.tool_instance.file_grid.queue_cell_value(row, self.tool_instance.file_grid.COL_RESULT, translate("result_nonexistent_path"))
                        continue
                    
                    if os.path.isdir(old_path):
                        self.tool_instance.file_grid.queue_cell_value(row, self.tool_instance.file_grid.COL_RESULT, translate("result_not_file"))
                        continue
                    
                    if not os.access(old_path, os.R_OK):
                        self.tool_instance.file_grid.queue_cell_value(row, self.tool_instance.file_grid.COL_RESULT, translate("result_no_permission"))
                        continue
                    
                    # 读取"旧路径"里的文件，并按选择的算法计算ID
                    try:
                        # 计算文件ID
                        current_algorithm = self.algorithm
                        if current_algorithm == "filename":
                            # 按文件名计算ID
                            file_id = os.path.basename(old_path)
                        elif current_algorithm == "filename_size":
                            # 按文件名+大小计算ID
                            file_size = os.path.getsize(old_path)
                            file_id = f"{os.path.basename(old_path)}_{file_size}"
                        else:
                            # 默认按文件名
                            file_id = os.path.basename(old_path)
                        
                        # 将计算出来的结果字串作为ID添加到字典
                        if file_id not in duplicate_files:
                            duplicate_files[file_id] = set()
                        duplicate_files[file_id].add(row)
                        
                    except Exception as e:
                        # 处理错误
                        self.tool_instance.file_grid.queue_cell_value(row, 3, translate("result_error", error=str(e)))
                        continue
            
            # 遍历完所有行后，处理重复文件：遍历"重复文件ID到重复文件路径Set集合的字典"里的所有键
            # 待删除行在此阶段以本地列表记录，供 EXECUTE 直接使用；
            # 不能依赖 wx.CallAfter 异步写入 Grid 的 [WILL DELETE] 文本（存在竞态）。
            rows_to_delete = []
            for file_id, row_set in duplicate_files.items():
                # 对每个键遍历Set类型值里的每个行号
                if len(row_set) <= 1:
                    # 只有一个文件，标记为无重复
                    for row in row_set:
                        self.tool_instance.file_grid.queue_cell_value(row, 3, translate("result_no_duplicate"))
                    continue
                
                # 有多个重复文件，增加重复文件组数
                duplicate_groups += 1
                
                # 收集文件信息
                file_info = []
                stat_failed_reason = None
                for row in row_set:
                    path = self.snapshot_old_paths[row]
                    try:
                        # 获取文件属性
                        stat = os.stat(path)
                        file_info.append({
                            'row': row,
                            'path': path,
                            'ctime': stat.st_ctime,
                            'mtime': stat.st_mtime,
                            'filename': os.path.basename(path),
                            'path_length': len(path),
                            'filename_length': len(os.path.basename(path))
                        })
                    except Exception as e:
                        # 元数据读不到时无法按规则安全判定保留项：
                        # 该组重复文件整组不删除任何文件，仅在结果列写入警告原因
                        log_error(f"获取文件状态失败 {path}: {e}")
                        stat_failed_reason = str(e)
                        break

                if stat_failed_reason is not None:
                    for info_row in row_set:
                        self.tool_instance.file_grid.queue_cell_value(info_row, 3,
                                     translate("duplicate_stat_failed", error=stat_failed_reason))
                    continue
                
                # 应用去重规则，选择要保留的文件
                current_rule = self.rule
                if current_rule == "keep_create_time_latest":
                    # 按创建时间降序排序，时间相同则按文件名降序，再相同则按路径长度降序，最后按路径降序
                    # 使用reverse=True实现降序
                    file_info.sort(key=lambda x: (x['ctime'], x['filename'], x['path_length'], x['path']), reverse=True)
                elif current_rule == "keep_create_time_earliest":
                    # 按创建时间升序排序，时间相同则按文件名升序，再相同则按路径长度升序，最后按路径升序
                    file_info.sort(key=lambda x: (x['ctime'], x['filename'], x['path_length'], x['path']))
                elif current_rule == "keep_modify_time_latest":
                    # 按修改时间降序排序，时间相同则按文件名降序，再相同则按路径长度降序，最后按路径降序
                    file_info.sort(key=lambda x: (x['mtime'], x['filename'], x['path_length'], x['path']), reverse=True)
                elif current_rule == "keep_modify_time_earliest":
                    # 按修改时间升序排序，时间相同则按文件名升序，再相同则按路径长度升序，最后按路径升序
                    file_info.sort(key=lambda x: (x['mtime'], x['filename'], x['path_length'], x['path']))
                elif current_rule == "keep_filename_longest":
                    # 按文件名长度降序排序，长度相同则按文件名降序，再相同则按路径长度降序，最后按路径降序
                    file_info.sort(key=lambda x: (x['filename_length'], x['filename'], x['path_length'], x['path']), reverse=True)
                elif current_rule == "keep_filename_shortest":
                    # 按文件名长度升序排序，长度相同则按文件名升序，再相同则按路径长度升序，最后按路径升序
                    file_info.sort(key=lambda x: (x['filename_length'], x['filename'], x['path_length'], x['path']))
                elif current_rule == "keep_path_longest":
                    # 按路径长度降序排序，长度相同则按路径降序
                    file_info.sort(key=lambda x: (x['path_length'], x['path']), reverse=True)
                elif current_rule == "keep_path_shortest":
                    # 按路径长度升序排序，长度相同则按路径升序
                    file_info.sort(key=lambda x: (x['path_length'], x['path']))
                
                # 第一个文件是要保留的
                keep_row = file_info[0]['row']
                
                # 处理每个文件
                for info in file_info:
                    row = info['row']
                    if row == keep_row:
                        # 保留该文件；执行模式的最终结果不能停留在预览态"[将保留]"
                        retain_key = "result_retained" if self.worker_mode == WorkerMode.EXECUTE else "result_will_retain"
                        self.tool_instance.file_grid.queue_cell_value(row, 3, translate(retain_key))
                    else:
                        # 删除该文件
                        self.tool_instance.file_grid.queue_cell_value(row, 3, translate("result_will_delete"))
                        files_to_delete += 1
                        rows_to_delete.append((row, info['path']))
            
            # 更新进度信息
            self.progress_info = (rows, rows, duplicate_groups, files_to_delete, 0)
            
            # 更新最底部左侧的状态栏
            wx.CallAfter(self.tool_instance.status_bar.SetStatusText, translate("worker_status_duplicate_found", groups=duplicate_groups, files=files_to_delete), 0)
            
            # 强制刷新表格
            wx.CallAfter(self.tool_instance.file_grid.ForceRefresh)
            wx.CallAfter(self.tool_instance.file_grid.Update)
            
            # 如果需要执行删除操作
            if self.worker_mode != WorkerMode.APPLY:
                deleted_count = 0
                # 操作级撤销/重做：获取当前操作条目和备份目录
                op_entry = getattr(self.tool_instance, '_current_op_entry', None)
                op_history_mgr = getattr(self.tool_instance, '_op_history_manager', None)
                backup_dir = None
                if op_entry is not None and op_history_mgr is not None:
                    backup_dir = op_history_mgr.ensure_backup_dir(op_entry)
                backup_idx = 0
                for row, old_path in rows_to_delete:
                    if self._stop_flag.is_set(): break

                    match_name = self.snapshot_match_names[row]

                    if old_path in self.delete_result_dict:
                        result_text, was_success = self.delete_result_dict[old_path]
                        self.tool_instance.file_grid.queue_cell_value(row, self.tool_instance.file_grid.COL_RESULT, result_text)
                        if was_success:
                            deleted_count += 1
                        self.progress_info = (rows, rows, duplicate_groups, files_to_delete, deleted_count)
                        continue
                    
                    if not os.path.exists(old_path):
                        result_text = translate("success_file_not_exist")
                        self.tool_instance.file_grid.queue_cell_value(row, 3, result_text)
                        self.delete_result_dict[old_path] = (result_text, True)
                        deleted_count += 1
                        if self.worker_mode == WorkerMode.EXECUTE:
                            log_file_operation(translate("tab_duplicate"), old_path, "", match_name,
                                               skipped=True, row_index=row)
                        self.progress_info = (rows, rows, duplicate_groups, files_to_delete, deleted_count)
                        continue
                    
                    if self.worker_mode == WorkerMode.PREVIEW:
                        result_text = translate("duplicate_will_be_deleted")
                        self.tool_instance.file_grid.queue_cell_value(row, 3, result_text)
                        self.delete_result_dict[old_path] = (result_text, False)
                        self.progress_info = (rows, rows, duplicate_groups, files_to_delete, deleted_count)
                    else:
                        try:
                            # 操作级撤销/重做：删除前备份文件
                            path_backup = None
                            if backup_dir:
                                path_backup, _ = backup_file_or_dir(old_path, backup_dir, "deleted_files", backup_idx)
                                backup_idx += 1
                            result = delete_to_recycle(old_path)
                            if result == 0:
                                result_text = translate("success_deleted_to_recycle_bin")
                                self.delete_result_dict[old_path] = (result_text, True)
                                deleted_count += 1
                                log_file_operation(translate("tab_duplicate"), old_path, "", match_name,
                                                   success=True, row_index=row)
                                # 操作级撤销/重做：记录 delete_to_recycle 操作
                                if op_history_mgr and op_entry:
                                    op_history_mgr.append_file_op(op_entry, {
                                        "op": "delete_to_recycle",
                                        "path": old_path,
                                        "path_backup": path_backup,
                                        "success": True,
                                        "error": None,
                                    })
                            else:
                                result_text = translate("failure_cannot_delete_to_recycle_bin", error_code=result)
                                self.delete_result_dict[old_path] = (result_text, False)
                                log_file_operation(translate("tab_duplicate"), old_path, "", match_name,
                                                   success=False, error=f"recycle error_code={result}", row_index=row)
                            
                            self.tool_instance.file_grid.queue_cell_value(row, 3, result_text)
                            self.progress_info = (rows, rows, duplicate_groups, files_to_delete, deleted_count)
                            
                        except PermissionError:
                            result_text = translate("failure_cannot_delete_permission")
                            self.tool_instance.file_grid.queue_cell_value(row, 3, result_text)
                            self.delete_result_dict[old_path] = (result_text, False)
                            log_file_operation(translate("tab_duplicate"), old_path, "", match_name,
                                               success=False, error="permission error", row_index=row)
                            self.progress_info = (rows, rows, duplicate_groups, files_to_delete, deleted_count)
                        except Exception as e:
                            result_text = translate("failure_cannot_delete_with_error", error=str(e))
                            self.tool_instance.file_grid.queue_cell_value(row, 3, result_text)
                            self.delete_result_dict[old_path] = (result_text, False)
                            log_file_operation(translate("tab_duplicate"), old_path, "", match_name,
                                               success=False, error=e, row_index=row)
                            self.progress_info = (rows, rows, duplicate_groups, files_to_delete, deleted_count)
                
                # 最终更新进度信息
                self.progress_info = (rows, rows, duplicate_groups, files_to_delete, deleted_count)
                self.deleted_count = deleted_count
                
                # 更新状态栏
                wx.CallAfter(self.tool_instance.status_bar.SetStatusText, translate("worker_status_duplicate_completed", groups=duplicate_groups, deleted=deleted_count), 0)
            
            log_info(f"[DuplicateWorker] 执行完成, 重复组: {duplicate_groups}, 已删除: {deleted_count}")
        except Exception as e:
            log_error(f"[DuplicateWorker] 去重操作错误: {e}")

    def stop(self):
        self._stop_flag.set()

    def is_stopped(self):
        return self._stop_flag.is_set()

    def get_progress_info(self):
        return self.progress_info

    def get_hash_progress_info(self):
        return self.hash_progress_info
