# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
TabulexFlow 工具基类体系（主程序内部版本）

⚠️ 工具开发者请使用 SDK 版本：from tfp_toolkit.tfp_base_tool import ...
此文件仅供主程序内部使用（含 from build_mode import IPC_HOST_IP 等主程序特有依赖）。

三层基类：
  TFP_BaseTool (ABC)               - 所有工具的公共基类
  ├── TFP_BuiltinProgramTool (ABC)  - BuiltinProgram工具基类（嵌入主窗口运行）
  ├── TFP_RemoteProgramTool (ABC)   - RemoteProgram工具基类（独立进程运行）
  └── TFP_RemoteWebpageTool (ABC)   - RemoteWebpage工具基类（主程序创建WebView）

注意：此文件应与SDK的 tfp_toolkit/tfp_base_tool.py 保持接口一致。
主程序版本保留自己的特有依赖（如 from build_mode import IPC_HOST_IP），
但基类接口签名和行为逻辑必须与SDK版本一致。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from enum import Enum
from datetime import datetime
import json
import logging
import sys

from build_mode import IPC_HOST_IP

logger = logging.getLogger(__name__)


def _get_ipc_config_defaults():
    try:
        # 直接读取已加载的 __main__（编译产物或 python main.py 均为 main.py），
        # 避免顶层 `import main` 把主模块重复执行（在 PyInstaller 单文件里会造成二次初始化/资源重复）
        main_module = sys.modules.get('__main__')
        if main_module and hasattr(main_module, 'IPC_HOST') and hasattr(main_module, 'IPC_PORT_BASE'):
            return main_module.IPC_HOST, main_module.IPC_PORT_BASE
    except Exception:
        pass
    return IPC_HOST_IP, 0  # IPC 端口为动态分配，0 表示"由系统分配"

_DEFAULT_IPC_HOST, _DEFAULT_IPC_PORT = _get_ipc_config_defaults()


class TFP_ToolType(Enum):
    BUILTIN_PROGRAM = "BuiltinProgram"
    REMOTE_PROGRAM = "RemoteProgram"
    REMOTE_WEBPAGE = "RemoteWebpage"


class TFP_ToolRunMode(Enum):
    EMBEDDED = "embedded"
    STANDALONE = "standalone"


@dataclass
class TFP_AuthContext:
    user_id: Optional[int] = None
    user_type: str = "free"
    permissions: List[str] = field(default_factory=list)
    expires_at: Optional[str] = None
    machine_id: Optional[str] = None
    can_request_api: bool = False

    def is_logged_in(self) -> bool:
        return self.user_id is not None and self.can_request_api

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    def is_expired(self) -> bool:
        if not self.expires_at:
            return True
        try:
            expires = datetime.fromisoformat(self.expires_at.replace('Z', '+00:00'))
            return datetime.now(expires.tzinfo) > expires
        except (ValueError, AttributeError):
            return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "user_type": self.user_type,
            "permissions": self.permissions,
            "expires_at": self.expires_at,
            "machine_id": self.machine_id,
            "can_request_api": self.can_request_api
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TFP_AuthContext':
        return cls(
            user_id=data.get("user_id"),
            user_type=data.get("user_type", "free"),
            permissions=data.get("permissions", []),
            expires_at=data.get("expires_at"),
            machine_id=data.get("machine_id"),
            can_request_api=data.get("can_request_api", False)
        )


@dataclass
class TFP_SettingsContext:
    language: str = "zh"
    theme: str = "light"
    backend_url: str = ""
    debug_mode: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "language": self.language,
            "theme": self.theme,
            "backend_url": self.backend_url,
            "debug_mode": self.debug_mode
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TFP_SettingsContext':
        return cls(
            language=data.get("language", "zh"),
            theme=data.get("theme", "light"),
            backend_url=data.get("backend_url", ""),
            debug_mode=data.get("debug_mode", False)
        )


