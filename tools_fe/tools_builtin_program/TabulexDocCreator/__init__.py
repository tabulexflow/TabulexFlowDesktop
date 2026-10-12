# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

try:
    from tool_main import tdc_TabulexDocCreatorTool
    __all__ = ['tdc_TabulexDocCreatorTool']
except ImportError:
    __all__ = []
