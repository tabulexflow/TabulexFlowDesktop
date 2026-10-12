# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""菜单配置加载器 / 菜单动作分发器 / 主程序工具函数测试

覆盖：TFP_MenuConfigLoader 解析/校验/缓存/热重载、TFP_MenuGroup/MenuItem 查询、
TFP_MenuActionDispatcher 注册/执行/钩子/历史、tfp_main_utils 路径与模块重载。
"""
import json
import os
import time

import pytest

from tfp_utils.tfp_menu_loader import (
    TFP_MenuConfig,
    TFP_MenuConfigError,
    TFP_MenuConfigLoader,
    TFP_MenuGroup,
    TFP_MenuItem,
    TFP_MenuItemType,
)
from tfp_utils.tfp_menu_handler import (
    TFP_MenuActionDispatcher,
    TFP_MenuActionResult,
    TFP_MenuActionStatus,
    TFP_MenuActionHandler,
    get_menu_dispatcher,
    register_default_actions,
)
from tfp_utils import tfp_main_utils

SAMPLE_CONFIG = {
    "version": "1.0.0",
    "main_menu": {
        "file": {
            "id": "file",
            "label": {"zh": "文件", "en": "File"},
            "items": [
                {"id": "file.exit", "type": "normal", "label": {"zh": "退出", "en": "Exit"}},
                {"type": "separator"},
                {"id": "file.open", "type": "normal", "label": {"en": "Open"},
                 "children": [{"id": "file.open.txt", "type": "normal", "label": {"en": "TXT"}}]},
            ],
        },
        "help": {"id": "help", "label": {"en": "Help"}, "items": []},
    },
    "tool_menu_template": {
        "edit": {"id": "edit", "label": {"en": "Edit"}, "items": []},
    },
}


def _write_config(tmp_path, data):
    path = tmp_path / "menu_config.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


# ========== TFP_MenuConfigLoader ==========

def test_load_success(tmp_path):
    path = _write_config(tmp_path, SAMPLE_CONFIG)
    loader = TFP_MenuConfigLoader(config_dir=str(tmp_path))
    config = loader.load()
    assert config.version == "1.0.0"
    assert config.is_loaded is True
    assert config.get_main_menu_group("file") is not None
    assert config.get_tool_menu_group("edit") is not None


def test_load_caches_result(tmp_path):
    path = _write_config(tmp_path, SAMPLE_CONFIG)
    loader = TFP_MenuConfigLoader(config_dir=str(tmp_path))
    c1 = loader.load()
    c2 = loader.load()
    assert c1 is c2  # 命中缓存


def test_load_force_reload(tmp_path):
    path = _write_config(tmp_path, SAMPLE_CONFIG)
    loader = TFP_MenuConfigLoader(config_dir=str(tmp_path))
    loader.load()
    path.write_text(json.dumps({**SAMPLE_CONFIG, "version": "9.9.9"}), encoding="utf-8")
    os.utime(path, (time.time(), time.time()))
    config = loader.load(force_reload=True)
    assert config.version == "9.9.9"


def test_load_missing_file_raises(tmp_path):
    loader = TFP_MenuConfigLoader(config_dir=str(tmp_path))
    with pytest.raises(TFP_MenuConfigError):
        loader.load()


def test_load_invalid_json_raises(tmp_path):
    (tmp_path / "menu_config.json").write_text("{bad json", encoding="utf-8")
    loader = TFP_MenuConfigLoader(config_dir=str(tmp_path))
    with pytest.raises(TFP_MenuConfigError):
        loader.load()


def test_validate_config_ok(tmp_path):
    _write_config(tmp_path, SAMPLE_CONFIG)
    loader = TFP_MenuConfigLoader(config_dir=str(tmp_path))
    ok, errors = loader.validate_config()
    assert ok is True
    assert errors == []


def test_validate_config_errors(tmp_path):
    bad = {"main_menu": {"file": {"id": "mismatch", "items": [{"type": "normal"}]}}}
    _write_config(tmp_path, bad)
    loader = TFP_MenuConfigLoader(config_dir=str(tmp_path))
    ok, errors = loader.validate_config()
    assert ok is False
    joined = "\n".join(errors)
    assert "version" in joined
    assert "tool_menu_template" in joined
    assert "ID 不匹配" in joined
    assert "缺少 id 字段" in joined


def test_reload_if_changed(tmp_path):
    path = _write_config(tmp_path, SAMPLE_CONFIG)
    loader = TFP_MenuConfigLoader(config_dir=str(tmp_path))
    loader.load()
    time.sleep(0.01)
    path.write_text(json.dumps({**SAMPLE_CONFIG, "version": "2.0.0"}), encoding="utf-8")
    os.utime(path, (time.time(), time.time()))
    assert loader.reload_if_changed() is True
    assert loader.current_config.version == "2.0.0"
    assert loader.reload_if_changed() is False  # 未变化


def test_load_callbacks(tmp_path):
    _write_config(tmp_path, SAMPLE_CONFIG)
    loader = TFP_MenuConfigLoader(config_dir=str(tmp_path))
    seen = []
    loader.add_load_callback(lambda cfg: seen.append(cfg.version))
    loader.load()
    assert seen == ["1.0.0"]


def test_menu_group_get_item_by_id():
    group = TFP_MenuGroup(id="file", items=[
        TFP_MenuItem(id="file.exit", label={"en": "Exit"}),
        TFP_MenuItem(id="file.open", label={"en": "Open"}, children=[
            TFP_MenuItem(id="file.open.txt", label={"en": "TXT"}),
        ]),
    ])
    assert group.get_item_by_id("file.exit").id == "file.exit"
    assert group.get_item_by_id("file.open.txt").id == "file.open.txt"  # 递归查找子菜单
    assert group.get_item_by_id("missing") is None


def test_menu_config_find_item():
    config = TFP_MenuConfig()
    config.main_menu["file"] = TFP_MenuGroup(id="file", items=[
        TFP_MenuItem(id="file.exit", label={"en": "Exit"}),
    ])
    config.tool_menu_template["edit"] = TFP_MenuGroup(id="edit", items=[
        TFP_MenuItem(id="edit.paste", label={"en": "Paste"}),
    ])
    found = config.find_item("edit.paste")
    assert found is not None
    group, item = found
    assert group.id == "edit"
    assert item.id == "edit.paste"
    assert config.find_item("nope") is None


def test_menu_item_properties():
    sep = TFP_MenuItem(item_type="separator")
    assert sep.is_separator is True
    assert sep.is_action_item is False
    normal = TFP_MenuItem(id="a", label={"en": "A"})
    assert normal.is_action_item is True
    assert normal.has_submenu is False
    sub = TFP_MenuItem(id="b", label={"en": "B"}, children=[TFP_MenuItem(id="c", label={"en": "C"})])
    assert sub.has_submenu is True
    d = normal.to_dict()
    assert d["id"] == "a"


def test_menu_group_label_text():
    group = TFP_MenuGroup(label={"zh": "文件"})
    assert group.label_text == "文件"
    group2 = TFP_MenuGroup(label={"en": "File"})
    assert group2.label_text == "File"  # 无 zh 回退 en


# ========== TFP_MenuActionDispatcher ==========

@pytest.fixture()
def dispatcher():
    TFP_MenuActionDispatcher._instance = None
    d = TFP_MenuActionDispatcher()
    yield d
    TFP_MenuActionDispatcher._instance = None


def test_register_and_get(dispatcher):
    assert dispatcher.register_action("a.b", lambda **k: {"ok": 1}, label="A") is True
    assert dispatcher.has_handler("a.b") is True
    assert dispatcher.get_handler("a.b").label == "A"
    assert dispatcher.unregister_handler("a.b") is True
    assert dispatcher.has_handler("a.b") is False


def test_register_empty_id_rejected(dispatcher):
    assert dispatcher.register_action("", lambda **k: None) is False


def test_execute_success(dispatcher):
    dispatcher.register_action("a.b", lambda source_tool=None, data=None: {"done": True})
    result = dispatcher.execute("a.b")
    assert result.is_success is True
    assert result.status == TFP_MenuActionStatus.SUCCESS
    assert result.data == {"done": True}


def test_execute_not_found(dispatcher):
    result = dispatcher.execute("nope")
    assert result.status == TFP_MenuActionStatus.NOT_FOUND


def test_execute_disabled(dispatcher):
    dispatcher.register_action("a.b", lambda **k: None, enabled_check=lambda: False)
    result = dispatcher.execute("a.b")
    assert result.status == TFP_MenuActionStatus.DISABLED


def test_execute_requires_confirmation(dispatcher):
    dispatcher.register_action("a.b", lambda **k: None, requires_confirmation=True)
    result = dispatcher.execute("a.b", data={})
    assert result.status == TFP_MenuActionStatus.REQUIRES_CONFIRM
    result2 = dispatcher.execute("a.b", data={"confirmed": True})
    assert result2.is_success is True


def test_execute_handler_exception(dispatcher):
    def boom(**k):
        raise RuntimeError("boom")
    dispatcher.register_action("a.b", boom)
    handled = []
    dispatcher.add_error_handler(lambda result, kind: handled.append(kind))
    result = dispatcher.execute("a.b")
    assert result.status == TFP_MenuActionStatus.FAILED
    assert handled == ["exception"]


def test_execute_pre_hook_reject(dispatcher):
    dispatcher.register_action("a.b", lambda **k: None)
    dispatcher.add_pre_hook(lambda mid, src, data: False)
    result = dispatcher.execute("a.b")
    assert result.status == TFP_MenuActionStatus.FAILED


def test_history_and_clear(dispatcher):
    dispatcher.register_action("a.b", lambda **k: None)
    dispatcher.execute("a.b")
    history = dispatcher.get_action_history()
    assert len(history) == 1
    assert history[0]["menu_id"] == "a.b"
    dispatcher.clear_history()
    assert dispatcher.get_action_history() == []


def test_get_registered_actions_sorted(dispatcher):
    dispatcher.register_action("z.z", lambda **k: None)
    dispatcher.register_action("a.a", lambda **k: None)
    actions = dispatcher.get_registered_actions()
    assert [a["menu_id"] for a in actions] == ["a.a", "z.z"]


def test_register_default_actions(dispatcher):
    register_default_actions(dispatcher)
    assert dispatcher.has_handler("file.refresh_tools") is True
    assert dispatcher.has_handler("file.exit") is True
    assert dispatcher.has_handler("help.about") is True
    result = dispatcher.execute("file.refresh_tools")
    assert result.is_success is True
    assert result.data["refreshed"] is True


def test_action_result_serialization():
    r = TFP_MenuActionResult(status=TFP_MenuActionStatus.SUCCESS, menu_id="a", message="ok")
    d = r.to_dict()
    assert d["status"] == "success"
    assert d["menu_id"] == "a"


def test_action_handler_checks():
    handler = TFP_MenuActionHandler(
        menu_id="a", handler=lambda **k: None,
        enabled_check=lambda: True, visible_check=lambda: False,
    )
    assert handler.is_enabled() is True
    assert handler.is_visible() is False
    # 检查函数异常时默认启用/可见
    handler2 = TFP_MenuActionHandler(
        menu_id="b", handler=lambda **k: None,
        enabled_check=lambda: (_ for _ in ()).throw(RuntimeError()),
    )
    assert handler2.is_enabled() is True


# ========== tfp_main_utils ==========

def test_get_base_path():
    path = tfp_main_utils.get_base_path()
    assert path is not None
    assert (path / "main.py").exists() or (path / "tfp_utils").exists()


def test_get_config_path():
    path = tfp_main_utils.get_config_path()
    assert path is not None
    assert path.exists()


def test_get_resource_path_existing():
    p = tfp_main_utils.get_resource_path("tfp_utils")
    assert p.exists()


def test_reload_tool_modules_returns_int():
    # 开发模式（非 frozen）下执行，无工具目录模块时返回 0
    result = tfp_main_utils.reload_tool_modules("nonexistent_tool_dir")
    assert isinstance(result, int)
