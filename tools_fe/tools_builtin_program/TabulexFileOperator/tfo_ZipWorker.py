# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
import os
import threading
import zipfile
from tfo_utils.tfo_i18n_manager import translate, i18n
from tfo_utils.tfo_file_utils import format_file_size, MAX_FILE_SIZE, MAX_ZIP_SIZE, backup_file_or_dir
from tfo_utils.tfo_logger import log_error, log_info, log_warning, log_file_operation
from tfo_utils.tfo_worker_mode import WorkerMode

"""压缩工作线程"""
class tfo_ZipWorker(threading.Thread):
    def __init__(self, tool_instance, use_old_path, use_match_name, 
                 save_dir, file_conflict_method="overwrite", dir_conflict_method="replace", execute_zip=True, preview_mode=False, worker_mode=None):
        super().__init__()
        self.tool_instance = tool_instance
        self.use_old_path = use_old_path
        self.use_match_name = use_match_name
        self.save_dir = save_dir
        self.file_conflict_method = file_conflict_method
        self.dir_conflict_method = dir_conflict_method
        if worker_mode is not None:
            self.worker_mode = worker_mode
        else:
            if not execute_zip:
                self.worker_mode = WorkerMode.APPLY
            elif preview_mode:
                self.worker_mode = WorkerMode.PREVIEW
            else:
                self.worker_mode = WorkerMode.EXECUTE
        # 是否真正执行压缩：以 worker_mode 为准（供状态栏区分 APPLY/PREVIEW/EXECUTE），
        # 避免 APPLY 模式下因属性缺失被 getattr 默认值误判为执行模式
        self.execute_zip = (self.worker_mode == WorkerMode.EXECUTE)
        self._stop_flag = threading.Event()
        self.progress_info = (0, 0, 0, 0)
        self.created_zips = 0
        self.total_zips = 0
        # __init__ 在 UI 线程执行：在此快照行数据、列数与搜索目录输入框，Worker 线程内不再跨线程读取 Grid/控件
        grid = tool_instance.file_grid
        self.snapshot_rows_total = grid.GetNumberRows()
        self.snapshot_cols_total = grid.GetNumberCols()
        self.snapshot_old_paths = [grid.GetCellValue(r, grid.COL_OLD_PATH).strip() for r in range(self.snapshot_rows_total)]
        self.snapshot_new_paths = [grid.GetCellValue(r, grid.COL_NEW_PATH).strip() for r in range(self.snapshot_rows_total)]
        self.snapshot_match_names = [grid.GetCellValue(r, grid.COL_MATCH_NAME).strip() for r in range(self.snapshot_rows_total)]
        self.snapshot_search_path = tool_instance.input_search_path01.GetValue().strip()
    
    def _build_zip_structure(self, grouped_paths, actual_save_dir):
        """构建ZIP文件结构字典

        返回: {zip_path -> {"arcname_dict": {arcname -> [full_paths]}, "items": [item, ...]}}

        EXECUTE 模式下每个 item 携带用户填写的目标压缩包路径 "dest_zip"（"新路径"列），
        zip 按该路径落盘；未携带（APPLY/PREVIEW）时按分组名在 actual_save_dir 下计算。
        """
        zip_structure = {}  # zip_path -> {"arcname_dict": ..., "items": [...]}
        
        for group_name, path_list in grouped_paths.items():
            if self._stop_flag.is_set():
                break
            
            for item in path_list:
                actual_path = item["actual_path"]
                is_dir = item["is_dir"]
                dest_zip = item.get("dest_zip")
                if dest_zip:
                    zip_path = dest_zip
                else:
                    zip_path = os.path.join(actual_save_dir, f"{group_name}.zip")
                
                if zip_path not in zip_structure:
                    zip_structure[zip_path] = {"arcname_dict": {}, "items": []}
                zip_entry = zip_structure[zip_path]
                if item not in zip_entry["items"]:
                    zip_entry["items"].append(item)
                arcname_dict = zip_entry["arcname_dict"]
                
                if is_dir:
                    # 处理目录
                    for root, dirs, files in os.walk(actual_path, onerror=lambda e: None):
                        for file in files:
                            loop_file_path = os.path.join(root, file)
                            
                            # 计算在ZIP中的相对路径
                            if self.use_match_name:
                                # 按匹配名分组：group_name/实际目录basename/相对路径
                                actual_dir_name = os.path.basename(actual_path)
                                rel_path = os.path.relpath(loop_file_path, actual_path)
                                arcname = os.path.join(group_name, actual_dir_name, rel_path)
                            else:
                                # 按目录名分组：group_name/相对路径
                                rel_path = os.path.relpath(loop_file_path, actual_path)
                                arcname = os.path.join(group_name, rel_path)
                            
                            # 添加文件路径到列表（不区分冲突处理方式）
                            if arcname not in arcname_dict:
                                arcname_dict[arcname] = []
                            
                            # 将所有文件路径都添加到列表中
                            arcname_dict[arcname].append(loop_file_path)
                else:
                    # 处理文件
                    if self.use_match_name:
                        # 按匹配名分组：group_name/文件名
                        arcname = os.path.join(group_name, os.path.basename(actual_path))
                    else:
                        # 按目录名分组：group_name/文件名
                        arcname = os.path.join(group_name, os.path.basename(actual_path))
                    
                    if arcname not in arcname_dict:
                        arcname_dict[arcname] = []
                    
                    # 将所有文件路径都添加到列表中
                    arcname_dict[arcname].append(actual_path)
        
        return zip_structure

    def run(self):
        log_info(f"[ZipWorker] 开始执行, 模式: {self.worker_mode.name}, 保存目录: {self.save_dir}")
        try:
            # 第一步：计算压缩文件默认存储路径 - 使用与on_apply_zip_group()相同的逻辑
            # 如果调用方提供了目标路径（非空），则直接使用该路径
            provided_save_dir = (self.save_dir or "").strip()
            if provided_save_dir:
                actual_save_dir = provided_save_dir
                # 仅在真正执行压缩（EXECUTE）时创建目标目录；Apply/Preview 只计算路径不写文件
                if self.worker_mode == WorkerMode.EXECUTE:
                    try:
                        os.makedirs(actual_save_dir, exist_ok=True)
                    except OSError as e:
                        log_error(f"[ZipWorker] 创建目标目录失败 {actual_save_dir}: {e}")
                        # 创建失败时回退到自动计算路径
                        actual_save_dir = None
                        provided_save_dir = ""
            else:
                actual_save_dir = None

            # 未提供目标路径时，自动计算默认存储路径
            default_zip_path = None
            
            # 检查Tab01里的搜索目录路径（来自 UI 线程快照）
            search_path_val = self.snapshot_search_path
            if search_path_val and os.path.exists(search_path_val):
                # 获取搜索目录的父路径
                parent_path = os.path.dirname(search_path_val)
                if not parent_path or parent_path == search_path_val:
                    # 没有父路径（如分区根路径），取自身
                    default_zip_path = search_path_val
                else:
                    default_zip_path = parent_path
            else:
                # 遍历表格里的"旧路径"列，按分区分组
                partition_paths = {}
                all_paths = []
                
                for row in range(self.snapshot_rows_total):
                    old_path = self.snapshot_old_paths[row]
                    if old_path:
                        all_paths.append(old_path)
                        # 获取分区名称
                        if os.name == 'nt':
                            # Windows系统，获取盘符
                            if len(old_path) >= 2 and old_path[1] == ':':
                                partition = old_path[:2].upper()
                                if partition not in partition_paths:
                                    partition_paths[partition] = []
                                partition_paths[partition].append(old_path)
                        else:
                            # 非Windows系统，使用根目录
                            partition = '/'
                            if partition not in partition_paths:
                                partition_paths[partition] = []
                            partition_paths[partition].append(old_path)
                
                if all_paths:
                    # 找到数量最多的分区组
                    max_count = 0
                    max_partition_paths = []
                    for partition, paths in partition_paths.items():
                        if len(paths) > max_count:
                            max_count = len(paths)
                            max_partition_paths = paths
                        elif len(paths) == max_count and not max_partition_paths:
                            max_partition_paths = paths
                    
                    if max_partition_paths:
                        # 计算公共父路径：先取每个路径的所在目录再求公共路径，
                        # 避免单个文件路径被 commonpath 直接当成目录返回
                        # （否则会生成 "<文件>/<目录名>.zip" 的非法路径）
                        parent_dirs = [os.path.dirname(p) or p for p in max_partition_paths]
                        try:
                            common_path = os.path.commonpath(parent_dirs)
                        except Exception:
                            common_path = None
                        
                        if not common_path:
                            # 没有公共父路径，使用第一个路径的所在目录
                            common_path = parent_dirs[0]
                        default_zip_path = common_path
            
            # 使用计算出的默认路径，如果为空则使用当前目录
            # 若调用方已提供目标路径，则保持该路径不变（不覆盖）
            if not provided_save_dir:
                if default_zip_path:
                    actual_save_dir = default_zip_path
                else:
                    actual_save_dir = os.getcwd()
            
            self.save_dir = actual_save_dir
            
            # 构建分组字典 - 使用与on_apply_zip_group()相同的逻辑
            grouped_paths = {}  # 匹配名称 -> [项目列表]
            rows_total = self.snapshot_rows_total
            # PREVIEW/EXECUTE：先清空整个"执行结果"列，避免残留上一次操作的结果；
            # APPLY：不修改 Result（仅对 New Path 变化的行清空，见 13.0 / 6.1）
            if self.worker_mode != WorkerMode.APPLY:
                for _clear_row in range(rows_total):
                    self.tool_instance.file_grid.queue_cell_value(_clear_row, self.tool_instance.file_grid.COL_RESULT, "")
            
            # 第一步：构建分组字典
            for row_idx in range(rows_total):
                if self._stop_flag.is_set(): break
                # 根据路径选择确定主路径（来自 UI 线程快照）
                if self.use_old_path:
                    primary_path = self.snapshot_old_paths[row_idx]
                else:
                    primary_path = self.snapshot_new_paths[row_idx]

                # 主路径为空：不做任何修改（不自动 Apply、不清空其它列）
                if not primary_path:
                    continue
                
                # 检查路径是否合法
                primary_valid = primary_path and self.tool_instance.is_valid_path(primary_path)
                if not (primary_path and primary_valid):
                    if self.worker_mode != WorkerMode.APPLY:
                        self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, translate("failure_path_invalid"))
                    continue
                
                # 检查路径是否存在
                primary_exists = primary_valid and os.path.exists(primary_path)
                if not primary_exists:
                    if self.worker_mode != WorkerMode.APPLY:
                        if self.use_old_path:
                            self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, translate("failure_old_path_not_exist"))
                        else:
                            self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, translate("failure_new_path_not_exist"))
                    continue

                # 确定实际使用的路径
                actual_path = primary_path
                
                if os.path.isfile(actual_path):
                    try:
                        file_size = os.path.getsize(actual_path)
                        if file_size > MAX_FILE_SIZE:
                            size_str = format_file_size(file_size)
                            if self.worker_mode != WorkerMode.APPLY:
                                self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, translate("warning_file_too_large", size=size_str))
                            continue
                    except OSError:
                        pass
                
                match_name = self.snapshot_match_names[row_idx]
                if self.use_match_name:
                    if match_name:
                        zip_filename = match_name
                    else:
                        # 匹配名为空，按父目录名分组
                        if os.path.isdir(actual_path):
                            zip_filename = os.path.basename(actual_path)
                        else:
                            zip_filename = os.path.basename(os.path.dirname(actual_path))
                else:
                    # 按父目录名分组
                    if os.path.isdir(actual_path):
                        zip_filename = os.path.basename(actual_path)
                    else:
                        zip_filename = os.path.basename(os.path.dirname(actual_path))
                
                # 剔除文件名非法字符 - 使用与on_apply_zip_group()相同的逻辑
                if os.name == 'nt':
                    illegal_chars = r'<>"|:*?'
                else:
                    illegal_chars = ''
                
                for char in illegal_chars:
                    zip_filename = zip_filename.replace(char, '')
                
                # 确保文件名不为空
                if not zip_filename:
                    zip_filename = "default"
                
                # 目标压缩包路径（见 Note 13.0 / 6.2）：
                # - APPLY：按分组自动计算并写入"新路径"列（Apply 是唯一可写 New Path 的按钮）
                # - PREVIEW/EXECUTE：只使用用户已填写的非空"新路径"；为空视为未设置，
                #   写提示到 Result 并跳过本行（绝不自动计算/回写 New Path）
                user_dest = self.snapshot_new_paths[row_idx]
                if self.worker_mode == WorkerMode.APPLY:
                    dest_zip = os.path.join(actual_save_dir, f"{zip_filename}.zip")
                    auto_fill = True
                elif user_dest:
                    dest_zip = user_dest
                    auto_fill = False
                else:
                    self.tool_instance.file_grid.queue_cell_value(
                                 row_idx, self.tool_instance.file_grid.COL_RESULT,
                                 translate("warning_new_path_not_set"))
                    continue
                
                # 添加到分组字典
                if zip_filename not in grouped_paths:
                    grouped_paths[zip_filename] = []
                
                grouped_paths[zip_filename].append({
                    "row_idx": row_idx,
                    "actual_path": actual_path,
                    "is_dir": os.path.isdir(actual_path),
                    "dest_zip": dest_zip,
                    "auto_fill": auto_fill,
                    "match_name": match_name,
                })
            
            # 第二步：统计总行数（用于进度显示）
            total_rows = sum(len(path_list) for path_list in grouped_paths.values())
            finished_rows = 0
            ok_rows = 0
            
            # 第三步：初始化ZIP统计
            self.total_zips = len(grouped_paths)  # 总的匹配名数量
            self.created_zips = 0  # 实际创建（更新）的ZIP文件数量
            
            # 第四步：对每个分组进行处理
            if self.worker_mode == WorkerMode.APPLY:
                # 只计算路径，不执行压缩（用于"应用压缩分组"）
                for group_name, path_list in grouped_paths.items():
                    if self._stop_flag.is_set(): break
                    
                    # 如果没有需要压缩的路径，跳过
                    if not path_list:
                        continue
                    
                    # 创建ZIP文件路径
                    zip_filename = f"{group_name}.zip"
                    zip_path = os.path.join(actual_save_dir, zip_filename)
                    
                    # APPLY 模式：仅按分组规则把计算出的 ZIP 路径写入"新路径"列，不执行压缩；
                    # New Path 变化的行清空该行 Result（13.0 / 6.1），未变化的行 Result 保持不动
                    for item in path_list:
                        row_idx = item["row_idx"]
                        new_val = f"{zip_path}"
                        old_val = (self.snapshot_new_paths[row_idx] or "").strip()
                        self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_NEW_PATH, new_val)
                        if old_val != new_val.strip():
                            self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, "")
                        ok_rows += 1
                        finished_rows += 1
                    
                    # 更新进度
                    self.progress_info = (finished_rows, total_rows, ok_rows)
            else:
                # 执行压缩（用于"执行压缩"）
                
                # 构建ZIP结构字典（预预览和执行模式都需要）
                zip_structure = self._build_zip_structure(grouped_paths, actual_save_dir)

                # 操作级撤销/重做：获取当前操作条目和备份目录
                op_entry = getattr(self.tool_instance, '_current_op_entry', None)
                op_history_mgr = getattr(self.tool_instance, '_op_history_manager', None)
                backup_dir = None
                if op_entry is not None and op_history_mgr is not None:
                    backup_dir = op_history_mgr.ensure_backup_dir(op_entry)
                backup_idx = 0

                for zip_path, zip_data in zip_structure.items():
                    if self._stop_flag.is_set(): break
                    
                    arcname_dict = zip_data["arcname_dict"]
                    items = zip_data["items"]
                    if not items:
                        continue
                    
                    # 检查ZIP文件是否已存在
                    zip_exists = os.path.exists(zip_path)

                    def _log_zip_items(success=True, skipped=False, error=None):
                        """记录本组每个源行的执行结果（旧路径/目标ZIP/匹配名）"""
                        for it in items:
                            log_file_operation(translate("tab_zip"), it.get("actual_path", ""), zip_path,
                                               it.get("match_name", ""), success=success, skipped=skipped,
                                               error=error, row_index=it.get("row_idx"))
                    
                    if self.worker_mode == WorkerMode.PREVIEW:
                        # 预览：不修改 New Path；仅对已填非空"新路径"的行，按目标ZIP是否已存在
                        # 及目录冲突策略把预测结果写入"执行结果"列（空新路径行已在分组阶段跳过）
                        if not zip_exists:
                            result_text = translate("correct_will_add_to_zip")
                        elif self.dir_conflict_method == "skip":
                            result_text = translate("warning_will_be_skipped")
                        elif self.dir_conflict_method == "merge":
                            result_text = translate("warning_will_be_merged")
                        else:
                            result_text = translate("warning_will_be_replaced")
                        # 直接遍历该项对应的所有行（文件或目录）
                        for item in items:
                            row_idx = item["row_idx"]
                            self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, result_text)
                            ok_rows += 1
                            finished_rows += 1
                        self.progress_info = (finished_rows, total_rows, ok_rows)
                    else:
                        # EXECUTE：确保目标ZIP所在目录存在（用户可能手动填写了非标准目录的"新路径"）
                        # 创建失败时不中断整批：跳过本组并在结果列写原因
                        zip_parent = os.path.dirname(zip_path)
                        if zip_parent and not os.path.exists(zip_parent):
                            try:
                                os.makedirs(zip_parent, exist_ok=True)
                            except OSError as e:
                                log_error(f"[ZipWorker] 创建ZIP目标目录失败 {zip_parent}: {e}")
                                for item in items:
                                    row_idx = item["row_idx"]
                                    self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, translate("zip_parent_create_failed", error=str(e)))
                                    finished_rows += 1
                                _log_zip_items(success=False, error=str(e))
                                self.progress_info = (finished_rows, total_rows, ok_rows)
                                continue
                        zip_backup = None
                        if zip_exists:
                            if self.dir_conflict_method == "skip":
                                for item in items:
                                    row_idx = item["row_idx"]
                                    # 执行模式：最终结果写"已跳过"而非预览态的"将被跳过"
                                    self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, translate("warning_skipped"))
                                    finished_rows += 1
                                _log_zip_items(skipped=True)
                                self.progress_info = (finished_rows, total_rows, ok_rows)
                                continue
                            elif self.dir_conflict_method == "merge":
                                # 操作级撤销/重做：备份已存在的ZIP（合并模式会修改ZIP内容）
                                if backup_dir and zip_exists:
                                    zip_backup, _ = backup_file_or_dir(zip_path, backup_dir, "file_conflicts", backup_idx)
                                    backup_idx += 1
                                    if zip_backup is None:
                                        # 备份失败则中止本组（避免无可撤销备份仍就地修改旧ZIP），与 A2-1/A2-2 同策略
                                        for item in items:
                                            row_idx = item["row_idx"]
                                            self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, translate("zip_backup_failed"))
                                            finished_rows += 1
                                        _log_zip_items(success=False, error="ZIP backup failed")
                                        self.progress_info = (finished_rows, total_rows, ok_rows)
                                        continue
                                try:
                                    with zipfile.ZipFile(zip_path, 'a', zipfile.ZIP_DEFLATED) as zipf:
                                        existing_names = set(zipf.namelist())
                                        added_count = 0
                                        size_exceeded = False
                                        for arcname, full_paths in arcname_dict.items():
                                            if self._stop_flag.is_set(): break
                                            if size_exceeded: break
                                            if arcname in existing_names:
                                                continue
                                            if self.file_conflict_method == "skip":
                                                if full_paths:
                                                    zipf.write(full_paths[0], arcname)
                                                    added_count += 1
                                            elif self.file_conflict_method == "overwrite":
                                                if full_paths:
                                                    zipf.write(full_paths[-1], arcname)
                                                    added_count += 1
                                            if os.path.exists(zip_path):
                                                current_zip_size = os.path.getsize(zip_path)
                                                if current_zip_size > MAX_ZIP_SIZE:
                                                    size_exceeded = True
                                        if size_exceeded:
                                            for item in items:
                                                row_idx = item["row_idx"]
                                                self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, translate("warning_zip_size_exceeded", size=format_file_size(MAX_ZIP_SIZE)))
                                                finished_rows += 1
                                            _log_zip_items(success=False, error="ZIP size exceeded")
                                            self.progress_info = (finished_rows, total_rows, ok_rows)
                                            continue
                                        if added_count > 0:
                                            self.created_zips += 1
                                        for item in items:
                                            row_idx = item["row_idx"]
                                            self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, translate("success_compressed"))
                                            ok_rows += 1
                                            finished_rows += 1
                                        _log_zip_items(success=True)
                                        self.progress_info = (finished_rows, total_rows, ok_rows)
                                    # 操作级撤销/重做：记录 zip_create 操作（合并模式）
                                    if op_history_mgr and op_entry:
                                        zip_mtime_after = None
                                        try:
                                            zip_mtime_after = os.path.getmtime(zip_path)
                                        except OSError:
                                            pass
                                        op_history_mgr.append_file_op(op_entry, {
                                            "op": "zip_create",
                                            "zip_path": zip_path,
                                            "zip_backup": zip_backup,
                                            "zip_mtime_after": zip_mtime_after,
                                            "success": True,
                                            "error": None,
                                        })
                                    continue
                                except Exception as e:
                                    log_error(f"合并ZIP文件失败 {zip_path}: {e}")
                                    for item in items:
                                        row_idx = item["row_idx"]
                                        self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, translate("zip_failed", error=str(e)))
                                    _log_zip_items(success=False, error=e)
                                    continue
                            elif self.dir_conflict_method == "replace":
                                # 操作级撤销/重做：备份已存在的ZIP（替换模式会删除旧ZIP）
                                if backup_dir and zip_exists:
                                    zip_backup, _ = backup_file_or_dir(zip_path, backup_dir, "file_conflicts", backup_idx)
                                    backup_idx += 1
                                    if zip_backup is None:
                                        # 备份失败则中止本组（避免无可撤销备份仍永久删除旧ZIP），与 A2-1/A2-2 同策略
                                        for item in items:
                                            row_idx = item["row_idx"]
                                            self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, translate("zip_backup_failed"))
                                            finished_rows += 1
                                        _log_zip_items(success=False, error="ZIP backup failed")
                                        self.progress_info = (finished_rows, total_rows, ok_rows)
                                        continue
                                try:
                                    os.remove(zip_path)
                                    zip_exists = False
                                except Exception as e:
                                    error_msg = f"Cannot delete existing zip file: {str(e)}"
                                    print(error_msg)
                                    for item in items:
                                        row_idx = item["row_idx"]
                                        self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, translate("failure_with_error", error=error_msg))
                                        finished_rows += 1
                                    _log_zip_items(success=False, error=error_msg)
                                    self.progress_info = (finished_rows, total_rows, ok_rows)
                                    continue

                        current_file_conflict = self.file_conflict_method
                        try:
                            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                                added_count = 0
                                size_exceeded = False
                                
                                for arcname, full_paths in arcname_dict.items():
                                    if self._stop_flag.is_set(): break
                                    if size_exceeded: break
                                    
                                    if current_file_conflict == "skip":
                                        if full_paths:
                                            zipf.write(full_paths[0], arcname)
                                            added_count += 1
                                    elif current_file_conflict == "overwrite":
                                        if full_paths:
                                            zipf.write(full_paths[-1], arcname)
                                            added_count += 1
                                    
                                    if os.path.exists(zip_path):
                                        current_zip_size = os.path.getsize(zip_path)
                                        if current_zip_size > MAX_ZIP_SIZE:
                                            size_exceeded = True
                                
                                if size_exceeded:
                                    if os.path.exists(zip_path):
                                        try:
                                            os.remove(zip_path)
                                        except Exception:
                                            pass
                                    for item in items:
                                        row_idx = item["row_idx"]
                                        self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, translate("warning_zip_size_exceeded", size=format_file_size(MAX_ZIP_SIZE)))
                                        finished_rows += 1
                                    _log_zip_items(success=False, error="ZIP size exceeded")
                                    self.progress_info = (finished_rows, total_rows, ok_rows)
                                    continue
                                
                                # 检查是否添加了任何内容
                                if added_count == 0:
                                    # 如果没有任何项目被添加，删除ZIP文件
                                    if os.path.exists(zip_path):
                                        try:
                                            os.remove(zip_path)
                                            # 更新所有相关行的结果
                                            for item in items:
                                                row_idx = item["row_idx"]
                                                self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, translate("failure_empty_directory"))
                                                # 空目录时也更新新路径列为压缩文件路径
                                            _log_zip_items(success=False, error="empty directory")
                                            # 空ZIP不计入创建数量
                                            continue
                                        except Exception as e:
                                            log_error(f"删除空ZIP文件失败: {e}")
                                else:
                                    # 成功创建ZIP文件，增加计数
                                    self.created_zips += 1

                                    # 操作级撤销/重做：记录 zip_create 操作
                                    if op_history_mgr and op_entry:
                                        zip_mtime_after = None
                                        try:
                                            zip_mtime_after = os.path.getmtime(zip_path)
                                        except OSError:
                                            pass
                                        op_history_mgr.append_file_op(op_entry, {
                                            "op": "zip_create",
                                            "zip_path": zip_path,
                                            "zip_backup": zip_backup,
                                            "zip_mtime_after": zip_mtime_after,
                                            "success": True,
                                            "error": None,
                                        })

                                    # 更新表格结果
                                    for item in items:
                                        row_idx = item["row_idx"]
                                        # 由于总是先删除已存在的压缩包，所以总是显示"已压缩"
                                        self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, translate("success_compressed"))
                                        
                                        # 压缩成功后，更新新路径列为压缩文件路径
                                        
                                        ok_rows += 1
                                        finished_rows += 1
                                        self.progress_info = (finished_rows, total_rows, ok_rows)
                                    _log_zip_items(success=True)
                        
                        except Exception as e:
                            log_error(f"创建ZIP文件失败 {zip_path}: {e}")
                            # 更新表格结果
                            for item in items:
                                row_idx = item["row_idx"]
                                self.tool_instance.file_grid.queue_cell_value(row_idx, self.tool_instance.file_grid.COL_RESULT, translate("zip_failed", error=str(e)))
                                # 压缩失败时也更新新路径列为压缩文件路径
                            _log_zip_items(success=False, error=e)
            
            # 最终更新进度
            self.progress_info = (finished_rows, total_rows, ok_rows)
            log_info(f"[ZipWorker] 执行完成, 成功: {ok_rows}/{total_rows}")
        except Exception as e:
            log_error(f"[ZipWorker] 压缩操作错误: {e}")

    def stop(self):
        self._stop_flag.set()

    def is_stopped(self):
        return self._stop_flag.is_set()

    def get_progress_info(self):
        """获取进度信息"""
        return self.progress_info
