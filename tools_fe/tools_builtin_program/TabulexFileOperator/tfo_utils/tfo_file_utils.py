# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import json
import shutil
import ctypes
import tempfile

MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024
MAX_PATH_LENGTH = 248
MAX_ZIP_SIZE = 4 * 1024 * 1024 * 1024
MAX_SEARCH_DEPTH = 20

# 操作级撤销/重做备份根目录名（位于系统临时目录下，权限收紧为仅当前用户可访问）
OP_BACKUP_ROOT_NAME = "TabulexFileOperator_undo_backup"

def format_file_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

def is_file_locked(filepath):
    if os.name == 'nt':
        try:
            # 用 GENERIC_READ + 不共享(0)探测：文件已被其他进程占用时打开失败。
            # 不能用 GENERIC_WRITE，否则只读属性文件会因拒绝写入被误判为"被锁定"
            GENERIC_READ = 0x80000000
            OPEN_EXISTING = 3
            FILE_ATTRIBUTE_NORMAL = 0x80
            INVALID_HANDLE_VALUE = -1
            handle = ctypes.windll.kernel32.CreateFileW(
                filepath, GENERIC_READ, 0, None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None
            )
            if handle == INVALID_HANDLE_VALUE:
                return True
            ctypes.windll.kernel32.CloseHandle(handle)
            return False
        except Exception:
            return False
    else:
        try:
            fd = os.open(filepath, os.O_RDWR)
            os.close(fd)
            return False
        except (OSError, IOError):
            try:
                fd = os.open(filepath, os.O_RDONLY)
                os.close(fd)
                return False
            except (OSError, IOError):
                return True

def validate_file_operation(source_path, target_path, is_valid_path_func=None):
    errors = []
    
    if is_valid_path_func and not is_valid_path_func(source_path):
        errors.append(('source_invalid', None))
        return errors
    
    if not os.path.exists(source_path):
        errors.append(('source_not_exist', None))
        return errors
    
    if is_valid_path_func and not is_valid_path_func(target_path):
        errors.append(('target_invalid', None))
        return errors
    
    if os.name == 'nt' and len(target_path) > MAX_PATH_LENGTH:
        errors.append(('target_path_too_long', len(target_path)))
        return errors
    
    if os.path.isfile(source_path):
        parent_dir = os.path.dirname(source_path)
    else:
        parent_dir = source_path
    if parent_dir:
        try:
            fd, tmp_path = tempfile.mkstemp(dir=parent_dir)
            os.close(fd)
            os.unlink(tmp_path)
        except Exception:
            errors.append(('source_no_permission', None))
            return errors
    
    if os.path.isfile(source_path) and is_file_locked(source_path):
        errors.append(('source_locked', None))
        return errors

    # 2GB 大小上限不在此处检查：复制/移动/重命名大文件是合法场景，
    # 该限制仅适用于压缩等场景（ZipWorker 内自行检查 MAX_FILE_SIZE）

    target_dir = os.path.dirname(target_path)
    if target_dir and not os.path.exists(target_dir):
        parent_dir = os.path.dirname(target_dir)
        if parent_dir and os.path.exists(parent_dir) and not os.access(parent_dir, os.W_OK):
            errors.append(('target_no_permission', None))
            return errors
    elif target_dir and os.path.exists(target_dir) and not os.access(target_dir, os.W_OK):
        errors.append(('target_no_permission', None))
        return errors
    
    if os.path.normcase(source_path) == os.path.normcase(target_path):
        errors.append(('same_path', None))

    return errors


# ================================================================
#  操作级撤销/重做 - 备份与冲突扫描工具
# ================================================================

def get_op_backup_root():
    """获取操作级撤销/重做的备份根目录路径"""
    return os.path.join(tempfile.gettempdir(), OP_BACKUP_ROOT_NAME)


