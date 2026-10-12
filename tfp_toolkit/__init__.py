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
TabulexFlow Toolkit SDK - 第三方工具开发工具包

SDK 版本（__version__）：
    - 独立语义化版本，随 SDK 接口/行为变更递增，与前端主程序 version.txt 无联动
      （前端版本单一来源为 config/version.txt 的 ProductVersion）。
    - 构建脚本 build_remote_tools.py 打包 RemoteProgram EXE 时自动读取本值写入
      tool_manifest.json 的 sdk_version 字段，用于诊断用户机器上 EXE 内嵌的 SDK 版本。
    - 主程序侧派生副本 tfp_utils/__init__.py 的 __version__ 必须与本值保持一致
      （由 tests/test_tfp_dual_source_consistency.py 守护）。

使用方式：
    import tfp_toolkit

    # 基类
    class MyTool(tfp_toolkit.TFP_BuiltinProgramTool):
        ...

    # DPI
    size = tfp_toolkit.spx_calc(100)

    # I18n
    text = tfp_toolkit.translate("my_key")

    # Grid
    class MyGrid(tfp_toolkit.TFP_BaseGrid):
        ...

    # IPC (RemoteProgram)
    sdk = tfp_toolkit.TFP_IPCSDK()
"""

# SDK 版本标识（与 tfp_utils/__init__.py 的 __version__ 保持一致，见守护测试）
__version__ = "1.0.0"

# 基类和数据类
from .tfp_base_tool import (
    TFP_ToolType,
    TFP_ToolRunMode,
    TFP_AuthContext,
    TFP_SettingsContext,
    TFP_IPCConfig,
    TFP_ToolContext,
    TFP_ToolMetadata,
    TFP_BaseTool,
    TFP_BuiltinProgramTool,
    TFP_RemoteProgramTool,
    TFP_RemoteWebpageTool,
    create_tool_instance,
)

# I18n
from .tfp_i18n_manager import (
    TFP_I18nManager,
    translate,
    i18n,
    translate_list,
)

# DPI
from .tfp_dpi import (
    spx_calc,
    get_dpi_scale_factor,
    set_dpi_scale_factor,
)

# Grid
from .tfp_base_grid import TFP_BaseGrid

# IPC
from .tfp_ipc_sdk import (
    TFP_IPCSDK,
    TFP_IPCAPIError,
    IPC_HOST_IP,
)

# Auth
from .tfp_auth import (
    create_auth_context_from_dict,
    is_user_logged_in,
    has_permission,
    get_user_type,
    is_premium_user,
    is_auth_expired,
)

# Constants
from .tfp_constants import *

__all__ = [
    # 基类
    "TFP_BaseTool",
    "TFP_BuiltinProgramTool",
    "TFP_RemoteProgramTool",
    "TFP_RemoteWebpageTool",
    # 数据类
    "TFP_ToolType",
    "TFP_ToolRunMode",
    "TFP_AuthContext",
    "TFP_SettingsContext",
    "TFP_IPCConfig",
    "TFP_ToolContext",
    "TFP_ToolMetadata",
    "create_tool_instance",
    # I18n
    "TFP_I18nManager",
    "translate",
    "i18n",
    "translate_list",
    # DPI
    "spx_calc",
    "get_dpi_scale_factor",
    "set_dpi_scale_factor",
    # Grid
    "TFP_BaseGrid",
    # IPC
    "TFP_IPCSDK",
    "TFP_IPCAPIError",
    "IPC_HOST_IP",
    # Auth
    "create_auth_context_from_dict",
    "is_user_logged_in",
    "has_permission",
    "get_user_type",
    "is_premium_user",
    "is_auth_expired",
    # Constants
    "TOOL_TYPE_BUILTIN",
    "TOOL_TYPE_REMOTE_PROGRAM",
    "TOOL_TYPE_REMOTE_WEBPAGE",
    "IPC_HOST_DEFAULT",
    "IPC_PORT_BASE",
    "DEFAULT_MAX_UNDO",
    "SUPPORTED_LANGUAGES",
    "RUN_MODE_EMBEDDED",
    "RUN_MODE_STANDALONE",
    "TOOL_IDENT_PATTERN",
    "validate_tool_ident_format",
]
