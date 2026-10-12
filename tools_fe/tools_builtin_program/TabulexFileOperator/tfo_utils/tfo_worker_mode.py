# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

from enum import Enum


class WorkerMode(Enum):
    APPLY = "apply"
    PREVIEW = "preview"
    EXECUTE = "execute"
