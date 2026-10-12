# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_LOG_DIR = None
_LOG_DIR_INITIALIZED = False
_CURRENT_LOG_DATE = None


def _chmod_quiet(path, mode=0o600) -> None:
    """将日志文件/目录权限收紧（H-2 文件 0600 / M-4 目录 0700；失败仅告警，不阻断）"""
    try:
        os.chmod(path, mode)
    except Exception as e:
        print(f"Failed to set permissions {oct(mode)}: {path}: {e}")


# M-4 加固：日志敏感字段脱敏模式（输出前自动打码，避免 password/token/凭据落盘）
_SENSITIVE_PATTERNS = (
    # Authorization: Bearer <token>（任意分隔形式）
    (re.compile(r'(Authorization\s*[:=]\s*Bearer\s+)[^\s,;]+', re.IGNORECASE), r'\1***'),
    # token=xxx / token:xxx / session_token=xxx（覆盖 query、JSON、表单等场景）
    (re.compile(r'\b(token|session_token)\s*[=:]\s*[^\s,;&]+', re.IGNORECASE), r'\1=***'),
    # password=xxx / password: xxx
    (re.compile(r'\bpassword\s*[=:]\s*[^\s,;&]+', re.IGNORECASE), r'password=***'),
    # X-User-ID 不视为敏感，但 Refresh Token / api_key 也打码
    (re.compile(r'\b(api[_-]?key|refresh_token|access_token)\s*[=:]\s*[^\s,;&]+', re.IGNORECASE), r'\1=***'),
)


class SafeFormatter(logging.Formatter):
    """M-4 加固：日志格式化器——格式化输出前对常见敏感字段脱敏（***）。

    覆盖：Authorization Bearer 凭据、token/session_token/password/
    api_key/refresh_token 等键值。正常业务消息（无上述键值）不受影响。
    """

    def format(self, record):
        message = super().format(record)
        for pattern, repl in _SENSITIVE_PATTERNS:
            message = pattern.sub(repl, message)
        return message


def get_log_dir() -> Path:
    global _LOG_DIR, _LOG_DIR_INITIALIZED
    
    if _LOG_DIR_INITIALIZED:
        return _LOG_DIR
    
    _LOG_DIR_INITIALIZED = True
    
    if getattr(sys, 'frozen', False):
        _LOG_DIR = Path(sys.executable).parent / 'logs'
    else:
        _LOG_DIR = Path(__file__).parent.parent / 'logs'
    
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        _chmod_quiet(_LOG_DIR, 0o700)  # M-4 加固：日志目录收紧 0700
    except Exception as e:
        print(f"Failed to create log directory: {e}")
        _LOG_DIR = Path.cwd() / 'logs'
        try:
            _LOG_DIR.mkdir(parents=True, exist_ok=True)
            _chmod_quiet(_LOG_DIR, 0o700)  # M-4 加固：回退目录同样收紧 0700
        except OSError:
            _LOG_DIR = Path.cwd()
    
    return _LOG_DIR


def _should_reset_log(log_file: Path) -> bool:
    global _CURRENT_LOG_DATE
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    if _CURRENT_LOG_DATE != today:
        _CURRENT_LOG_DATE = today
        return True
    
    if not log_file.exists():
        return False
    
    return False


def get_logger(
    name: str,
    level: int = logging.DEBUG,
    log_file_name: Optional[str] = None,
    with_console: bool = False
) -> logging.Logger:
    logger = logging.getLogger(name)
    
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    if log_file_name is None:
        log_file_name = 'frontend_log.log'
    
    log_dir = get_log_dir()
    log_file = log_dir / log_file_name
    
    if _should_reset_log(log_file):
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"=== Log started at {datetime.now().isoformat()} ===\n")
            _chmod_quiet(log_file)  # H-2 加固：日志文件 0600
        except Exception as e:
            print(f"Failed to reset log file: {e}")
    
    try:
        file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
        file_handler.setLevel(level)
        # M-4 加固：统一使用 SafeFormatter，输出前对敏感字段（Bearer/token/password 等）脱敏
        file_formatter = SafeFormatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        _chmod_quiet(log_file)  # H-2 加固：日志文件 0600（含已存在文件的权限收紧）
    except Exception as e:
        print(f"Failed to create file handler for {name}: {e}")
    
    if with_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = SafeFormatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    logger.propagate = False
    
    return logger


def setup_main_logger(level: int = logging.INFO) -> logging.Logger:
    return get_logger('TabulexFlow', level=level, log_file_name='frontend_log.log')


def setup_tool_logger(tool_ident: str, level: int = logging.DEBUG, with_console: bool = False) -> logging.Logger:
    safe_ident = tool_ident.lower().replace(' ', '_').replace('-', '_')
    log_file_name = f'{safe_ident}_log.log'
    return get_logger(tool_ident, level=level, log_file_name=log_file_name, with_console=with_console)


def clear_logger_handlers(name: str) -> None:
    logger = logging.getLogger(name)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)


class DualLogger:
    def __init__(self, log_file: Path, original_stream):
        self.log_file = log_file
        self.original_stream = original_stream
        self.stream_available = original_stream is not None and hasattr(original_stream, 'write')
    
    def write(self, message):
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(message)
        except Exception:
            pass
        
        if self.stream_available:
            try:
                self.original_stream.write(message)
            except Exception:
                self.stream_available = False
    
    def flush(self):
        if self.stream_available:
            try:
                self.original_stream.flush()
            except Exception:
                self.stream_available = False


def setup_stdout_redirect(log_file_prefix: str = 'frontend_log') -> Path:
    log_dir = get_log_dir()
    log_file = log_dir / f'{log_file_prefix}.log'
    
    if _should_reset_log(log_file):
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"=== Log started at {datetime.now().isoformat()} ===\n")
            _chmod_quiet(log_file)  # H-2 加固：日志文件 0600
        except Exception as e:
            print(f"Failed to reset log file: {e}")
    
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    stdout_available = original_stdout is not None and hasattr(original_stdout, 'write')
    stderr_available = original_stderr is not None and hasattr(original_stderr, 'write')
    
    if stdout_available:
        sys.stdout = DualLogger(log_file, original_stdout)
    if stderr_available:
        sys.stderr = DualLogger(log_file, original_stderr)
    
    return log_file
