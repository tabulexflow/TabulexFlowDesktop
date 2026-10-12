# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-TabulexFlow-Commercial
#
# Dual License / 双重许可:
#
#   Option 1 - GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later).
#   Applies to the open-source frontend main program and its BuiltinProgram tools.
#   选项 1 - GNU AGPL v3 或更高版本（AGPL-3.0-or-later）。
#   适用于开源前端主程序及其 BuiltinProgram 工具。
#
#   Option 2 - TabulexFlow Commercial License
#   (LicenseRef-TabulexFlow-Commercial).
#   Applies to closed-source commercial tools in the TabulexFlow ecosystem
#   that are authorized to use this file under that license.
#   选项 2 - TabulexFlow 商业许可（LicenseRef-TabulexFlow-Commercial）。
#   适用于已获授权使用该许可的 TabulexFlow 生态内闭源商业工具。
#
# Full terms of both licenses are provided in the LICENSE file in this directory
# (AGPL terms are also in LICENSE.txt at the repository root).
# 两种许可的完整条款见本目录下 LICENSE 文件（AGPL 条款另见仓库根 LICENSE.txt）。
#
# IMPORTANT / 重要（维护者须知）：
# 本文件属双许可 SDK，不得 import 仅以 GPL/AGPL 授权的 copyleft-only 库（如 mutagen、PyMuPDF），
# 否则商业许可选项将失效。详见本目录 LICENSE 文件的 "Maintainer Note / 维护者须知"。
# This file is dual-licensed; do NOT import copyleft-only (GPL/AGPL-exclusive) libraries
# such as mutagen or PyMuPDF, or the commercial license option is invalidated.
# See the Maintainer Note in the LICENSE file in this directory.

"""
TabulexFlow DPI适配工具（SDK权威源）

提供DPI缩放因子计算和像素值缩放功能。
子工具应使用此模块的 spx_calc() 函数进行DPI适配，
而非各自手动实现。

注意：此文件是SDK的权威源。主程序的 spx_calc 方法和 TFP_DPI_SCALE_FACTOR 属性
应与此模块的行为逻辑保持一致。
"""

import logging
import sys
from typing import Optional

logger = logging.getLogger(__name__)

# 全局DPI缩放因子（模块级变量）
_TFP_DPI_SCALE_FACTOR: Optional[float] = None


def get_dpi_scale_factor() -> float:
    """获取DPI缩放因子，首次调用时自动计算。

    计算优先级：
    1. wxPython wx.Display.GetPPI()（如果wx可用）
    2. Win32 API GetDpiForSystem() 或 GetDeviceCaps()（如果ctypes可用）
    3. 默认值 1.0

    Returns:
        DPI缩放因子（>= 1.0）
    """
    global _TFP_DPI_SCALE_FACTOR
    if _TFP_DPI_SCALE_FACTOR is not None:
        return _TFP_DPI_SCALE_FACTOR

    # Linux(wxGTK)/macOS(Cocoa)：工具包已按系统 DPI 自动缩放，wx 坐标为逻辑像素，
    # 不能用 GetPPI()/96 再缩放（会双重放大）。仅 Windows 在 per-monitor DPI aware
    # 模式下使用物理像素，需手动缩放。此逻辑与前端主程序 TFP_MainFrame 保持一致。
    if sys.platform != 'win32':
        _TFP_DPI_SCALE_FACTOR = 1.0
        logger.info("[DPI] non-Windows platform: toolkit handles DPI scaling, scale_factor=1.0")
        return _TFP_DPI_SCALE_FACTOR

    dpi_wx = 0
    dpi_winapi = 0

    # 尝试wxPython方式
    try:
        import wx
        display = wx.Display(0)
        ppi = display.GetPPI()
        dpi_wx = ppi.x
    except Exception as e:
        logger.debug(f"wx.Display.GetPPI() failed: {e}")

    # 尝试Win32 API方式
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.GetDpiForSystem.restype = ctypes.c_uint
        dpi_winapi = user32.GetDpiForSystem()
    except Exception:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            hdc = user32.GetDC(None)
            if hdc:
                dpi_winapi = gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX = 88
                user32.ReleaseDC(None, hdc)
        except Exception:
            pass

    # 选择最终DPI值：优先wx，回退Win32 API，最低96
    final_dpi = dpi_wx if dpi_wx > 96 else (dpi_winapi if dpi_winapi > 96 else max(dpi_wx, dpi_winapi, 96))
    _TFP_DPI_SCALE_FACTOR = max(1.0, final_dpi / 96.0)

    logger.info(f"[DPI] scale_factor={_TFP_DPI_SCALE_FACTOR} (dpi_wx={dpi_wx}, dpi_winapi={dpi_winapi}, final_dpi={final_dpi})")
    return _TFP_DPI_SCALE_FACTOR


def spx_calc(value):
    """Scale pixels by DPI factor. 对固定像素值进行DPI缩放。

    Args:
        value: 逻辑像素值（96 DPI基准下的像素数）。
               传入 -1 时返回 -1（wxPython中-1表示"默认尺寸"）。

    Returns:
        缩放后的整数值。

    Example:
        spx_calc(100)  # 在192 DPI下返回 200
        spx_calc(-1)   # 返回 -1
    """
    if value == -1:
        return -1
    sf = get_dpi_scale_factor()
    return int(value * sf)


def set_dpi_scale_factor(scale_factor: float):
    """设置DPI缩放因子（由主程序在初始化时调用）。

    当主程序已经计算了DPI缩放因子时，可通过此函数设置，
    避免子工具重复计算。子工具也可从父进程的上下文中获取
    缩放因子后调用此函数。

    Args:
        scale_factor: DPI缩放因子（必须 >= 1.0，小于1.0的值会被忽略）
    """
    global _TFP_DPI_SCALE_FACTOR
    if scale_factor and scale_factor > 1.0:
        _TFP_DPI_SCALE_FACTOR = scale_factor
        logger.info(f"[DPI] Using externally set DPI scale factor: {scale_factor}")
