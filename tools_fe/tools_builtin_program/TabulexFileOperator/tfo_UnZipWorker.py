# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
import os
import io
import posixpath
import threading
import zipfile
import tarfile
import shutil

from tfo_utils.tfo_i18n_manager import translate, i18n
from tfo_utils.tfo_file_utils import backup_file_or_dir
from tfo_utils.tfo_logger import log_error, log_info, log_warning, log_file_operation
from tfo_utils.tfo_worker_mode import WorkerMode

"""解压工作线程

支持格式（按扩展名识别，不依赖外部程序）：
- zip            -> Python 标准库 zipfile
- tar / tar.gz / tgz / tar.bz2 / tar.xz -> Python 标准库 tarfile
- 7z             -> py7zr（纯 Python，无需系统安装 7-Zip）

三种模式（WorkerMode）：
- APPLY   : 只计算每个压缩包的目标子目录路径，写入"新路径"列
- PREVIEW : 计算目标子目录路径 + 按顶层同名目录冲突策略给出预览结果
- EXECUTE : 真正解压到目标子目录，并按"目录明细粒度"处理冲突
            （文件冲突：目标已存在同名文件 -> 跳过/覆盖；
              目录冲突：目标已存在同名目录 -> 跳过整个子树/合并/替换）

边界情况：Old Path 中不是受支持压缩包格式的文件 -> 跳过不处理。

目标子目录：解压目标路径输入框为空时，默认解压到每个压缩包所在目录（压缩包旁边），
即 New Path = 压缩包所在目录/分组名；填写了目标路径时，所有压缩包解压到该目录下各自的子目录。
"""

# 支持的压缩包格式 -> 归档类型标识
_ARCHIVE_EXT_MAP = {
    ".zip": "zip",
    ".7z": "7z",
    ".tar": "tar",
    ".tar.gz": "tar.gz",
    ".tgz": "tar.gz",
    ".tar.bz2": "tar.bz2",
    ".tbz2": "tar.bz2",
    ".tbz": "tar.bz2",
    ".tar.xz": "tar.xz",
    ".txz": "tar.xz",
}


def detect_archive_format(path):
    """按扩展名识别压缩包格式；不支持返回 None"""
    name = (path or "").lower()
    if not name:
        return None
    # 先匹配双扩展名
    for ext, fmt in ((".tar.gz", "tar.gz"), (".tar.bz2", "tar.bz2"), (".tar.xz", "tar.xz")):
        if name.endswith(ext):
            return fmt
    base = os.path.basename(name)
    _, dot_ext = os.path.splitext(base)
    return _ARCHIVE_EXT_MAP.get(dot_ext.lower())


def strip_archive_extension(path):
    """去掉压缩包扩展名得到分组名（含 tar.gz/tar.bz2/tar.xz 双扩展名）"""
    name = (path or "").lower()
    for ext in (".tar.gz", ".tar.bz2", ".tar.xz"):
        if name.endswith(ext):
            return os.path.basename(path)[: -len(ext)]
    return os.path.splitext(os.path.basename(path))[0]


def _sanitize_member_name(arcname):
    """规整压缩包内成员名（统一为正斜杠相对路径），并检测路径穿越。

    Returns:
        (safe_arcname_or_None, is_unsafe): 不安全时返回 (None, True)
    """
    if not arcname:
        return None, True
    name = arcname.replace("\\", "/")
    # 拒绝绝对路径 / 盘符 / .. 跳出
    if name.startswith("/") or name.startswith("\\\\"):
        return None, True
    parts = name.split("/")
    if any(p in ("",) and False for p in parts):  # noqa
        pass
    if any(p == ".." for p in parts):
        return None, True
    # 去除首尾空段与重复斜杠
    parts = [p for p in parts if p != ""]
    if not parts:
        return None, True
    clean = "/".join(parts)
    # 拒绝 Windows 盘符形式的成员名（如 C:/xxx 或 C:\xxx）
    if clean[0].isalpha() and len(clean) > 1 and clean[1] == ":":
        return None, True
    return clean, False


