#!/usr/bin/env python3
# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""前端版本号读取（T1.2，tfpdesktop_build.bat / tfpdesktop_build.sh / 版本自检共用单一实现）。

单一来源：config/version.txt（PyInstaller VSVersionInfo 结构）的 ProductVersion 字段。
本模块只负责"解析并返回版本字符串"，不做占位值校验（那是
tfpdesktop_version_check.py 的职责），避免多处重复正则逻辑。

用法：python tfpdesktop_version.py <PROJECT_DIR>   # stdout 输出对外版本号（前三段），失败非 0 退出
"""

import os
import re
import sys

# ProductVersion：允许 1~4 段数字（与 main.py 的运行时读取保持一致）
_PRODUCTVERSION_RE = re.compile(
    r"StringStruct\(u?'ProductVersion',\s*u?'(\d+(?:\.\d+){1,3})'\)"
)


def read_product_version(project_dir):
    """读取 config/version.txt 的 ProductVersion 并返回其原始字符串（1~4 段）。

    解析/读取失败时抛 OSError 或 ValueError，由调用方决定如何提示。
    """
    version_file_path = os.path.join(project_dir, 'config', 'version.txt')
    with open(version_file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    match = _PRODUCTVERSION_RE.search(text)
    if not match:
        raise ValueError("ProductVersion field not found in config/version.txt")
    return match.group(1)


def short_version(version):
    """取前三段作为对外版本号（与 main.py 运行时读取一致）。"""
    return '.'.join(version.split('.')[:3])


def main():
    if len(sys.argv) != 2:
        print("usage: tfpdesktop_version.py <PROJECT_DIR>", file=sys.stderr)
        return 1
    try:
        print(short_version(read_product_version(sys.argv[1])))
    except (OSError, ValueError) as e:
        print(f"[FAIL] Cannot read frontend version: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
