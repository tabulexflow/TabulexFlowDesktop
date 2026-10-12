# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""TabulexDocCreator 公共 Grid 基类

继承自 TFP_BaseGrid（SDK共享Grid基类），提供 BDC 特有的 Grid 行为。
TFP_BaseGrid 已提供：Delete/Ctrl+C/V/A/Z/Y、复制/粘贴、撤销/重做、
行/列标签右键菜单、单元格右键菜单、只读模式、提示Label、列对齐等。

本类保留 BDC 特有的配置（MAX_UNDO=50）和可能的扩展。
"""

from tfp_toolkit.tfp_base_grid import TFP_BaseGrid
from tdc_i18n_manager import translate as tdc_translate


class tdc_BaseGrid(TFP_BaseGrid):
    """TabulexDocCreator 公共 Grid 基类

    继承 TFP_BaseGrid，BDC 特有配置：MAX_UNDO=50。

    子类可通过重写以下 hook 方法扩展行为：
    - on_cells_cleared(cells): 单元格被清空后调用
    - on_cells_pasted(cells): 单元格被粘贴后调用
    - on_rows_added(count): 行被添加后调用
    - on_rows_deleted(rows): 行被删除后调用

    子类若重写 _on_key_down，应先处理自身特殊按键，
    然后对未处理的按键调用 super()._on_key_down(event)。
    """

    MAX_UNDO = 50

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_undo', self.MAX_UNDO)
        super().__init__(*args, **kwargs)

    def _translate(self, key, **kwargs):
        """使用BDC的i18n管理器翻译，确保能找到BDC locales目录下的翻译键"""
        return tdc_translate(key, **kwargs)
