# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Callable, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .tfp_main_utils import get_runtime_base_dir

logger = logging.getLogger(__name__)


class TFP_MenuActionStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    NOT_FOUND = "not_found"
    DISABLED = "disabled"
    REQUIRES_CONFIRM = "requires_confirm"
    ASYNC = "async"


@dataclass
class TFP_MenuActionResult:
    status: TFP_MenuActionStatus = TFP_MenuActionStatus.SUCCESS
    menu_id: str = ""
    
    message: str = ""
    data: Optional[Dict[str, Any]] = None
    
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    execution_time_ms: float = 0
    
    @property
    def is_success(self) -> bool:
        return self.status == TFP_MenuActionStatus.SUCCESS
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "menu_id": self.menu_id,
            "message": self.message,
            "data": self.data,
            "executed_at": self.executed_at,
            "execution_time_ms": round(self.execution_time_ms, 2)
        }


@dataclass
class TFP_MenuActionHandler:
    menu_id: str
    handler: Callable
    label: str = ""
    description: str = ""
    requires_auth: bool = False
    requires_confirmation: bool = False
    confirmation_message: str = ""
    enabled_check: Optional[Callable[[], bool]] = None
    visible_check: Optional[Callable[[], bool]] = None
    
    def is_enabled(self) -> bool:
        if self.enabled_check:
            try:
                return self.enabled_check()
            except Exception as e:
                logger.warning(f"Enabled-status check failed ({self.menu_id}): {e}")
                return True
        return True
    
    def is_visible(self) -> bool:
        if self.visible_check:
            try:
                return self.visible_check()
            except Exception as e:
                logger.warning(f"Visibility check failed ({self.menu_id}): {e}")
                return True
        return True


class TFP_MenuHandlerError(Exception):
    pass