def _secure_backup_dir_structure(backup_dir):
    """收紧备份目录结构的访问权限：备份目录及其 4 个分类子目录统一为 0700

    备份内容（被删除/覆盖的用户文件完整副本）位于系统共享临时目录下，
    Linux/macOS 多用户环境下若不收紧权限，其他本地账户可读取备份内容。
    仅收紧备份目录结构本身，不递归修改备份内的用户文件/目录权限，
    从而保证撤销/重做还原时用户文件权限与备份前一致。
    Windows 上 chmod 仅影响只读属性，权限收紧实际在 POSIX 生效。
    """
    try:
        os.chmod(backup_dir, 0o700)
        for sub in ("file_conflicts", "dir_conflicts", "deleted_files", "deleted_dirs"):
            sub_path = os.path.join(backup_dir, sub)
            if os.path.isdir(sub_path):
                os.chmod(sub_path, 0o700)
    except OSError:
        pass


def create_op_backup_dir(op_id):
    """创建指定操作的备份目录

    Args:
        op_id: 操作ID（如 "20260721_143025_rename_execute"）
    Returns:
        backup_dir: 备份目录路径（已创建，含4个子目录，权限收紧为仅当前用户可访问）
    """
    root = get_op_backup_root()
    backup_dir = os.path.join(root, op_id)
    os.makedirs(backup_dir, mode=0o700, exist_ok=True)
    os.makedirs(os.path.join(backup_dir, "file_conflicts"), mode=0o700, exist_ok=True)
    os.makedirs(os.path.join(backup_dir, "dir_conflicts"), mode=0o700, exist_ok=True)
    os.makedirs(os.path.join(backup_dir, "deleted_files"), mode=0o700, exist_ok=True)
    os.makedirs(os.path.join(backup_dir, "deleted_dirs"), mode=0o700, exist_ok=True)
    # 备份根目录可能为历史会话遗留（启动清理只删子项不删根），同样收紧为 0700
    if os.path.isdir(root):
        try:
            os.chmod(root, 0o700)
        except OSError:
            pass
    _secure_backup_dir_structure(backup_dir)
    return backup_dir


def cleanup_op_backup_dir(backup_dir):
    """清除指定备份目录（递归删除整个目录树）

    Args:
        backup_dir: 备份目录路径
    Returns:
        True=成功清除; False=失败（异常已捕获）
    """
    if not backup_dir or not os.path.exists(backup_dir):
        return True
    try:
        shutil.rmtree(backup_dir, ignore_errors=True)
        return True
    except Exception:
        return False


def cleanup_all_stale_backups():
    """清除所有遗留的备份目录（启动时调用）"""
    root = get_op_backup_root()
    if not os.path.exists(root):
        return
    # 优先收紧根目录权限，避免清理完成前其他本地账户读取遗留备份
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    try:
        for entry in os.listdir(root):
            entry_path = os.path.join(root, entry)
            if os.path.isdir(entry_path):
                shutil.rmtree(entry_path, ignore_errors=True)
    except Exception:
        pass


def _sanitize_backup_name(name, index):
    """生成备份子目录下的项名称：序号_安全化的basename"""
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    if not safe_name:
        safe_name = "item"
    return f"{index:04d}_{safe_name}"


def backup_file_or_dir(src_path, backup_dir, category, index):
    """备份文件或目录到备份目录的指定分类下

    Args:
        src_path: 原始路径（文件或目录）
        backup_dir: 备份根目录（含 file_conflicts/ 等子目录）
        category: "file_conflicts" / "dir_conflicts" / "deleted_files" / "deleted_dirs"
        index: 序号（用于命名）
    Returns:
        (backup_path, meta_dict) 备份后的路径和元数据；若备份失败返回 (None, None)
    """
    if not src_path or not os.path.exists(src_path):
        return None, None
    category_dir = os.path.join(backup_dir, category)
    os.makedirs(category_dir, mode=0o700, exist_ok=True)
    basename = os.path.basename(src_path.rstrip(os.sep)) or f"item{index}"
    backup_name = _sanitize_backup_name(basename, index)
    backup_path = os.path.join(category_dir, backup_name)
    # 防止重名
    counter = 1
    while os.path.exists(backup_path):
        backup_path = os.path.join(category_dir, f"{backup_name}_{counter}")
        counter += 1
    try:
        is_dir = os.path.isdir(src_path)
        # 记录元数据（备份前的状态）
        try:
            st = os.stat(src_path)
            meta = {
                "original_path": os.path.abspath(src_path),
                "is_dir": is_dir,
                "size": st.st_size,
                "mtime": st.st_mtime,
                "ctime": st.st_ctime,
                "mode": st.st_mode & 0o7777,
            }
        except OSError:
            meta = {
                "original_path": os.path.abspath(src_path),
                "is_dir": os.path.isdir(src_path),
                "size": 0,
                "mtime": 0,
                "ctime": 0,
                "mode": None,
            }
        # 执行备份
        if is_dir:
            # 目录备份保留符号链接本身（不跟随解引用），避免整树放大或越出预期范围
            shutil.copytree(src_path, backup_path, symlinks=True)
        else:
            shutil.copy2(src_path, backup_path)
            # 文件备份权限收紧为 0600（仅当前用户可读写），原权限记录于 meta 供撤销还原
            try:
                os.chmod(backup_path, 0o600)
            except OSError:
                pass
        write_meta_file(backup_path, meta)
        return backup_path, meta
    except Exception:
        return None, None


