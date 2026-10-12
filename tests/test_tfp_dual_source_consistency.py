# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""T3.2 tfp_utils ↔ tfp_toolkit 双源一致性守护测试

背景：tfp_toolkit（SDK 权威源，随 RemoteProgram EXE 分发）与 tfp_utils（主程序内部
派生版）存在同名双源文件。两文件头部均声明"基类接口签名和行为逻辑必须与 SDK 版本
一致"。本测试用 AST 对比守护该约定：

- 剥离全部 docstring 后逐符号（函数/类/模块级赋值）对比两侧源码；
- imports 豁免（两侧依赖差异是约定允许的：主程序版有 build_mode 等特有依赖）；
- 白名单外的单侧独有符号或共有符号体不一致 → 测试失败；
- 另守护 tfp_toolkit.__version__ == tfp_utils.__version__。

纯 stdlib 实现（ast/re，不 import 被测包——其依赖 wx，测试环境不可用）。
"""

import ast
import re
from pathlib import Path

FE_ROOT = Path(__file__).resolve().parent.parent

# 双源同名文件清单（tfp_utils/ 与 tfp_toolkit/ 下）
DUAL_SOURCE_FILES = (
    "tfp_base_tool.py",
    "tfp_i18n_manager.py",
)

# 差异白名单（T3.2 执行时梳理确认的允许差异基线）：
# - only_in_one_side_ok: 允许单侧独有（另一侧没有）的模块级符号名
# - shared_diff_ok: 允许两侧共有但实现体不同的模块级符号名
WHITELIST = {
    "tfp_base_tool.py": {
        # 主程序特有：IPC 配置从已加载的 __main__ 解析（SDK 版无 build_mode 依赖，
        # 直接硬编码默认值）；_DEFAULT_IPC_PORT 在主程序侧为 Tuple 解包赋值的一部分
        "only_in_one_side_ok": {"_get_ipc_config_defaults", "_DEFAULT_IPC_PORT"},
        # 同名默认值，取值来源不同（主程序=函数解析结果，SDK=字面量），语义等价
        "shared_diff_ok": {"_DEFAULT_IPC_HOST"},
    },
    "tfp_i18n_manager.py": {
        "only_in_one_side_ok": set(),
        "shared_diff_ok": set(),
    },
}

# 版本标识文件（__version__ 必须两侧一致）
VERSION_FILES = {
    "tfp_toolkit": FE_ROOT / "tfp_toolkit" / "__init__.py",
    "tfp_utils": FE_ROOT / "tfp_utils" / "__init__.py",
}


def _strip_docstrings(node):
    """递归剥离 AST 子树中所有函数/类/模块的首个 docstring 表达式。"""
    for child in ast.walk(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (child.body and isinstance(child.body[0], ast.Expr)
                    and isinstance(child.body[0].value, ast.Constant)
                    and isinstance(child.body[0].value.value, str)):
                child.body = child.body[1:]
    return node


def _assign_target_name(node):
    """提取模块级 Assign/AnnAssign 的目标名；Tuple 解包取第一个元素名。"""
    if isinstance(node, ast.Assign):
        t = node.targets[0]
        if isinstance(t, ast.Name):
            return t.id
        if isinstance(t, ast.Tuple) and t.elts and isinstance(t.elts[0], ast.Name):
            return t.elts[0].id
        return None
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def collect_symbols(path):
    """解析文件，返回 {符号名: [规范化 AST dump, ...]}（imports/裸表达式豁免）。"""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    symbols = {}
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Expr)):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        else:
            name = _assign_target_name(node)
        if not name:
            continue
        normalized = ast.dump(_strip_docstrings(node), include_attributes=False)
        symbols.setdefault(name, []).append(normalized)
    return symbols


def compare_pair(utils_path, toolkit_path, whitelist):
    """对比一对双源文件，返回违规描述列表（空列表 = 一致）。"""
    problems = []
    utils_syms = collect_symbols(utils_path)
    toolkit_syms = collect_symbols(toolkit_path)

    only_utils = sorted(set(utils_syms) - set(toolkit_syms) - whitelist["only_in_one_side_ok"])
    only_toolkit = sorted(set(toolkit_syms) - set(utils_syms) - whitelist["only_in_one_side_ok"])
    if only_utils:
        problems.append(f"仅 tfp_utils 侧存在（白名单外）: {only_utils}")
    if only_toolkit:
        problems.append(f"仅 tfp_toolkit 侧存在（白名单外）: {only_toolkit}")

    shared_diff = sorted(
        name for name in set(utils_syms) & set(toolkit_syms)
        if utils_syms[name] != toolkit_syms[name] and name not in whitelist["shared_diff_ok"]
    )
    if shared_diff:
        problems.append(f"共有符号实现体不一致（白名单外）: {shared_diff}")
    return problems


def test_dual_source_files_exist():
    """双源文件必须两侧同时存在（文件重命名/移动须同步更新本测试）。"""
    for name in DUAL_SOURCE_FILES:
        assert (FE_ROOT / "tfp_utils" / name).is_file(), f"tfp_utils/{name} 缺失"
        assert (FE_ROOT / "tfp_toolkit" / name).is_file(), f"tfp_toolkit/{name} 缺失"


def test_dual_source_implementation_consistency():
    """白名单外任何实现体差异即失败（docstring/注释差异不参与对比）。"""
    for name in DUAL_SOURCE_FILES:
        problems = compare_pair(
            FE_ROOT / "tfp_utils" / name,
            FE_ROOT / "tfp_toolkit" / name,
            WHITELIST[name],
        )
        assert not problems, (
            f"tfp_utils/{name} 与 tfp_toolkit/{name}（SDK 权威源）实现不一致:\n  "
            + "\n  ".join(problems)
            + "\n请将修改贡献回权威源（tfp_toolkit）或同步两侧实现，"
            "差异基线以本测试中的白名单为准"
        )


def test_sdk_version_consistency():
    """tfp_toolkit.__version__ 必须与 tfp_utils.__version__ 一致（正则读取，不 import）。"""
    versions = {}
    for pkg, path in VERSION_FILES.items():
        match = re.search(
            r'^__version__\s*=\s*["\']([^"\']+)["\']',
            path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        assert match, f"{pkg}/__init__.py 缺少 __version__ 定义"
        versions[pkg] = match.group(1)
    assert versions["tfp_toolkit"] == versions["tfp_utils"], (
        f"两侧 SDK 版本不一致: tfp_toolkit={versions['tfp_toolkit']}, "
        f"tfp_utils={versions['tfp_utils']}（请同步后统一递增）"
    )


# ---------- 故意制造 diff 验证守护的失败路径 ----------

def _make_minimal_pair(tmp_path, body):
    utils_file = tmp_path / "tfp_base_tool.py"
    toolkit_file = tmp_path / "tfp_toolkit_copy.py"
    utils_file.write_text(body, encoding="utf-8")
    toolkit_file.write_text(body, encoding="utf-8")
    return utils_file, toolkit_file


def test_compare_detects_shared_body_diff(tmp_path):
    """共有符号实现体不一致（白名单外）必须被检出。"""
    utils_file, toolkit_file = _make_minimal_pair(
        tmp_path, "def helper(x):\n    return x + 1\n"
    )
    toolkit_file.write_text("def helper(x):\n    return x + 2\n", encoding="utf-8")
    problems = compare_pair(utils_file, toolkit_file, WHITELIST["tfp_base_tool.py"])
    assert any("helper" in p for p in problems)


def test_compare_detects_unlisted_single_side_symbol(tmp_path):
    """白名单外的单侧独有符号必须被检出。"""
    utils_file, toolkit_file = _make_minimal_pair(
        tmp_path, "def helper(x):\n    return x\n"
    )
    toolkit_file.write_text(
        "def helper(x):\n    return x\n\n\ndef extra_only_in_toolkit():\n    return 1\n",
        encoding="utf-8",
    )
    problems = compare_pair(utils_file, toolkit_file, WHITELIST["tfp_base_tool.py"])
    assert any("extra_only_in_toolkit" in p for p in problems)


def test_compare_ignores_docstring_and_import_diff(tmp_path):
    """docstring 与 import 差异不触发失败（约定允许的差异）。"""
    utils_file, toolkit_file = _make_minimal_pair(
        tmp_path,
        "import os\n\n\ndef helper(x):\n    \"\"\"utils docstring\"\"\"\n    return x\n",
    )
    toolkit_file.write_text(
        "import sys\nimport json\n\n\ndef helper(x):\n"
        "    \"\"\"SDK docstring, much longer.\"\"\"\n    return x\n",
        encoding="utf-8",
    )
    assert compare_pair(utils_file, toolkit_file, WHITELIST["tfp_base_tool.py"]) == []


def test_compare_respects_whitelist(tmp_path):
    """白名单内的单侧独有符号与共有差异不触发失败。"""
    wl = {"only_in_one_side_ok": {"utils_only_fn"}, "shared_diff_ok": {"shared_var"}}
    utils_file = tmp_path / "a.py"
    toolkit_file = tmp_path / "b.py"
    utils_file.write_text(
        "def utils_only_fn():\n    return 1\n\n\nshared_var = ('a', 'b')\n",
        encoding="utf-8",
    )
    toolkit_file.write_text("shared_var = 'c'\n", encoding="utf-8")
    assert compare_pair(utils_file, toolkit_file, wl) == []
