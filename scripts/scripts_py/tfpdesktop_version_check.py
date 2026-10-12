#!/usr/bin/env python3
# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""前端打包前版本自检（T1.4，tfpdesktop_build.bat / tfpdesktop_build.sh 共用单一实现）。

检查项：
1. config/version.txt 的 ProductVersion 必须可解析且非占位值（首段为 0 视为占位）；
   前端版本号单一来源为 config/version.txt 的 ProductVersion。

输出：人类可读的 [OK]/[FAIL] 行；退出码 0=通过，1=拦截构建。
用法：python3 tfpdesktop_version_check.py <PROJECT_DIR>
"""

import os
import sys

# 版本解析单一实现（同目录）——直接运行本脚本时 sys.path[0] 即本目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tfpdesktop_version import read_product_version


def fail(msg):
    print(f"  [FAIL] {msg}")
    return 1


def main():
    if len(sys.argv) != 2:
        print("usage: tfpdesktop_version_check.py <PROJECT_DIR>")
        return 1
    project_dir = sys.argv[1]

    # 解析 version.txt 的 ProductVersion（解析逻辑单一实现于 tfpdesktop_version.py）
    try:
        version = read_product_version(project_dir)
    except OSError as e:
        return fail(f"Cannot read config/version.txt: {e}. Aborting build.")
    except ValueError:
        return fail("Cannot parse ProductVersion from config/version.txt. Aborting build.")
    if version.split('.')[0] == '0':
        return fail(f"config/version.txt contains placeholder version '{version}'. Aborting build.")
    print(f"  [OK] Frontend version from config/version.txt: {version}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
