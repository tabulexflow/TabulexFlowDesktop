# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""平台后端 API 路径集中定义（主程序侧唯一定义处）。

主程序代码引用后端 API 版本前缀时必须从本模块导入 `API_V1_PREFIX`，
禁止在其他位置硬编码 `/api/v1` 字符串。其他唯一定义处：
- SDK 侧（第三方子工具使用）：`tfp_toolkit.tfp_ipc_sdk.API_V1_PREFIX`
- 后端侧：`be_utils.be_api_version.API_V1_PREFIX`

URL 前缀当前统一为 /api/v1；未来如引入 v2，仅需在此扩展。
"""

# 平台后端 API 版本前缀
API_V1_PREFIX = '/api/v1'
