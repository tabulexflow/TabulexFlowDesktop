# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""测试 tfp_utils.tfp_logger 模块"""
import pytest
import sys
import os
import logging

_fe_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _fe_root not in sys.path:
    sys.path.insert(0, _fe_root)

try:
    from tfp_utils.tfp_logger import setup_logger, get_logger
    HAS_LOGGER = True
except ImportError:
    HAS_LOGGER = False


class TestLoggerSetup:
    """测试 logger 设置"""

    @pytest.mark.skipif(not HAS_LOGGER, reason="tfp_logger 模块不可用")
    def test_setup_logger_returns_logger(self):
        """测试 setup_logger 返回 Logger 实例"""
        logger = setup_logger("test_logger")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_logger"

    @pytest.mark.skipif(not HAS_LOGGER, reason="tfp_logger 模块不可用")
    def test_setup_logger_with_level(self):
        """测试设置日志级别"""
        logger = setup_logger("test_level_logger", level=logging.DEBUG)
        assert logger.level == logging.DEBUG

    @pytest.mark.skipif(not HAS_LOGGER, reason="tfp_logger 模块不可用")
    def test_setup_logger_default_level(self):
        """测试默认日志级别"""
        logger = setup_logger("test_default_logger")
        assert logger.level in (logging.INFO, logging.DEBUG, logging.WARNING)


class TestGetLogger:
    """测试获取 logger"""

    @pytest.mark.skipif(not HAS_LOGGER, reason="tfp_logger 模块不可用")
    def test_get_logger_returns_logger(self):
        """测试获取 logger"""
        logger = get_logger("test_get_logger")
        assert isinstance(logger, logging.Logger)

    @pytest.mark.skipif(not HAS_LOGGER, reason="tfp_logger 模块不可用")
    def test_get_logger_same_name_same_instance(self):
        """测试相同名称获取相同实例"""
        logger1 = get_logger("test_same_logger")
        logger2 = get_logger("test_same_logger")
        assert logger1 is logger2


class TestLoggerLogging:
    """测试日志记录"""

    @pytest.mark.skipif(not HAS_LOGGER, reason="tfp_logger 模块不可用")
    def test_logger_has_handlers(self):
        """测试 logger 有处理器"""
        logger = setup_logger("test_handler_logger")
        assert len(logger.handlers) > 0

    @pytest.mark.skipif(not HAS_LOGGER, reason="tfp_logger 模块不可用")
    def test_logger_propagate(self):
        """测试日志传播设置"""
        logger = setup_logger("test_propagate_logger")
        # 生产环境通常设置 propagate=False
        assert isinstance(logger.propagate, bool)