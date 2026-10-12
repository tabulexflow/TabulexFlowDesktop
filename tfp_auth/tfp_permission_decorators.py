# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
from typing import Optional, Callable, Dict, Any
from functools import wraps

from .tfp_auth_manager import auth_manager


def require_login(message: str = "此功能需要登录后才能使用"):
    def decorator(func):
        @wraps(func)
        def wrapper(self, event, *args, **kwargs):
            if not auth_manager.is_user_logged_in():
                from .tfp_login_dialog import TFP_LoginRequiredDialog
                
                parent = self if isinstance(self, wx.Window) else None
                if hasattr(self, 'GetTopLevelParent'):
                    parent = self.GetTopLevelParent()
                
                dlg = TFP_LoginRequiredDialog(parent, message)
                result = dlg.ShowModal()
                dlg.Destroy()
                
                if result != wx.ID_OK:
                    return
            
            return func(self, event, *args, **kwargs)
        return wrapper
    return decorator


def require_permission(tool_ident: str, feature_key: str, message: str = None):
    def decorator(func):
        @wraps(func)
        def wrapper(self, event, *args, **kwargs):
            result = auth_manager.check_feature_access(tool_ident, feature_key)

            if not result.get("allowed"):
                from .tfp_login_dialog import TFP_PermissionRequiredDialog, TFP_LoginRequiredDialog

                parent = self if isinstance(self, wx.Window) else None
                if hasattr(self, 'GetTopLevelParent'):
                    parent = self.GetTopLevelParent()

                reason = result.get("reason", "")
                msg = message or result.get("message", "权限不足")

                if reason == "login_required":
                    dlg = TFP_LoginRequiredDialog(parent, msg)
                    dlg.ShowModal()
                    dlg.Destroy()
                else:
                    # required_type 默认 'toolkit'（订购工具集），current_type 用 display_tier
                    required_type = result.get("required_type") or "toolkit"
                    current_type = result.get("user_type") or auth_manager.get_display_tier() or "free"

                    dlg = TFP_PermissionRequiredDialog(
                        parent,
                        message=msg,
                        required_type=required_type,
                        current_type=current_type
                    )
                    dlg.ShowModal()
                    dlg.Destroy()

                return

            return func(self, event, *args, **kwargs)
        return wrapper
    return decorator