def detect_single_top_dir(members):
    """检测压缩包第一层是否仅含一个目录。

    若压缩包第一层有且只有一个目录（第一层既没有文件，也没有其他目录），返回该
    目录名（保留原始大小写）；否则返回 None。满足条件时解压将剥离该首层目录，
    使其内容直接落在目标子目录内，避免出现双层目录。
    注意：不少压缩包不包含显式的目录条目（只有文件条目，其路径以该目录为前缀），
    因此既匹配显式目录条目，也匹配以该首层段为前缀的文件条目。
    """
    top_segments = {}  # 首层段名 -> 该段是否为目录
    for arcname, is_dir in members:
        parts = arcname.split("/")
        if not parts:
            continue
        seg = parts[0]
        is_seg_dir = is_dir or len(parts) > 1
        top_segments[seg] = (seg in top_segments and top_segments[seg]) or is_seg_dir
    if len(top_segments) != 1:
        return None
    seg, is_seg_dir = next(iter(top_segments.items()))
    return seg if is_seg_dir else None


def unwrap_member_parts(arcname, strip_top_dir):
    """计算压缩包成员相对目标目录的路径段。

    若成员位于待剥离的首层目录（strip_top_dir）之下，剥离该首层目录段，使解压内容
    直接落在目标子目录内，避免出现双层目录。剥离后无剩余路径段（即该首层目录本身）
    时返回空列表，调用方应跳过（目标子目录已创建）。深层同名目录段不会被剥离。
    """
    parts = arcname.split("/")
    if strip_top_dir and parts and parts[0].lower() == strip_top_dir.lower():
        return parts[1:]
    return parts