class TFP_MenuActionDispatcher:
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        
        self._handlers: Dict[str, TFP_MenuActionHandler] = {}
        self._pre_hooks: List[Callable] = []
        self._post_hooks: List[Callable] = []
        self._error_handlers: List[Callable] = []
        
        self._action_history: List[TFP_MenuActionResult] = []
        self._max_history_size = 100
        
        self._initialized = True
    
    def register_handler(self, handler: TFP_MenuActionHandler) -> bool:
        if not handler.menu_id:
            logger.error("Cannot register a handler without an ID")
            return False
        
        existing = self._handlers.get(handler.menu_id)
        if existing:
            logger.debug(f"Overriding existing handler: {handler.menu_id}")
        
        self._handlers[handler.menu_id] = handler
        logger.debug(f"Registering menu handler: {handler.menu_id} -> {handler.label or handler.handler.__name__}")
        
        return True
    
    def register_action(self,
                       menu_id: str,
                       handler: Callable,
                       **kwargs) -> bool:
        action_handler = TFP_MenuActionHandler(
            menu_id=menu_id,
            handler=handler,
            **kwargs
        )
        return self.register_handler(action_handler)
    
    def unregister_handler(self, menu_id: str) -> bool:
        if menu_id in self._handlers:
            del self._handlers[menu_id]
            logger.debug(f"Removing menu handler: {menu_id}")
            return True
        return False
    
    def has_handler(self, menu_id: str) -> bool:
        return menu_id in self._handlers
    
    def get_handler(self, menu_id: str) -> Optional[TFP_MenuActionHandler]:
        return self._handlers.get(menu_id)
    
    def add_pre_hook(self, hook: Callable):
        self._pre_hooks.append(hook)
    
    def add_post_hook(self, hook: Callable):
        self._post_hooks.append(hook)
    
    def add_error_handler(self, handler: Callable):
        self._error_handlers.append(handler)
    
    async def execute_async(self, 
                            menu_id: str,
                            source_tool: str = "",
                            data: Optional[Dict[str, Any]] = None) -> TFP_MenuActionResult:
        import time
        start_time = time.time()
        
        result = TFP_MenuActionResult(menu_id=menu_id)
        
        try:
            for hook in self._pre_hooks:
                try:
                    hook_result = hook(menu_id, source_tool, data)
                    if hook_result is False:
                        result.status = TFP_MenuActionStatus.FAILED
                        result.message = "被前置钩子拒绝"
                        return result
                except Exception as e:
                    logger.warning(f"Pre-hook execution failed: {e}")
            
            action_handler = self._handlers.get(menu_id)
            
            if not action_handler:
                result.status = TFP_MenuActionStatus.NOT_FOUND
                result.message = f"未找到菜单操作处理器: {menu_id}"
                
                for error_handler in self._error_handlers:
                    try:
                        error_handler(result, "not_found")
                    except Exception:
                        pass
                
                return result
            
            if not action_handler.is_enabled():
                result.status = TFP_MenuActionStatus.DISABLED
                result.message = f"菜单操作已禁用: {menu_id}"
                return result
            
            if action_handler.requires_confirmation and not (data or {}).get("confirmed"):
                result.status = TFP_MenuActionStatus.REQUIRES_CONFIRM
                result.message = action_handler.confirmation_message or "确认执行此操作？"
                result.data = {"needs_confirmation": True}
                return result
            
            import asyncio
            if isinstance(action_handler.handler, type(lambda: None)):
                import inspect
                if inspect.iscoroutinefunction(action_handler.handler):
                    handler_result = await action_handler.handler(source_tool=source_tool, data=data)
                else:
                    loop = asyncio.get_event_loop()
                    handler_result = await loop.run_in_executor(
                        None, 
                        lambda: action_handler.handler(source_tool=source_tool, data=data)
                    )
            else:
                handler_result = action_handler.handler(source_tool=source_tool, data=data)
            
            if isinstance(handler_result, dict):
                result.data = handler_result
                result.message = handler_result.get("message", "")
            elif handler_result is not None:
                result.data = {"result": handler_result}
            
            result.status = TFP_MenuActionStatus.SUCCESS
            result.message = f"操作执行成功: {menu_id}"
            
            for hook in self._post_hooks:
                try:
                    hook(result, source_tool, data)
                except Exception as e:
                    logger.warning(f"Post-hook execution failed: {e}")
            
        except Exception as e:
            logger.error(f"Menu action execution failed ({menu_id}): {e}", exc_info=True)
            
            result.status = TFP_MenuActionStatus.FAILED
            result.message = f"操作执行失败: {str(e)}"
            
            for error_handler in self._error_handlers:
                try:
                    error_handler(result, "exception")
                except Exception:
                    pass
        
        finally:
            end_time = time.time()
            result.execution_time_ms = (end_time - start_time) * 1000
            
            self._record_action(result)
        
        return result
    
    def execute(self,
               menu_id: str,
               source_tool: str = "",
               data: Optional[Dict[str, Any]] = None) -> TFP_MenuActionResult:
        import asyncio
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run, 
                        self.execute_async(menu_id, source_tool, data)
                    )
                    return future.result(timeout=30)
            else:
                return loop.run_until_complete(
                    self.execute_async(menu_id, source_tool, data)
                )
        except RuntimeError:
            return asyncio.run(self.execute_async(menu_id, source_tool, data))
    
    def get_registered_actions(self) -> List[Dict[str, Any]]:
        actions = []
        for menu_id, handler in self._handlers.items():
            actions.append({
                "menu_id": menu_id,
                "label": handler.label,
                "description": handler.description,
                "enabled": handler.is_enabled(),
                "visible": handler.is_visible(),
                "requires_auth": handler.requires_auth,
                "requires_confirmation": handler.requires_confirmation
            })
        return sorted(actions, key=lambda x: x["menu_id"])
    
    def get_action_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        history = self._action_history[-limit:]
        return [r.to_dict() for r in history]
    
    def clear_history(self):
        self._action_history.clear()
    
    def clear_all_handlers(self):
        self._handlers.clear()
        logger.info("All menu handlers cleared")
    
    def _record_action(self, result: TFP_MenuActionResult):
        self._action_history.append(result)
        
        if len(self._action_history) > self._max_history_size:
            self._action_history = self._action_history[-self._max_history_size // 2:]


def get_menu_dispatcher() -> TFP_MenuActionDispatcher:
    return TFP_MenuActionDispatcher()


def register_default_actions(dispatcher: TFP_MenuActionDispatcher = None):
    if dispatcher is None:
        dispatcher = get_menu_dispatcher()
    
    def handle_refresh_tools(source_tool=None, data=None):
        logger.info(f"Refreshing tool list (source: {source_tool})")
        return {"refreshed": True, "timestamp": datetime.now(timezone.utc).isoformat()}
    
    def handle_clear_cache(source_tool=None, data=None):
        logger.info(f"Clearing cache (source: {source_tool})")
        # 缓存与主程序其它运行时数据同源：<运行时根目录>/cache（见 get_runtime_base_dir）
        cache_dir = get_runtime_base_dir() / "cache"
        cleared_files = 0
        if cache_dir.is_dir():
            for item in cache_dir.iterdir():
                try:
                    if item.is_file():
                        item.unlink()
                        cleared_files += 1
                except Exception as e:
                    logger.warning(f"Failed to delete cache file {item.name}: {e}")
        return {"cleared": True, "files_removed": cleared_files}
    
    def handle_exit_app(source_tool=None, data=None):
        logger.info(f"Exiting application (source: {source_tool})")
        import sys
        sys.exit(0)
    
    def handle_go_home(source_tool=None, data=None):
        logger.info(f"Returning to home (source: {source_tool})")
        return {"navigated": "home"}
    
    def handle_about(source_tool=None, data=None):
        return {
            "show_dialog": "about",
            "version": "Unknown",
            "name": "TabulexFlow"
        }
    
    def handle_check_update(source_tool=None, data=None):
        # T1.3：原返回值含 url "/api/update/check"，但后端并无该端点
        # （死链接），且本 action registry 无运行时消费方。真实的更新检查入口：
        # 1) 主程序菜单 main.py on_check_update（刷新工具列表）；
        # 2) 启动时前端自更新检查 main.py _start_frontend_update_check（T1.2）。
        logger.info("Checking for updates (menu action placeholder; real flow lives in main.on_check_update)")
        return {"checking": True}
    
    actions_config = [
        ("file.refresh_tools", handle_refresh_tools, "刷新工具", "刷新可用工具列表"),
        ("file.clear_cache", handle_clear_cache, "清除缓存", "清除本地缓存文件"),
        ("file.exit", handle_exit_app, "退出", "退出应用程序", True),
        ("window.home", handle_go_home, "主页", "导航到主页"),
        ("help.about", handle_about, "关于", "显示关于对话框"),
        ("help.check_update", handle_check_update, "检查更新", "检查新版本"),
    ]
    
    for config in actions_config:
        menu_id = config[0]
        handler_func = config[1]
        kwargs = {
            "label": config[2],
            "description": config[3]
        }
        if len(config) > 4:
            kwargs["requires_confirmation"] = config[4]
        
        dispatcher.register_action(menu_id, handler_func, **kwargs)
    
    logger.info(f"Registered {len(actions_config)} default menu actions")
