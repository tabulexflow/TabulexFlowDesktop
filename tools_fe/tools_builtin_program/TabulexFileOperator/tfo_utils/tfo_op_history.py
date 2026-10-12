# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""TabulexFileOperator 操作级撤销/重做管理器

实现"应用/预览/执行"按钮点击后的操作级撤销/重做。
与 Grid 的单元格级撤销/重做（tfo_BaseGrid._undo_stack）完全独立。

核心数据结构:
    _OpUndoEntry: 一个操作级撤销/重做条目
    _OpHistoryManager: 操作历史栈管理器

操作流程:
    1. 按钮处理函数开始时调用 begin_operation() 捕获 before_grid 快照
    2. Worker 执行实际操作，过程中通过 append_file_op() 累积 file_ops_log
       （仅执行类操作）
    3. 操作完成后调用 commit_operation() 捕获 after_grid 快照，推入 undo 栈
    4. 撤销/重做由 undo()/redo() 完成
"""

import os
import time
import shutil
import datetime

import wx

from tfo_utils.tfo_i18n_manager import translate
from tfo_utils.tfo_file_utils import (
    backup_file_or_dir,
    create_op_backup_dir, cleanup_op_backup_dir, cleanup_all_stale_backups,
    restore_from_backup,
)
from tfo_utils.tfo_recycle_bin import delete_to_recycle
from tfo_utils.tfo_logger import log_info, log_error, log_warning
from tfo_UnZipWorker import detect_archive_format, _extract_member


# 操作类型常量
OP_TYPE_SEARCH = "search"

OP_TYPE_RENAME_APPLY = "rename_apply"
OP_TYPE_RENAME_PREVIEW = "rename_preview"
OP_TYPE_RENAME_EXECUTE = "rename_execute"

OP_TYPE_MOVE_APPLY = "move_apply"
OP_TYPE_MOVE_PREVIEW = "move_preview"
OP_TYPE_MOVE_EXECUTE = "move_execute"

OP_TYPE_COPY_APPLY = "copy_apply"
OP_TYPE_COPY_PREVIEW = "copy_preview"
OP_TYPE_COPY_EXECUTE = "copy_execute"

OP_TYPE_ZIP_APPLY = "zip_apply"
OP_TYPE_ZIP_PREVIEW = "zip_preview"
OP_TYPE_ZIP_EXECUTE = "zip_execute"

OP_TYPE_UNZIP_APPLY = "unzip_apply"
OP_TYPE_UNZIP_PREVIEW = "unzip_preview"
OP_TYPE_UNZIP_EXECUTE = "unzip_execute"

OP_TYPE_DELETE_APPLY = "delete_apply"
OP_TYPE_DELETE_PREVIEW = "delete_preview"
OP_TYPE_DELETE_EXECUTE = "delete_execute"

OP_TYPE_DUPLICATE_APPLY = "duplicate_apply"
OP_TYPE_DUPLICATE_PREVIEW = "duplicate_preview"
OP_TYPE_DUPLICATE_EXECUTE = "duplicate_execute"

# 执行类操作集合（需要修改文件系统）
EXECUTE_OP_TYPES = {
    OP_TYPE_RENAME_EXECUTE, OP_TYPE_MOVE_EXECUTE, OP_TYPE_COPY_EXECUTE,
    OP_TYPE_ZIP_EXECUTE, OP_TYPE_UNZIP_EXECUTE, OP_TYPE_DELETE_EXECUTE,
    OP_TYPE_DUPLICATE_EXECUTE,
}

# op_type → i18n 标签键
_OP_TYPE_LABEL_KEY = {
    OP_TYPE_SEARCH: "op_type_search",
    OP_TYPE_RENAME_APPLY: "op_type_rename_apply",
    OP_TYPE_RENAME_PREVIEW: "op_type_rename_preview",
    OP_TYPE_RENAME_EXECUTE: "op_type_rename_execute",
    OP_TYPE_MOVE_APPLY: "op_type_move_apply",
    OP_TYPE_MOVE_PREVIEW: "op_type_move_preview",
    OP_TYPE_MOVE_EXECUTE: "op_type_move_execute",
    OP_TYPE_COPY_APPLY: "op_type_copy_apply",
    OP_TYPE_COPY_PREVIEW: "op_type_copy_preview",
    OP_TYPE_COPY_EXECUTE: "op_type_copy_execute",
    OP_TYPE_ZIP_APPLY: "op_type_zip_apply",
    OP_TYPE_ZIP_PREVIEW: "op_type_zip_preview",
    OP_TYPE_ZIP_EXECUTE: "op_type_zip_execute",
    OP_TYPE_UNZIP_APPLY: "op_type_unzip_apply",
    OP_TYPE_UNZIP_PREVIEW: "op_type_unzip_preview",
    OP_TYPE_UNZIP_EXECUTE: "op_type_unzip_execute",
    OP_TYPE_DELETE_APPLY: "op_type_delete_apply",
    OP_TYPE_DELETE_PREVIEW: "op_type_delete_preview",
    OP_TYPE_DELETE_EXECUTE: "op_type_delete_execute",
    OP_TYPE_DUPLICATE_APPLY: "op_type_duplicate_apply",
    OP_TYPE_DUPLICATE_PREVIEW: "op_type_duplicate_preview",
    OP_TYPE_DUPLICATE_EXECUTE: "op_type_duplicate_execute",
}

# tab_index → i18n tab标签键
_TAB_LABEL_KEY = {
    0: "tab_search",
    1: "tab_rename",
    2: "tab_move",
    3: "tab_copy",
    4: "tab_zip",
    5: "tab_unzip",
    6: "tab_delete",
    7: "tab_duplicate",
}


class _OpUndoEntry:
    """操作级撤销/重做条目"""

    def __init__(self, op_type, op_label, tab_index, timestamp, op_id, before_grid):
        self.op_type = op_type
        self.op_label = op_label
        self.op_summary = ""                # 操作摘要（commit时计算，如"5项操作"）
        self.tab_index = tab_index
        self.timestamp = timestamp
        self.op_id = op_id
        self.before_grid = before_grid       # 操作前Grid快照
        self.after_grid = None               # 操作后Grid快照（commit时填充）
        self.file_ops_log = []               # 执行类操作的文件系统修改记录
        self.backup_dir = None               # 备份目录路径（仅执行类且有备份时）

    def is_execute_op(self):
        return self.op_type in EXECUTE_OP_TYPES


class _OpHistoryManager:
    """操作级撤销/重做栈管理器"""

    MAX_HISTORY = 20

    def __init__(self):
        self._undo_stack = []
        self._redo_stack = []
        self._counter = 0  # 用于生成唯一 op_id 后缀
        self._pending_entry = None  # begin_operation 但未 commit 的条目

    # ================================================================
    #  入栈（begin/commit/abort）
    # ================================================================

    def begin_operation(self, op_type, tab_index, tool):
        """在按钮处理函数开始时调用（操作真正开始后），捕获 before_grid 快照

        Args:
            op_type: 操作类型常量
            tab_index: 操作时所在 Tab 索引
            tool: tfo_TabulexFileOperatorTool 实例
        Returns:
            entry: _OpUndoEntry 实例（暂未入栈）
        """
        self._counter += 1
        ts = time.time()
        ts_str = datetime.datetime.fromtimestamp(ts).strftime("%Y%m%d_%H%M%S")
        op_id = f"{ts_str}_{op_type}_{self._counter}"
        # 生成显示标签（格式：Tab名/按钮类型，如"重命名/执行"）
        op_label_key = _OP_TYPE_LABEL_KEY.get(op_type, op_type)
        tab_label_key = _TAB_LABEL_KEY.get(tab_index, "")
        tab_label = translate(tab_label_key) if tab_label_key else ""
        op_label = translate(op_label_key)
        op_display_label = f"{tab_label}/{op_label}" if tab_label else op_label
        # 捕获 before_grid
        before_grid = self._capture_grid_snapshot(tool.file_grid)
        entry = _OpUndoEntry(op_type, op_display_label, tab_index, ts, op_id, before_grid)
        self._pending_entry = entry
        return entry

    def commit_operation(self, entry, tool):
        """操作完成后调用，捕获 after_grid 快照，推入 undo 栈

        若操作未产生任何变更（Grid无变化且无文件操作），则不入栈（abort处理）。
        """
        if entry is None:
            return
        # 捕获 after_grid
        entry.after_grid = self._capture_grid_snapshot(tool.file_grid)
        # 检查是否有实际变更：Grid数据变化 或 文件系统操作
        grid_changed = not self._grids_equal(entry.before_grid, entry.after_grid)
        has_file_ops = bool(entry.file_ops_log)
        if not grid_changed and not has_file_ops:
            # 无任何变更，不入栈，按abort处理
            log_info(f"[OpHistory] 操作无变更，不入栈: {entry.op_label} (op_id={entry.op_id})")
            self.abort_operation(entry)
            return
        # 计算操作摘要
        entry.op_summary = self._compute_op_summary(entry)
        # 推入 undo 栈
        self._undo_stack.append(entry)
        # 清空 redo 栈（标准撤销/重做行为）
        self._clear_redo_stack()
        # 限制栈大小，淘汰超限的旧条目并清除其备份
        while len(self._undo_stack) > self.MAX_HISTORY:
            old = self._undo_stack.pop(0)
            if old.backup_dir:
                cleanup_op_backup_dir(old.backup_dir)
                old.backup_dir = None
        self._pending_entry = None
        log_info(f"[OpHistory] 提交操作: {entry.op_label} — {entry.op_summary} (op_id={entry.op_id})")

    def abort_operation(self, entry):
        """操作被取消（如参数无效）时调用，丢弃 entry 及其备份"""
        if entry is None:
            return
        if entry.backup_dir:
            cleanup_op_backup_dir(entry.backup_dir)
            entry.backup_dir = None
        if self._pending_entry is entry:
            self._pending_entry = None
        log_info(f"[OpHistory] 中止操作: {entry.op_label} (op_id={entry.op_id})")

    def _clear_redo_stack(self):
        """清空 redo 栈，清除其条目的备份"""
        for entry in self._redo_stack:
            if entry.backup_dir:
                cleanup_op_backup_dir(entry.backup_dir)
                entry.backup_dir = None
        self._redo_stack.clear()

    def clear_all(self):
        """清空撤销/重做栈并清理所有条目的备份目录

        在工具"重置"操作时调用，使撤销/重做菜单恢复为空状态。
        """
        self._clear_redo_stack()
        for entry in self._undo_stack:
            if entry.backup_dir:
                cleanup_op_backup_dir(entry.backup_dir)
                entry.backup_dir = None
        self._undo_stack.clear()
        self._pending_entry = None

    # ================================================================
    #  文件操作日志（Worker执行过程中调用）
    # ================================================================

    def append_file_op(self, entry, op_dict):
        """向 entry.file_ops_log 追加一条文件操作记录

        Args:
            entry: _OpUndoEntry 实例
            op_dict: 文件操作记录字典
        """
        if entry is not None and op_dict:
            entry.file_ops_log.append(op_dict)

    # ================================================================
    #  备份管理
    # ================================================================

    def ensure_backup_dir(self, entry):
        """确保 entry 有备份目录（按需创建）

        Args:
            entry: _OpUndoEntry 实例
        Returns:
            backup_dir: 备份目录路径
        """
        if entry.backup_dir is None:
            entry.backup_dir = create_op_backup_dir(entry.op_id)
        return entry.backup_dir

    @staticmethod
    def cleanup_stale_backups():
        """启动时调用，清除所有遗留的备份目录"""
        cleanup_all_stale_backups()

    # ================================================================
    #  撤销/重做
    # ================================================================

    def undo(self, tool):
        """撤销最近一步操作

        对于执行类操作（EXECUTE）：先还原文件系统，再恢复Grid到操作前状态
        对于非执行类操作（应用/预览）：仅恢复Grid到操作前状态

        总原则：除不可控的外部修改（磁盘外部修改、权限问题）外，
        撤销必须能正确恢复到操作前状态（Grid + 文件系统）。
        若文件系统还原失败，则不恢复Grid，保持当前状态。
        """
        if not self._undo_stack:
            return
        entry = self._undo_stack[-1]  # 先取栈顶不弹

        # === 阶段1：还原文件系统（仅执行类操作） ===
        if entry.file_ops_log:
            conflicts = self._detect_external_modifications(entry)
            if conflicts:
                choice = self._show_conflict_dialog(conflicts, tool)
                if choice == "cancel":
                    return  # 取消撤销
                # "overwrite": 强制还原所有（覆盖外部修改）
            # 逆向还原文件系统（倒序遍历确保依赖顺序正确）
            try:
                for op in reversed(entry.file_ops_log):
                    self._revert_file_op(op, tool)
            except Exception as e:
                log_error(f"[OpHistory] 撤销文件操作失败: {e}")
                # 文件系统还原失败，不恢复Grid，保持当前状态
                tool.status_bar.SetStatusText(
                    translate("undo_op_fs_failed").format(error=str(e)), 0)
                return

        # === 阶段2：恢复Grid数据（所有操作类型，包括执行类） ===
        entry = self._undo_stack.pop()
        # 保存当前Grid快照作为after_grid（供重做使用）
        entry.after_grid = self._capture_grid_snapshot(tool.file_grid)
        # 恢复Grid到操作前状态（before_grid）
        self._restore_grid_snapshot(tool.file_grid, entry.before_grid)

        # === 阶段3：清理备份并推入redo栈 ===
        if entry.backup_dir:
            cleanup_op_backup_dir(entry.backup_dir)
            entry.backup_dir = None
        self._redo_stack.append(entry)
        log_info(f"[OpHistory] 撤销操作: {entry.op_label}")

    def redo(self, tool):
        """重做最近一步撤销的操作

        对于执行类操作（EXECUTE）：重新执行文件系统操作，再恢复Grid到操作后状态
        对于非执行类操作（应用/预览）：仅恢复Grid到操作后状态

        总原则：除不可控的外部修改外，重做必须能正确恢复到操作后状态（Grid + 文件系统）。
        若文件系统重做失败，则不恢复Grid，保持当前状态。
        """
        if not self._redo_stack:
            return
        entry = self._redo_stack[-1]

        # === 阶段1：重新执行文件系统操作（仅执行类操作） ===
        if entry.file_ops_log:
            try:
                for op in entry.file_ops_log:
                    # delete_to_recycle 重做前必须重新备份原文件（撤销时已从备份还原），
                    # 备份失败则抛出异常中止重做并提示，避免撤销安全保证被击穿
                    if op.get("op") == "delete_to_recycle":
                        self._re_backup_for_redo(op, entry)
                    self._reapply_file_op(op, tool)
            except Exception as e:
                log_error(f"[OpHistory] 重做文件操作失败: {e}")
                # 文件系统重做失败，不恢复Grid，保持当前状态
                tool.status_bar.SetStatusText(
                    translate("redo_op_fs_failed").format(error=str(e)), 0)
                return

        # === 阶段2：恢复Grid数据（所有操作类型，包括执行类） ===
        entry = self._redo_stack.pop()
        if entry.after_grid is None:
            entry.after_grid = self._capture_grid_snapshot(tool.file_grid)
        # 恢复Grid到操作后状态（after_grid）
        self._restore_grid_snapshot(tool.file_grid, entry.after_grid)

        # === 阶段3：推入undo栈 ===
        self._undo_stack.append(entry)
        log_info(f"[OpHistory] 重做操作: {entry.op_label}")

    def undo_to_step(self, index, tool):
        """撤销到 undo 栈中第 index 步（0=撤销1步；len-1=撤销全部）

        Args:
            index: 目标步骤索引（0=撤销最近1步；len-1=撤销到最早）
        """
        if index < 0 or index >= len(self._undo_stack):
            return
        steps = index + 1
        for _ in range(steps):
            self.undo(tool)

    def redo_to_step(self, index, tool):
        """重做到 redo 栈中第 index 步（0=重做1步；len-1=重做全部）"""
        if index < 0 or index >= len(self._redo_stack):
            return
        steps = index + 1
        for _ in range(steps):
            self.redo(tool)

    # ================================================================
    #  状态查询
    # ================================================================

    def can_undo(self):
        return len(self._undo_stack) > 0

    def can_redo(self):
        return len(self._redo_stack) > 0

    def get_undo_history(self):
        """返回 undo 栈所有条目，倒序（最新在前）"""
        return list(reversed(self._undo_stack))

    def get_redo_history(self):
        """返回 redo 栈所有条目，正序（最早在前）"""
        return list(self._redo_stack)

    # ================================================================
    #  Grid 快照
    # ================================================================

    def _capture_grid_snapshot(self, grid):
        """捕获 Grid 完整快照（二维字符串列表）"""
        rows = grid.GetNumberRows()
        cols = grid.GetNumberCols()
        return [[grid.GetCellValue(r, c) for c in range(cols)] for r in range(rows)]

    def _restore_grid_snapshot(self, grid, snapshot):
        """恢复 Grid 到快照状态"""
        grid.BeginBatch()
        try:
            current_rows = grid.GetNumberRows()
            target_rows = len(snapshot)
            if target_rows > current_rows:
                grid.AppendRows(target_rows - current_rows)
            elif target_rows < current_rows:
                grid.DeleteRows(target_rows, current_rows - target_rows)
            for r, row_data in enumerate(snapshot):
                for c, val in enumerate(row_data):
                    grid.SetCellValue(r, c, val)
        finally:
            grid.EndBatch()
            grid.ForceRefresh()
            grid.Update()
            wx.Yield()

    @staticmethod
    def _grids_equal(grid_a, grid_b):
        """比较两个Grid快照是否相同（仅比较前4列：旧路径/新路径/匹配名/执行结果）

        其他列（父目录名、文件名、层级、类型、大小、时间、隐藏、读写）依附于旧路径列，
        不需要独立比较。
        """
        if len(grid_a) != len(grid_b):
            return False
        # 仅比较前4列（COL_OLD_PATH=0, COL_NEW_PATH=1, COL_MATCH_NAME=2, COL_RESULT=3）
        compare_cols = min(4, min(len(grid_a[0]) if grid_a else 0, len(grid_b[0]) if grid_b else 0))
        for r in range(len(grid_a)):
            if len(grid_a[r]) != len(grid_b[r]):
                return False
            for c in range(compare_cols):
                if grid_a[r][c] != grid_b[r][c]:
                    return False
        return True

    def _compute_op_summary(self, entry):
        """计算操作摘要文本（用于菜单项和状态栏显示）

        根据操作类型生成不同的摘要：
        - 执行类操作：N项操作（基于file_ops_log数量）
        - 所有非执行类操作（搜索/应用/预览）：N行变更（基于前4列比较）
        """
        op_type = entry.op_type
        before = entry.before_grid
        after = entry.after_grid
        file_ops_count = len(entry.file_ops_log)

        # 执行类操作：显示文件操作数
        if op_type in EXECUTE_OP_TYPES:
            if file_ops_count > 0:
                return translate("op_summary_execute").format(count=file_ops_count)
            # 执行类操作但无file_ops_log（理论上不应发生，但防御性处理）
            return translate("op_summary_no_change")

        # 所有非执行类操作（搜索/应用/预览）：统计前4列变更行数
        # 注：搜索操作后Grid会经过DeleteRows和adjust_table_rows处理，
        #     行数差异不能准确反映搜索结果，因此统一用前4列变更行数
        changed_rows = self._count_changed_rows(before, after)

        if op_type == OP_TYPE_SEARCH:
            if changed_rows > 0:
                return translate("op_summary_search").format(count=changed_rows)
            return translate("op_summary_no_change")
        elif op_type.endswith("_preview"):
            if changed_rows > 0:
                return translate("op_summary_preview").format(count=changed_rows)
            return translate("op_summary_no_change")
        else:  # _apply
            if changed_rows > 0:
                return translate("op_summary_apply").format(count=changed_rows)
            return translate("op_summary_no_change")

    @staticmethod
    def _count_changed_rows(before, after):
        """统计前4列（旧路径/新路径/匹配名/执行结果）有变更的行数

        包括：原有行中前4列有变化的 + 新增的行（after比before多出的行）
        """
        changed_rows = 0
        min_rows = min(len(before), len(after))
        # 比较共有行中前4列是否有变化
        for r in range(min_rows):
            if (before[r][0] != after[r][0] or before[r][1] != after[r][1] or
                before[r][2] != after[r][2] or before[r][3] != after[r][3]):
                changed_rows += 1
        # after比before多出的行（新增行，前4列必然有变化）
        if len(after) > len(before):
            changed_rows += len(after) - len(before)
        return changed_rows

    # ================================================================
    #  文件系统还原
    # ================================================================

    @staticmethod
    def _op_key(op):
        """生成文件操作的唯一键（用于冲突匹配）"""
        if op.get("op") == "move":
            return f"move:{os.path.normcase(op.get('dst', ''))}"
        elif op.get("op") == "copy":
            return f"copy:{os.path.normcase(op.get('dst', ''))}"
        elif op.get("op") == "zip_create":
            return f"zip:{os.path.normcase(op.get('zip_path', ''))}"
        elif op.get("op") == "unzip_extract":
            return f"unzip:{os.path.normcase(op.get('dst', ''))}"
        elif op.get("op") == "unzip_mkdir":
            return f"unzipdir:{os.path.normcase(op.get('dst', ''))}"
        elif op.get("op") == "unzip_dir_replace":
            return f"unzipdir:{os.path.normcase(op.get('dir_path', ''))}"
        elif op.get("op") == "delete_to_recycle":
            return f"delete:{os.path.normcase(op.get('path', ''))}"
        elif op.get("op") == "merge_dirs":
            return f"merge:{os.path.normcase(op.get('dst_dir', ''))}"
        return ""

    def _detect_external_modifications(self, entry):
        """检测执行类操作的 file_ops_log 中是否有外部修改

        Returns:
            conflicts: List[dict] 冲突列表，每项:
                {"key": 操作键, "path": 文件路径, "expected_mtime": 期望mtime,
                 "actual_mtime": 实际mtime}
        """
        conflicts = []
        for op in entry.file_ops_log:
            if not op.get("success", False):
                continue
            op_type = op.get("op")
            # move: 检查 dst 当前 mtime 是否与执行后记录的一致
            if op_type == "move":
                dst = op.get("dst", "")
                if dst and os.path.exists(dst):
                    try:
                        actual_mtime = os.path.getmtime(dst)
                        # 记录执行后mtime（在op中记录为 dst_mtime_after）
                        expected = op.get("dst_mtime_after")
                        if expected is not None and abs(actual_mtime - expected) > 1.0:
                            conflicts.append({
                                "key": self._op_key(op),
                                "path": dst,
                                "expected_mtime": expected,
                                "actual_mtime": actual_mtime,
                            })
                    except OSError:
                        pass
            elif op_type == "copy":
                dst = op.get("dst", "")
                if dst and os.path.exists(dst):
                    try:
                        actual_mtime = os.path.getmtime(dst)
                        expected = op.get("dst_mtime_after")
                        if expected is not None and abs(actual_mtime - expected) > 1.0:
                            conflicts.append({
                                "key": self._op_key(op),
                                "path": dst,
                                "expected_mtime": expected,
                                "actual_mtime": actual_mtime,
                            })
                    except OSError:
                        pass
            elif op_type == "zip_create":
                zip_path = op.get("zip_path", "")
                if zip_path and os.path.exists(zip_path):
                    try:
                        actual_mtime = os.path.getmtime(zip_path)
                        expected = op.get("zip_mtime_after")
                        if expected is not None and abs(actual_mtime - expected) > 1.0:
                            conflicts.append({
                                "key": self._op_key(op),
                                "path": zip_path,
                                "expected_mtime": expected,
                                "actual_mtime": actual_mtime,
                            })
                    except OSError:
                        pass
            elif op_type == "unzip_extract":
                dst = op.get("dst", "")
                if dst and os.path.exists(dst):
                    try:
                        actual_mtime = os.path.getmtime(dst)
                        expected = op.get("dst_mtime_after")
                        if expected is not None and abs(actual_mtime - expected) > 1.0:
                            conflicts.append({
                                "key": self._op_key(op),
                                "path": dst,
                                "expected_mtime": expected,
                                "actual_mtime": actual_mtime,
                            })
                    except OSError:
                        pass
            # delete_to_recycle 无需检测（文件已删除）
            # merge_dirs 无需检测（合并后的目录由 src_dir_backup/dst_dir_backup 完整还原）
            # unzip_mkdir / unzip_dir_replace 无需检测（由备份完整还原）
        return conflicts

    def _show_conflict_dialog(self, conflicts, tool):
        """显示冲突对话框

        Returns:
            "overwrite" / "cancel"
        """
        try:
            parent = tool.frame if tool.frame else tool.panel
        except Exception:
            parent = None
        msg_lines = [translate("undo_op_conflict_message"), ""]
        for c in conflicts[:20]:
            msg_lines.append(f"  {c['path']}")
        if len(conflicts) > 20:
            msg_lines.append(f"  ... ({len(conflicts) - 20} more)")
        msg = "\n".join(msg_lines)
        dlg = wx.MessageDialog(
            parent,
            msg,
            translate("undo_op_conflict_title"),
            wx.OK | wx.CANCEL | wx.ICON_WARNING
        )
        dlg.SetOKLabel(translate("undo_op_conflict_overwrite"))
        ret = dlg.ShowModal()
        dlg.Destroy()
        if ret == wx.ID_OK:
            return "overwrite"
        else:
            return "cancel"

    @staticmethod
    def _remove_to_recycle(path):
        """将路径移入回收站（替代永久删除）

        撤销/重做过程中对操作产物/冲突目标的删除统一走回收站通道，
        避免永久删除造成不可恢复。失败时抛出异常，由调用方决定是否继续。
        """
        if not path or not os.path.exists(path):
            return
        result = delete_to_recycle(path)
        if result != 0:
            raise RuntimeError(
                f"move to recycle bin failed: {path} (error_code={result})")

    def _revert_file_op(self, op, tool):
        """逆向还原单个文件操作

        失败时抛出异常，由调用方（undo）决定是否继续。
        这确保Grid与文件系统保持一致：若文件系统还原失败，Grid不会被恢复。
        """
        op_type = op.get("op")
        if op_type == "move":
            # 撤销move: 把dst移回src
            src = op.get("src", "")
            dst = op.get("dst", "")
            if dst and os.path.exists(dst):
                # 若 src 在原位置不存在或被备份过，需确保父目录存在
                if src:
                    parent = os.path.dirname(src)
                    if parent and not os.path.exists(parent):
                        os.makedirs(parent, exist_ok=True)
                    # 若 src 已被备份（merge情况），从备份还原
                    src_backup = op.get("src_backup")
                    if src_backup and not os.path.exists(src):
                        restore_from_backup(src_backup, src)
                    elif os.path.exists(dst):
                        shutil.move(dst, src)
                else:
                    # src未知：将dst移入回收站（替代永久删除，保证可恢复）
                    self._remove_to_recycle(dst)
            # 若 dst 已被备份过（dst_existed_before=True 且有 dst_backup），从备份还原
            dst_backup = op.get("dst_backup")
            if dst_backup and dst and not os.path.exists(dst):
                restore_from_backup(dst_backup, dst)
        elif op_type == "copy":
            # 撤销copy: 删除新建的dst（移入回收站）
            dst = op.get("dst", "")
            if dst and os.path.exists(dst):
                self._remove_to_recycle(dst)
            # 若 dst 已存在被备份过，从备份还原
            dst_backup = op.get("dst_backup")
            if dst_backup and dst and not os.path.exists(dst):
                restore_from_backup(dst_backup, dst)
        elif op_type == "zip_create":
            # 撤销zip_create: 删除新建的ZIP（移入回收站）
            zip_path = op.get("zip_path", "")
            if zip_path and os.path.exists(zip_path):
                self._remove_to_recycle(zip_path)
            # 若 ZIP 已存在被备份过，从备份还原
            zip_backup = op.get("zip_backup")
            if zip_backup and zip_path and not os.path.exists(zip_path):
                restore_from_backup(zip_backup, zip_path)
        elif op_type == "unzip_extract":
            # 撤销解压文件：删除新建的 dst（移入回收站），若曾被覆盖则从备份还原
            dst = op.get("dst", "")
            if dst and os.path.exists(dst):
                self._remove_to_recycle(dst)
            dst_backup = op.get("dst_backup")
            if dst_backup and dst and not os.path.exists(dst):
                restore_from_backup(dst_backup, dst)
        elif op_type == "unzip_mkdir":
            # 撤销新建目录：目录应为空，直接 rmdir；若非空整树进回收站
            dst = op.get("dst", "")
            if dst and os.path.isdir(dst):
                try:
                    os.rmdir(dst)
                except OSError:
                    self._remove_to_recycle(dst)
        elif op_type == "unzip_dir_replace":
            # 撤销替换目录：删除已被替换的目录，从备份还原旧目录
            dir_path = op.get("dir_path", "")
            if dir_path and os.path.exists(dir_path):
                self._remove_to_recycle(dir_path)
            dir_backup = op.get("dir_backup")
            if dir_backup and dir_path and not os.path.exists(dir_path):
                restore_from_backup(dir_backup, dir_path)
        elif op_type == "delete_to_recycle":
            # 撤销delete: 从备份还原到原路径
            path_backup = op.get("path_backup")
            original_path = op.get("path", "")
            if path_backup and original_path:
                # 确保父目录存在
                parent = os.path.dirname(original_path)
                if parent and not os.path.exists(parent):
                    os.makedirs(parent, exist_ok=True)
                restore_from_backup(path_backup, original_path)
        elif op_type == "merge_dirs":
            # 撤销merge_dirs: 从src_dir_backup还原源目录，从dst_dir_backup还原目标目录
            src_dir_backup = op.get("src_dir_backup")
            src_dir = op.get("src_dir", "")
            dst_dir_backup = op.get("dst_dir_backup")
            dst_dir = op.get("dst_dir", "")
            # 还原源目录
            if src_dir_backup and src_dir:
                if not os.path.exists(src_dir):
                    restore_from_backup(src_dir_backup, src_dir)
            # 还原目标目录（撤销合并，先移入回收站再还原备份）
            if dst_dir_backup and dst_dir:
                if os.path.exists(dst_dir):
                    self._remove_to_recycle(dst_dir)
                restore_from_backup(dst_dir_backup, dst_dir)

    def _reapply_file_op(self, op, tool):
        """重做单个文件操作

        失败时抛出异常，由调用方（redo）决定是否继续。
        这确保Grid与文件系统保持一致：若文件系统重做失败，Grid不会被恢复。
        """
        op_type = op.get("op")
        if op_type == "move":
            src = op.get("src", "")
            dst = op.get("dst", "")
            if src and os.path.exists(src):
                parent = os.path.dirname(dst)
                if parent and not os.path.exists(parent):
                    os.makedirs(parent, exist_ok=True)
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        self._remove_to_recycle(dst)
                    shutil.move(src, dst)
                else:
                    shutil.move(src, dst)
        elif op_type == "copy":
            src = op.get("src", "")
            dst = op.get("dst", "")
            if src and os.path.exists(src):
                parent = os.path.dirname(dst)
                if parent and not os.path.exists(parent):
                    os.makedirs(parent, exist_ok=True)
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        self._remove_to_recycle(dst)
                    shutil.copytree(src, dst, symlinks=True)
                else:
                    shutil.copy2(src, dst)
        elif op_type == "zip_create":
            # 重做zip_create: 从备份还原zip文件
            # 注：zip无法简单地重新压缩（需要原始文件），因此依赖备份还原
            zip_path = op.get("zip_path", "")
            zip_backup = op.get("zip_backup")
            if zip_path:
                if zip_backup and not os.path.exists(zip_path):
                    # 从备份还原zip文件
                    restore_from_backup(zip_backup, zip_path)
                # 若zip_backup为None且zip不存在，说明执行时zip不存在且未备份，
                # 重做无法恢复（违反原则，但属于不可控场景）
        elif op_type == "unzip_extract":
            # 重做解压文件：从压缩包中重新解压该成员到 dst
            archive_path = op.get("archive_path", "")
            arcname = op.get("arcname", "")
            dst = op.get("dst", "")
            if not (archive_path and os.path.exists(archive_path) and dst):
                raise RuntimeError(
                    f"redo unzip extract failed: archive missing or dst empty ({dst})")
            fmt = detect_archive_format(archive_path)
            if not fmt:
                raise RuntimeError(
                    f"redo unzip extract failed: unsupported archive {archive_path}")
            parent = os.path.dirname(dst)
            if parent:
                os.makedirs(parent, exist_ok=True)
            if op.get("is_dir"):
                os.makedirs(dst, exist_ok=True)
            else:
                _extract_member(archive_path, fmt, arcname, dst, False)
        elif op_type == "unzip_mkdir":
            # 重做新建目录：重新创建
            dst = op.get("dst", "")
            if dst:
                os.makedirs(dst, exist_ok=True)
        elif op_type == "unzip_dir_replace":
            # 重做替换目录：先删除当前（撤销时已还原旧内容的）目录，
            # 后续 unzip_mkdir/unzip_extract 重做会重建解压内容
            dir_path = op.get("dir_path", "")
            if dir_path and os.path.exists(dir_path):
                self._remove_to_recycle(dir_path)
        elif op_type == "delete_to_recycle":
            # 重做删除：与正向操作一致，将文件/目录移入回收站（而非永久删除）
            path = op.get("path", "")
            if path and os.path.exists(path):
                result = delete_to_recycle(path)
                if result != 0:
                    raise RuntimeError(
                        f"redo delete to recycle failed: {path} (error_code={result})")
        elif op_type == "merge_dirs":
            # 复用 tool.merge_directories，保证重做与正向执行完全一致
            # （含同名文件的 跳过/覆盖 策略与 is_move）
            src_dir = op.get("src_dir", "")
            dst_dir = op.get("dst_dir", "")
            is_move = op.get("is_move", True)
            file_conflict = op.get("file_conflict", "skip")
            if src_dir and os.path.exists(src_dir):
                tool.merge_directories(src_dir, dst_dir, is_move=is_move,
                                       file_conflict=file_conflict)

    def _re_backup_for_redo(self, op, entry):
        """重做 delete_to_recycle 操作前重新备份

        撤销时已从备份还原原文件（且原备份目录已在撤销时清除），
        重做前需重新备份原文件，以便重做后再次撤销可正确还原。
        备份失败时抛出异常，由调用方（redo）中止重做并提示。
        """
        path = op.get("path", "")
        if not path or not os.path.exists(path):
            return
        backup_dir = self.ensure_backup_dir(entry)
        is_dir = os.path.isdir(path)
        category = "deleted_dirs" if is_dir else "deleted_files"
        bp, meta = backup_file_or_dir(path, backup_dir, category, 0)
        if bp:
            op["path_backup"] = bp
        else:
            raise RuntimeError(
                f"redo backup failed: {path} (op_id={entry.op_id})")
