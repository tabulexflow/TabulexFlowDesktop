# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
from typing import Dict, Any, Optional
from tfp_utils.tfp_i18n_manager import translate
from .tfp_auth_manager import auth_manager
from .tfp_constants import USER_TYPE_LABELS, USER_TYPE_LABELS_ZH


class TFP_ButtonPermissionController:
    
    def __init__(self, tool_ident: str, parent: wx.Window = None):
        self.tool_ident = tool_ident
        self.parent = parent
    
    def set_parent(self, parent: wx.Window):
        self.parent = parent
    
    def handle_permission_error(self, status_code: int, response_data: Dict[str, Any] = None):
        if status_code == 401:
            from .tfp_login_dialog import TFP_LoginRequiredDialog
            message = translate("perm_need_login_msg")
            if response_data and isinstance(response_data, dict):
                message = response_data.get('message', message)
            dlg = TFP_LoginRequiredDialog(self.parent, message)
            dlg.ShowModal()
            dlg.Destroy()
            return True
        elif status_code == 403:
            from .tfp_login_dialog import TFP_PermissionRequiredDialog
            message = translate("perm_need_higher_permission")
            required_type = "toolkit"
            current_type = "free"
            if response_data and isinstance(response_data, dict):
                message = response_data.get('message', message)
                required_type = response_data.get('required_type') or required_type
                current_type = response_data.get('current_type') or current_type
            dlg = TFP_PermissionRequiredDialog(
                self.parent,
                message=message,
                required_type=required_type,
                current_type=current_type
            )
            dlg.ShowModal()
            dlg.Destroy()
            return True
        return False
    
    def is_permission_error(self, status_code: int) -> bool:
        return status_code in (401, 403)


def create_button_permission_controller(tool_ident: str, parent: wx.Window = None) -> TFP_ButtonPermissionController:
    return TFP_ButtonPermissionController(tool_ident, parent)