@dataclass
class TFP_IPCConfig:
    socket_port: int = 0
    socket_host: str = _DEFAULT_IPC_HOST
    data_file_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "socket_port": self.socket_port,
            "socket_host": self.socket_host,
            "data_file_path": self.data_file_path
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TFP_IPCConfig':
        return cls(
            socket_port=data.get("socket_port", 0),
            socket_host=data.get("socket_host", _DEFAULT_IPC_HOST),
            data_file_path=data.get("data_file_path")
        )


@dataclass
class TFP_ToolContext:
    version: str = "1.0.0"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    auth: TFP_AuthContext = field(default_factory=TFP_AuthContext)
    settings: TFP_SettingsContext = field(default_factory=TFP_SettingsContext)
    tool_params: Dict[str, Any] = field(default_factory=dict)
    ipc: TFP_IPCConfig = field(default_factory=TFP_IPCConfig)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "timestamp": self.timestamp,
            "auth": self.auth.to_dict(),
            "settings": self.settings.to_dict(),
            "tool_params": self.tool_params,
            "ipc": self.ipc.to_dict()
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TFP_ToolContext':
        return cls(
            version=data.get("version", "1.0.0"),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat() + "Z"),
            auth=TFP_AuthContext.from_dict(data.get("auth", {})),
            settings=TFP_SettingsContext.from_dict(data.get("settings", {})),
            tool_params=data.get("tool_params", {}),
            ipc=TFP_IPCConfig.from_dict(data.get("ipc", {}))
        )

    @classmethod
    def from_json(cls, json_str: str) -> 'TFP_ToolContext':
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def load_from_file(cls, file_path: str) -> 'TFP_ToolContext':
        with open(file_path, 'r', encoding='utf-8') as f:
            return cls.from_json(f.read())

    def save_to_file(self, file_path: str) -> None:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())


@dataclass
class TFP_ToolMetadata:
    tool_ident: str
    tool_title: Dict[str, str]
    tool_type: TFP_ToolType
    tool_version: str
    tool_description: Dict[str, str]
    tool_is_free: bool = True
    tool_need_ai: bool = False
    tool_folder_path: str = ""
    tool_need_version: str = "1.0.0"
    tool_dependencies: List[str] = field(default_factory=list)
    tool_window_width: int = 800
    tool_window_height: int = 600
    tool_api_url: str = ""
    tool_deploy_mode: str = "platform"
    tool_icon_path: Optional[str] = None
    tool_author: str = ""
    tool_license: str = ""
    tool_tags: List[str] = field(default_factory=list)
    tool_min_frontend_version: str = "1.0.0"

    def get_title(self, language: str = "zh") -> str:
        return self.tool_title.get(language, self.tool_title.get("en", self.tool_ident))

    def get_description(self, language: str = "zh") -> str:
        return self.tool_description.get(language, self.tool_description.get("en", ""))

    def is_builtin(self) -> bool:
        return self.tool_type == TFP_ToolType.BUILTIN_PROGRAM

    def is_local(self) -> bool:
        return False

    def is_remote(self) -> bool:
        return self.tool_type == TFP_ToolType.REMOTE_PROGRAM

    def is_webpage(self) -> bool:
        return self.tool_type == TFP_ToolType.REMOTE_WEBPAGE

    def requires_auth(self) -> bool:
        return self.tool_type in [TFP_ToolType.REMOTE_PROGRAM, TFP_ToolType.REMOTE_WEBPAGE]

    def supports_offline(self) -> bool:
        if self.is_builtin():
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "tool_ident": self.tool_ident,
            "tool_title": self.tool_title,
            "tool_type": self.tool_type.value,
            "tool_version": self.tool_version,
            "tool_description": self.tool_description,
            "tool_is_free": self.tool_is_free,
            "tool_need_ai": self.tool_need_ai,
            "tool_folder_path": self.tool_folder_path,
            "tool_need_version": self.tool_need_version,
            "tool_dependencies": self.tool_dependencies
        }

        if self.tool_type != TFP_ToolType.BUILTIN_PROGRAM:
            result["tool_api_url"] = self.tool_api_url
            result["tool_deploy_mode"] = self.tool_deploy_mode

        if self.tool_type in [TFP_ToolType.BUILTIN_PROGRAM, TFP_ToolType.REMOTE_PROGRAM]:
            result["tool_window_width"] = self.tool_window_width
            result["tool_window_height"] = self.tool_window_height

        if self.tool_icon_path:
            result["tool_icon_path"] = self.tool_icon_path
        if self.tool_author:
            result["tool_author"] = self.tool_author
        if self.tool_license:
            result["tool_license"] = self.tool_license
        if self.tool_tags:
            result["tool_tags"] = self.tool_tags
        if self.tool_min_frontend_version != "1.0.0":
            result["tool_min_frontend_version"] = self.tool_min_frontend_version

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TFP_ToolMetadata':
        tool_type_str = data.get("tool_type", "BuiltinProgram")
        try:
            tool_type = TFP_ToolType(tool_type_str)
        except ValueError:
            tool_type = TFP_ToolType.BUILTIN_PROGRAM

        return cls(
            tool_ident=data.get("tool_ident", ""),
            tool_title=data.get("tool_title", {}),
            tool_type=tool_type,
            tool_version=data.get("tool_version", "1.0.0"),
            tool_description=data.get("tool_description", {}),
            tool_is_free=data.get("tool_is_free", True),
            tool_need_ai=data.get("tool_need_ai", False),
            tool_folder_path=data.get("tool_folder_path", ""),
            tool_need_version=data.get("tool_need_version", "1.0.0"),
            tool_dependencies=data.get("tool_dependencies", []),
            tool_window_width=data.get("tool_window_width", 800),
            tool_window_height=data.get("tool_window_height", 600),
            tool_api_url=data.get("tool_api_url", ""),
            tool_deploy_mode=data.get("tool_deploy_mode", "platform"),
            tool_icon_path=data.get("tool_icon_path"),
            tool_author=data.get("tool_author", ""),
            tool_license=data.get("tool_license", ""),
            tool_tags=data.get("tool_tags", []),
            tool_min_frontend_version=data.get("tool_min_frontend_version", "1.0.0")
        )


