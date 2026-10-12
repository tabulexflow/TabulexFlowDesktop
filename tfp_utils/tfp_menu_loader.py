# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import os
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class TFP_MenuItemType(Enum):
    NORMAL = "normal"
    SEPARATOR = "separator"
    SUBMENU = "submenu"
    CHECKABLE = "checkable"
    RADIO = "radio"


@dataclass
class TFP_MenuItem:
    id: str = ""
    label: Dict[str, str] = field(default_factory=dict)
    shortcut: str = ""
    icon: str = ""
    
    item_type: str = "normal"
    submenu: bool = False
    checkable: bool = False
    checked: bool = False
    enabled: bool = True
    visible: bool = True
    
    action: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    tooltip: str = ""
    
    children: list = field(default_factory=list)
    parent_id: str = ""
    
    @property
    def label_text(self) -> str:
        return self.label.get("en", self.id)
    
    def get_label(self, lang: str = "zh") -> str:
        return self.label.get(lang, self.label.get("en", self.id))
    
    @property
    def is_separator(self) -> bool:
        return self.item_type == "separator"
    
    @property
    def has_submenu(self) -> bool:
        return self.submenu or len(self.children) > 0
    
    @property
    def is_action_item(self) -> bool:
        return not self.is_separator and self.id != ""
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "label": self.label,
            "item_type": self.item_type,
            "enabled": self.enabled,
            "visible": self.visible
        }
        
        if self.shortcut:
            result["shortcut"] = self.shortcut
        if self.icon:
            result["icon"] = self.icon
        if self.submenu:
            result["submenu"] = True
        if self.checkable:
            result["checkable"] = True
            result["checked"] = self.checked
        if self.action:
            result["action"] = self.action
        if self.tooltip:
            result["tooltip"] = self.tooltip
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        
        return result


@dataclass
class TFP_MenuGroup:
    id: str = ""
    label: Dict[str, str] = field(default_factory=dict)
    items: List[TFP_MenuItem] = field(default_factory=list)
    
    @property
    def label_text(self) -> str:
        return self.label.get("zh", self.label.get("en", self.id))
    
    def get_label(self, lang: str = "zh") -> str:
        return self.label.get(lang, self.label.get("en", self.id))
    
    def get_item_by_id(self, item_id: str) -> Optional[TFP_MenuItem]:
        for item in self.items:
            if item.id == item_id:
                return item
            
            if item.has_submenu:
                for child in item.children:
                    if child.id == item_id:
                        return child
        
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "items": [item.to_dict() for item in self.items]
        }


@dataclass 
class TFP_MenuConfig:
    version: str = "1.0.0"
    main_menu: Dict[str, TFP_MenuGroup] = field(default_factory=dict)
    tool_menu_template: Dict[str, TFP_MenuGroup] = field(default_factory=dict)
    
    config_path: str = ""
    loaded_at: str = ""
    
    @property
    def is_loaded(self) -> bool:
        return len(self.main_menu) > 0 or self.config_path != ""
    
    def get_main_menu_group(self, group_id: str) -> Optional[TFP_MenuGroup]:
        return self.main_menu.get(group_id)
    
    def get_tool_menu_group(self, group_id: str) -> Optional[TFP_MenuGroup]:
        return self.tool_menu_template.get(group_id)
    
    def get_main_menu_items(self) -> List[TFP_MenuGroup]:
        order = ["file", "tools", "window", "settings", "account", "help"]
        groups = []
        
        for group_id in order:
            if group_id in self.main_menu:
                groups.append(self.main_menu[group_id])
        
        for group_id, group in self.main_menu.items():
            if group_id not in order:
                groups.append(group)
        
        return groups
    
    def get_tool_menu_items(self) -> List[TFP_MenuGroup]:
        order = ["file", "edit", "view", "tools", "help"]
        groups = []
        
        for group_id in order:
            if group_id in self.tool_menu_template:
                groups.append(self.tool_menu_template[group_id])
        
        for group_id, group in self.tool_menu_template.items():
            if group_id not in order:
                groups.append(group)
        
        return groups
    
    def find_item(self, menu_id: str) -> Optional[Tuple[TFP_MenuGroup, TFP_MenuItem]]:
        for group in self.main_menu.values():
            item = group.get_item_by_id(menu_id)
            if item:
                return (group, item)
        
        for group in self.tool_menu_template.values():
            item = group.get_item_by_id(menu_id)
            if item:
                return (group, item)
        
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "main_menu": {k: v.to_dict() for k, v in self.main_menu.items()},
            "tool_menu_template": {k: v.to_dict() for k, v in self.tool_menu_template.items()}
        }


