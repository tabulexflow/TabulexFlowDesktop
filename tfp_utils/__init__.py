# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

# 主程序侧 SDK 派生版本标识：与 tfp_toolkit/__init__.py 的 __version__ 保持一致
# （tfp_toolkit 为 SDK 权威源，本包是其主程序内部派生；由
# tests/test_tfp_dual_source_consistency.py 守护两侧一致性）。
__version__ = "1.0.0"

from .tfp_base_tool import (
    TFP_ToolType,
    TFP_ToolRunMode,
    TFP_AuthContext,
    TFP_SettingsContext,
    TFP_IPCConfig,
    TFP_ToolContext,
    TFP_ToolMetadata,
    TFP_BaseTool,
    create_tool_instance,
)

from .tfp_backend_config import (
    TFP_BackendConfigManager,
    get_backend_manager,
)

from .tfp_i18n_manager import (
    TFP_I18nManager,
    i18n,
    translate,
    translate_list,
)

from .tfp_main_utils import (
    setup_debug,
    get_base_path,
    get_config_path,
    get_resource_path,
    output_system_info,
    check_resource_structure,
    reload_tool_modules,
    get_runtime_base_dir,
    get_user_runtime_base_dir,
    is_writable_dir,
)

from .tfp_secure_storage import (
    TFP_SecureStorage,
    TFP_AuthTokenStorage,
)

from .tfp_menu_loader import (
    TFP_MenuItemType,
    TFP_MenuItem,
    TFP_MenuGroup,
    TFP_MenuConfig,
    TFP_MenuConfigError,
    TFP_MenuConfigLoader,
    create_menu_loader,
    load_menu_config,
)

from .tfp_menu_handler import (
    TFP_MenuActionStatus,
    TFP_MenuActionResult,
    TFP_MenuActionHandler,
    TFP_MenuHandlerError,
    TFP_MenuActionDispatcher,
    get_menu_dispatcher,
    register_default_actions,
)

from .tfp_main_menu import (
    TFP_MenuBarPosition,
    TFP_GeneratedMenuItem,
    TFP_GeneratedMenuGroup,
    TFP_MainMenuGenerator,
    create_main_menu_generator,
    build_tool_menu_for_child,
)

ToolType = TFP_ToolType
ToolRunMode = TFP_ToolRunMode
AuthContext = TFP_AuthContext
SettingsContext = TFP_SettingsContext
IPCConfig = TFP_IPCConfig
ToolContext = TFP_ToolContext
ToolMetadata = TFP_ToolMetadata
BaseTool = TFP_BaseTool
BackendConfigManager = TFP_BackendConfigManager
I18nManager = TFP_I18nManager
SecureStorage = TFP_SecureStorage
AuthTokenStorage = TFP_AuthTokenStorage
MenuItemType = TFP_MenuItemType
MenuItem = TFP_MenuItem
MenuGroup = TFP_MenuGroup
MenuConfig = TFP_MenuConfig
MenuConfigError = TFP_MenuConfigError
MenuConfigLoader = TFP_MenuConfigLoader
MenuActionStatus = TFP_MenuActionStatus
MenuActionResult = TFP_MenuActionResult
MenuActionHandler = TFP_MenuActionHandler
MenuHandlerError = TFP_MenuHandlerError
MenuActionDispatcher = TFP_MenuActionDispatcher
MenuBarPosition = TFP_MenuBarPosition
GeneratedMenuItem = TFP_GeneratedMenuItem
GeneratedMenuGroup = TFP_GeneratedMenuGroup
MainMenuGenerator = TFP_MainMenuGenerator

__all__ = [
    'TFP_ToolType', 'TFP_ToolRunMode', 'TFP_AuthContext', 'TFP_SettingsContext',
    'TFP_IPCConfig', 'TFP_ToolContext', 'TFP_ToolMetadata', 'TFP_BaseTool',
    'create_tool_instance',
    'TFP_BackendConfigManager', 'get_backend_manager',
    'TFP_I18nManager', 'i18n', 'translate', 'translate_list',
    'setup_debug', 'get_base_path', 'get_config_path', 'get_resource_path',
    'output_system_info', 'check_resource_structure', 'reload_tool_modules',
    'get_runtime_base_dir', 'get_user_runtime_base_dir', 'is_writable_dir',
    'TFP_SecureStorage', 'TFP_AuthTokenStorage',
    'TFP_MenuItemType', 'TFP_MenuItem', 'TFP_MenuGroup', 'TFP_MenuConfig',
    'TFP_MenuConfigError', 'TFP_MenuConfigLoader', 'create_menu_loader', 'load_menu_config',
    'TFP_MenuActionStatus', 'TFP_MenuActionResult', 'TFP_MenuActionHandler',
    'TFP_MenuHandlerError', 'TFP_MenuActionDispatcher', 'get_menu_dispatcher',
    'register_default_actions',
    'TFP_MenuBarPosition', 'TFP_GeneratedMenuItem', 'TFP_GeneratedMenuGroup',
    'TFP_MainMenuGenerator', 'create_main_menu_generator', 'build_tool_menu_for_child',
]
