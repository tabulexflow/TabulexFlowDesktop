# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""TabulexFileOperator test conftest - ensure tool directory is in sys.path"""
import sys
import os

_tool_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _tool_dir not in sys.path:
    sys.path.insert(0, _tool_dir)