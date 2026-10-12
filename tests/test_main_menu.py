# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""TFP_MainMenuGenerator 菜单生成逻辑测试（UI 解耦纯逻辑）

覆盖：菜单生成器初始化、菜单栏构建与排序、菜单项查找/启停/勾选/改标签、
自定义项插入/移除、点击处理、状态快照、生成菜单项/组的序列化。
通过注入内存 config loader，不依赖真实配置文件与 wx 界面。
"""
import pytest

from tfp_utils.tfp_main_menu import (
    TFP_MainMenuGenerator,
    TFP_GeneratedMenuGroup,
    TFP_GeneratedMenuItem,
    TFP_MenuBarPosition,
)
from tfp_utils.tfp_menu_loader import TFP_MenuConfig, TFP_MenuGroup, TFP_MenuItem, TFP_MenuConfigError


def _build_config() -> TFP_MenuConfig:
    config = TFP_MenuConfig(version="1.0.0")
    config.main_menu["file"] = TFP_MenuGroup(id="file", label={"zh": "文件", "en": "File"}, items=[
        TFP_MenuItem(id="file.exit", label={"zh": "退出", "en": "Exit"}),
        TFP_MenuItem(id="file.open", label={"en": "Open"}, children=[
            TFP_MenuItem(id="file.open.txt", label={"en": "TXT"}),
        ]),
        TFP_MenuItem(id="file.check", label={"en": "Check"}, item_type="checkable", checkable=True),
    ])
    config.main_menu["tools"] = TFP_MenuGroup(id="tools", label={"en": "Tools"}, items=[
        TFP_MenuItem(id="tools.bom", label={"en": "BOM"}),
    ])
    config.main_menu["extra"] = TFP_MenuGroup(id="extra", label={"en": "Extra"}, items=[])
    return config


class FakeLoader:
    def __init__(self, config):
        self._config = config

    def load(self, force_reload=False):
        return self._config


@pytest.fixture()
def generator():
    g = TFP_MainMenuGenerator()
    g.initialize(FakeLoader(_build_config()))
    return g


def test_default_menu_order():
    assert TFP_MainMenuGenerator.DEFAULT_MENU_ORDER == ["file", "tools", "window", "settings", "account", "help"]


def test_initialize_success():
    g = TFP_MainMenuGenerator()
    assert g.initialize(FakeLoader(_build_config())) is True
    assert g.get_menu_group("file") is not None


def test_initialize_failure():
    class BadLoader:
        def load(self, force_reload=False):
            raise TFP_MenuConfigError("boom")
    g = TFP_MainMenuGenerator()
    assert g.initialize(BadLoader()) is False


def test_get_menu_bar_ordered_and_filters_empty(generator):
    groups = generator.get_menu_bar()
    ids = [g.id for g in groups]
    assert ids == ["file", "tools"]  # 按 DEFAULT_MENU_ORDER 排序，空组 extra 被过滤


def test_find_item_nested(generator):
    result = generator.find_item("file.open.txt")
    assert result is not None
    group, item = result
    assert group.id == "file"
    assert item.id == "file.open.txt"
    assert generator.find_item("nope") is None


def test_set_item_enabled(generator):
    assert generator.set_item_enabled("file.exit", False) is True
    item = generator.find_item("file.exit")[1]
    assert item.enabled is False
    assert generator.set_item_enabled("nope", False) is False


def test_set_item_visible(generator):
    assert generator.set_item_visible("file.exit", False) is True
    assert generator.find_item("file.exit")[1].visible is False


def test_set_item_checked_only_checkable(generator):
    assert generator.set_item_checked("file.check", True) is True
    assert generator.find_item("file.check")[1].checked is True
    # 非 checkable 项不可设置勾选
    assert generator.set_item_checked("file.exit", True) is False


def test_set_item_label(generator):
    assert generator.set_item_label("file.exit", "退出应用") is True
    assert generator.find_item("file.exit")[1].display_text == "退出应用"


def test_insert_and_remove_custom_item(generator):
    new_item = TFP_GeneratedMenuItem(id="file.custom", display_text="Custom")
    assert generator.insert_custom_item("file", "file.exit", new_item) is True
    group = generator.get_menu_group("file")
    ids = [i.id for i in group.items]
    assert ids == ["file.exit", "file.custom", "file.open", "file.check"]
    assert generator.remove_custom_item("file.custom") is True
    assert generator.find_item("file.custom") is None
    # 插入到不存在的组失败
    assert generator.insert_custom_item("nope", None, new_item) is False


def test_handle_menu_click_not_found(generator):
    result = generator.handle_menu_click("nope")
    assert result["success"] is False


def test_handle_menu_click_disabled(generator):
    generator.set_item_enabled("file.exit", False)
    result = generator.handle_menu_click("file.exit")
    assert result["success"] is False


def test_handle_menu_click_action_callback(generator):
    calls = []
    item = generator.find_item("file.exit")[1]
    item.action_callback = lambda menu_id, tag: calls.append(menu_id) or {"ok": True}
    result = generator.handle_menu_click("file.exit")
    assert calls == ["file.exit"]
    assert result["ok"] is True


def test_handle_menu_click_fallback_callback(generator):
    generator.set_on_menu_click(lambda menu_id, group_id: {"action": "default"})
    result = generator.handle_menu_click("tools.bom")
    assert result["action"] == "default"


def test_get_menu_state_snapshot(generator):
    snapshot = generator.get_menu_state_snapshot()
    assert snapshot["language"] == "zh"
    assert "file" in snapshot["groups"]


def test_generated_menu_item_to_dict():
    item = TFP_GeneratedMenuItem(
        id="a", display_text="A", shortcut="Ctrl+A", item_type="normal",
        enabled=True, visible=True, checked=False, tooltip="tip",
        has_submenu=True,
        children=[TFP_GeneratedMenuItem(id="b", display_text="B")],
    )
    d = item.to_dict()
    assert d["id"] == "a"
    assert d["shortcut"] == "Ctrl+A"
    assert len(d["children"]) == 1


def test_generated_menu_group_visible_items():
    group = TFP_GeneratedMenuGroup(id="g", display_text="G", items=[
        TFP_GeneratedMenuItem(id="v", display_text="V", visible=True),
        TFP_GeneratedMenuItem(id="h", display_text="H", visible=False),
    ])
    assert [i.id for i in group.visible_items] == ["v"]
    d = group.to_dict()
    assert len(d["items"]) == 2


def test_menu_bar_position_enum():
    assert TFP_MenuBarPosition("top") == TFP_MenuBarPosition.TOP
    assert TFP_MenuBarPosition("bottom") == TFP_MenuBarPosition.BOTTOM
