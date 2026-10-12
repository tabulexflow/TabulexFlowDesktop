# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import logging

_logger = None

def get_logger():
    global _logger
    if _logger is None:
        try:
            from tfp_utils.tfp_logger import setup_tool_logger
            _logger = setup_tool_logger('TabulexDocCreator')
        except Exception as e:
            print(f"Failed to initialize logger: {e}")
            _logger = logging.getLogger('TabulexDocCreator')
            _logger.setLevel(logging.INFO)  # B6-2：兜底级别至少 INFO（原为 DEBUG，同 A6-3）
            _logger.propagate = False
    return _logger

def clear_log():
    global _logger
    if _logger is not None:
        for handler in _logger.handlers[:]:
            _logger.removeHandler(handler)
        _logger = None

def log_info(message):
    logger = get_logger()
    if logger:
        logger.info(message)

def log_error(message):
    logger = get_logger()
    if logger:
        logger.error(message)

def log_warning(message):
    logger = get_logger()
    if logger:
        logger.warning(message)

def log_debug(message):
    logger = get_logger()
    if logger:
        logger.debug(message)