class TFP_MenuConfigError(Exception):
    pass


class TFP_MenuConfigLoader:
    
    DEFAULT_CONFIG_FILENAME = "menu_config.json"
    SUPPORTED_VERSIONS = ["1.0.0"]
    
    def __init__(self, config_dir: str = ""):
        if config_dir:
            self._config_dir = config_dir
        else:
            app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self._config_dir = os.path.join(app_dir, "config")
        
        self._config_path = os.path.join(self._config_dir, self.DEFAULT_CONFIG_FILENAME)
        self._current_config: Optional[TFP_MenuConfig] = None
        self._last_modified: float = 0
        self._load_callbacks: list = []
    
    @property
    def config_path(self) -> str:
        return self._config_path
    
    @property
    def current_config(self) -> Optional[TFP_MenuConfig]:
        return self._current_config
    
    def add_load_callback(self, callback):
        self._load_callbacks.append(callback)
    
    def remove_load_callback(self, callback):
        if callback in self._load_callbacks:
            self._load_callbacks.remove(callback)
    
    def load(self, force_reload: bool = False) -> TFP_MenuConfig:
        if not force_reload and self._current_config and self._is_cache_valid():
            return self._current_config
        
        if not os.path.exists(self._config_path):
            raise TFP_MenuConfigError(f"Config file not found: {self._config_path}")
        
        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            
            config = self._parse_config(raw_data)
            config.config_path = self._config_path
            
            stat = os.stat(self._config_path)
            self._last_modified = stat.st_mtime
            
            self._current_config = config
            
            for callback in self._load_callbacks:
                try:
                    callback(config)
                except Exception as e:
                    print(f"menu config load callback execution failed: {e}")
            
            return config
            
        except json.JSONDecodeError as e:
            raise TFP_MenuConfigError(f"JSON parsing error: {e}")
        except TFP_MenuConfigError:
            raise
        except Exception as e:
            raise TFP_MenuConfigError(f"Failed to load config: {e}")
    
    def load_for_tool(self, tool_ident: str = "") -> Dict[str, Any]:
        config = self.load()
        
        result = {
            "version": config.version,
            "menus": {}
        }
        
        for group_id, group in config.tool_menu_template.items():
            result["menus"][group_id] = group.to_dict()
        
        return result
    
    def reload_if_changed(self) -> bool:
        if not os.path.exists(self._config_path):
            return False
        
        try:
            stat = os.stat(self._config_path)
            if stat.st_mtime > self._last_modified:
                self.load(force_reload=True)
                return True
        except Exception:
            pass
        
        return False
    
    def validate_config(self) -> Tuple[bool, List[str]]:
        errors = []
        
        if not os.path.exists(self._config_path):
            errors.append(f"配置文件不存在: {self._config_path}")
            return (False, errors)
        
        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if "version" not in data:
                errors.append("缺少 version 字段")
            
            if "main_menu" not in data:
                errors.append("缺少 main_menu 字段")
            else:
                if not isinstance(data["main_menu"], dict):
                    errors.append("main_menu 必须是对象")
                else:
                    for group_id, group_data in data["main_menu"].items():
                        group_errors = self._validate_menu_group(group_id, group_data)
                        errors.extend(group_errors)
            
            if "tool_menu_template" not in data:
                errors.append("缺少 tool_menu_template 字段")
            else:
                if not isinstance(data["tool_menu_template"], dict):
                    errors.append("tool_menu_template 必须是对象")
            
            return (len(errors) == 0, errors)
            
        except json.JSONDecodeError as e:
            errors.append(f"JSON格式错误: {e}")
            return (False, errors)
        except Exception as e:
            errors.append(str(e))
            return (False, errors)
    
    def _is_cache_valid(self) -> bool:
        if not self._current_config:
            return False
        
        if not os.path.exists(self._config_path):
            return False
        
        try:
            stat = os.stat(self._config_path)
            return stat.st_mtime <= self._last_modified
        except Exception:
            return False
    
    def _parse_config(self, raw_data: Dict[str, Any]) -> TFP_MenuConfig:
        config = TFP_MenuConfig(
            version=raw_data.get("version", "1.0.0"),
            loaded_at=self._get_current_timestamp()
        )
        
        if "main_menu" in raw_data:
            for group_id, group_data in raw_data["main_menu"].items():
                group = self._parse_menu_group(group_id, group_data)
                config.main_menu[group_id] = group
        
        if "tool_menu_template" in raw_data:
            for group_id, group_data in raw_data["tool_menu_template"].items():
                group = self._parse_menu_group(group_id, group_data)
                config.tool_menu_template[group_id] = group
        
        return config
    
    def _parse_menu_group(self, group_id: str, group_data: Dict[str, Any]) -> TFP_MenuGroup:
        group = TFP_MenuGroup(
            id=group_id,
            label=group_data.get("label", {})
        )
        
        items_data = group_data.get("items", [])
        for item_data in items_data:
            item = self._parse_menu_item(item_data, parent_id=group_id)
            group.items.append(item)
        
        return group
    
    def _parse_menu_item(self, item_data: Dict[str, Any], parent_id: str = "") -> TFP_MenuItem:
        item_type = item_data.get("type", "normal")
        
        if item_type == "separator":
            return TFP_MenuItem(
                item_type="separator",
                parent_id=parent_id
            )
        
        item = TFP_MenuItem(
            id=item_data.get("id", ""),
            label=item_data.get("label", {}),
            shortcut=item_data.get("shortcut", ""),
            icon=item_data.get("icon", ""),
            item_type=item_type,
            submenu=item_data.get("submenu", False),
            checkable=item_data.get("checkable", False),
            checked=item_data.get("checked", False),
            enabled=item_data.get("enabled", True),
            visible=item_data.get("visible", True),
            action=item_data.get("action"),
            data=item_data.get("data"),
            tooltip=item_data.get("tooltip", ""),
            parent_id=parent_id
        )
        
        if "children" in item_data:
            for child_data in item_data["children"]:
                child = self._parse_menu_item(child_data, parent_id=item.id)
                item.children.append(child)
        
        return item
    
    def _validate_menu_group(self, group_id: str, group_data: Any) -> List[str]:
        errors = []
        
        if not isinstance(group_data, dict):
            errors.append(f"菜单组 '{group_id}' 必须是对象")
            return errors
        
        if "id" not in group_data:
            errors.append(f"菜单组 '{group_id}' 缺少 id 字段")
        elif group_data.get("id") != group_id:
            errors.append(f"菜单组 ID 不匹配: 期望 '{group_id}', 得到 '{group_data.get('id')}'")
        
        if "label" not in group_data:
            errors.append(f"菜单组 '{group_id}' 缺少 label 字段")
        
        if "items" in group_data:
            items = group_data["items"]
            if not isinstance(items, list):
                errors.append(f"菜单组 '{group_id}' 的 items 必须是数组")
            else:
                for i, item in enumerate(items):
                    item_errors = self._validate_menu_item(item, f"{group_id}[{i}]")
                    errors.extend(item_errors)
        
        return errors
    
    def _validate_menu_item(self, item_data: Any, path: str) -> List[str]:
        errors = []
        
        if not isinstance(item_data, dict):
            errors.append(f"{path} 必须是对象")
            return errors
        
        item_type = item_data.get("type", "normal")
        
        if item_type == "separator":
            return errors
        
        if "id" not in item_data:
            errors.append(f"{path} 缺少 id 字段")
        
        if "label" not in item_data:
            errors.append(f"{path} 缺少 label 字段")
        
        if "children" in item_data:
            children = item_data["children"]
            if not isinstance(children, list):
                errors.append(f"{path}.children 必须是数组")
            else:
                for i, child in enumerate(children):
                    child_errors = self._validate_menu_item(child, f"{path}.children[{i}]")
                    errors.extend(child_errors)
        
        return errors
    
    def _get_current_timestamp(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


def create_menu_loader(config_dir: str = "") -> TFP_MenuConfigLoader:
    return TFP_MenuConfigLoader(config_dir=config_dir)


def load_menu_config(config_path: str = "") -> TFP_MenuConfig:
    if config_path:
        loader = TFP_MenuConfigLoader(config_dir=os.path.dirname(config_path))
        loader._config_path = config_path
    else:
        loader = create_menu_loader()
    
    return loader.load()
