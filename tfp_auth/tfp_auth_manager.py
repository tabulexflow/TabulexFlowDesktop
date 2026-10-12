# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import sys
import json
import logging
import threading
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable, List, Tuple
from dataclasses import dataclass, field
import wx
from .tfp_constants import (
    USER_TYPE_HIERARCHY,
    USER_TYPE_VALUES,
    DISPLAY_TIER_VALUES,
    DISPLAY_TIER_COLORS,
    DISPLAY_TIER_LABELS,
    normalize_user_type,
)

logger = logging.getLogger(__name__)

if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from tfp_utils.tfp_secure_storage import TFP_AuthTokenStorage
    SECURE_STORAGE_AVAILABLE = True
except ImportError:
    SECURE_STORAGE_AVAILABLE = False
    logger.warning("Secure storage module unavailable; using fallback")

from tfp_utils.tfp_api_paths import API_V1_PREFIX
from build_mode import IS_PRODUCTION_BUILD, IS_LOCAL_TEST_BUILD, BACKEND_BASE_URL, LOCAL_HOST_IP, LOCAL_HOST_NAME


def _is_private_ip(hostname: str) -> bool:
    try:
        import ipaddress
        ip = ipaddress.ip_address(hostname)
        return ip.is_private
    except (ValueError, ImportError):
        return False


