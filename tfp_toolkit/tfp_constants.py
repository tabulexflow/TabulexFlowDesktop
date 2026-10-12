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
TabulexFlow 公共常量（SDK权威源）

定义所有工具共享的常量值，避免各工具各自硬编码。
"""

import re

# ============================================================
#  工具类型
# ============================================================

TOOL_TYPE_BUILTIN = "BuiltinProgram"
TOOL_TYPE_REMOTE_PROGRAM = "RemoteProgram"
TOOL_TYPE_REMOTE_WEBPAGE = "RemoteWebpage"

# ============================================================
#  IPC 默认配置
# ============================================================

IPC_HOST_DEFAULT = "127.0.0.1"   # IPC 回环绑定地址（仅本机进程通信）
IPC_PORT_BASE = 0                # 0 表示由系统动态分配端口

# ============================================================
#  撤销/重做
# ============================================================

DEFAULT_MAX_UNDO = 20  # Grid 撤销/重做默认最大步数

# ============================================================
#  支持的语言
# ============================================================

SUPPORTED_LANGUAGES = ['en', 'zh', 'fr', 'ru', 'es', 'ar']

# ============================================================
#  工具运行模式
# ============================================================

RUN_MODE_EMBEDDED = "embedded"
RUN_MODE_STANDALONE = "standalone"

# ============================================================
#  IPC 通信
# ============================================================

IPC_SOCKET_TIMEOUT = 5.0          # IPC 连接超时（秒）
IPC_LISTEN_TIMEOUT = 1.0          # IPC 监听超时（秒）
IPC_RECV_BUFFER = 4096            # IPC 接收缓冲区大小
IPC_API_REQUEST_TIMEOUT = 30.0    # IPC API 请求默认超时（秒）
IPC_CHECK_PERMISSION_TIMEOUT = 15.0  # IPC 权限检查默认超时（秒）
IPC_RECONNECT_INTERVAL = 3.0      # IPC 重连间隔（秒）
IPC_MAX_RECONNECT_ATTEMPTS = 5    # IPC 最大重连次数

# ============================================================
#  tool_ident 格式校验
# ============================================================

# 与后端 input_validation.py 保持一致：字母开头，仅含字母/数字/下划线
TOOL_IDENT_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]*$')


def validate_tool_ident_format(tool_ident: str) -> bool:
    """校验 tool_ident 格式是否合法

    规则：字母开头，仅含字母/数字/下划线（与后端一致）。
    用于防止路径穿越、子进程注入等安全风险。

    Args:
        tool_ident: 工具标识字符串

    Returns:
        True 表示格式合法
    """
    return bool(tool_ident and TOOL_IDENT_PATTERN.match(tool_ident))