def restore_from_backup(backup_path, original_path):
    """从备份还原到原路径

    Args:
        backup_path: 备份项路径
        original_path: 原始路径
    Returns:
        True=成功; False=失败
    """
    if not backup_path or not os.path.exists(backup_path):
        return False
    try:
        meta = read_meta_file(backup_path)
        is_dir = meta.get("is_dir", os.path.isdir(backup_path)) if meta else os.path.isdir(backup_path)
        # 确保父目录存在
        parent_dir = os.path.dirname(original_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
        if is_dir:
            if os.path.exists(original_path):
                shutil.rmtree(original_path, ignore_errors=True)
            shutil.copytree(backup_path, original_path, symlinks=True)
        else:
            if os.path.exists(original_path):
                try:
                    os.remove(original_path)
                except OSError:
                    pass
            shutil.copy2(backup_path, original_path)
            # 备份文件权限已收紧为 0600，还原后恢复原文件权限（mode 记录于元数据）
            mode = meta.get("mode") if meta else None
            if mode:
                try:
                    os.chmod(original_path, mode)
                except OSError:
                    pass
        return True
    except Exception:
        return False


def write_meta_file(backup_path, meta_dict):
    """写入 .meta.json 元数据文件到备份项旁

    Args:
        backup_path: 备份项路径（文件或目录）
        meta_dict: 元数据字典
    """
    meta_path = backup_path + ".meta.json"
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_dict, f, ensure_ascii=False, indent=2)
        # 元数据文件同样收紧为 0600（仅当前用户可读写）
        try:
            os.chmod(meta_path, 0o600)
        except OSError:
            pass
    except Exception:
        pass


def read_meta_file(backup_path):
    """读取 .meta.json 元数据文件

    Args:
        backup_path: 备份项路径
    Returns:
        meta_dict 或 None（读取失败）
    """
    meta_path = backup_path + ".meta.json"
    if not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def finalize_apply_new_path_only(grid, rows, cols, before, col_new_path, col_result):
    """Apply 收尾：强制"仅修改 New Path 列"语义，tfo_RenameMoveWorker / tfo_CopyWorker 共用。

    约定：
    - 只有 New Path 列允许保留被 Apply 修改后的值；
    - New Path 发生变化的行：清空该行 Result；
    - New Path 未变化的行：Result 恢复为 Apply 前的值；
    - 除 New Path 外的所有列一律恢复为 Apply 前的值。

    Args:
        grid: 网格对象（需支持 GetNumberRows/GetCellValue/SetCellValue）
        rows, cols: Apply 前的行列数快照
        before: Apply 前逐行逐列的值快照（before[row][col]）
        col_new_path, col_result: New Path 列索引、Result 列索引
    Returns:
        New Path 发生变化（被 Apply 修改）的行数
    """
    def _norm(v):
        return (v or "").strip()

    changed_count = 0
    for r in range(rows):
        changed = _norm(grid.GetCellValue(r, col_new_path)) != _norm(before[r][col_new_path])
        if changed:
            changed_count += 1
        for c in range(cols):
            if c == col_new_path:
                continue
            target = ("" if changed else before[r][c]) if c == col_result else before[r][c]
            if grid.GetCellValue(r, c) != target:
                grid.SetCellValue(r, c, target)
    return changed_count

