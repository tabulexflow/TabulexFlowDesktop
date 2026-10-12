# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
import os
import json
import logging
from typing import Optional, Dict, Any, Callable, List
from tfp_utils.tfp_i18n_manager import translate
from .tfp_auth_manager import auth_manager
from .tfp_constants import USER_TYPE_HIERARCHY

logger = logging.getLogger(__name__)


class TFP_PermissionManager:
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self._permission_cache: Dict[str, Dict[str, Any]] = {}
        self._feature_cache: Dict[str, Dict[str, Any]] = {}
        self._feature_permissions: Dict[str, List[Dict[str, Any]]] = {}
    
    def clear_cache(self):
        self._permission_cache.clear()
        self._feature_cache.clear()
    
    def load_feature_permissions_from_tools(self, tools_data: Dict[str, Any]):
        self._feature_permissions.clear()
        
        for tool in tools_data.get('tools_remote_program', []):
            tool_ident = tool.get('tool_ident')
            if tool_ident:
                features = tool.get('feature_permissions', [])
                self._feature_permissions[tool_ident] = features
        
        for tool in tools_data.get('tools_remote_webpage', []):
            tool_ident = tool.get('tool_ident')
            if tool_ident:
                features = tool.get('feature_permissions', [])
                self._feature_permissions[tool_ident] = features
    
    def load_feature_permissions_from_json(self, json_path: str):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.load_feature_permissions_from_tools(data)
        except Exception as e:
            logger.error(f"Failed to load permission definitions: {e}")
    
    def get_feature_permission_local(self, tool_ident: str, feature_key: str) -> Optional[Dict[str, Any]]:
        features = self._feature_permissions.get(tool_ident, [])
        for feature in features:
            if feature.get('feature_key') == feature_key:
                return feature
        return None
    
    def check_feature_permission_local(self, tool_ident: str, feature_key: str, user_type: str) -> Dict[str, Any]:
        """本地权限检查（基于 requires_subscription + tool_subscriptions）

        优先使用后端 tool_subscriptions 表的权威判断（通过 auth_manager.has_tool_subscription）。
        本地回退仅用于离线场景或后端不可用时。
        """
        feature = self.get_feature_permission_local(tool_ident, feature_key)

        if feature is None:
            return {
                "allowed": True,
                "reason": "no_permission_defined",
                "message": "该功能未定义权限要求"
            }

        requires_subscription = feature.get('requires_subscription')
        if requires_subscription is None:
            min_user_type = feature.get('min_user_type', 'free')
            requires_subscription = bool(min_user_type and min_user_type != 'free')

        # 不需要订购的功能直接通过
        if not requires_subscription:
            return {
                "allowed": True,
                "reason": "ok",
                "message": "权限验证通过（无需订购）"
            }

        # 检查企业级功能权限
        requires_enterprise = feature.get('requires_enterprise_subscription', False)
        if requires_enterprise:
            if auth_manager.is_platform_user():
                return {"allowed": True, "reason": "ok", "message": "权限验证通过（Platform 用户）"}
            if auth_manager.is_enterprise_user():
                # 企业用户的 enterprise 年费订购状态由后端 tool_subscriptions 体现
                # 简化判断：若 display_tier 为 enterprise/enterprise_admin 则通过
                tier = auth_manager.get_display_tier()
                if tier in ("enterprise", "enterprise_admin"):
                    return {"allowed": True, "reason": "ok", "message": "权限验证通过（企业年费已开通）"}
            return {
                "allowed": False,
                "reason": "enterprise_required",
                "message": "该功能需要开通 Enterprise 年费",
                "required_type": "enterprise",
                "user_type": user_type
            }

        # 检查工具订购状态（优先用 auth_manager 的本地缓存）
        if auth_manager.is_platform_user():
            return {"allowed": True, "reason": "ok", "message": "权限验证通过（Platform 用户）"}

        # 本地订购状态检查（auth_manager.has_tool_subscription 已综合个人 + 企业订购）
        if auth_manager.has_tool_subscription(tool_ident):
            return {"allowed": True, "reason": "ok", "message": "权限验证通过（已订购）"}

        # 无订购 → 走免费次数（实际由后端 check_feature_permission 处理，这里仅返回未通过）
        free_usage_limit = feature.get('free_usage_limit', 0)
        return {
            "allowed": False,
            "reason": "subscription_required",
            "message": f"此功能需要订购 {tool_ident} 或 TFP_CORE 工具集",
            "required_type": "toolkit",
            "user_type": user_type,
            "free_usage_limit": free_usage_limit
        }

    def check_tool_subscription(self, tool_ident: str, parent: wx.Window = None) -> Dict[str, Any]:
        """检查工具订购状态（含个人 + 企业共享）

        优先走后端 check_tool_access（含免费次数判断），失败回退到本地 has_tool_subscription。
        """
        result = auth_manager.check_tool_access(tool_ident)

        if result.get("allowed"):
            return result

        # 后端未通过，回退到本地订购状态
        if auth_manager.has_tool_subscription(tool_ident):
            return {"allowed": True, "reason": "ok", "message": "权限验证通过（已订购）"}

        if parent:
            self._show_permission_dialog(parent, {
                "allowed": False,
                "reason": "subscription_required",
                "message": f"此功能需要订购 {tool_ident} 或 TFP_CORE 工具集",
                "required_type": "toolkit",
                "user_type": auth_manager.get_display_tier() or "free",
            })

        return {
            "allowed": False,
            "reason": "subscription_required",
            "message": f"此功能需要订购 {tool_ident} 或 TFP_CORE 工具集",
            "required_type": "toolkit",
            "user_type": auth_manager.get_display_tier() or "free",
        }
    
    def check_tool_permission(self, tool_ident: str, show_dialog: bool = True, 
                              parent: wx.Window = None) -> Dict[str, Any]:
        result = auth_manager.check_tool_access(tool_ident)
        
        if not result.get("allowed") and show_dialog and parent:
            self._show_permission_dialog(parent, result)
        
        return result
    
    def check_feature_permission(self, tool_ident: str, feature_key: str, 
                                  show_dialog: bool = True, parent: wx.Window = None) -> Dict[str, Any]:
        if not auth_manager.is_user_logged_in():
            result = {
                "allowed": False,
                "reason": "login_required",
                "message": "请先登录"
            }
        else:
            user_type = auth_manager.get_user_type()
            local_feature = self.get_feature_permission_local(tool_ident, feature_key)
            
            if local_feature:
                result = self.check_feature_permission_local(tool_ident, feature_key, user_type)
            else:
                result = auth_manager.check_feature_access(tool_ident, feature_key)
        
        if not result.get("allowed") and show_dialog and parent:
            self._show_permission_dialog(parent, result)
        
        return result
    
    def _show_permission_dialog(self, parent: wx.Window, result: Dict[str, Any]):
        from .tfp_login_dialog import TFP_PermissionRequiredDialog, TFP_LoginRequiredDialog

        reason = result.get("reason", "")
        message = result.get("message", "权限不足")

        if reason == "login_required":
            dlg = TFP_LoginRequiredDialog(parent, message)
            dlg.ShowModal()
            dlg.Destroy()
        else:
            # required_type 默认 'toolkit'，current_type 用 display_tier
            required_type = result.get("required_type") or "toolkit"
            current_type = result.get("user_type") or auth_manager.get_display_tier() or "free"

            dlg = TFP_PermissionRequiredDialog(
                parent,
                message=message,
                required_type=required_type,
                current_type=current_type
            )
            dlg.ShowModal()
            dlg.Destroy()
    
    def require_login(self, parent: wx.Window, message: str = None,
                      on_success: Callable = None) -> bool:
        if auth_manager.is_user_logged_in():
            return True
        
        from .tfp_login_dialog import TFP_LoginRequiredDialog
        
        dlg = TFP_LoginRequiredDialog(parent, message, on_success)
        result = dlg.ShowModal()
        dlg.Destroy()
        
        return result == wx.ID_OK
    
    def require_permission(self, parent: wx.Window, tool_ident: str, feature_key: str = None,
                           on_success: Callable = None) -> bool:
        if not auth_manager.is_user_logged_in():
            return self.require_login(parent, on_success=on_success)
        
        if feature_key:
            result = self.check_feature_permission(tool_ident, feature_key, show_dialog=False)
        else:
            result = self.check_tool_permission(tool_ident, show_dialog=False)
        
        if result.get("allowed"):
            if on_success:
                on_success()
            return True
        else:
            self._show_permission_dialog(parent, result)
            return False
    
    def get_user_features(self, tool_ident: str) -> List[str]:
        result = auth_manager.get_user_features(tool_ident)
        
        if result.get("success"):
            features = result.get("features", [])
            return [f.get("feature_key") for f in features]
        
        return []
    
    def is_feature_accessible(self, tool_ident: str, feature_key: str) -> bool:
        result = auth_manager.check_feature_access(tool_ident, feature_key)
        return result.get("allowed", False)
    
    def wrap_button_with_permission(self, button: wx.Button, tool_ident: str, 
                                     feature_key: str, parent: wx.Window = None):
        original_handler = None
        
        for handler in button.GetHandlers():
            if hasattr(handler, 'callable'):
                original_handler = handler.callable
                break
        
        if original_handler is None:
            return
        
        button.Unbind(wx.EVT_BUTTON)
        
        def wrapped_handler(event):
            if parent is None:
                parent = button.GetTopLevelParent()
            
            if self.require_permission(parent, tool_ident, feature_key):
                original_handler(event)
        
        button.Bind(wx.EVT_BUTTON, wrapped_handler)
    
    def update_button_state(self, button: wx.Button, tool_ident: str, feature_key: str):
        accessible = self.is_feature_accessible(tool_ident, feature_key)
        
        if not accessible:
            button.Disable()
            button.SetToolTip(translate("perm_need_higher_permission"))
        else:
            button.Enable()
            button.SetToolTip("")


permission_manager = TFP_PermissionManager()
