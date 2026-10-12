# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import os
import logging
from typing import Optional, Dict, Any, List, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TFP_MenuBarPosition(Enum):
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"
    FLOATING = "floating"


@dataclass
class TFP_GeneratedMenuItem:
    id: str = ""
    display_text: str = ""
    shortcut: str = ""
    icon: str = ""
    
    item_type: str = "normal"
    enabled: bool = True
    visible: bool = True
    checked: bool = False
    
    tooltip: str = ""
    
    has_submenu: bool = False
    children: list = field(default_factory=list)
    
    action_callback: Optional[Callable] = None
    tag: Any = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "display_text": self.display_text,
            "shortcut": self.shortcut,
            "icon": self.icon,
            "item_type": self.item_type,
            "enabled": self.enabled,
            "visible": self.visible,
            "checked": self.checked,
            "tooltip": self.tooltip,
            "has_submenu": self.has_submenu,
            "children": [c.to_dict() for c in self.children]
        }


@dataclass
class TFP_GeneratedMenuGroup:
    id: str = ""
    display_text: str = ""
    items: List[TFP_GeneratedMenuItem] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "display_text": self.display_text,
            "items": [item.to_dict() for item in self.items]
        }
    
    @property
    def visible_items(self) -> List[TFP_GeneratedMenuItem]:
        return [item for item in self.items if item.visible]


