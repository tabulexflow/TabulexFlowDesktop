# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import sys
import ctypes
from ctypes import wintypes


def delete_to_recycle(path):
    if not isinstance(path, str):
        path = str(path)

    if os.name == 'nt':
        return _delete_to_recycle_windows(path)
    else:
        return _delete_to_recycle_cross_platform(path)


def _delete_to_recycle_windows(path):
    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ('hwnd', wintypes.HWND),
            ('wFunc', wintypes.UINT),
            ('pFrom', wintypes.LPCWSTR),
            ('pTo', wintypes.LPCWSTR),
            ('fFlags', wintypes.DWORD),
            ('fAnyOperationsAborted', wintypes.BOOL),
            ('hNameMappings', wintypes.LPVOID),
            ('lpszProgressTitle', wintypes.LPCWSTR)
        ]

    SHFileOperation = ctypes.windll.shell32.SHFileOperationW
    SHFileOperation.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
    SHFileOperation.restype = wintypes.DWORD

    path = path + '\0\0'

    fileop = SHFILEOPSTRUCTW()
    fileop.hwnd = None
    fileop.wFunc = 0x0003
    fileop.pFrom = path
    fileop.pTo = None
    # FOF_ALLOWUNDO(0x40) 移入回收站；FOF_NOCONFIRMATION(0x10) 不弹确认框；
    # FOF_NOERRORUI(0x400) + FOF_SILENT(0x4) 不弹系统错误UI/进度对话框，
    # 错误统一由调用方通过返回值写结果列，避免双重弹窗
    fileop.fFlags = 0x0040 | 0x0010 | 0x0400 | 0x0004
    fileop.fAnyOperationsAborted = False
    fileop.hNameMappings = None
    fileop.lpszProgressTitle = None

    result = SHFileOperation(ctypes.byref(fileop))
    return result


def _delete_to_recycle_cross_platform(path):
    try:
        import send2trash
        send2trash.send2trash(path)
        return 0
    except ImportError:
        return -1