class TFP_BaseTool(ABC):
    """所有工具的公共基类。

    提供工具标识、上下文管理、生命周期回调等公共功能。
    子类必须实现 tool_ident 和 tool_name 抽象属性。

    注意：create_embedded_interface() 和 show_interface() 已从此基类移到
    TFP_BuiltinProgramTool，因为只有BuiltinProgram工具需要嵌入主窗口。
    """

    def __init__(self, parent=None, context: Optional[TFP_ToolContext] = None):
        self.parent = parent
        self.context = context or TFP_ToolContext()
        self.frame = None
        self.panel = None
        self.is_embedded = False
        self.is_operating = False
        self._metadata: Optional[TFP_ToolMetadata] = None

    @property
    @abstractmethod
    def tool_ident(self) -> str:
        pass

    @property
    @abstractmethod
    def tool_name(self) -> str:
        pass

    @property
    def metadata(self) -> Optional[TFP_ToolMetadata]:
        return self._metadata

    @metadata.setter
    def metadata(self, value: TFP_ToolMetadata):
        self._metadata = value

    def get_window_size(self) -> tuple:
        if self._metadata:
            return (self._metadata.tool_window_width, self._metadata.tool_window_height)
        return (800, 600)

    def set_context(self, context: TFP_ToolContext):
        self.context = context

    def get_context(self) -> TFP_ToolContext:
        return self.context

    def on_before_show(self):
        pass

    def on_after_show(self):
        pass

    def on_before_close(self) -> bool:
        return True

    def on_after_close(self):
        pass

    def is_standalone(self) -> bool:
        return not self.is_embedded

    def get_language(self) -> str:
        return self.context.settings.language

    def is_user_logged_in(self) -> bool:
        return self.context.auth.is_logged_in()

    def has_permission(self, permission: str) -> bool:
        return self.context.auth.has_permission(permission)

    def get_backend_url(self) -> str:
        return self.context.settings.backend_url

    def get_user_id(self) -> Optional[int]:
        return self.context.auth.user_id

    def get_user_type(self) -> str:
        return self.context.auth.user_type

    def get_tool_param(self, key: str, default: Any = None) -> Any:
        return self.context.tool_params.get(key, default)

    def set_tool_param(self, key: str, value: Any):
        self.context.tool_params[key] = value

    def get_ipc_config(self) -> TFP_IPCConfig:
        return self.context.ipc


