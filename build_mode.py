# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
构建模式常量与后端地址唯一配置源

一、构建模式：
- 源码运行（python main.py，开发调试）：sys.frozen 不存在 / 无 __compiled__ → False → 开发模式
- PyInstaller/Nuitka 打包产物：sys.frozen=True 或存在 __compiled__ → True → 生产模式，
  后端地址强制为公网 HTTPS 域名
- 本地测试构建（_build_target.py 中 BUILD_TARGET_FRONTEND="localtest"）：打包产物但后端指向本地
  127.0.0.1:8080，仅用于开发环境测试打包后的 EXE，禁止发布给终端用户

二、后端地址唯一配置源（仅此处配置，禁止在多个位置硬编码）：
- 开发/本地测试：http://127.0.0.1:8080
- 生产：https://tabulexflow.com:443
所有模块（main.py / tfp_backend_config.py / tfp_auth_manager.py）统一从此模块导入后端地址。

三、构建目标标记：
- tfpdesktop_build.bat 在编译前写入 _build_target.py（BUILD_TARGET_FRONTEND = "production" 或 "localtest"）
- PyInstaller 将 _build_target.py 打包进 EXE，运行时由本模块读取
- 源码运行时 _build_target.py 不存在或 BUILD_TARGET_FRONTEND 为空，视为开发模式
"""

import os
import sys

IS_PRODUCTION_BUILD = bool(getattr(sys, 'frozen', False)) or ('__compiled__' in globals())

# 读取构建目标标记（由 tfpdesktop_build.bat 在编译前写入 _build_target.py）
_BUILD_TARGET_VALUE = ""
if IS_PRODUCTION_BUILD:
    try:
        from _build_target import BUILD_TARGET_FRONTEND as _BUILD_TARGET_VALUE
    except ImportError:
        pass

# 本地测试构建：_build_target.py 中 BUILD_TARGET_FRONTEND="localtest"
# 此模式下 EXE 为打包产物（sys.frozen=True），但后端地址指向本地 127.0.0.1:8080
# 仅用于开发环境测试，禁止发布给终端用户
IS_LOCAL_TEST_BUILD = (
    IS_PRODUCTION_BUILD
    and _BUILD_TARGET_VALUE.lower() == 'localtest'
)

# 社区发布版（OSS）标记：
# - 默认 False，便于平时开发/测试后端与收费子工具（登录、RemoteProgram、RemoteWebpage 均可用）；
# - 使用 tfpdesktop_build.bat / tfpdesktop_build.sh 编译前端工程时，脚本会让执行者选择构建版本：
#   选择 [1] OSS 社区版（默认）时临时将本标记替换为 True 后打包，
#   使发布版变为"纯前端 + BuiltinProgram"社区版（隐藏登录/后端/远程工具）；
#   选择 [2] 完整版时保持 False（含登录/远程工具，连接后端）。
#   编译完成后脚本再把本标记还原为 False，避免影响后续开发。
IS_OSS_COMMUNITY_BUILD = False

if IS_LOCAL_TEST_BUILD or not IS_PRODUCTION_BUILD:
    # 本地测试构建 或 源码开发运行：连接本地后端
    BACKEND_HOST = "127.0.0.1"
    BACKEND_PORT = 8080
    BACKEND_PROTOCOL = "http"
else:
    # 生产构建（打包产物）：通过域名和HTTPS连接
    BACKEND_HOST = "tabulexflow.com"
    BACKEND_PORT = 443
    BACKEND_PROTOCOL = "https"

BACKEND_BASE_URL = f"{BACKEND_PROTOCOL}://{BACKEND_HOST}:{BACKEND_PORT}"

# 前端下载页 URL（自更新提示跳转用，T1.2）。
# 与生产后端同域的公开下载页；本地/开发构建发现新版本时也跳转此页（下载页为官网公开资源）。
FRONTEND_DOWNLOAD_PAGE_URL = "https://tabulexflow.com/web/download"

# 本机回环地址常量（IPC 通信与本地地址判断用）
IPC_HOST_IP = "127.0.0.1"     # IPC 回环绑定
LOCAL_HOST_IP = "127.0.0.1"   # 本地回环地址
LOCAL_HOST_NAME = "localhost"  # 本地主机名


def is_dev_mode() -> bool:
    """开发模式判断（统一入口）
    
    - 打包产物恒为 False
    - 源码运行：仅当 TFP_DEV_MODE=development 时为 True
    """
    if IS_PRODUCTION_BUILD:
        return False
    return os.environ.get('TFP_DEV_MODE', 'production').lower() == 'development'
