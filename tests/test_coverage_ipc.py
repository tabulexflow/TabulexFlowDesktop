# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""IPC 模块覆盖率最低线 — 防止 tfp_tool_ipc_mixin 覆盖倒退

机制：
1. subprocess 运行 IPC 测试（test_tool_ipc_mixin.py + test_tool_ipc_mixin_extra.py），
   使用 coverage 统计 tfp_mixins/tfp_tool_ipc_mixin.py 的行覆盖率。
2. 覆盖率必须 ≥ 60%（用户确认的最低线）。

注意：
- 使用独立 data-file（.cov_ipc_minimum），不影响其他 coverage 运行。
- IPC 为核心模块（auth/permission/ipc）中的 ipc 部分，前端工程独立统计。
"""
import json
import os
import subprocess
import sys

import pytest

_FE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_CORE_FILE = "*/tfp_mixins/tfp_tool_ipc_mixin.py"
_TEST_FILES = [
    "tests/test_tool_ipc_mixin.py",
    "tests/test_tool_ipc_mixin_extra.py",
]
THRESHOLD = 60.0


def _run_ipc_coverage():
    """运行 IPC 测试并统计覆盖率，返回总覆盖率"""
    data_file = os.path.join(_FE_ROOT, '.cov_ipc_minimum')
    json_file = os.path.join(_FE_ROOT, '.cov_ipc_minimum.json')
    for f in (data_file, json_file):
        if os.path.exists(f):
            os.remove(f)
    proc = subprocess.run(
        [sys.executable, '-m', 'coverage', 'run',
         f'--data-file={data_file}', f'--include={_CORE_FILE}',
         '-m', 'pytest', *_TEST_FILES,
         '-q', '-p', 'no:cacheprovider', '--tb=short'],
        cwd=_FE_ROOT, capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        tail = '\n'.join(proc.stdout.splitlines()[-15:])
        raise RuntimeError(f"IPC coverage subset run failed (exit={proc.returncode}):\n{tail}")
    subprocess.run(
        [sys.executable, '-m', 'coverage', 'json',
         f'--data-file={data_file}', '-o', json_file],
        cwd=_FE_ROOT, capture_output=True, text=True, timeout=120,
    )
    with open(json_file, 'r', encoding='utf-8') as f:
        report = json.load(f)
    return report['totals']['percent_covered'], report


def test_ipc_coverage_meets_threshold():
    """IPC 模块（tfp_tool_ipc_mixin.py）覆盖率 ≥ 60%"""
    pct, report = _run_ipc_coverage()
    assert pct >= THRESHOLD, (
        f"IPC 模块覆盖率 {pct:.1f}% 低于最低线 {THRESHOLD:.0f}%，"
        f"请补充测试或检查是否有覆盖倒退"
    )
