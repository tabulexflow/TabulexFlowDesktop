# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import wx
import os


class tfo_FileDropToPathInput(wx.FileDropTarget):
    def __init__(self, text_ctrl, tool_instance):
        super().__init__()
        self.text_ctrl = text_ctrl
        self.tool_instance = tool_instance

    def OnDragOver(self, x, y, default):
        return wx.DragLink

    def OnDropFiles(self, x, y, filenames):
        if not filenames:
            return False

        target_path = None
        for filepath in filenames:
            if os.path.isdir(filepath):
                target_path = filepath
                break

        if target_path is None:
            return False

        self.text_ctrl.SetValue(target_path)
        self.text_ctrl.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
        if self.text_ctrl == self.tool_instance.input_search_path01:
            self.tool_instance.on_search_path_changed(None)
        elif self.text_ctrl == self.tool_instance.input_source_path03:
            self.tool_instance.on_source_path_changed(None)
        elif self.text_ctrl == self.tool_instance.input_dest_path03:
            self.tool_instance.on_dest_path_changed(None)
        return False