def _is_local_url(url: str) -> bool:
    """判断URL是否指向本地地址（回环地址或内网私有IP）"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if hostname.lower() in (LOCAL_HOST_NAME, LOCAL_HOST_IP, "::1"):
        return True
    return _is_private_ip(hostname)


def _is_dev_host(host: str) -> bool:
    """判断是否为开发环境主机（本地或内网IP），开发环境允许HTTP"""
    h = host.strip()
    if ":" in h and not h.startswith("["):
        h = f"[{h}]"  # IPv6 地址需加方括号才能被 urlparse 正确解析
    return _is_local_url(f"http://{h}")


def _get_backend_default_url():
    try:
        # 直接读取已加载的 __main__（编译产物或 python main.py 均为 main.py），
        # 避免顶层 `import main` 把主模块重复执行（在 PyInstaller 单文件里会造成二次初始化/资源重复）
        main_module = sys.modules.get('__main__')
        if main_module and hasattr(main_module, 'BACKEND_HOST') and hasattr(main_module, 'BACKEND_PORT'):
            host = main_module.BACKEND_HOST
            scheme = "http" if _is_dev_host(host) else "https"
            return f"{scheme}://{host}:{main_module.BACKEND_PORT}"
    except Exception:
        pass
    return BACKEND_BASE_URL

_DEFAULT_BACKEND_URL = _get_backend_default_url()


def _extract_trusted_host():
    try:
        from urllib.parse import urlparse
        parsed = urlparse(_DEFAULT_BACKEND_URL)
        return parsed.hostname or ""
    except Exception:
        return ""

_TRUSTED_BACKEND_HOST = _extract_trusted_host()


@dataclass
class TFP_UserInfo:
    """前端用户信息（支持 tool_subscriptions + display_tier）

    - user_type 仅 3 值：individual / enterprise / platform（账户身份）
    - tool_subscriptions：用户可访问的订购列表（个人 + 所在企业共享）
    - display_tier：UI 派生显示等级（free/premium/enterprise/enterprise_admin/platform）
    - display_tier_color：徽章颜色（gray/gold/blue/red）
    """
    id: int = 0
    username: str = ""
    email: str = ""
    display_name: str = ""
    user_type: str = "individual"
    company_id: Optional[int] = None
    company_role: Optional[str] = None
    status: str = "active"
    created_at: str = ""
    last_login_at: str = ""
    # 新增字段
    tool_subscriptions: List[Dict[str, Any]] = field(default_factory=list)
    display_tier: str = "free"
    display_tier_color: str = "gray"

    def is_individual(self) -> bool:
        return self.user_type == "individual"

    def is_enterprise(self) -> bool:
        return self.user_type == "enterprise"

    def is_platform(self) -> bool:
        return self.user_type == "platform"

    def is_company_admin(self) -> bool:
        return self.company_role == "admin"

    def has_any_tool_subscription(self) -> bool:
        """是否拥有任意 active 工具订购（用于派生 Premium 显示等级）"""
        return bool(self.tool_subscriptions)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name,
            "user_type": self.user_type,
            "status": self.status,
            "created_at": self.created_at,
            "last_login_at": self.last_login_at,
            "tool_subscriptions": self.tool_subscriptions,
            "display_tier": self.display_tier,
            "display_tier_color": self.display_tier_color,
        }
        if self.company_id:
            result["company_id"] = self.company_id
            result["company_role"] = self.company_role
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TFP_UserInfo':
        if not data:
            return cls()
        raw_user_type = data.get("user_type", "individual")
        user_type = normalize_user_type(raw_user_type)

        # 派生 display_tier（若后端未返回则本地派生）
        display_tier = data.get("display_tier") or ""
        display_tier_color = data.get("display_tier_color") or ""
        if not display_tier:
            subs = data.get("tool_subscriptions") or []
            display_tier, display_tier_color = _derive_display_tier_local(
                user_type, bool(subs), data.get("company_role")
            )

        return cls(
            id=data.get("id", 0),
            username=data.get("username", ""),
            email=data.get("email", ""),
            display_name=data.get("display_name", ""),
            user_type=user_type,
            company_id=data.get("company_id"),
            company_role=data.get("company_role"),
            status=data.get("status", "active"),
            created_at=data.get("created_at", ""),
            last_login_at=data.get("last_login_at", ""),
            tool_subscriptions=data.get("tool_subscriptions") or [],
            display_tier=display_tier,
            display_tier_color=display_tier_color,
        )


def _derive_display_tier_local(user_type: str, has_any_subscription: bool,
                                company_role: Optional[str] = None) -> Tuple[str, str]:
    """本地派生 UI 显示等级 + 徽章颜色（与后端 derive_display_tier 保持一致）

    返回 (display_tier, display_tier_color)
    """
    user_type = normalize_user_type(user_type)
    if user_type == "platform":
        tier = "platform"
    elif user_type == "enterprise":
        tier = "enterprise_admin" if company_role == "admin" else "enterprise"
    else:  # individual
        tier = "premium" if has_any_subscription else "free"
    color = DISPLAY_TIER_COLORS.get(tier, "gray")
    return tier, color


def mask_display_name(name: str) -> str:
    """状态栏用户名打码（平台用户隐私保护，仅用于底部状态栏显示）：
    1~2 字保留 1 字，3~5 字保留 2 字，>5 字保留 3 字，其余字符以 * 代替。

    注意：本函数与 TabulexBomComparator tbc_exe_auth_manager.mask_display_name 保持实现一致。
    """
    if not name:
        return name
    if len(name) <= 2:
        return name[:1] + "*"
    if len(name) <= 5:
        return name[:2] + "*" * (len(name) - 2)
    return name[:3] + "*" * (len(name) - 3)


# 工具集 → 工具映射
# 当前仅 TFP_CORE 一个工具集，包含 TabulexBomComparator 和 PalletLayout
_TOOLKIT_TOOLS_MAP: Dict[str, List[str]] = {
    "TFP_CORE": ["TabulexBomComparator", "PalletLayout"],
}


def _toolkit_contains_tool(toolkit_id: Optional[str], tool_ident: str) -> bool:
    """检查某工具集是否包含某工具（本地映射，用于前端权限判断的快速回退）

    注意：权威判断应由后端 tool_subscriptions + toolkit_tools 表完成。
    此函数仅用于前端在已获取 tool_subscriptions 后的本地匹配。
    """
    if not toolkit_id or not tool_ident:
        return False
    tools = _TOOLKIT_TOOLS_MAP.get(toolkit_id, [])
    return tool_ident in tools


@dataclass
class TFP_LicenseInfo:
    id: int = 0
    user_id: int = 0
    license_type: str = "free"
    features: List[str] = field(default_factory=list)
    max_operations_per_day: int = 100
    max_exports_per_day: int = 10
    expiry_date: Optional[str] = None
    is_valid: bool = True
    
    def is_premium(self) -> bool:
        return self.license_type in ("premium", "enterprise")
    
    def has_feature(self, feature: str) -> bool:
        if "unlimited" in self.features:
            return True
        return feature in self.features
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "license_type": self.license_type,
            "features": self.features,
            "max_operations_per_day": self.max_operations_per_day,
            "max_exports_per_day": self.max_exports_per_day,
            "expiry_date": self.expiry_date,
            "is_valid": self.is_valid
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TFP_LicenseInfo':
        if not data:
            return cls()
        return cls(
            id=data.get("id", 0),
            user_id=data.get("user_id", 0),
            license_type=data.get("license_type", "free"),
            features=data.get("features", []),
            max_operations_per_day=data.get("max_operations_per_day", 100),
            max_exports_per_day=data.get("max_exports_per_day", 10),
            expiry_date=data.get("expiry_date"),
            is_valid=data.get("is_valid", True)
        )


@dataclass
class TFP_CompanyInfo:
    id: int = 0
    company_name: str = ""
    company_code: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    address: str = ""
    license_count: int = 1
    used_license_count: int = 0
    license_type: str = "enterprise"
    license_expiry_date: Optional[str] = None
    status: str = "active"
    created_at: str = ""
    updated_at: Optional[str] = None
    
    def is_active(self) -> bool:
        return self.status == "active"
    
    def has_available_license(self) -> bool:
        return self.used_license_count < self.license_count
    
    def available_licenses(self) -> int:
        return max(0, self.license_count - self.used_license_count)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "company_name": self.company_name,
            "company_code": self.company_code,
            "contact_email": self.contact_email,
            "contact_phone": self.contact_phone,
            "address": self.address,
            "license_count": self.license_count,
            "used_license_count": self.used_license_count,
            "available_licenses": self.available_licenses(),
            "license_type": self.license_type,
            "license_expiry_date": self.license_expiry_date,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TFP_CompanyInfo':
        if not data:
            return cls()
        return cls(
            id=data.get("id", 0),
            company_name=data.get("company_name", ""),
            company_code=data.get("company_code", ""),
            contact_email=data.get("contact_email", ""),
            contact_phone=data.get("contact_phone", ""),
            address=data.get("address", ""),
            license_count=data.get("license_count", 1),
            used_license_count=data.get("used_license_count", 0),
            license_type=data.get("license_type", "enterprise"),
            license_expiry_date=data.get("license_expiry_date"),
            status=data.get("status", "active"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at")
        )


class TFP_AuthManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self._user: Optional[TFP_UserInfo] = None
        self._license: Optional[TFP_LicenseInfo] = None
        self._session_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

        self._backend_url: str = _DEFAULT_BACKEND_URL
        self._auth_change_callbacks: List[Callable] = []
        
        if SECURE_STORAGE_AVAILABLE:
            try:
                self._secure_storage = TFP_AuthTokenStorage()
                storage_info = self._secure_storage.get_storage_info()
                logger.debug(f"Secure storage enabled: {storage_info['backend']}")
            except Exception as e:
                logger.warning(f"Secure storage init failed, using fallback: {e}")
                self._secure_storage = None
        else:
            self._secure_storage = None
        
        self._load_saved_session()
        
        self._token_refresh_lock = threading.Lock()
        self._token_refreshing = False
    
    @staticmethod
    def _is_trusted_host(url: str) -> bool:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        return hostname == _TRUSTED_BACKEND_HOST

    @property
    def backend_url(self) -> str:
        return self._backend_url

    def set_backend_url(self, url: str):
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme == "http" and not _is_local_url(url):
            logger.warning(f"Refusing to set non-local HTTP backend URL: {url}")
            logger.warning("Production environment must use HTTPS to protect auth Token security")
            return False
        # 生产模式：禁止将后端设置为本地地址（回环或内网IP）
        # 本地测试构建（IS_LOCAL_TEST_BUILD）除外：该模式下 EXE 需连接本地后端
        if IS_PRODUCTION_BUILD and not IS_LOCAL_TEST_BUILD and _is_local_url(url):
            logger.warning(f"Production mode forbids setting backend to local loopback/private address: {url}")
            return False
        # L-3 加固（2026-09-01）：生产模式仅允许唯一可信后端域名，
        # 杜绝 token 被导向任意 HTTPS 主机（当前唯一调用链传 build_mode 固化 URL，此为纵深防御）
        if IS_PRODUCTION_BUILD and not IS_LOCAL_TEST_BUILD and not self._is_trusted_host(url):
            logger.warning(f"Production mode forbids setting backend to untrusted host: {url}")
            return False
        self._backend_url = url
        return True
    
    def _get_auth_url(self, endpoint: str) -> str:
        return f"{self._backend_url}{API_V1_PREFIX}/auth/{endpoint}"
    
    def _get_perm_url(self, endpoint: str) -> str:
        return f"{self._backend_url}{API_V1_PREFIX}/permissions/{endpoint}"

    def _get_enterprise_url(self, endpoint: str) -> str:
        return f"{self._backend_url}{API_V1_PREFIX}/enterprise/{endpoint}"
    
    def _get_headers(self) -> Dict[str, str]:
        self._ensure_token_valid()
        headers = {"Content-Type": "application/json"}
        if self._session_token:
            headers["Authorization"] = f"Bearer {self._session_token}"
        return headers
    
    def _ensure_token_valid(self):
        if not self._session_token or not self._token_expiry:
            return
        
        now = datetime.now()
        if self._token_expiry.tzinfo is not None:
            from datetime import timezone
            now = datetime.now(timezone.utc)
        
        time_until_expiry = self._token_expiry - now
        refresh_threshold = timedelta(minutes=5)
        
        if time_until_expiry <= refresh_threshold and time_until_expiry > timedelta(seconds=0):
            if not self._token_refreshing:
                with self._token_refresh_lock:
                    if not self._token_refreshing:
                        self._token_refreshing = True
                        try:
                            if self._refresh_token:
                                result = self.refresh_session()
                                if not result.get("success"):
                                    logger.warning(f"Token auto-refresh failed: {result.get('message', 'unknown error')}")
                        finally:
                            self._token_refreshing = False
        elif time_until_expiry <= timedelta(seconds=0):
            logger.warning("Token expired")
            if self._refresh_token and not self._token_refreshing:
                with self._token_refresh_lock:
                    if not self._token_refreshing:
                        self._token_refreshing = True
                        try:
                            result = self.refresh_session()
                            if not result.get("success"):
                                logger.warning(f"Token refresh failed, clearing session")
                                self._clear_session()
                        finally:
                            self._token_refreshing = False
            else:
                logger.warning(f"No refresh_token or refresh in progress, clearing session")
                self._clear_session()
    
    def _load_saved_session(self):
        try:
            if self._secure_storage:
                data = self._secure_storage.load_auth_session()
                
                if data:
                    self._session_token = data.get("session_token")
                    self._refresh_token = data.get("refresh_token")
                    
                    expiry_str = data.get("expires_at")
                    if expiry_str:
                        self._token_expiry = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
                    
                    user_data = data.get("user")
                    if user_data:
                        self._user = TFP_UserInfo.from_dict(user_data)
                    
                    license_data = data.get("license")
                    if license_data:
                        self._license = TFP_LicenseInfo.from_dict(license_data)

                    if self._session_token:
                        self._validate_session_async()
            else:
                logger.warning("Secure storage unavailable, cannot load saved session")
                    
        except Exception as e:
            logger.error(f"Failed to load saved session: {e}")
    
    def _save_session(self):
        try:
            data = {
                "session_token": self._session_token,
                "refresh_token": self._refresh_token,
                "expires_at": self._token_expiry.isoformat() if self._token_expiry else None,
                "user": self._user.to_dict() if self._user else None,
                "license": self._license.to_dict() if self._license else None,
            }
            
            if self._secure_storage:
                success = self._secure_storage.save_auth_session(data)
                if not success:
                    logger.error("Failed to securely save session")
            else:
                logger.warning("Secure storage unavailable, cannot save session")
                
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
    
    def _clear_saved_session(self):
        try:
            if self._secure_storage:
                success = self._secure_storage.clear_auth_session()
                if not success:
                    logger.error("Failed to securely clear session")
            else:
                logger.warning("Secure storage unavailable, cannot clear session")
                
        except Exception as e:
            logger.error(f"Failed to clear session: {e}")
    
    def _validate_session_async(self):
        import threading
        thread = threading.Thread(target=self._validate_session, daemon=True)
        thread.start()
    
    def _validate_session(self) -> bool:
        try:
            if self._token_expiry and datetime.now() > self._token_expiry:
                if self._refresh_token:
                    refresh_result = self.refresh_session()
                    if refresh_result.get("success"):
                        return True

                self._clear_session()
                return False

            response = requests.get(
                self._get_auth_url("me"),
                headers=self._get_headers(),
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    # 合并 user + tool_subscriptions + display_tier 到 TFP_UserInfo
                    payload = data.get("data", {}) or {}
                    user_data = dict(payload.get("user", {}) or {})
                    if "tool_subscriptions" in payload:
                        user_data["tool_subscriptions"] = payload.get("tool_subscriptions") or []
                    display_tier = payload.get("display_tier")
                    if isinstance(display_tier, dict):
                        user_data["display_tier"] = display_tier.get("display_tier", "")
                        user_data["display_tier_color"] = display_tier.get("display_tier_color", "")
                    elif isinstance(display_tier, str):
                        user_data["display_tier"] = display_tier
                    license_data = payload.get("license")

                    self._user = TFP_UserInfo.from_dict(user_data)
                    self._license = TFP_LicenseInfo.from_dict(license_data)
                    self._notify_auth_change()
                    return True

            # T7.2 弃用契约：验证端点被弃用（410 API_DEPRECATED）——不静默清会话
            # （避免"莫名被登出"），本地会话保留，弹统一升级提示后返回 False。
            # 不尝试 refresh：端点弃用意味着客户端必须升级，刷新令牌无法解决。
            if response.status_code == 410:
                try:
                    err_body = response.json()
                except Exception:
                    err_body = {}
                if isinstance(err_body, dict) and err_body.get('code') == 'API_DEPRECATED':
                    logger.warning(
                        "Auth endpoint deprecated (410 API_DEPRECATED); session kept locally, upgrade required")
                    self._prompt_api_deprecated_upgrade(err_body)
                    return False

            if self._refresh_token:
                refresh_result = self.refresh_session()
                if refresh_result.get("success"):
                    return True

            self._clear_session()
            return False

        except Exception as e:
            logger.error(f"Failed to validate session: {e}")
            return False

    def _prompt_api_deprecated_upgrade(self, payload):
        """410 弃用契约：提示"客户端版本过旧，请升级"（T7.2）。

        认证服务层不直接持 UI，经 wx.CallAfter 找到主窗口后复用其统一升级
        提示（同启动周期防重复，正文优先取后端 message）——与既有登录对话框
        的主窗口查找方式一致；找不到主窗口时仅记日志（会话已保留，不影响
        本地功能）。
        """
        def _do_prompt():
            frame = None
            try:
                for tlw in wx.GetTopLevelWindows():
                    if type(tlw).__name__ == 'TFP_MainFrame':
                        frame = tlw
                        break
            except Exception:
                pass
            if frame is not None and hasattr(frame, '_prompt_api_deprecated'):
                frame._prompt_api_deprecated(payload)
            else:
                logger.warning("Auth API deprecated; main frame not available for upgrade prompt")
        wx.CallAfter(_do_prompt)

    def refresh_session(self) -> Dict[str, Any]:
        if not self._refresh_token:
            return {"success": False, "message": "无refresh_token"}

        try:
            response = requests.post(
                self._get_auth_url("refresh"),
                json={"refresh_token": self._refresh_token},
                timeout=15
            )

            result = response.json()

            if result.get("success"):
                data = result.get("data", {})

                # 合并 user + tool_subscriptions + display_tier（若后端返回）
                user_data = dict(data.get("user", {}) or {})
                if "tool_subscriptions" in data:
                    user_data["tool_subscriptions"] = data.get("tool_subscriptions") or []
                display_tier = data.get("display_tier")
                if isinstance(display_tier, dict):
                    user_data["display_tier"] = display_tier.get("display_tier", "")
                    user_data["display_tier_color"] = display_tier.get("display_tier_color", "")
                elif isinstance(display_tier, str):
                    user_data["display_tier"] = display_tier

                self._user = TFP_UserInfo.from_dict(user_data)

                license_data = data.get("license")
                self._license = TFP_LicenseInfo.from_dict(license_data)

                self._session_token = data.get("session_token")
                self._refresh_token = data.get("refresh_token")

                expires_at = data.get("expires_at")
                if expires_at:
                    self._token_expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

                self._save_session()
                self._notify_auth_change()

                return {"success": True, "message": "令牌刷新成功"}
            else:
                self._refresh_token = None
                self._clear_saved_session()
                return result

        except Exception as e:
            return {"success": False, "message": f"刷新令牌失败: {str(e)}"}
    
    def _clear_session(self):
        self._user = None
        self._license = None
        self._session_token = None
        self._refresh_token = None
        self._token_expiry = None
        self._clear_saved_session()
    
    def _notify_auth_change(self):
        for callback in self._auth_change_callbacks:
            try:
                if threading.current_thread() is threading.main_thread():
                    callback()
                else:
                    wx.CallAfter(callback)
            except Exception as e:
                logger.error(f"Failed to execute auth change callback: {e}")
    
    def add_auth_change_callback(self, callback: Callable):
        if callback not in self._auth_change_callbacks:
            self._auth_change_callbacks.append(callback)
    
    def remove_auth_change_callback(self, callback: Callable):
        if callback in self._auth_change_callbacks:
            self._auth_change_callbacks.remove(callback)
    
    def restore_session(self) -> bool:
        self._load_saved_session()
        return self.is_user_logged_in()
    
    def is_user_logged_in(self) -> bool:
        if not self._session_token or not self._user:
            return False
        
        if self._token_expiry and datetime.now() > self._token_expiry:
            self._clear_session()
            return False
        
        return True
    
    def get_current_user(self) -> Optional[TFP_UserInfo]:
        return self._user
    
    def get_current_license(self) -> Optional[TFP_LicenseInfo]:
        return self._license
    
    def get_session_token(self) -> Optional[str]:
        return self._session_token
    
    def get_auth_headers(self) -> Dict[str, str]:
        self._ensure_token_valid()
        if self._session_token:
            headers = {
                'Authorization': f'Bearer {self._session_token}'
            }
            if self._user and self._user.id:
                headers['X-User-ID'] = str(self._user.id)
            return headers
        logger.warning(f"get_auth_headers: session_token is empty, returning empty headers")
        return {}
    
    def request_login_via_ipc(self, feature_key: str = None, message: str = None) -> bool:
        """通过IPC请求登录（主程序模式下直接显示登录对话框）
        
        Args:
            feature_key: 功能键
            message: 登录提示信息
            
        Returns:
            True 表示请求已处理
        """
        try:
            from .tfp_login_dialog import TFP_LoginRegisterDialog
            
            def on_login_ok():
                self._notify_auth_change()
            
            def show_login_dialog():
                # 获取主窗口作为 parent，确保登录对话框继承正确的 DPI 缩放因子
                # 若无法获取主窗口（如异常场景），则回退到 None
                parent = None
                try:
                    for tlw in wx.GetTopLevelWindows():
                        if tlw.GetName() == 'TFP_MainFrame' or type(tlw).__name__ == 'TFP_MainFrame':
                            parent = tlw
                            break
                    if parent is None:
                        # 回退：取第一个可见的顶层窗口
                        for tlw in wx.GetTopLevelWindows():
                            if tlw.IsShown():
                                parent = tlw
                                break
                except Exception:
                    pass
                dlg = TFP_LoginRegisterDialog(parent, on_login_ok)
                if message:
                    dlg.SetTitle(message)
                dlg.ShowModal()
                dlg.Destroy()
            
            if threading.current_thread() is threading.main_thread():
                show_login_dialog()
            else:
                wx.CallAfter(show_login_dialog)
            
            return True
        except Exception as e:
            logger.error(f"Failed to show login dialog: {e}")
            return False
    
    def get_user_display_name(self) -> str:
        if self._user:
            return self._user.display_name or self._user.username
        return ""
    
    def get_user_type(self) -> str:
        if self._user:
            return self._user.user_type
        return "individual"

    def is_individual_user(self) -> bool:
        if self._user:
            return self._user.is_individual()
        return False

    def is_enterprise_user(self) -> bool:
        if self._user:
            return self._user.is_enterprise()
        return False

    def is_platform_user(self) -> bool:
        """Platform 用户拥有全部权限"""
        if self._user:
            return self._user.is_platform()
        return False

    def is_platform(self) -> bool:
        """is_platform_user 的统一接口别名（与 tbc_ExeAuthManager.is_platform 对齐）"""
        return self.is_platform_user()

    def get_display_tier(self) -> str:
        """获取 UI 派生显示等级（free/premium/enterprise/enterprise_admin/platform）"""
        if self._user:
            return self._user.display_tier
        return "free"

    def get_display_tier_color(self) -> str:
        """获取 UI 派生显示等级对应的徽章颜色"""
        if self._user:
            return self._user.display_tier_color
        return "gray"

    def get_tool_subscriptions(self) -> List[Dict[str, Any]]:
        """获取用户可访问的订购列表（个人订购 + 所在企业共享订购）"""
        if self._user:
            return self._user.tool_subscriptions
        return []

    def has_any_tool_subscription(self) -> bool:
        """是否拥有任意 active 工具订购（用于派生 Premium 显示等级）"""
        if self._user:
            return self._user.has_any_tool_subscription()
        return False

    def has_tool_subscription(self, tool_ident: str) -> bool:
        """检查用户是否订购了某工具（含个人订购 + 企业共享订购）

        匹配规则：
        - subscription_type='single_tool' 且 tool_ident 匹配
        - subscription_type='toolkit' 且该工具集包含此 tool_ident
        - subscription_type='enterprise'（企业年费，推广期含 TFP_CORE 赠送）
        - subscription_type='third_party' 且 tool_ident 匹配
        - platform 用户直接返回 True
        """
        if not self._user:
            return False
        if self._user.is_platform():
            return True
        for sub in self._user.tool_subscriptions:
            sub_type = sub.get("subscription_type")
            sub_tool = sub.get("tool_ident")
            toolkit_id = sub.get("toolkit_id")
            if sub_type == "single_tool" and sub_tool == tool_ident:
                return True
            if sub_type == "third_party" and sub_tool == tool_ident:
                return True
            if sub_type == "toolkit" and _toolkit_contains_tool(toolkit_id, tool_ident):
                return True
            if sub_type == "enterprise" and _toolkit_contains_tool("TFP_CORE", tool_ident):
                # 推广期 Enterprise 年费赠送 TFP_CORE
                return True
        return False

    def has_toolkit_subscription(self, toolkit_id: str) -> bool:
        """检查用户是否订购了某工具集（含个人订购 + 企业共享订购）

        platform 用户直接返回 True。
        """
        if not self._user:
            return False
        if self._user.is_platform():
            return True
        for sub in self._user.tool_subscriptions:
            if sub.get("subscription_type") == "toolkit" and sub.get("toolkit_id") == toolkit_id:
                return True
        return False

    def derive_display_tier(self) -> Tuple[str, str]:
        """派生 UI 显示等级 + 徽章颜色（基于本地缓存的 user + tool_subscriptions）

        返回 (display_tier, display_tier_color)
        """
        if not self._user:
            return "free", "gray"
        return _derive_display_tier_local(
            self._user.user_type,
            self._user.has_any_tool_subscription(),
            self._user.company_role,
        )
    
    def register_user(self, username: str, email: str, password: str, display_name: str = None) -> Dict[str, Any]:
        try:
            data = {
                "username": username,
                "email": email,
                "password": password
            }
            if display_name:
                data["display_name"] = display_name
            
            response = requests.post(
                self._get_auth_url("register"),
                json=data,
                timeout=10
            )
            
            result = response.json()
            return result
            
        except Exception as e:
            return {"success": False, "message": f"注册失败: {str(e)}"}
    
    def login_user(self, username: str, password: str) -> Dict[str, Any]:
        try:
            response = requests.post(
                self._get_auth_url("login"),
                json={"username": username, "password": password},
                timeout=10
            )

            result = response.json()

            if result.get("success"):
                data = result.get("data", {})

                # 合并 user + tool_subscriptions + display_tier（若后端返回）
                user_data = dict(data.get("user", {}) or {})
                if "tool_subscriptions" in data:
                    user_data["tool_subscriptions"] = data.get("tool_subscriptions") or []
                display_tier = data.get("display_tier")
                if isinstance(display_tier, dict):
                    user_data["display_tier"] = display_tier.get("display_tier", "")
                    user_data["display_tier_color"] = display_tier.get("display_tier_color", "")
                elif isinstance(display_tier, str):
                    user_data["display_tier"] = display_tier

                self._user = TFP_UserInfo.from_dict(user_data)

                license_data = data.get("license")
                self._license = TFP_LicenseInfo.from_dict(license_data)

                self._session_token = data.get("session_token")
                self._refresh_token = data.get("refresh_token")

                expires_at = data.get("expires_at")
                if expires_at:
                    self._token_expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

                self._save_session()
                self._notify_auth_change()

                return {"success": True, "message": "登录成功"}
            else:
                return result

        except Exception as e:
            return {"success": False, "message": f"登录失败: {str(e)}"}
    
    def logout_user(self) -> bool:
        try:
            if self._session_token:
                requests.post(
                    self._get_auth_url("logout"),
                    headers=self._get_headers(),
                    timeout=10
                )
            
            self._clear_session()
            self._notify_auth_change()
            return True
            
        except Exception as e:
            logger.error(f"Failed to log out: {e}")
            self._clear_session()
            self._notify_auth_change()
            return False

    def force_logout_local(self) -> None:
        """本地强制登出（不调用后端 logout 接口）

        用于后端校验会话失效（如401刷新token失败）时，仅清理本地会话状态，
        并触发认证变化回调刷新主平台 Account 菜单显示为登录状态。
        避免向已失效的 token 发起一次注定失败的网络请求。
        """
        try:
            self._clear_session()
            self._notify_auth_change()
        except Exception as e:
            logger.error(f"Failed to force local logout: {e}")
    
    def check_tool_access(self, tool_ident: str) -> Dict[str, Any]:
        try:
            response = requests.get(
                self._get_perm_url(f"tool/{tool_ident}/check"),
                headers=self._get_headers(),
                timeout=10
            )
            
            result = response.json()
            if not isinstance(result, dict) or 'allowed' not in result:
                logger.error(f"Backend returned unexpected format when checking tool access, denying access per fail-safe: {tool_ident}")
                return {"allowed": False, "reason": "unexpected_response", "message": "后端返回格式异常，按安全失败原则拒绝访问"}
            return result
            
        except requests.exceptions.ConnectionError:
            logger.error(f"Backend unavailable when checking tool access, denying access per fail-safe: {tool_ident}")
            return {"allowed": False, "reason": "backend_unavailable", "message": "后端服务不可用，按安全失败原则拒绝访问"}
        except requests.exceptions.Timeout:
            logger.error(f"Backend timeout when checking tool access, denying access per fail-safe: {tool_ident}")
            return {"allowed": False, "reason": "backend_timeout", "message": "后端服务超时，按安全失败原则拒绝访问"}
        except Exception as e:
            logger.error(f"Exception when checking tool access, denying access per fail-safe: {e}")
            return {"allowed": False, "reason": "backend_error", "message": "后端服务异常，按安全失败原则拒绝访问"}
    
    def check_feature_access(self, tool_ident: str, feature_key: str) -> Dict[str, Any]:
        try:
            response = requests.get(
                self._get_perm_url(f"feature/{tool_ident}/{feature_key}"),
                headers=self._get_headers(),
                timeout=10
            )
            
            result = response.json()
            if not isinstance(result, dict) or 'allowed' not in result:
                logger.error(f"Backend returned unexpected format when checking feature access, denying access per fail-safe: {tool_ident}/{feature_key}")
                return {"allowed": False, "reason": "unexpected_response", "message": "后端返回格式异常，按安全失败原则拒绝访问"}
            return result
            
        except requests.exceptions.ConnectionError:
            logger.error(f"Backend unavailable when checking feature access, denying access per fail-safe: {tool_ident}/{feature_key}")
            return {"allowed": False, "reason": "backend_unavailable", "message": "后端服务不可用，按安全失败原则拒绝访问"}
        except requests.exceptions.Timeout:
            logger.error(f"Backend timeout when checking feature access, denying access per fail-safe: {tool_ident}/{feature_key}")
            return {"allowed": False, "reason": "backend_timeout", "message": "后端服务超时，按安全失败原则拒绝访问"}
        except Exception as e:
            logger.error(f"Exception when checking feature access, denying access per fail-safe: {e}")
            return {"allowed": False, "reason": "backend_error", "message": "后端服务异常，按安全失败原则拒绝访问"}

    # ===== 工具席位管理 =====

    def occupy_seat(self, tool_ident: str) -> Dict[str, Any]:
        """占用收费工具席位（打开工具窗口时调用）"""
        try:
            response = requests.post(
                self._get_perm_url("seats/occupy"),
                headers=self._get_headers(),
                json={"tool_ident": tool_ident},
                timeout=10
            )
            return response.json()
        except Exception as e:
            logger.error(f"Failed to occupy seat: {e}")
            return {"success": False, "message": str(e)}

    def release_seat(self, tool_ident: str) -> Dict[str, Any]:
        """释放单个收费工具席位（关闭工具窗口时调用）"""
        try:
            response = requests.post(
                self._get_perm_url("seats/release"),
                headers=self._get_headers(),
                json={"tool_ident": tool_ident},
                timeout=10
            )
            return response.json()
        except Exception as e:
            logger.error(f"Failed to release seat: {e}")
            return {"success": False, "message": str(e)}

    def release_all_seats(self) -> Dict[str, Any]:
        """释放所有收费工具席位"""
        try:
            response = requests.post(
                self._get_perm_url("seats/release"),
                headers=self._get_headers(),
                json={"all": True},
                timeout=10
            )
            return response.json()
        except Exception as e:
            logger.error(f"Failed to release all seats: {e}")
            return {"success": False, "message": str(e)}

    def get_my_occupations(self) -> Dict[str, Any]:
        """获取当前用户占用的席位列表"""
        try:
            response = requests.get(
                self._get_perm_url("seats/my-occupations"),
                headers=self._get_headers(),
                timeout=10
            )
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get seat occupations: {e}")
            return {"success": False, "occupations": []}

    def get_company_seat_usage(self) -> Dict[str, Any]:
        """获取企业席位使用情况（企业管理员）"""
        try:
            response = requests.get(
                self._get_perm_url("seats/company-usage"),
                headers=self._get_headers(),
                timeout=10
            )
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get company seat usage: {e}")
            return {"success": False, "message": str(e)}

    def release_tool_all_users(self, tool_ident: str) -> Dict[str, Any]:
        """企业管理员释放某工具的所有企业席位（强制踢出所有在线用户）"""
        try:
            response = requests.post(
                self._get_enterprise_url(f"seats/release-tool/{tool_ident}"),
                headers=self._get_headers(),
                timeout=10
            )
            return response.json()
        except Exception as e:
            logger.error(f"Failed to release all seats for tool: {e}")
            return {"success": False, "message": str(e)}

    def release_tool_user_seat(self, tool_ident: str, target_user_id: int) -> Dict[str, Any]:
        """企业管理员释放指定用户在某工具的席位"""
        try:
            response = requests.post(
                self._get_enterprise_url(f"seats/release-tool-user/{tool_ident}/{target_user_id}"),
                headers=self._get_headers(),
                timeout=10
            )
            return response.json()
        except Exception as e:
            logger.error(f"Failed to release user seat for tool: {e}")
            return {"success": False, "message": str(e)}

    def get_user_features(self, tool_ident: str) -> Dict[str, Any]:
        try:
            response = requests.get(
                self._get_perm_url(f"user/features/{tool_ident}"),
                headers=self._get_headers(),
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            return {"success": False, "message": str(e), "features": []}
    
    def update_profile(self, display_name: str, email: str = None) -> Dict[str, Any]:
        try:
            data = {"display_name": display_name}
            if email:
                data["email"] = email
            
            response = requests.post(
                self._get_auth_url("update-profile"),
                json=data,
                headers=self._get_headers(),
                timeout=10
            )
            
            result = response.json()
            
            if result.get("success"):
                user_data = result.get("user", {})
                self._user = TFP_UserInfo.from_dict(user_data)
                self._save_session()
                self._notify_auth_change()
            
            return result
            
        except Exception as e:
            return {"success": False, "message": f"更新资料失败: {str(e)}"}
    
    def change_password(self, current_password: str, new_password: str) -> Dict[str, Any]:
        try:
            response = requests.post(
                self._get_auth_url("change-password"),
                json={
                    "current_password": current_password,
                    "new_password": new_password
                },
                headers=self._get_headers(),
                timeout=10
            )
            
            result = response.json()
            
            if result.get("success"):
                self._clear_session()
                self._notify_auth_change()
            
            return result
            
        except Exception as e:
            return {"success": False, "message": f"修改密码失败: {str(e)}"}
    
    def request_upgrade(self, target_type: str) -> Dict[str, Any]:
        try:
            response = requests.post(
                self._get_auth_url("upgrade-request"),
                json={"target_type": target_type},
                headers=self._get_headers(),
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            return {"success": False, "message": f"申请升级失败: {str(e)}"}
    
    def get_user_type_info(self) -> Dict[str, Any]:
        try:
            response = requests.get(
                self._get_auth_url("user-type-info"),
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            return {"success": False, "message": str(e), "types": []}
    
    def refresh_user_info(self) -> bool:
        try:
            response = requests.get(
                self._get_auth_url("me"),
                headers=self._get_headers(),
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    # 合并 user + tool_subscriptions + display_tier
                    payload = data.get("data", {}) or {}
                    user_data = dict(payload.get("user", {}) or {})
                    if "tool_subscriptions" in payload:
                        user_data["tool_subscriptions"] = payload.get("tool_subscriptions") or []
                    display_tier = payload.get("display_tier")
                    if isinstance(display_tier, dict):
                        user_data["display_tier"] = display_tier.get("display_tier", "")
                        user_data["display_tier_color"] = display_tier.get("display_tier_color", "")
                    elif isinstance(display_tier, str):
                        user_data["display_tier"] = display_tier
                    license_data = payload.get("license")

                    self._user = TFP_UserInfo.from_dict(user_data)
                    self._license = TFP_LicenseInfo.from_dict(license_data)
                    self._save_session()
                    return True

            return False

        except Exception as e:
            logger.error(f"Failed to refresh user info: {e}")
            return False
    
    def register_user_with_invitation(self, username: str, email: str, password: str, 
                                       display_name: str = None, invitation_code: str = None) -> Dict[str, Any]:
        try:
            data = {
                "username": username,
                "email": email,
                "password": password
            }
            if display_name:
                data["display_name"] = display_name
            if invitation_code:
                data["invitation_code"] = invitation_code
            
            response = requests.post(
                self._get_auth_url("register"),
                json=data,
                timeout=10
            )
            
            result = response.json()
            return result
            
        except Exception as e:
            return {"success": False, "message": f"注册失败: {str(e)}"}
    
    def send_email_verify_code(self, email: str, username: str = '') -> Dict[str, Any]:
        """发送邮箱验证码"""
        try:
            response = requests.post(
                self._get_auth_url("send-verify-code"),
                json={"email": email, "username": username},
                timeout=15
            )
            return response.json()
        except Exception as e:
            return {"success": False, "message": f"发送验证码失败: {str(e)}"}
    
    def verify_email_code(self, email: str, code: str) -> Dict[str, Any]:
        """验证邮箱验证码"""
        try:
            response = requests.post(
                self._get_auth_url("verify-email"),
                json={"email": email, "code": code},
                timeout=10
            )
            return response.json()
        except Exception as e:
            return {"success": False, "message": f"验证失败: {str(e)}"}
    
    def validate_invitation_code(self, code: str) -> Dict[str, Any]:
        try:
            response = requests.post(
                self._get_enterprise_url("validate-invitation"),
                json={"code": code},
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            return {"valid": False, "message": f"验证失败: {str(e)}"}
    
    def get_company_info(self) -> Dict[str, Any]:
        try:
            response = requests.get(
                self._get_enterprise_url("info"),
                headers=self._get_headers(),
                timeout=10
            )
            
            result = response.json()
            
            if result.get("success"):
                data = result.get("data", {})
                company_data = data.get("company", {})
                is_admin = data.get("is_admin", False)
                
                company = TFP_CompanyInfo.from_dict(company_data)
                
                return {
                    "success": True,
                    "company": company,
                    "is_admin": is_admin
                }
            
            return result
            
        except Exception as e:
            return {"success": False, "message": f"获取企业信息失败: {str(e)}"}
    
    def register_company(self, company_name: str, company_code: str, contact_email: str,
                         contact_phone: str = None, address: str = None, 
                         license_count: int = 1) -> Dict[str, Any]:
        try:
            data = {
                "company_name": company_name,
                "company_code": company_code,
                "contact_email": contact_email,
                "license_count": license_count
            }
            if contact_phone:
                data["contact_phone"] = contact_phone
            if address:
                data["address"] = address
            
            response = requests.post(
                self._get_enterprise_url("register"),
                json=data,
                headers=self._get_headers(),
                timeout=10
            )
            
            result = response.json()
            
            if result.get("success"):
                self.refresh_user_info()
                self._notify_auth_change()
            
            return result
            
        except Exception as e:
            return {"success": False, "message": f"注册企业失败: {str(e)}"}
    
    def join_company(self, code: str) -> Dict[str, Any]:
        try:
            response = requests.post(
                self._get_enterprise_url("join"),
                json={"code": code},
                headers=self._get_headers(),
                timeout=10
            )
            
            result = response.json()
            
            if result.get("success"):
                self.refresh_user_info()
                self._notify_auth_change()
            
            return result
            
        except Exception as e:
            return {"success": False, "message": f"加入企业失败: {str(e)}"}
    
    def get_company_members(self) -> Dict[str, Any]:
        try:
            response = requests.get(
                self._get_enterprise_url("members"),
                headers=self._get_headers(),
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            return {"success": False, "message": f"获取成员列表失败: {str(e)}"}
    
    def update_member_role(self, member_user_id: int, role: str) -> Dict[str, Any]:
        try:
            response = requests.put(
                self._get_enterprise_url(f"members/{member_user_id}/role"),
                json={"role": role},
                headers=self._get_headers(),
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            return {"success": False, "message": f"更新角色失败: {str(e)}"}
    
    def remove_member(self, member_user_id: int) -> Dict[str, Any]:
        try:
            response = requests.delete(
                self._get_enterprise_url(f"members/{member_user_id}"),
                headers=self._get_headers(),
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            return {"success": False, "message": f"移除成员失败: {str(e)}"}
    
    def get_invitation_codes(self, active_only: bool = True) -> Dict[str, Any]:
        try:
            url = self._get_enterprise_url("invitation-codes")
            if active_only:
                url += "?active_only=true"
            
            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            return {"success": False, "message": f"获取邀请码列表失败: {str(e)}"}
    
    def create_invitation_code(self, code_type: str = "single", max_uses: int = 1, 
                                expires_days: int = 30) -> Dict[str, Any]:
        try:
            response = requests.post(
                self._get_enterprise_url("invitation-codes"),
                json={
                    "code_type": code_type,
                    "max_uses": max_uses,
                    "expires_days": expires_days
                },
                headers=self._get_headers(),
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            return {"success": False, "message": f"创建邀请码失败: {str(e)}"}
    
    def deactivate_invitation_code(self, code_id: int) -> Dict[str, Any]:
        try:
            response = requests.post(
                self._get_enterprise_url(f"invitation-codes/{code_id}/deactivate"),
                headers=self._get_headers(),
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            return {"success": False, "message": f"停用邀请码失败: {str(e)}"}
    
    def update_company_license(self, license_count: int) -> Dict[str, Any]:
        try:
            response = requests.post(
                self._get_enterprise_url("license/update"),
                json={"license_count": license_count},
                headers=self._get_headers(),
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            return {"success": False, "message": f"更新许可证数量失败: {str(e)}"}
    
    def get_license_usage(self) -> Dict[str, Any]:
        try:
            response = requests.get(
                self._get_enterprise_url("license/usage"),
                headers=self._get_headers(),
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            return {"success": False, "message": f"获取License使用统计失败: {str(e)}"}
    
    def check_license_availability(self) -> Dict[str, Any]:
        try:
            response = requests.get(
                self._get_enterprise_url("license/check"),
                headers=self._get_headers(),
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            return {"available": False, "message": f"检查License可用性失败: {str(e)}"}
    
    def get_online_users(self) -> Dict[str, Any]:
        try:
            response = requests.get(
                self._get_enterprise_url("online-users"),
                headers=self._get_headers(),
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            return {"success": False, "message": f"获取在线用户列表失败: {str(e)}"}
    
    def get_user_sessions(self) -> Dict[str, Any]:
        try:
            response = requests.get(
                self._get_enterprise_url("sessions"),
                headers=self._get_headers(),
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            return {"success": False, "message": f"获取会话列表失败: {str(e)}"}
    
    def terminate_other_sessions(self) -> Dict[str, Any]:
        try:
            response = requests.post(
                self._get_enterprise_url("sessions/terminate-others"),
                headers=self._get_headers(),
                timeout=10
            )
            
            return response.json()
            
        except Exception as e:
            return {"success": False, "message": f"终止其他会话失败: {str(e)}"}


auth_manager = TFP_AuthManager()