class TFP_MainMenuGenerator:
    
    DEFAULT_MENU_ORDER = ["file", "tools", "window", "settings", "account", "help"]
    
    def __init__(self):
        self._config = None
        self._loader = None
        
        self._generated_groups: Dict[str, TFP_GeneratedMenuGroup] = {}
        
        self._current_language = "zh"
        self._user_type = "free"
        self._is_logged_in = False
        
        self._state_overrides: Dict[str, Dict[str, Any]] = {}
        self._custom_menu_insertions: Dict[str, List[TFP_GeneratedMenuItem]] = {}
        
        self._on_menu_click_callback: Optional[Callable] = None
        self._on_menu_update_callback: Optional[Callable] = None
    
    @property
    def current_language(self) -> str:
        return self._current_language
    
    @current_language.setter
    def current_language(self, value: str):
        if value != self._current_language:
            self._current_language = value
            if self._config:
                self._regenerate_all()
    
    @property
    def user_type(self) -> str:
        return self._user_type
    
    @user_type.setter
    def user_type(self, value: str):
        if value != self._user_type:
            self._user_type = value
            if self._config:
                self._apply_user_type_filters()
    
    @property
    def is_logged_in(self) -> bool:
        return self._is_logged_in
    
    @is_logged_in.setter
    def is_logged_in(self, value: bool):
        if value != self._is_logged_in:
            self._is_logged_in = value
            if self._config:
                self._apply_auth_filters()
    
    def set_on_menu_click(self, callback: Callable):
        self._on_menu_click_callback = callback
    
    def set_on_menu_update(self, callback: Callable):
        self._on_menu_update_callback = callback
    
    def initialize(self, config_loader=None) -> bool:
        try:
            from .tfp_menu_loader import create_menu_loader
            
            self._loader = config_loader or create_menu_loader()
            self._config = self._loader.load()
            
            self._regenerate_all()
            
            logger.info(f"Menu generator initialized successfully, version: {self._config.version}")
            
            return True
            
        except Exception as e:
            logger.error(f"Menu generator initialization failed: {e}")
            return False
    
    def reload_config(self) -> bool:
        if not self._loader:
            return False
        
        try:
            self._config = self._loader.load(force_reload=True)
            self._regenerate_all()
            
            logger.info("Menu configuration reloaded")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to reload menu configuration: {e}")
            return False
    
    def get_menu_bar(self) -> List[TFP_GeneratedMenuGroup]:
        groups = []
        
        for group_id in self.DEFAULT_MENU_ORDER:
            if group_id in self._generated_groups:
                groups.append(self._generated_groups[group_id])
        
        for group_id, group in self._generated_groups.items():
            if group_id not in self.DEFAULT_MENU_ORDER and len(group.visible_items) > 0:
                groups.append(group)
        
        return groups
    
    def get_menu_group(self, group_id: str) -> Optional[TFP_GeneratedMenuGroup]:
        return self._generated_groups.get(group_id)
    
    def find_item(self, menu_id: str) -> Optional[Tuple[TFP_GeneratedMenuGroup, TFP_GeneratedMenuItem]]:
        for group in self._generated_groups.values():
            item = self._find_item_recursive(group.items, menu_id)
            if item:
                return (group, item)
        
        return None
    
    def set_item_enabled(self, menu_id: str, enabled: bool) -> bool:
        result = self.find_item(menu_id)
        if result:
            _, item = result
            item.enabled = enabled
            self._notify_update(menu_id)
            return True
        return False
    
    def set_item_visible(self, menu_id: str, visible: bool) -> bool:
        result = self.find_item(menu_id)
        if result:
            _, item = result
            item.visible = visible
            self._notify_update(menu_id)
            return True
        return False
    
    def set_item_checked(self, menu_id: str, checked: bool) -> bool:
        result = self.find_item(menu_id)
        if result:
            _, item = result
            if item.item_type == "checkable":
                item.checked = checked
                self._notify_update(menu_id)
                return True
        return False
    
    def set_item_label(self, menu_id: str, label: str) -> bool:
        result = self.find_item(menu_id)
        if result:
            _, item = result
            item.display_text = label
            self._notify_update(menu_id)
            return True
        return False
    
    def insert_custom_item(self,
                          group_id: str,
                          after_id: Optional[str],
                          item: TFP_GeneratedMenuItem) -> bool:
        group = self._generated_groups.get(group_id)
        if not group:
            return False
        
        if after_id:
            insert_index = 0
            for i, existing in enumerate(group.items):
                if existing.id == after_id:
                    insert_index = i + 1
                    break
            group.items.insert(insert_index, item)
        else:
            group.items.insert(0, item)
        
        self._notify_update(item.id)
        
        return True
    
    def remove_custom_item(self, menu_id: str) -> bool:
        for group in self._generated_groups.values():
            for i, item in enumerate(group.items):
                if item.id == menu_id:
                    group.items.pop(i)
                    self._notify_update(menu_id)
                    return True
        return False
    
    def handle_menu_click(self, menu_id: str) -> Optional[Dict[str, Any]]:
        result = self.find_item(menu_id)
        
        if not result:
            logger.warning(f"Menu item not found: {menu_id}")
            return {"success": False, "error": f"未找到菜单项: {menu_id}"}
        
        group, item = result
        
        if not item.enabled:
            logger.debug(f"Menu item is disabled: {menu_id}")
            return {"success": False, "error": "菜单项已禁用"}
        
        if item.action_callback:
            try:
                callback_result = item.action_callback(menu_id, item.tag)
                
                if isinstance(callback_result, dict):
                    return callback_result
                
                return {"success": True}
                
            except Exception as e:
                logger.error(f"Menu action execution failed ({menu_id}): {e}")
                return {"success": False, "error": str(e)}
        
        if self._on_menu_click_callback:
            try:
                return self._on_menu_click_callback(menu_id, group.id)
            except Exception as e:
                logger.error(f"Menu click callback failed: {e}")
        
        return {"success": True, "action": "default"}
    
    def get_menu_state_snapshot(self) -> Dict[str, Any]:
        state = {
            "language": self._current_language,
            "user_type": self._user_type,
            "is_logged_in": self._is_logged_in,
            "groups": {},
            "total_visible_items": 0
        }
        
        for group_id, group in self._generated_groups.items():
            visible_count = len(group.visible_items)
            state["groups"][group_id] = {
                "display_text": group.display_text,
                "total_items": len(group.items),
                "visible_items": visible_count
            }
            state["total_visible_items"] += visible_count
        
        return state
    
    def to_serializable_dict(self) -> Dict[str, Any]:
        return {
            "version": self._config.version if self._config else "",
            "language": self._current_language,
            "menu_bar": [g.to_dict() for g in self.get_menu_bar()]
        }
    
    def _regenerate_all(self):
        if not self._config:
            return
        
        self._generated_groups.clear()
        
        main_menus = self._config.get_main_menu_items()
        
        for group in main_menus:
            generated_group = self._generate_group(group)
            self._generated_groups[group.id] = generated_group
        
        self._apply_user_type_filters()
        self._apply_auth_filters()
    
    def _generate_group(self, source_group) -> TFP_GeneratedMenuGroup:
        items = []
        
        for source_item in source_group.items:
            generated_item = self._generate_item(source_item)
            items.append(generated_item)
        
        group = TFP_GeneratedMenuGroup(
            id=source_group.id,
            display_text=source_group.get_label(self._current_language),
            items=items
        )
        
        return group
    
    def _generate_item(self, source_item) -> TFP_GeneratedMenuItem:
        if source_item.is_separator:
            return TFP_GeneratedMenuItem(
                id="",
                item_type="separator",
                visible=True
            )
        
        label = source_item.get_label(self._current_language)
        
        item = TFP_GeneratedMenuItem(
            id=source_item.id,
            display_text=label,
            shortcut=source_item.shortcut,
            icon=source_item.icon,
            item_type="checkable" if source_item.checkable else "normal",
            enabled=source_item.enabled,
            visible=source_item.visible,
            checked=source_item.checked,
            tooltip=source_item.tooltip or label,
            has_submenu=source_item.has_submenu,
            children=self._generate_children(source_item.children),
            tag={
                "original_label": source_item.label,
                "requires_auth": getattr(source_item, 'requires_auth', False)
            }
        )
        
        override = self._state_overrides.get(source_item.id)
        if override:
            if "enabled" in override:
                item.enabled = override["enabled"]
            if "visible" in override:
                item.visible = override["visible"]
            if "checked" in override:
                item.checked = override["checked"]
            if "label" in override:
                item.display_text = override["label"]
        
        return item
    
    def _generate_children(self, children: list) -> List[TFP_GeneratedMenuItem]:
        return [self._generate_item(child) for child in children]
    
    def _apply_user_type_filters(self):
        restricted_items = {
            "free": [],
            "premium": [],
            "enterprise": []
        }
        
        for menu_id in restricted_items.get(self._user_type, []):
            self.set_item_visible(menu_id, False)
    
    def _apply_auth_filters(self):
        login_required_items = [
            "account.profile",
            "account.devices",
            "account.feedback",
            "account.upgrade",
            "account.logout"
        ]
        
        for menu_id in login_required_items:
            self.set_item_visible(menu_id, self._is_logged_in)
        
        self.set_item_visible("account.login", not self._is_logged_in)
    
    def _find_item_recursive(self, 
                            items: List[TFP_GeneratedMenuItem], 
                            menu_id: str) -> Optional[TFP_GeneratedMenuItem]:
        for item in items:
            if item.id == menu_id:
                return item
            
            if item.has_submenu and item.children:
                found = self._find_item_recursive(item.children, menu_id)
                if found:
                    return found
        
        return None
    
    def _notify_update(self, menu_id: str):
        if self._on_menu_update_callback:
            try:
                self._on_menu_update_callback(menu_id)
            except Exception as e:
                logger.warning(f"Menu update notification callback failed: {e}")


def create_main_menu_generator() -> TFP_MainMenuGenerator:
    return TFP_MainMenuGenerator()


def get_main_menu_instance() -> TFP_MainMenuGenerator:
    raise NotImplementedError(
        "Use create_main_menu_generator() to create an instance and call initialize()"
    )


def build_tool_menu_for_child(tool_ident: str,
                             parent_generator: TFP_MainMenuGenerator = None) -> Dict[str, Any]:
    from .tfp_menu_loader import create_menu_loader
    
    loader = create_menu_loader()
    config = loader.load_for_tool(tool_ident)
    
    return {
        "version": config.get("version", "1.0.0"),
        "tool_ident": tool_ident,
        "menus": config.get("menus", {}),
        "parent_menu_actions": [
            "file.open",
            "file.save",
            "file.save_as",
            "edit.undo",
            "edit.redo",
            "edit.copy",
            "edit.paste",
            "view.zoom_in",
            "view.zoom_out",
            "view.fullscreen"
        ]
    }