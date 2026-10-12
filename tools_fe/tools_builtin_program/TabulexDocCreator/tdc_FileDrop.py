# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
import os
import re
import ctypes

ALLOWED_EXTENSIONS = {'.pdf', '.xlsx', '.xls', '.docx', '.doc', '.pptx', '.ppt', '.csv'}


def parse_shortcut(lnk_path):
    try:
        class GUID(ctypes.Structure):
            _fields_ = [
                ('Data1', ctypes.wintypes.DWORD),
                ('Data2', ctypes.wintypes.WORD),
                ('Data3', ctypes.wintypes.WORD),
                ('Data4', ctypes.wintypes.BYTE * 8)
            ]
        IID_IShellLink = GUID(0x000214EE, 0x0000, 0x0000, (0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))
        CLSID_ShellLink = GUID(0x00021401, 0x0000, 0x0000, (0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))
        class IPersistFile(ctypes.c_void_p):
            pass
        class IShellLink(ctypes.c_void_p):
            pass
        ole32 = ctypes.windll.ole32
        shell32 = ctypes.windll.shell32
        ole32.CoInitialize(None)
        psl = ctypes.POINTER(IShellLink)()
        hr = ole32.CoCreateInstance(ctypes.byref(CLSID_ShellLink), None, 1, ctypes.byref(IID_IShellLink), ctypes.byref(psl))
        if hr != 0:
            ole32.CoUninitialize()
            return None
        ppf = ctypes.POINTER(IPersistFile)()
        hr = psl.QueryInterface(ctypes.byref(IID_IShellLink), ctypes.byref(ppf))
        if hr != 0:
            psl.Release()
            ole32.CoUninitialize()
            return None
        hr = ppf.Load(lnk_path, 0)
        if hr != 0:
            ppf.Release()
            psl.Release()
            ole32.CoUninitialize()
            return None
        buf = ctypes.create_unicode_buffer(260)
        psl.GetPath(buf, ctypes.sizeof(buf), None, 0)
        target_path = buf.value
        ppf.Release()
        psl.Release()
        ole32.CoUninitialize()
        return target_path if target_path else None
    except Exception:
        try:
            with open(lnk_path, 'rb') as f:
                content = f.read()
                path_pattern = r'[A-Za-z]:\\[^\x00]*'
                matches = re.findall(path_pattern.encode('latin-1'), content)
                for match in matches:
                    try:
                        potential_path = match.decode('utf-8', errors='ignore')
                        if os.path.exists(potential_path):
                            # B1-1：兜底路径同样要求扩展名在白名单内再返回
                            # （防止 .lnk 内嵌的非真实目标被直接接受，统一受 ALLOWED_EXTENSIONS 约束）
                            _, ext = os.path.splitext(potential_path)
                            if ext.lower() in ALLOWED_EXTENSIONS:
                                return potential_path
                    except Exception:
                        continue
        except Exception:
            pass
        return None


def _resolve_dropped_path(path):
    if os.path.isfile(path):
        _, ext = os.path.splitext(path)
        ext = ext.lower()
        if ext == '.lnk' or ext == '':
            target_path = parse_shortcut(path)
            if target_path and os.path.exists(target_path):
                return target_path
            else:
                parent_dir = os.path.dirname(path)
                if os.path.isdir(parent_dir):
                    return parent_dir
    return path


class tdc_FileDropToGrid(wx.FileDropTarget):
    def __init__(self, grid, col_index):
        super().__init__()
        self.grid = grid
        self.col_index = col_index

    def OnDragOver(self, x, y, default):
        return wx.DragLink

    def OnDropFiles(self, x, y, filenames):
        if not filenames:
            return False
        existing_paths = set()
        for row_idx in range(self.grid.DATA_ROW_START, self.grid.GetNumberRows()):
            path = self.grid.GetCellValue(row_idx, self.col_index).strip()
            if path:
                existing_paths.add(path.lower())
        new_paths = []
        rejected_files = []
        for path in filenames:
            resolved = _resolve_dropped_path(path)
            if not os.path.exists(resolved):
                continue
            if os.path.isfile(resolved):
                _, ext = os.path.splitext(resolved)
                if ext.lower() not in ALLOWED_EXTENSIONS:
                    rejected_files.append(os.path.basename(resolved))
                    continue
            if resolved.lower() not in existing_paths:
                new_paths.append(resolved)
                existing_paths.add(resolved.lower())
        if rejected_files:
            from tdc_i18n_manager import translate
            wx.MessageBox(
                translate('msg_files_rejected', count=len(rejected_files), files=', '.join(rejected_files[:5])),
                translate('dialog_title_warning'), wx.OK | wx.ICON_WARNING
            )
        if not new_paths:
            return True
        last_nonempty_row = self.grid.DATA_ROW_START - 1
        for i in range(self.grid.DATA_ROW_START, self.grid.GetNumberRows()):
            if self.grid.GetCellValue(i, self.col_index).strip():
                last_nonempty_row = i
        insert_position = last_nonempty_row + 1
        total_row_count = self.grid.GetNumberRows()
        if insert_position + len(new_paths) > total_row_count:
            self.grid.AppendRows(insert_position + len(new_paths) - total_row_count)
        for i, path in enumerate(new_paths):
            row_idx = insert_position + i
            self.grid.SetCellValue(row_idx, self.col_index, path)
            self.grid.SetCellValue(row_idx, self.grid.COL_ID, str(row_idx - self.grid.DATA_ROW_START + 1))
        if hasattr(self.grid, 'tool_instance') and hasattr(self.grid, 'doc_type'):
            from tdc_i18n_manager import translate
            self.grid.tool_instance.update_status_left(self.grid.doc_type, translate('msg_files_dropped', count=len(new_paths)))
        return True


class tdc_FileDropToPathInput(wx.FileDropTarget):
    def __init__(self, text_ctrl, callback=None):
        super().__init__()
        self.text_ctrl = text_ctrl
        self.callback = callback

    def OnDragOver(self, x, y, default):
        return wx.DragLink

    def OnDropFiles(self, x, y, filenames):
        if filenames:
            old_path = _resolve_dropped_path(filenames[0])
            if os.path.isfile(old_path):
                _, ext = os.path.splitext(old_path)
                if ext.lower() not in ALLOWED_EXTENSIONS:
                    from tdc_i18n_manager import translate
                    wx.MessageBox(
                        translate('msg_files_rejected', count=1, files=os.path.basename(old_path)),
                        translate('dialog_title_warning'), wx.OK | wx.ICON_WARNING
                    )
                    return True
            elif os.path.isdir(old_path):
                pass
            else:
                return True
            self.text_ctrl.SetValue(old_path)
            self.text_ctrl.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
            if self.callback:
                self.callback(old_path)
        return True
