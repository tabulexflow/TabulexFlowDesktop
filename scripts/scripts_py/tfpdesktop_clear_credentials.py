#!/usr/bin/env python3
# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""构建收尾：清除构建机本机残留的登录会话（tfpdesktop_build.bat / .sh 共用）。

背景：tfp_auth 启动时会从"操作系统钥匙串(keyring) / config 回退文件"恢复上次登录，
因此刚编译出的产物在**编译机同一 OS 用户**下首次打开会显示为已登录。本脚本在编译
成功后清除这些本机凭据，使新产物首次打开为未登录。

⚠ 破坏性：会删除当前 OS 用户已保存的登录会话（需重新登录），仅由构建脚本调用。

清理对象（与 tfp_utils/tfp_secure_storage.py 保持单一来源）：
1. keyring：service='TabulexFlow_Auth'，key='auth_token'
   （经 TFP_AuthTokenStorage.clear_auth_session 实现：优先钥匙串，回退文件）；
2. 文件回退：<PROJECT_DIR>/config/.auth_token 与 <PROJECT_DIR>/config/.tfp_fernet_key。

失败不影响构建（fail-soft，仅 [WARN]）：例如 headless 环境无 D-Bus/SecretService 时。
用法：python3 tfpdesktop_clear_credentials.py <PROJECT_DIR>
退出码：0（始终；凭据清理失败不拦截构建）。
"""

import importlib.util
import os
import sys


def _load_auth_token_storage_cls(project_dir):
    """按文件路径加载 tfp_secure_storage，避免触发 tfp_utils 包 __init__ 的副作用。"""
    module_path = os.path.join(project_dir, 'tfp_utils', 'tfp_secure_storage.py')
    spec = importlib.util.spec_from_file_location('_tfp_secure_storage_build_helper', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TFP_AuthTokenStorage


def main():
    if len(sys.argv) != 2:
        print("usage: tfpdesktop_clear_credentials.py <PROJECT_DIR>")
        return 1
    project_dir = sys.argv[1]

    print("[Credentials] Clearing saved login session so the freshly built artifact starts logged-out / 清除已保存登录会话，使新构建产物首次打开为未登录...")

    # 1) 钥匙串会话（优先 keyring；keyring 不可用时 clear_auth_session 内部回退删文件）
    try:
        storage_cls = _load_auth_token_storage_cls(project_dir)
        removed = storage_cls().clear_auth_session()
        if removed:
            print("  [OK] auth session cleared (keyring or fallback): service=TabulexFlow_Auth, key=auth_token / 已清除登录会话")
        else:
            print("  [WARN] auth session clear returned False (storage unavailable?) / 清理返回 False（存储不可用？）")
    except Exception as e:
        # 兜底：任何异常都不得中断构建
        print(f"  [WARN] Failed to clear keyring auth session: {e} / 清除钥匙串登录会话失败")

    # 2) 文件回退凭据（防御性：不同 _get_fallback_path 解析下仍确保删除）
    config_dir = os.path.join(project_dir, 'config')
    for name in ('.auth_token', '.tfp_fernet_key'):
        path = os.path.join(config_dir, name)
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"  [OK] deleted fallback credential file: {path} / 已删除回退凭据文件")
        except OSError as e:
            print(f"  [WARN] Failed to delete {path}: {e} / 删除回退凭据文件失败")

    return 0


if __name__ == '__main__':
    sys.exit(main())
