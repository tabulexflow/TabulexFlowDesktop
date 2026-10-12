# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-TabulexFlow-Commercial
#
# Dual License / 双重许可:
#
#   Option 1 - GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later).
#   Applies to the open-source frontend main program and its BuiltinProgram tools.
#   选项 1 - GNU AGPL v3 或更高版本（AGPL-3.0-or-later）。
#   适用于开源前端主程序及其 BuiltinProgram 工具。
#
#   Option 2 - TabulexFlow Commercial License
#   (LicenseRef-TabulexFlow-Commercial).
#   Applies to closed-source commercial tools in the TabulexFlow ecosystem
#   that are authorized to use this file under that license.
#   选项 2 - TabulexFlow 商业许可（LicenseRef-TabulexFlow-Commercial）。
#   适用于已获授权使用该许可的 TabulexFlow 生态内闭源商业工具。
#
# Full terms of both licenses are provided in the LICENSE file in this directory
# (AGPL terms are also in LICENSE.txt at the repository root).
# 两种许可的完整条款见本目录下 LICENSE 文件（AGPL 条款另见仓库根 LICENSE.txt）。
#
# IMPORTANT / 重要（维护者须知）：
# 本文件属双许可 SDK，不得 import 仅以 GPL/AGPL 授权的 copyleft-only 库（如 mutagen、PyMuPDF），
# 否则商业许可选项将失效。详见本目录 LICENSE 文件的 "Maintainer Note / 维护者须知"。
# This file is dual-licensed; do NOT import copyleft-only (GPL/AGPL-exclusive) libraries
# such as mutagen or PyMuPDF, or the commercial license option is invalidated.
# See the Maintainer Note in the LICENSE file in this directory.

"""
TabulexFlow 认证上下文辅助（SDK权威源）

提供认证上下文的便捷创建、检查和查询功能。
是对 TFP_AuthContext 的便捷封装，减少子工具中的样板代码。
"""

from typing import Optional, Dict, Any
from tfp_toolkit.tfp_base_tool import TFP_AuthContext


def create_auth_context_from_dict(data: Dict[str, Any]) -> TFP_AuthContext:
    """从字典创建认证上下文

    Args:
        data: 认证上下文字典，通常来自IPC上下文文件或API响应

    Returns:
        TFP_AuthContext 实例
    """
    return TFP_AuthContext.from_dict(data)


def is_user_logged_in(auth: TFP_AuthContext) -> bool:
    """检查用户是否已登录

    Args:
        auth: 认证上下文

    Returns:
        True 表示用户已登录
    """
    return auth.is_logged_in()


def has_permission(auth: TFP_AuthContext, permission: str) -> bool:
    """检查用户是否有指定权限

    Args:
        auth: 认证上下文
        permission: 权限标识

    Returns:
        True 表示用户拥有该权限
    """
    return auth.has_permission(permission)


def get_user_type(auth: TFP_AuthContext) -> str:
    """获取用户类型

    Args:
        auth: 认证上下文

    Returns:
        用户类型字符串（如 "free"、"premium"、"enterprise"）
    """
    return auth.user_type


def is_premium_user(auth: TFP_AuthContext) -> bool:
    """检查用户是否为付费用户

    Args:
        auth: 认证上下文

    Returns:
        True 表示用户为付费用户（premium 或 enterprise）
    """
    return auth.user_type in ("premium", "enterprise")


def is_auth_expired(auth: TFP_AuthContext) -> bool:
    """检查认证是否已过期

    Args:
        auth: 认证上下文

    Returns:
        True 表示认证已过期
    """
    return auth.is_expired()