def require_tool_subscription(tool_ident: str, message: str = None):
    """要求用户已订购指定工具（含个人订购 + 企业共享）

    Args:
        tool_ident: 工具标识（如 TabulexBomComparator）
        message: 自定义提示信息
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, event, *args, **kwargs):
            if not auth_manager.is_user_logged_in():
                from .tfp_login_dialog import TFP_LoginRequiredDialog

                parent = self if isinstance(self, wx.Window) else None
                if hasattr(self, 'GetTopLevelParent'):
                    parent = self.GetTopLevelParent()

                dlg = TFP_LoginRequiredDialog(parent, "此功能需要登录后才能使用")
                result = dlg.ShowModal()
                dlg.Destroy()

                if result != wx.ID_OK:
                    return

            # 优先使用后端权限检查（含企业级功能、免费次数等逻辑）
            result = auth_manager.check_tool_access(tool_ident)
            if result.get("allowed"):
                return func(self, event, *args, **kwargs)

            # 后端未通过，回退到本地订购状态检查
            if auth_manager.has_tool_subscription(tool_ident):
                return func(self, event, *args, **kwargs)

            from .tfp_login_dialog import TFP_PermissionRequiredDialog

            parent = self if isinstance(self, wx.Window) else None
            if hasattr(self, 'GetTopLevelParent'):
                parent = self.GetTopLevelParent()

            current_tier = auth_manager.get_display_tier() or "free"
            dlg = TFP_PermissionRequiredDialog(
                parent,
                message=message or f"此功能需要订购 {tool_ident} 或 TFP_CORE 工具集",
                required_type="toolkit",
                current_type=current_tier
            )
            dlg.ShowModal()
            dlg.Destroy()
            return

        return wrapper
    return decorator


class TFP_PermissionMixin:
    
    _tool_ident: str = ""
    
    def set_tool_ident(self, tool_ident: str):
        self._tool_ident = tool_ident
    
    def check_login(self, message: str = "此功能需要登录后才能使用") -> bool:
        if auth_manager.is_user_logged_in():
            return True
        
        from .tfp_login_dialog import TFP_LoginRequiredDialog
        
        parent = self if isinstance(self, wx.Window) else None
        if hasattr(self, 'GetTopLevelParent'):
            parent = self.GetTopLevelParent()
        
        dlg = TFP_LoginRequiredDialog(parent, message)
        result = dlg.ShowModal()
        dlg.Destroy()
        
        return result == wx.ID_OK
    
    def check_permission(self, feature_key: str, message: str = None) -> bool:
        if not self._tool_ident:
            return True

        result = auth_manager.check_feature_access(self._tool_ident, feature_key)

        if result.get("allowed"):
            return True

        from .tfp_login_dialog import TFP_PermissionRequiredDialog, TFP_LoginRequiredDialog

        parent = self if isinstance(self, wx.Window) else None
        if hasattr(self, 'GetTopLevelParent'):
            parent = self.GetTopLevelParent()

        reason = result.get("reason", "")
        msg = message or result.get("message", "权限不足")

        if reason == "login_required":
            dlg = TFP_LoginRequiredDialog(parent, msg)
            dlg.ShowModal()
            dlg.Destroy()
        else:
            # required_type 默认 'toolkit'，current_type 用 display_tier
            required_type = result.get("required_type") or "toolkit"
            current_type = result.get("user_type") or auth_manager.get_display_tier() or "free"

            dlg = TFP_PermissionRequiredDialog(
                parent,
                message=msg,
                required_type=required_type,
                current_type=current_type
            )
            dlg.ShowModal()
            dlg.Destroy()

        return False

    def check_tool_subscription(self, tool_ident: str = None, message: str = None) -> bool:
        """检查工具订购状态（含个人 + 企业共享）"""
        tool_ident = tool_ident or self._tool_ident
        if not tool_ident:
            return True

        if not auth_manager.is_user_logged_in():
            return self.check_login("此功能需要登录后才能使用")

        # 优先走后端权限检查（含免费次数）
        result = auth_manager.check_tool_access(tool_ident)
        if result.get("allowed"):
            return True

        # 回退到本地订购状态
        if auth_manager.has_tool_subscription(tool_ident):
            return True

        from .tfp_login_dialog import TFP_PermissionRequiredDialog

        parent = self if isinstance(self, wx.Window) else None
        if hasattr(self, 'GetTopLevelParent'):
            parent = self.GetTopLevelParent()

        current_tier = auth_manager.get_display_tier() or "free"
        dlg = TFP_PermissionRequiredDialog(
            parent,
            message=message or f"此功能需要订购 {tool_ident} 或 TFP_CORE 工具集",
            required_type="toolkit",
            current_type=current_tier
        )
        dlg.ShowModal()
        dlg.Destroy()
        return False

    def update_button_states(self, tool_ident: str = None):
        tool_ident = tool_ident or self._tool_ident
        if not tool_ident:
            return

        result = auth_manager.get_user_features(tool_ident)

        if result.get("success"):
            accessible_features = [f.get("feature_key") for f in result.get("features", [])]
            all_features = result.get("all_features", [])

            for feature in all_features:
                feature_key = feature.get("feature_key")
                btn = getattr(self, f"{feature_key}_btn", None)

                if btn and isinstance(btn, wx.Button):
                    if feature_key in accessible_features:
                        btn.Enable()
                        btn.SetToolTip("")
                    else:
                        btn.Disable()
                        btn.SetToolTip(f"此功能需要订购 {tool_ident} 或 TFP_CORE 工具集")
    
    def get_user_display_name(self) -> str:
        return auth_manager.get_user_display_name()

    def get_user_type(self) -> str:
        return auth_manager.get_user_type()

    def get_display_tier(self) -> str:
        """获取 UI 显示等级"""
        return auth_manager.get_display_tier()

    def is_logged_in(self) -> bool:
        return auth_manager.is_user_logged_in()

    def has_tool_subscription(self, tool_ident: str) -> bool:
        """检查工具订购状态"""
        return auth_manager.has_tool_subscription(tool_ident)

    def get_session_token(self) -> Optional[str]:
        return auth_manager.get_session_token()


def create_permission_button(parent: wx.Window, label: str, tool_ident: str,
                             feature_key: str, callback: Callable = None,
                             **kwargs) -> wx.Button:
    btn = wx.Button(parent, label=label, **kwargs)

    result = auth_manager.check_feature_access(tool_ident, feature_key)

    if not result.get("allowed"):
        btn.Disable()
        btn.SetToolTip(f"此功能需要订购 {tool_ident} 或 TFP_CORE 工具集")

    if callback:
        if result.get("allowed"):
            btn.Bind(wx.EVT_BUTTON, callback)
        else:
            def on_disabled_click(event):
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

            btn.Bind(wx.EVT_BUTTON, on_disabled_click)

    return btn
