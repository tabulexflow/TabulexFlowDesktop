# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""TabulexDocCreator test conftest - ensure TabulexDocCreator is first in sys.path"""
import sys
import os

# Insert TabulexDocCreator directory at the front of sys.path
# to prevent tool_main from resolving to TabulexFileOperator's tool_main
_tool_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _tool_dir in sys.path:
    sys.path.remove(_tool_dir)
sys.path.insert(0, _tool_dir)

# 追加 Desktop 根目录（置于末尾，避免 tool_main 名称冲突），供 Worker 导入 tfp_toolkit
_desktop_dir = os.path.dirname(os.path.dirname(os.path.dirname(_tool_dir)))
if os.path.isdir(os.path.join(_desktop_dir, 'tfp_toolkit')) and _desktop_dir not in sys.path:
    sys.path.append(_desktop_dir)

# Worker 的 _show_results 依赖 wx 事件循环/弹窗；测试中直接同步执行并忽略弹窗
try:
    import wx
    wx.CallAfter = lambda func, *args, **kwargs: func(*args, **kwargs)
    wx.MessageBox = lambda *args, **kwargs: 0
except Exception:
    pass
