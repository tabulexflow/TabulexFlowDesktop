# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""测试 tfp_utils.tfp_backend_config 模块"""
import pytest
import sys
import os

_fe_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _fe_root not in sys.path:
    sys.path.insert(0, _fe_root)

from build_mode import LOCAL_HOST_IP, LOCAL_HOST_NAME

from tfp_utils.tfp_backend_config import (
    _is_dev_host,
    _mask_url,
    _is_valid_health_endpoint,
    TFP_BackendConfigManager,
    BACKEND_HOST,
    BACKEND_PORT,
    BACKEND_BASE_URL,
)


class TestIsDevHost:
    """测试开发环境主机判断"""

    def test_localhost(self):
        assert _is_dev_host(LOCAL_HOST_NAME) is True

    def test_loopback(self):
        assert _is_dev_host(LOCAL_HOST_IP) is True

    def test_private_ip(self):
        assert _is_dev_host("192.168.1.1") is True
        assert _is_dev_host("10.0.0.1") is True
        assert _is_dev_host("172.16.0.1") is True

    def test_public_ip(self):
        assert _is_dev_host("8.8.8.8") is False
        assert _is_dev_host("www.example.com") is False


class TestMaskUrl:
    """测试URL脱敏"""

    def test_mask_ip_url(self):
        masked = _mask_url("http://192.168.1.100:8080")
        assert "192.168" in masked
        assert "*.*" in masked
        assert "100" not in masked.split("*.*")[1] if "*.*" in masked else True

    def test_mask_domain_url(self):
        masked = _mask_url("https://www.example.com:443")
        # 域名不应被脱敏
        assert "example.com" in masked


class TestBackendConfig:
    """测试后端配置常量"""

    def test_backend_host_defined(self):
        assert BACKEND_HOST is not None
        assert isinstance(BACKEND_HOST, str)
        assert len(BACKEND_HOST) > 0

    def test_backend_port_defined(self):
        assert BACKEND_PORT is not None
        assert isinstance(BACKEND_PORT, int)

    def test_backend_base_url_format(self):
        assert BACKEND_BASE_URL.startswith("http")
        assert "://" in BACKEND_BASE_URL
        assert str(BACKEND_PORT) in BACKEND_BASE_URL or BACKEND_HOST in BACKEND_BASE_URL


class TestBackendConfigManagerSingleton:
    """测试 TFP_BackendConfigManager 单例模式"""

    def test_singleton(self):
        mgr1 = TFP_BackendConfigManager.get_instance()
        mgr2 = TFP_BackendConfigManager.get_instance()
        assert mgr1 is mgr2

    def test_reset_instance(self):
        TFP_BackendConfigManager.reset_instance()
        mgr = TFP_BackendConfigManager.get_instance()
        assert mgr is not None
        TFP_BackendConfigManager.reset_instance()

    def test_get_available_url(self):
        TFP_BackendConfigManager.reset_instance()
        mgr = TFP_BackendConfigManager.get_instance()
        url = mgr.get_available_url()
        assert isinstance(url, str)
        assert url.startswith("http")
        TFP_BackendConfigManager.reset_instance()

    def test_get_all_urls(self):
        TFP_BackendConfigManager.reset_instance()
        mgr = TFP_BackendConfigManager.get_instance()
        urls = mgr.get_all_urls()
        assert isinstance(urls, list)
        assert len(urls) > 0
        TFP_BackendConfigManager.reset_instance()

    def test_single_backend_url(self):
        # 唯一后端地址来自 main.py 硬编码
        TFP_BackendConfigManager.reset_instance()
        mgr = TFP_BackendConfigManager.get_instance()
        assert mgr.get_all_urls() == [BACKEND_BASE_URL]
        assert mgr.get_available_url() == BACKEND_BASE_URL
        TFP_BackendConfigManager.reset_instance()

    def test_get_timeout(self):
        TFP_BackendConfigManager.reset_instance()
        mgr = TFP_BackendConfigManager.get_instance()
        timeout = mgr.get_timeout()
        assert isinstance(timeout, int)
        assert timeout > 0
        TFP_BackendConfigManager.reset_instance()

    def test_get_config_info(self):
        TFP_BackendConfigManager.reset_instance()
        mgr = TFP_BackendConfigManager.get_instance()
        info = mgr.get_config_info()
        assert isinstance(info, dict)
        assert 'available_url' in info
        assert 'all_urls' in info
        TFP_BackendConfigManager.reset_instance()


class TestHealthEndpointValidation:
    """L-4（2026-09-01）：健康检查端点白名单校验"""

    # ========== _is_valid_health_endpoint ==========

    @pytest.mark.parametrize("endpoint", [
        "/api/v1/health",
        "/api/v1/health/v2",
        "/ping-1",
        "/a.b_c-d/0",
    ])
    def test_valid_endpoints(self, endpoint):
        assert _is_valid_health_endpoint(endpoint) is True

    @pytest.mark.parametrize("endpoint", [
        "@evil.com/",          # userinfo 语法逃逸 host
        "http://evil.com/x",   # 协议构造
        "//evil.com:80/x",     # 端口/协议构造
        "/evil.com:8443/x",    # 端口语法
        "api/health",          # 不以 / 开头
        "/…",                  # 非 ASCII
        "",                    # 空串
        None,                  # 非字符串
        123,                   # 非字符串
    ])
    def test_invalid_endpoints(self, endpoint):
        assert _is_valid_health_endpoint(endpoint) is False

    # ========== _check_health fail-closed ==========

    def test_check_health_rejects_invalid_endpoint_without_request(self, monkeypatch):
        # 非法端点：即使 requests.get 可用，也不应发出任何请求（fail-closed）
        from tfp_utils import tfp_backend_config as bc
        called = []
        monkeypatch.setattr(bc.requests, "get", lambda *a, **k: called.append(a) or object())
        # 隔离构造函数的后端探测副作用（构造期会请求合法默认端点，与本测试无关）
        monkeypatch.setattr(bc.TFP_BackendConfigManager, "_detect_available_backend", lambda self: None)
        mgr = TFP_BackendConfigManager()
        mgr._backend_reachable = False
        assert mgr._check_health(BACKEND_BASE_URL, "@evil.com/") is False
        assert called == []  # 无任何请求发出

    # ========== _detect_available_backend 非法配置回退默认 ==========

    def test_detect_available_backend_fallback_on_invalid_endpoint(self, monkeypatch):
        from tfp_utils import tfp_backend_config as bc

        class _Resp:
            status_code = 200
            def json(self):
                return {"status": "healthy"}

        hits = []
        monkeypatch.setattr(bc.requests, "get", lambda url, **k: hits.append(url) or _Resp())
        TFP_BackendConfigManager.reset_instance()
        mgr = TFP_BackendConfigManager.get_instance()
        mgr._config = {"health_check_endpoint": "@evil.com/", "timeout": 5}
        try:
            mgr._detect_available_backend()
        finally:
            TFP_BackendConfigManager.reset_instance()
        # 应回退默认端点拼接请求（BACKEND_BASE_URL + /api/v1/health），而非 "@evil.com/"
        assert hits and all(BACKEND_BASE_URL.rstrip("/") + "/api/v1/health" in h for h in hits)
        assert not any("@evil.com" in h for h in hits)
