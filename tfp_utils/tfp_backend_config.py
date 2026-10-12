# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import re
import sys
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any


def _mask_url(url: str) -> str:
    """URL脱敏：隐藏IP地址的中间段，保留域名"""
    import re
    # 匹配 http(s)://数字IP:端口
    masked = re.sub(
        r'(https?://)(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(:\d+)?',
        lambda m: f"{m.group(1)}{m.group(2)}.{m.group(3)}.*.*{m.group(6) or ''}",
        url
    )
    return masked

try:
    import requests
except ImportError:
    requests = None

from build_mode import (
    IS_PRODUCTION_BUILD,
    IS_LOCAL_TEST_BUILD,
    BACKEND_HOST,
    BACKEND_PORT,
    BACKEND_PROTOCOL,
    BACKEND_BASE_URL,
    LOCAL_HOST_IP,
    LOCAL_HOST_NAME,
)

from .tfp_api_paths import API_V1_PREFIX

logger = logging.getLogger(__name__)


def _is_dev_host(host: str) -> bool:
    """判断是否为开发环境主机（本地或内网IP），开发环境允许HTTP"""
    host_lower = host.lower()
    if host_lower in (LOCAL_HOST_NAME, LOCAL_HOST_IP, "::1"):
        return True
    try:
        import ipaddress
        return ipaddress.ip_address(host).is_private
    except (ValueError, ImportError):
        return False


# L-4 加固（2026-09-01）：健康检查端点白名单。
# 必须以 / 开头且仅含安全字符；前缀锚定 + 排除 @ : \\ ? 等构造，防止 userinfo/端口/协议导致 host 逃逸
_HEALTH_ENDPOINT_RE = re.compile(r"^/[a-zA-Z0-9/_\-\.]+$")


def _is_valid_health_endpoint(endpoint: str) -> bool:
    """健康检查端点白名单校验（fail-closed）。

    合法示例：/api/v1/health、/api/v1/health/v2、/ping-1。
    `@evil.com/`、`http://...`、`//evil.com:80/` 等用户名/端口/协议构造一律拒绝。
    """
    if not isinstance(endpoint, str):
        return False
    return bool(_HEALTH_ENDPOINT_RE.match(endpoint))