class TFP_BuiltinProgramTool(TFP_BaseTool):
    """BuiltinProgram工具基类——嵌入主窗口运行。

    BuiltinProgram工具通过 importlib 动态加载 tool_main.py，
    调用 create_embedded_interface() 嵌入主窗口面板。
    也支持独立窗口模式（调用 show_interface() 创建独立 wx.Frame），
    但当前所有BuiltinProgram工具均以嵌入模式运行。

    必须实现：
      - tool_ident (抽象属性)
      - tool_name (抽象属性)
      - create_embedded_interface() (抽象方法)
    """

    @abstractmethod
    def create_embedded_interface(self, parent_panel, parent_sizer):
        """嵌入主窗口面板（必须实现）。

        Args:
            parent_panel: 主窗口中的工具面板容器
            parent_sizer: 面板容器的Sizer

        Returns:
            嵌入的面板对象
        """
        pass

    def show_interface(self):
        """独立窗口模式（可选重写）。

        默认实现：显示已嵌入的面板。
        如需创建独立 wx.Frame，子类可重写此方法。
        """
        if self.panel:
            self.panel.Show()


class TFP_RemoteProgramTool(TFP_BaseTool):
    """RemoteProgram工具基类——独立进程运行。

    RemoteProgram以独立进程启动（源码模式 python tool_main.py --context
    或EXE模式 tool_main.exe --context），通过IPC Socket与主程序通信。
    主程序通过IPC命令控制show/hide/close，工具自行管理窗口创建和UI。

    必须实现：
      - tool_ident (抽象属性)
      - tool_name (抽象属性)
      - run_tool() (抽象方法)

    不需要：
      - create_embedded_interface() —— RemoteProgram始终独立进程运行，不嵌入主窗口
      - create_tool() 工厂函数 —— 主程序通过subprocess启动，不importlib加载
    """

    @abstractmethod
    def run_tool(self):
        """EXE独立运行入口（必须实现）。

        当工具以独立进程启动时（python tool_main.py --context 或 EXE模式），
        此方法作为运行入口。
        """
        pass


class TFP_RemoteWebpageTool(TFP_BaseTool):
    """RemoteWebpage工具基类——主程序创建WebView，无需前端代码。

    RemoteWebpage工具的前端由主程序直接创建 wx.html2.WebView 对话框
    加载后端URL，无需工具端实现任何UI代码。

    第三方开发者只需：
      1. 提供后端网页服务（Flask/FastAPI等）
      2. 在 tool_manifest.json 中设置 tool_type="RemoteWebpage" 和 tool_api_url
      3. 后端网页通过 Cookie 认证（由前端 WebView 自动传递）
      4. 后端 API 需实现 CSRF 防护

    前端主程序会自动：
      - 创建 wx.html2.WebView 对话框加载 tool_api_url
      - 通过一次性 token 交换机制传递认证 Cookie
      - 处理登录/权限检查

    详细开发指南（《RemoteWebpage 前端开发指南》）因涉及商业平台集成细节，
    不随本开源仓库发布，请联系 tabulexflow@outlook.com 获取。

    必须实现：
      - tool_ident (抽象属性)
      - tool_name (抽象属性)
    """
    pass


def create_tool_instance(tool_class, parent=None, context: Optional[TFP_ToolContext] = None, **kwargs):
    return tool_class(parent=parent, context=context, **kwargs)