def _extract_member(archive_path, fmt, arcname, dest_path, is_dir):
    """将压缩包单个成员解压到 dest_path（保留内部结构由调用方决定）

    模块级函数：供解压工作线程（tfo_UnZipWorker）与操作级撤销/重做
    （tfo_utils/tfo_op_history.py 重做 unzip_extract）共用。
    """
    if is_dir:
        os.makedirs(dest_path, exist_ok=True)
        return
    parent = os.path.dirname(dest_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if fmt == "zip":
        with zipfile.ZipFile(archive_path, 'r') as zf:
            with zf.open(arcname) as src, open(dest_path, 'wb') as out:
                shutil.copyfileobj(src, out, length=1024 * 1024)
    elif fmt.startswith("tar"):
        mode_map = {
            "tar": "r:",
            "tar.gz": "r:gz",
            "tar.bz2": "r:bz2",
            "tar.xz": "r:xz",
        }
        with tarfile.open(archive_path, mode_map.get(fmt, "r:*")) as tf:
            m = tf.getmember(arcname)
            src = tf.extractfile(m)
            if src is None:
                raise RuntimeError("cannot read member: %s" % arcname)
            with open(dest_path, 'wb') as out:
                shutil.copyfileobj(src, out, length=1024 * 1024)
    elif fmt == "7z":
        import py7zr
        with py7zr.SevenZipFile(archive_path, 'r') as z:
            data = z.read(targets=[arcname])
            fo = data.get(arcname)
            if fo is None:
                raise RuntimeError("cannot read member: %s" % arcname)
            try:
                with open(dest_path, 'wb') as out:
                    shutil.copyfileobj(fo, out, length=1024 * 1024)
            finally:
                try:
                    fo.close()
                except Exception:
                    pass


class tfo_UnZipWorker(threading.Thread):
    def __init__(self, tool_instance, use_match_name, save_dir,
                 file_conflict_method="overwrite",
                 dir_conflict_method="replace", worker_mode=None):
        super().__init__()
        self.tool_instance = tool_instance
        self.use_match_name = use_match_name      # True=按匹配名分组; False=按压缩包分组
        self.save_dir = save_dir                  # 目标目录（可为空字符串/None）
        self.file_conflict_method = file_conflict_method  # "skip"/"overwrite"
        self.dir_conflict_method = dir_conflict_method    # "skip"/"merge"/"replace"
        self.worker_mode = worker_mode if worker_mode is not None else WorkerMode.EXECUTE
        self._stop_flag = threading.Event()
        self.progress_info = (0, 0, 0)
        self.unzipped_packages = 0
        self.total_packages = 0
        # __init__ 在 UI 线程执行：在此快照行数据与列数，Worker 线程内不再跨线程读取 Grid
        grid = tool_instance.file_grid
        self.snapshot_rows_total = grid.GetNumberRows()
        self.snapshot_cols_total = grid.GetNumberCols()
        self.snapshot_old_paths = [grid.GetCellValue(r, grid.COL_OLD_PATH).strip() for r in range(self.snapshot_rows_total)]
        self.snapshot_new_paths = [grid.GetCellValue(r, grid.COL_NEW_PATH).strip() for r in range(self.snapshot_rows_total)]
        self.snapshot_match_names = [grid.GetCellValue(r, grid.COL_MATCH_NAME).strip() for r in range(self.snapshot_rows_total)]

    # ================================================================
    #  压缩包成员枚举
    # ================================================================
    def _list_members(self, archive_path, fmt):
        """返回成员列表 [(safe_arcname, is_dir), ...]，按归档内顺序"""
        members = []
        if fmt == "zip":
            with zipfile.ZipFile(archive_path, 'r') as zf:
                for info in zf.infolist():
                    name = info.filename
                    # 跳过符号链接（防御性安全策略，不创建链接）
                    if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                        continue
                    clean, unsafe = _sanitize_member_name(name)
                    if unsafe:
                        continue
                    members.append((clean, name.endswith("/")))
        elif fmt.startswith("tar"):
            mode_map = {
                "tar": "r:",
                "tar.gz": "r:gz",
                "tar.bz2": "r:bz2",
                "tar.xz": "r:xz",
            }
            with tarfile.open(archive_path, mode_map.get(fmt, "r:*")) as tf:
                for m in tf.getmembers():
                    if m.issym() or m.islnk() or m.isdev():
                        continue
                    clean, unsafe = _sanitize_member_name(m.name)
                    if unsafe:
                        continue
                    members.append((clean, m.isdir()))
        elif fmt == "7z":
            try:
                import py7zr
            except ImportError:
                return None  # 标记为格式可用但库缺失
            with py7zr.SevenZipFile(archive_path, 'r') as z:
                for info in z.list():
                    clean, unsafe = _sanitize_member_name(info.filename)
                    if unsafe:
                        continue
                    members.append((clean, bool(info.is_directory)))
        return members

    # ================================================================
    #  主流程
    # ================================================================
    def run(self):
        log_info(f"[UnZipWorker] 开始执行, 模式: {self.worker_mode.name}, 保存目录: {self.save_dir}")
        try:
            # 用户显式指定的目标目录（解压目标路径输入框）；为空字符串/None 时表示
            # 未指定，默认"解压到压缩包旁边"：目标子目录取各压缩包自身所在目录。
            provided_save_dir = (self.save_dir or "").strip()
            # EXECUTE 模式：仅在用户显式指定目标目录时预创建（Apply/Preview 只计算路径不创建）
            if self.worker_mode == WorkerMode.EXECUTE and provided_save_dir:
                try:
                    os.makedirs(provided_save_dir, exist_ok=True)
                except OSError as e:
                    log_error(f"[UnZipWorker] 创建目标目录失败 {provided_save_dir}: {e}")
                    if hasattr(self.tool_instance, 'status_bar'):
                        wx.CallAfter(self.tool_instance.status_bar.SetStatusText,
                                     translate("unzip_target_create_failed", error=str(e)), 0)
                    return
            self.save_dir = provided_save_dir

            # ---- 第一遍：逐行收集待解压的压缩包 ----
            packages = []  # [{"row_idx", "archive_path", "fmt", "group_name", "dest_top"}]
            rows_total = self.snapshot_rows_total
            # PREVIEW/EXECUTE：先清空整个"执行结果"列；APPLY：不修改 Result（仅对 New Path 变化行清空）
            if self.worker_mode != WorkerMode.APPLY:
                for _clear_row in range(rows_total):
                    self.tool_instance.file_grid.queue_cell_value(_clear_row, self.tool_instance.file_grid.COL_RESULT, "")
            for row_idx in range(rows_total):
                if self._stop_flag.is_set():
                    break
                # 压缩包路径来自 UI 线程快照
                old_path = self.snapshot_old_paths[row_idx]
                if not old_path:
                    # 路径为空：不做任何修改（不自动 Apply、不清空其它列）
                    continue
                if not (old_path and self.tool_instance.is_valid_path(old_path)):
                    if self.worker_mode != WorkerMode.APPLY:
                        self.tool_instance.file_grid.queue_cell_value(
                                     row_idx, self.tool_instance.file_grid.COL_RESULT,
                                     translate("failure_path_invalid"))
                    continue
                if not os.path.exists(old_path):
                    if self.worker_mode != WorkerMode.APPLY:
                        self.tool_instance.file_grid.queue_cell_value(
                                     row_idx, self.tool_instance.file_grid.COL_RESULT,
                                     translate("failure_old_path_not_exist"))
                    continue
                if not os.path.isfile(old_path):
                    # 非文件（目录）跳过不处理
                    if self.worker_mode != WorkerMode.APPLY:
                        self.tool_instance.file_grid.queue_cell_value(
                                     row_idx, self.tool_instance.file_grid.COL_RESULT,
                                     translate("skipped_not_archive"))
                    continue

                fmt = detect_archive_format(old_path)
                if fmt is None:
                    # 边界情况：非受支持压缩包 -> 跳过不处理
                    if self.worker_mode != WorkerMode.APPLY:
                        self.tool_instance.file_grid.queue_cell_value(
                                     row_idx, self.tool_instance.file_grid.COL_RESULT,
                                     translate("skipped_not_archive"))
                    continue

                # 计算分组名
                if self.use_match_name:
                    match_name = self.snapshot_match_names[row_idx]
                    if match_name:
                        group_name = match_name
                    else:
                        # 匹配名为空 -> 回退为压缩包文件名(不带扩展名)
                        group_name = strip_archive_extension(old_path)
                else:
                    group_name = strip_archive_extension(old_path)

                # 剔除非法字符
                if os.name == 'nt':
                    illegal_chars = r'<>"|:*?'
                else:
                    illegal_chars = ''
                for ch in illegal_chars:
                    group_name = group_name.replace(ch, '')
                group_name = group_name.strip()
                if not group_name:
                    group_name = "default"

                # 自动计算的目标子目录：显式指定目标目录时用该目录，否则解压到压缩包旁边
                if provided_save_dir:
                    auto_dest_top = os.path.join(provided_save_dir, group_name)
                else:
                    auto_dest_top = os.path.join(os.path.dirname(old_path), group_name)

                # 目标子目录（见 Note 13.0 / 6.2）：
                # - APPLY：按分组自动计算并写入"新路径"列（Apply 是唯一可写 New Path 的按钮）
                # - PREVIEW/EXECUTE：只使用用户已填写的非空"新路径"；为空视为未设置，
                #   写提示到 Result 并跳过本行（绝不自动计算/回写 New Path）
                user_new_path = self.snapshot_new_paths[row_idx]
                if self.worker_mode == WorkerMode.APPLY:
                    dest_top = auto_dest_top
                elif user_new_path:
                    dest_top = user_new_path
                else:
                    self.tool_instance.file_grid.queue_cell_value(
                                 row_idx, self.tool_instance.file_grid.COL_RESULT,
                                 translate("warning_new_path_not_set"))
                    continue

                packages.append({
                    "row_idx": row_idx,
                    "archive_path": old_path,
                    "fmt": fmt,
                    "group_name": group_name,
                    "dest_top": dest_top,
                    "match_name": self.snapshot_match_names[row_idx],
                })

            self.total_packages = len(packages)

            if self.worker_mode == WorkerMode.APPLY:
                for pkg in packages:
                    if self._stop_flag.is_set():
                        break
                    row_idx = pkg["row_idx"]
                    new_val = pkg["dest_top"]
                    old_val = (self.snapshot_new_paths[row_idx] or "").strip()
                    self.tool_instance.file_grid.queue_cell_value(
                                 row_idx, self.tool_instance.file_grid.COL_NEW_PATH, new_val)
                    # Apply 仅修改 New Path；变化时清空该行 Result（13.0 / 6.1）
                    if old_val != (new_val or "").strip():
                        self.tool_instance.file_grid.queue_cell_value(
                                     row_idx, self.tool_instance.file_grid.COL_RESULT, "")
                self.progress_info = (len(packages), len(packages), len(packages))
                log_info(f"[UnZipWorker] APPLY 完成, 共 {len(packages)} 个压缩包")
                return

            if self.worker_mode == WorkerMode.PREVIEW:
                for pkg in packages:
                    if self._stop_flag.is_set():
                        break
                    row_idx = pkg["row_idx"]
                    dest_top = pkg["dest_top"]
                    # 预览：不修改 New Path；仅对已填非空"新路径"的行写预测结果到"执行结果"列
                    if os.path.exists(dest_top):
                        if self.dir_conflict_method == "skip":
                            result = translate("warning_will_be_skipped")
                        elif self.dir_conflict_method == "merge":
                            result = translate("warning_will_be_merged")
                        else:
                            result = translate("warning_will_be_replaced")
                    else:
                        result = translate("correct_will_be_extracted")
                    self.tool_instance.file_grid.queue_cell_value(
                                 row_idx, self.tool_instance.file_grid.COL_RESULT, result)
                self.progress_info = (len(packages), len(packages), len(packages))
                log_info(f"[UnZipWorker] PREVIEW 完成, 共 {len(packages)} 个压缩包")
                return

            # ============ EXECUTE：真正解压 ============
            self._execute_packages(packages)
            self.progress_info = (len(packages), len(packages), self.unzipped_packages)
            log_info(f"[UnZipWorker] EXECUTE 完成, 成功: {self.unzipped_packages}/{len(packages)}")
        except Exception as e:
            log_error(f"[UnZipWorker] 解压操作错误: {e}")

    # ================================================================
    #  执行解压
    # ================================================================
    def _execute_packages(self, packages):
        op_entry = getattr(self.tool_instance, '_current_op_entry', None)
        op_history_mgr = getattr(self.tool_instance, '_op_history_manager', None)
        backup_dir = None
        if op_entry is not None and op_history_mgr is not None:
            backup_dir = op_history_mgr.ensure_backup_dir(op_entry)
        backup_idx = 0

        for pkg in packages:
            if self._stop_flag.is_set():
                break
            row_idx = pkg["row_idx"]
            archive_path = pkg["archive_path"]
            fmt = pkg["fmt"]
            dest_top = pkg["dest_top"]
            match_name = pkg.get("match_name", "")
            try:
                # ---- 顶层目标子目录冲突处理（Group 目录视为同名目录）----
                dest_top_existed = os.path.exists(dest_top)
                if dest_top_existed:
                    if self.dir_conflict_method == "skip":
                        # 执行模式：最终结果写"已跳过"而非预览态的"将被跳过"
                        self.tool_instance.file_grid.queue_cell_value(
                                     row_idx, self.tool_instance.file_grid.COL_RESULT,
                                     translate("warning_skipped"))
                        log_file_operation(translate("tab_unzip"), archive_path, dest_top, match_name,
                                           skipped=True, row_index=row_idx)
                        continue
                    elif self.dir_conflict_method == "replace":
                        dir_backup = None
                        if backup_dir:
                            dir_backup, _ = backup_file_or_dir(dest_top, backup_dir, "dir_conflicts", backup_idx)
                            backup_idx += 1
                            if dir_backup is None:
                                self.tool_instance.file_grid.queue_cell_value(
                                             row_idx, self.tool_instance.file_grid.COL_RESULT,
                                             translate("unzip_backup_failed"))
                                log_file_operation(translate("tab_unzip"), archive_path, dest_top, match_name,
                                                   success=False, error="dir backup failed", row_index=row_idx)
                                continue
                        # 删除旧目录后重新创建
                        shutil.rmtree(dest_top, ignore_errors=True)
                        log_info(f"[UnZipWorker] 替换同名目录: {dest_top}")
                        if op_history_mgr and op_entry:
                            op_history_mgr.append_file_op(op_entry, {
                                "op": "unzip_dir_replace",
                                "dir_path": dest_top,
                                "dir_backup": dir_backup,
                                "success": True,
                                "error": None,
                            })
                os.makedirs(dest_top, exist_ok=True)
                # 顶层子目录为新建时记录 mkdir（撤销时清理空目录用）
                if not dest_top_existed and op_history_mgr and op_entry:
                    op_history_mgr.append_file_op(op_entry, {
                        "op": "unzip_mkdir",
                        "dst": dest_top,
                        "success": True,
                        "error": None,
                    })

                members = self._list_members(archive_path, fmt)
                if members is None:
                    # py7zr 库缺失
                    self.tool_instance.file_grid.queue_cell_value(
                                 row_idx, self.tool_instance.file_grid.COL_RESULT,
                                 translate("unzip_missing_py7zr"))
                    log_file_operation(translate("tab_unzip"), archive_path, dest_top, match_name,
                                       success=False, error="missing py7zr", row_index=row_idx)
                    continue

                # 若压缩包第一层有且只有一个目录（如 SubFolder01.zip 内含 SubFolder01/），
                # 解压时剥离该首层目录，使解压内容直接落在目标子目录内，避免出现双层目录。
                # 第一层有多个目录、或存在文件时不做剥离；深层目录不受影响。
                strip_top_dir = detect_single_top_dir(members)

                skipped_dirs = []  # 已按"跳过"处理的目录前缀
                for arcname, is_dir in members:
                    if self._stop_flag.is_set():
                        return
                    if any(arcname == p or arcname.startswith(p + "/") for p in skipped_dirs):
                        continue
                    parts = unwrap_member_parts(arcname, strip_top_dir)
                    if not parts:
                        # 剥离后无剩余路径段：即待剥离的首层目录本身，它对应目标子目录
                        # （已在上方创建），无需再创建，直接跳过
                        continue
                    dest_path = os.path.join(dest_top, *parts)

                    if is_dir:
                        if os.path.exists(dest_path):
                            if self.dir_conflict_method == "skip":
                                skipped_dirs.append(arcname)
                                continue
                            elif self.dir_conflict_method == "replace":
                                dir_backup = None
                                if backup_dir:
                                    dir_backup, _ = backup_file_or_dir(dest_path, backup_dir, "dir_conflicts", backup_idx)
                                    backup_idx += 1
                                    if dir_backup is None:
                                        # 备份失败则中止本包（避免无可撤销备份仍永久删除旧目录）
                                        raise RuntimeError("dir backup failed: %s" % dest_path)
                                shutil.rmtree(dest_path, ignore_errors=True)
                                if op_history_mgr and op_entry and dir_backup:
                                    op_history_mgr.append_file_op(op_entry, {
                                        "op": "unzip_dir_replace",
                                        "dir_path": dest_path,
                                        "dir_backup": dir_backup,
                                        "success": True,
                                        "error": None,
                                    })
                        os.makedirs(dest_path, exist_ok=True)
                        # 记录新建目录（撤销时清理空目录用）
                        if op_history_mgr and op_entry:
                            op_history_mgr.append_file_op(op_entry, {
                                "op": "unzip_mkdir",
                                "dst": dest_path,
                                "success": True,
                                "error": None,
                            })
                        continue

                    # 文件成员
                    if os.path.exists(dest_path):
                        if self.file_conflict_method == "skip":
                            continue
                        dst_backup = None
                        if backup_dir:
                            dst_backup, _ = backup_file_or_dir(dest_path, backup_dir, "file_conflicts", backup_idx)
                            backup_idx += 1
                    else:
                        dst_backup = None
                    try:
                        _extract_member(archive_path, fmt, arcname, dest_path, is_dir=False)
                    except Exception as e:
                        log_error(f"[UnZipWorker] 解压成员失败 {arcname}: {e}")
                        if dst_backup:
                            # 覆盖失败时从备份还原原文件
                            try:
                                shutil.rmtree(dest_path, ignore_errors=True)
                                shutil.copy2(dst_backup, dest_path)
                            except Exception:
                                pass
                        raise
                    if op_history_mgr and op_entry:
                        dst_mtime_after = None
                        try:
                            dst_mtime_after = os.path.getmtime(dest_path)
                        except OSError:
                            pass
                        op_history_mgr.append_file_op(op_entry, {
                            "op": "unzip_extract",
                            "archive_path": archive_path,
                            "arcname": arcname,
                            "dst": dest_path,
                            "dst_backup": dst_backup,
                            "dst_mtime_after": dst_mtime_after,
                            "is_dir": False,
                            "success": True,
                            "error": None,
                        })

                self.unzipped_packages += 1
                self.tool_instance.file_grid.queue_cell_value(
                             row_idx, self.tool_instance.file_grid.COL_RESULT,
                             translate("success_unzipped"))
                log_file_operation(translate("tab_unzip"), archive_path, dest_top, match_name,
                                   success=True, row_index=row_idx)
            except Exception as e:
                log_error(f"[UnZipWorker] 解压失败 {archive_path}: {e}")
                row_error = str(e)
                self.tool_instance.file_grid.queue_cell_value(
                             row_idx, self.tool_instance.file_grid.COL_RESULT,
                             translate("unzip_failed", error=row_error))
                log_file_operation(translate("tab_unzip"), archive_path, dest_top, match_name,
                                   success=False, error=e, row_index=row_idx)

    # ================================================================
    #  线程控制
    # ================================================================
    def stop(self):
        self._stop_flag.set()

    def is_stopped(self):
        return self._stop_flag.is_set()

    def get_progress_info(self):
        return self.progress_info