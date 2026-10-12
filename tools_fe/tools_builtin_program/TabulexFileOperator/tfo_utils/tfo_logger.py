# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import logging
import os
import re
from pathlib import Path

_logger = None

# A6-2 安全修复：日志路径脱敏开关——直接开启（无需用户选择）
# 该常量即"开启参数"：可通过环境变量 TFP_LOG_PATH_MASKING=0 关闭（默认开启）
_PATH_MASKING_ENABLED = os.environ.get("TFP_LOG_PATH_MASKING", "1") not in ("0", "false", "False")

_HOME_PREFIX_RE = None


def _get_home_prefix_re():
    """编译当前用户主目录前缀正则（含边界，避免误替换 /home/user2 类长路径）

    覆盖 POSIX（/home/<user>、/Users/<user>）与 Windows（C:\\Users\\<user>）。
    """
    global _HOME_PREFIX_RE
    if _HOME_PREFIX_RE is not None:
        return _HOME_PREFIX_RE
    try:
        home = os.path.normpath(Path.home())
    except Exception:
        home = os.path.normpath(os.path.expanduser("~"))
    if len(home) <= 1:
        # 异常兜底（主目录为根/单字符等），正则永不匹配
        _HOME_PREFIX_RE = re.compile(r"(?!x)x")
        return _HOME_PREFIX_RE
    escaped = re.escape(home)
    if os.name == 'nt':
        _HOME_PREFIX_RE = re.compile(escaped + r"(?=[\\/]|$)", re.IGNORECASE)
    else:
        _HOME_PREFIX_RE = re.compile(escaped + r"(?=/|$)")
    return _HOME_PREFIX_RE


def _mask_paths(message):
    """对日志消息中的用户主目录路径脱敏（A6-2 安全修复）

    将当前用户主目录及其下路径统一替换为 <home> 占位符，
    避免用户名与用户目录结构随日志落盘；默认直接开启，无需用户选择。
    """
    if not _PATH_MASKING_ENABLED or not isinstance(message, str):
        return message
    try:
        return _get_home_prefix_re().sub("<home>", message)
    except Exception:
        return message


def get_logger():
    global _logger
    if _logger is None:
        try:
            from tfp_utils.tfp_logger import setup_tool_logger
            _logger = setup_tool_logger('TabulexFileOperator')
        except Exception as e:
            print(f"Failed to initialize logger: {e}")
            _logger = logging.getLogger('TabulexFileOperator')
            _logger.setLevel(logging.INFO)  # A6-3：兜底级别至少 INFO（原为 DEBUG）
            _logger.propagate = False
    return _logger


def log_info(message):
    logger = get_logger()
    if logger:
        logger.info(_mask_paths(message))


def log_error(message):
    logger = get_logger()
    if logger:
        logger.error(_mask_paths(message))


def log_warning(message):
    logger = get_logger()
    if logger:
        logger.warning(_mask_paths(message))


def log_debug(message):
    logger = get_logger()
    if logger:
        logger.debug(_mask_paths(message))


def log_file_operation(operation, old_path, new_path, match_name,
                       success=True, skipped=False, error=None, row_index=None):
    """记录单个文件操作的执行结果（成功、失败、跳过都记录，便于复现与定位）

    Args:
        operation: 操作名（如"移动"/"复制"/"压缩"/"解压"/"删除"/"去重"）
        old_path:  该行"旧路径"
        new_path:  该行"新路径"
        match_name: 该行"匹配名"
        success:   True=成功；False=失败
        skipped:   True=按冲突策略跳过（未实际改动文件系统）
        error:     失败时的错误信息
        row_index: Grid 行号（可选）
    """
    if skipped:
        status = "跳过"
    elif success:
        status = "成功"
    else:
        status = "失败"
    parts = [f"[{operation}]"]
    if row_index is not None:
        parts.append(f"行{row_index}")
    parts.append(status)
    parts.append(f"old={old_path!r}")
    parts.append(f"new={new_path!r}")
    parts.append(f"match={match_name!r}")
    if error is not None:
        parts.append(f"error={error!r}")
    message = " ".join(parts)
    if success or skipped:
        log_info(message)
    else:
        log_error(message)
