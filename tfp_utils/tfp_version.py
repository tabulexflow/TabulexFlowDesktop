# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""语义化版本号比较辅助（主程序侧共享）。

使用方：
- main.py 前端自更新/最低版本强提醒
- tfp_tool_runner_mixin 工具清单 min_sdk_version 下载门槛（T8.4.1）
- tfp_tool_ipc_mixin IPC 能力下限握手诊断（T8.5.1）

注意：SDK 版本与前端主程序 version 为相互独立的语义化版本，
本辅助只做元组比较，不关心版本语义。
"""


def version_tuple(version_str):
    """语义化版本字符串 → 可比较元组；解析失败返回 (0, 0, 0)（视为最旧，仅诊断用途）。"""
    try:
        return tuple(int(x) for x in str(version_str).strip().split('.')[:3])
    except (ValueError, TypeError):
        return (0, 0, 0)
