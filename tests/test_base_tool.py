# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""TFP_BaseTool / 工具上下文 / 元数据 测试

覆盖：TFP_AuthContext / TFP_ToolContext / TFP_ToolMetadata / TFP_IPCConfig 等
数据模型的序列化、反序列化与核心判定逻辑，以及 TFP_BaseTool 基础行为。
"""
import json
from datetime import datetime, timedelta

import pytest

from build_mode import IPC_HOST_IP

from tfp_utils.tfp_base_tool import (
    TFP_BaseTool,
    TFP_AuthContext,
    TFP_SettingsContext,
    TFP_IPCConfig,
    TFP_ToolContext,
    TFP_ToolMetadata,
    TFP_ToolType,
    create_tool_instance,
)


# ========== TFP_AuthContext ==========

def test_auth_context_is_logged_in():
    ctx = TFP_AuthContext(user_id=None, can_request_api=False)
    assert ctx.is_logged_in() is False
    ctx.user_id = 1
    assert ctx.is_logged_in() is False  # can_request_api 仍为 False
    ctx.can_request_api = True
    assert ctx.is_logged_in() is True


def test_auth_context_has_permission():
    ctx = TFP_AuthContext(permissions=["export"])
    assert ctx.has_permission("export") is True
    assert ctx.has_permission("import") is False


def test_auth_context_is_expired():
    future = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
    past = (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z"
    assert TFP_AuthContext(expires_at=future).is_expired() is False
    assert TFP_AuthContext(expires_at=past).is_expired() is True
    assert TFP_AuthContext(expires_at=None).is_expired() is True
    assert TFP_AuthContext(expires_at="bad-format").is_expired() is True


def test_auth_context_roundtrip():
    ctx = TFP_AuthContext(user_id=5, user_type="enterprise", permissions=["a", "b"],
                          expires_at="2030-01-01T00:00:00Z", machine_id="m1", can_request_api=True)
    data = ctx.to_dict()
    restored = TFP_AuthContext.from_dict(data)
    assert restored == ctx


# ========== TFP_ToolContext ==========

def test_tool_context_json_roundtrip():
    ctx = TFP_ToolContext(
        version="1.2.3",
        auth=TFP_AuthContext(user_id=1, can_request_api=True),
        settings=TFP_SettingsContext(language="en", backend_url="https://x.com"),
        tool_params={"key": "value"},
        ipc=TFP_IPCConfig(socket_port=12345),
    )
    restored = TFP_ToolContext.from_json(ctx.to_json())
    assert restored.version == "1.2.3"
    assert restored.auth.user_id == 1
    assert restored.auth.can_request_api is True
    assert restored.settings.language == "en"
    assert restored.tool_params == {"key": "value"}
    assert restored.ipc.socket_port == 12345


def test_tool_context_file_roundtrip(tmp_path):
    ctx = TFP_ToolContext(auth=TFP_AuthContext(user_id=3, can_request_api=True))
    path = tmp_path / "ctx.json"
    ctx.save_to_file(str(path))
    restored = TFP_ToolContext.load_from_file(str(path))
    assert restored.auth.user_id == 3


# ========== TFP_ToolMetadata ==========

def test_tool_metadata_defaults():
    m = TFP_ToolMetadata.from_dict({
        "tool_ident": "ToolA",
        "tool_title": {"zh": "工具A", "en": "Tool A"},
        "tool_type": "RemoteProgram",
        "tool_version": "1.0.0",
        "tool_description": {"zh": "描述"},
    })
    assert m.tool_ident == "ToolA"
    assert m.get_title("zh") == "工具A"
    assert m.get_title("fr") == "Tool A"  # 回退英文
    assert m.is_remote() is True
    assert m.requires_auth() is True
    assert m.supports_offline() is False


def test_tool_metadata_types():
    builtin = TFP_ToolMetadata.from_dict({"tool_ident": "B", "tool_type": "BuiltinProgram"})
    assert builtin.is_builtin() is True
    webpage = TFP_ToolMetadata.from_dict({"tool_ident": "W", "tool_type": "RemoteWebpage"})
    assert webpage.is_webpage() is True
    assert webpage.requires_auth() is True
    # 未知类型回退 BuiltinProgram
    unknown = TFP_ToolMetadata.from_dict({"tool_ident": "U", "tool_type": "Unknown"})
    assert unknown.is_builtin() is True


def test_tool_metadata_to_dict_from_dict_roundtrip():
    m = TFP_ToolMetadata(
        tool_ident="T", tool_title={"en": "T"}, tool_type=TFP_ToolType.REMOTE_WEBPAGE,
        tool_version="2.0.0", tool_description={"en": "d"}, tool_api_url="https://x.com",
        tool_deploy_mode="platform", tool_icon_path="i.png",
    )
    restored = TFP_ToolMetadata.from_dict(m.to_dict())
    assert restored.tool_ident == "T"
    assert restored.tool_type == TFP_ToolType.REMOTE_WEBPAGE
    assert restored.tool_api_url == "https://x.com"


# ========== 枚举与 IPC 配置 ==========

def test_tool_type_enum():
    assert TFP_ToolType("BuiltinProgram") == TFP_ToolType.BUILTIN_PROGRAM
    assert TFP_ToolType("RemoteProgram") == TFP_ToolType.REMOTE_PROGRAM
    assert TFP_ToolType("RemoteWebpage") == TFP_ToolType.REMOTE_WEBPAGE


def test_ipc_config_defaults():
    cfg = TFP_IPCConfig()
    assert cfg.socket_host == IPC_HOST_IP  # 默认仅回环
    restored = TFP_IPCConfig.from_dict(cfg.to_dict())
    assert restored.socket_host == IPC_HOST_IP


def test_settings_context_roundtrip():
    s = TFP_SettingsContext(language="zh", theme="dark", backend_url="https://x.com", debug_mode=True)
    assert TFP_SettingsContext.from_dict(s.to_dict()) == s


# ========== TFP_BaseTool ==========

class ConcreteTool(TFP_BaseTool):
    @property
    def tool_ident(self):
        return "Concrete"

    @property
    def tool_name(self):
        return "Concrete Tool"

    def create_embedded_interface(self, parent_panel, parent_sizer):
        pass

    def show_interface(self):
        pass


def test_base_tool_basic():
    ctx = TFP_ToolContext(auth=TFP_AuthContext(user_id=9, can_request_api=True),
                          settings=TFP_SettingsContext(language="en", backend_url="https://b.com"))
    tool = ConcreteTool(context=ctx)
    assert tool.tool_ident == "Concrete"
    assert tool.is_user_logged_in() is True
    assert tool.has_permission("x") is False
    assert tool.get_language() == "en"
    assert tool.get_backend_url() == "https://b.com"
    assert tool.get_user_id() == 9
    assert tool.get_window_size() == (800, 600)
    assert tool.get_tool_param("missing", "d") == "d"
    tool.set_tool_param("k", "v")
    assert tool.get_tool_param("k") == "v"
    assert tool.on_before_close() is True
    assert tool.is_standalone() is True


def test_base_tool_metadata():
    tool = ConcreteTool()
    assert tool.metadata is None
    tool.metadata = TFP_ToolMetadata(
        tool_ident="C", tool_title={}, tool_type=TFP_ToolType.BUILTIN_PROGRAM,
        tool_version="1.0.0", tool_description={},
        tool_window_width=1200, tool_window_height=800,
    )
    assert tool.metadata is not None
    assert tool.get_window_size() == (1200, 800)


def test_create_tool_instance():
    tool = create_tool_instance(ConcreteTool)
    assert isinstance(tool, ConcreteTool)
    assert tool.context is not None
