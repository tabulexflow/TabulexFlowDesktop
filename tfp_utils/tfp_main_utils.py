# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import os, sys
import tempfile
import traceback
import importlib
from pathlib import Path

def setup_debug():
    try:
        from tfp_utils.tfp_logger import setup_stdout_redirect
        log_file = setup_stdout_redirect('frontend_debug')
        print(f"Log file path: {log_file}")
        print("Debug environment setup succeeded")
    except Exception as e:
        try:
            log_dir = Path(__file__).parent.parent / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            fallback_log = log_dir / 'frontend_debug_fallback.log'
            with open(fallback_log, 'a', encoding='utf-8') as f:
                f.write(f"Failed to set up debug environment: {e}\n")
        except OSError:
            pass

def get_base_path():
    if getattr(sys, 'frozen', False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).parent.parent
    return base_path

def get_config_path():
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        config_dir = exe_dir / "config"
    else:
        config_dir = Path(__file__).parent.parent / "config"
    
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir

def is_writable_dir(p):
    """判断目录是否可创建且可写（运行时根目录选址用）。"""
    try:
        p = Path(p)
        p.mkdir(parents=True, exist_ok=True)
        # 不可预测随机文件名 + O_EXCL 创建，本地攻击者无法预置 symlink 造成覆写；delete=True 自动清理
        with tempfile.NamedTemporaryFile(dir=str(p), prefix=".tfp_wt_", delete=True) as f:
            f.write(b"x")
        return True
    except Exception:
        return False

def get_user_runtime_base_dir():
    """每用户可写运行时根目录（只读挂载时的回退目标）。"""
    xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(xdg) / "TabulexFlow"

def get_runtime_base_dir():
    """可写运行时根目录（工具目录/用户配置/配置目录的上级）。

    - 开发（源码运行）：前端工程根目录
    - 打包：可执行文件所在目录（可写时，便于便携）
    - 只读挂载（AppImage 挂载 / .deb 系统目录）：回退每用户数据目录
      <XDG_DATA_HOME>/TabulexFlow（默认 ~/.local/share/TabulexFlow）
    """
    if not getattr(sys, 'frozen', False):
        return Path(__file__).resolve().parent.parent
    exe_dir = Path(sys.executable).parent
    if is_writable_dir(exe_dir):
        return exe_dir
    return get_user_runtime_base_dir()

def get_resource_path(relative_path):
    try:
        base_path = get_base_path()

        print(f"Fetching resource path: {relative_path}")
        print(f"Base path: {base_path}")
        print(f"Frozen status: {getattr(sys, 'frozen', False)}")

        resource_path = base_path / relative_path
        print(f"Resource path 1: {resource_path}")
        print(f"Path 1 exists: {resource_path.exists()}")

        if resource_path.exists():
            print(f"Using resource path 1: {resource_path}")
            return resource_path

        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            exe_resource_path = exe_dir / relative_path
            print(f"Resource path 2: {exe_resource_path}")
            print(f"Path 2 exists: {exe_resource_path.exists()}")

            if exe_resource_path.exists():
                print(f"Using resource path 2: {exe_resource_path}")
                return exe_resource_path

        print(f"Final path used: {resource_path}")
        return resource_path

    except Exception as e:
        print(f"Error fetching resource path: {e}")
        return Path(relative_path)

def output_system_info():
    print("=" * 50)
    print("TabulexFlow startup debug info")
    print(f"Python path: {sys.executable}")
    print(f"Working directory: {os.getcwd()}")
    print(f"Frozen status: {getattr(sys, 'frozen', False)}")
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        print(f"MEIPASS: {sys._MEIPASS}")
    print(f"sys.path: {sys.path}")
    print("=" * 50)

def check_resource_structure():
    print("=" * 50)
    print("Directory structure integrity check")
    print("=" * 50)

    categories_to_check = [
        "tools_fe/tools_builtin_program",
        "tools_fe/tools_remote_program",
    ]

    for category in categories_to_check:
        category_path = get_resource_path(category)
        exists = category_path.exists()
        print(f"{category}: {'exists' if exists else 'does not exist'}")

        if exists:
            tools = [item.name for item in category_path.iterdir() if item.is_dir()]
            print(f"  Contains tools: {tools}")

def reload_tool_modules(tool_dir, current_module_name=None):
    try:
        DEVELOPMENT_MODE = not getattr(sys, 'frozen', False)
        if not DEVELOPMENT_MODE:
            return 0
        tool_dir_path = str(tool_dir)
        modules_to_reload = {}
        for module_name, module in list(sys.modules.items()):
            try:
                if (hasattr(module, '__file__') and
                    module.__file__ and
                    tool_dir_path in module.__file__):
                    if current_module_name and module_name == current_module_name:
                        continue
                    module_file = module.__file__
                    if os.path.exists(module_file):
                        modules_to_reload[module_name] = {
                            'module': module,
                            'file': module_file,
                            'mtime': os.path.getmtime(module_file)
                        }
                        print(f"Dev mode: preparing to reload module: {module_name}")
            except (AttributeError, TypeError, FileNotFoundError):
                continue
        reloaded_count = 0
        for module_name, info in modules_to_reload.items():
            try:
                current_mtime = os.path.getmtime(info['file'])
                if current_mtime > info['mtime']:
                    importlib.reload(info['module'])
                    reloaded_count += 1
                    print(f"Dev mode: hot reloaded: {module_name}")
                else:
                    print(f"Dev mode: module unchanged, skipped: {module_name}")
            except Exception as e:
                print(f"Dev mode: failed to reload module {module_name}: {e}")
        print(f"Dev mode: reloaded {reloaded_count} modules in total")
        return reloaded_count
    except Exception as e:
        print(f"Dev mode: error reloading tool modules: {e}")
        return 0