class TFP_BackendConfigManager:
    
    _instance: Optional['TFP_BackendConfigManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._config: Dict[str, Any] = {}
        self._available_url: Optional[str] = None
        self._all_urls: List[str] = []
        self._config_file_path: Optional[Path] = None
        self._backend_reachable: bool = False
        
        self._load_config()
        self._detect_available_backend()
    
    @classmethod
    def get_instance(cls) -> 'TFP_BackendConfigManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        if cls._instance is not None:
            cls._instance._initialized = False
            cls._instance = None
    
    def _get_config_file_path(self) -> Path:
        config_filename = 'backend_config.json'
        
        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            config_paths = [
                exe_dir / 'config' / config_filename,
                exe_dir / config_filename,
            ]
        else:
            project_root = Path(__file__).parent.parent
            config_paths = [
                project_root / 'config' / config_filename,
                project_root / config_filename,
            ]
        
        for path in config_paths:
            if path.exists():
                logger.info(f"Config file found: {path}")
                return path
        
        if getattr(sys, 'frozen', False):
            default_path = Path(sys.executable).parent / 'config' / config_filename
        else:
            default_path = Path(__file__).parent.parent / 'config' / config_filename
        
        logger.warning(f"Config file not found; will use default path: {default_path}")
        return default_path
    
    def _load_config(self):
        # 生产模式（非本地测试构建）：后端地址固化，忽略本地配置文件
        if IS_PRODUCTION_BUILD and not IS_LOCAL_TEST_BUILD:
            self._config = self._get_default_config()
            self._config['description'] = '后端服务URL配置 - 生产模式（已固化，忽略本地配置）'
            self._all_urls = [BACKEND_BASE_URL]
            logger.info(f"Production mode: backend address is fixed {_mask_url(BACKEND_BASE_URL)}, ignoring config file")
            return

        # 本地测试构建：打包产物但连接本地后端，允许读取配置文件中的辅助参数
        if IS_LOCAL_TEST_BUILD:
            try:
                self._config_file_path = self._get_config_file_path()
                if self._config_file_path.exists():
                    with open(self._config_file_path, 'r', encoding='utf-8') as f:
                        self._config = json.load(f)
                    logger.info(f"Local test build: config file loaded: {self._config_file_path}")
                else:
                    self._config = self._get_default_config()
                    self._save_config()
            except Exception as e:
                logger.error(f"Local test build: failed to load config file: {e}", exc_info=True)
                self._config = self._get_default_config()
            self._all_urls = [BACKEND_BASE_URL]
            logger.info(f"Local test build: backend address {_mask_url(BACKEND_BASE_URL)}")
            return

        try:
            self._config_file_path = self._get_config_file_path()

            if self._config_file_path.exists():
                with open(self._config_file_path, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                logger.info(f"Config file loaded successfully: {self._config_file_path}")
            else:
                logger.warning("Config file does not exist; using default config")
                self._config = self._get_default_config()
                self._save_config()

            # 后端地址完全由 main.py 的 BACKEND_HOST/BACKEND_PORT 决定（开发模式），
            # 配置文件仅保留健康检查端点、超时等辅助参数，不再支持多候选后端列表
            self._all_urls = [BACKEND_BASE_URL]
            logger.info(f"Development mode backend address: {_mask_url(BACKEND_BASE_URL)}")

        except Exception as e:
            logger.error(f"Failed to load config file: {e}", exc_info=True)
            self._config = self._get_default_config()
            self._all_urls = [BACKEND_BASE_URL]
    
    def _get_default_config(self) -> Dict[str, Any]:
        return {
            'version': '1.0.0',
            'description': '后端服务配置 - 自动生成',
            'health_check_endpoint': API_V1_PREFIX + '/health',
            'timeout': 5,
            'retry_interval_ms': 1000,
        }
    
    def _save_config(self):
        try:
            if self._config_file_path:
                self._config_file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._config_file_path, 'w', encoding='utf-8') as f:
                    json.dump(self._config, f, ensure_ascii=False, indent=2)
                logger.info(f"Config saved to: {self._config_file_path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}", exc_info=True)
    
    def _detect_available_backend(self):
        timeout = self._config.get('timeout', 5)
        health_endpoint = self._config.get('health_check_endpoint', API_V1_PREFIX + '/health')
        # L-4（2026-09-01）：本地配置可能被篡改（config/backend_config.json），
        # 读取处校验非法值直接回退默认端点，杜绝拼接后把请求导向任意主机
        if not _is_valid_health_endpoint(health_endpoint):
            logger.warning(f"Invalid health_check_endpoint in config, falling back to default: {health_endpoint!r}")
            health_endpoint = API_V1_PREFIX + '/health'

        url = BACKEND_BASE_URL.rstrip('/')
        logger.info(f"Checking backend availability: {_mask_url(url)}")

        self._backend_reachable = self._check_health(url, health_endpoint, timeout)
        if self._backend_reachable:
            logger.info(f"✅ Successfully connected to backend service: {_mask_url(url)}")
        else:
            logger.warning(f"⚠️ Backend health check failed; still using the configured backend address: {_mask_url(url)}")

        # 后端地址唯一（来自 main.py 硬编码），无论健康检查结果如何均采用该地址
        self._available_url = url
    
    def is_backend_reachable(self) -> bool:
        """后端是否可达（启动/刷新时的健康检查结果）。

        用于登录门控：后端不可达时（如开源预览阶段未部署后端），
        免费内置工具免登录直接可用；后端可达时恢复登录要求。
        """
        return self._backend_reachable
    
    def _check_health(self, url: str, endpoint: str, timeout: int = 5) -> bool:
        if requests is None:
            logger.warning("requests library is not installed; skipping health check")
            return True

        # L-4 fail-closed（2026-09-01）：端点白名单校验，非法值在拼接 URL 前直接拒绝，
        # 即使有其他调用入口传入被篡改的 endpoint 也不会发出请求
        if not _is_valid_health_endpoint(endpoint):
            logger.warning(f"Rejected invalid health check endpoint: {endpoint!r}")
            return False

        try:
            full_url = f"{url}{endpoint}"
            response = requests.get(
                full_url,
                timeout=timeout,
                headers={'Accept': 'application/json'}
            )
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get('status') == 'healthy':
                        return True
                except (ValueError, KeyError):
                    pass
                # 响应格式校验：必须返回 status=healthy
                logger.warning(f"Health check response format does not meet requirements (missing status=healthy): {_mask_url(url)}")
                return False
            else:
                logger.warning(f"Backend responded abnormally: {url} (HTTP {response.status_code})")
                return False
                
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Cannot connect to backend: {url} (ConnectionError)")
            return False
        except requests.exceptions.Timeout as e:
            logger.warning(f"Connection timed out: {url} (Timeout after {timeout}s)")
            return False
        except Exception as e:
            logger.warning(f"Health check failed: {url} ({type(e).__name__}: {e})")
            return False
    
    def get_available_url(self) -> str:
        return self._available_url or BACKEND_BASE_URL
    
    def get_all_urls(self) -> List[str]:
        return self._all_urls.copy()
    
    def get_timeout(self) -> int:
        return self._config.get('timeout', 5)
    
    def force_refresh(self):
        logger.info("Forcing backend connection refresh...")
        self._available_url = None
        self._detect_available_backend()
        return self._available_url
    
    def reload_config(self):
        logger.info("Reloading config...")
        self._config = {}
        self._available_url = None
        self._load_config()
        self._detect_available_backend()
    
    def get_config_info(self) -> Dict[str, Any]:
        return {
            'config_file': str(self._config_file_path),
            'available_url': self._available_url,
            'all_urls': self._all_urls,
            'timeout': self._config.get('timeout', 5),
            'version': self._config.get('version', 'unknown')
        }


def get_backend_manager() -> TFP_BackendConfigManager:
    return TFP_BackendConfigManager.get_instance()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("BackendConfigManager Test")
    print("=" * 60)
    
    manager = get_backend_manager()
    
    print("\n📋 Config info:")
    info = manager.get_config_info()
    for key, value in info.items():
        print(f"  {key}: {value}")
    
    print(f"\n✅ Currently available URL: {manager.get_available_url()}")
    print(f"\n📝 All URLs: {manager.get_all_urls()}")
    print(f"\n⏱️  Timeout setting: {manager.get_timeout()}s")
    print(f"\n🔌 Backend reachable: {manager.is_backend_reachable()}")
