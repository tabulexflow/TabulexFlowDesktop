# TabulexFlow BuiltinProgram Development Guide

> **Document Version**: 5.1.0
> **Last Updated**: 2026-10-12
> **Applies to**: TabulexFlow v1.0.0
> **Target Audience**: Open-source contributors

> **中文版请翻到后面阅读 / Chinese version below** ↓

---
> **Community Edition (open source)**: This guide covers the **BuiltinProgram** tool type only (AGPL v3, embedded in the frontend main window). RemoteProgram and RemoteWebpage belong to the closed-source Commercial Edition and are not covered here.
>
> **开源社区版**：本指南仅覆盖 **BuiltinProgram** 工具类型（AGPL v3，内嵌在主程序窗口运行）。RemoteProgram、RemoteWebpage 属闭源商业版，不在本指南范围内。

---

This guide is intended for open-source contributors, introducing how to develop **BuiltinProgram** type open-source sub-tools for the TabulexFlow frontend project.

BuiltinProgram tools are open-sourced under the AGPL v3 license and distributed together with the main frontend program. Tools are dynamically loaded via `importlib`, running in the same process as the main program, and integrated into the main window as an embedded panel (wx.Panel).

### 1.1 Prerequisites

- Python 3.12.3+ and wxPython 4.2+
- Read the contributing guide (see [CONTRIBUTING.md](CONTRIBUTING.md))
- Signed the Contributor License Agreement (see [CLA.md](CLA.md))

---

## 2. Quick Start

### 2.1 Directory Structure

Create a tool directory under `tools_fe/tools_builtin_program/`:

```
tools_fe/tools_builtin_program/{ToolIdent}/
├── tool_main.py          # Tool entry file (required)
├── tool_manifest.json    # Tool manifest (required, auto-discovered)
├── app_icon.ico          # Tool icon (required)
├── locales/              # Internationalization files directory (optional)
│   ├── en.json
│   └── zh.json
├── assets/               # Resource files directory (optional)
└── requirements.txt      # Additional dependencies file (optional)
```

### 2.2 Minimal Example

**tool_main.py**:

```python
import wx
from tfp_toolkit.tfp_base_tool import TFP_BuiltinProgramTool
from tfp_toolkit.tfp_dpi import spx_calc


class MyTool(TFP_BuiltinProgramTool):

    @property
    def tool_ident(self) -> str:
        return "MyTool"

    @property
    def tool_name(self) -> str:
        return "My Tool"

    def create_embedded_interface(self, parent_panel, parent_sizer):
        self.panel = wx.Panel(parent_panel)
        sizer = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(self.panel, label="Hello, TabulexFlow!")
        sizer.Add(label, 0, wx.ALL, spx_calc(10))

        self.panel.SetSizer(sizer)
        parent_sizer.Add(self.panel, 1, wx.EXPAND)
        return self.panel


def create_tool(parent, user_setting_base_dir=None):
    return MyTool(parent)
```

### 2.3 Register the Tool

BuiltinProgram tools are registered via `tool_manifest.json` in the tool directory. The main program automatically scans `tools_fe/tools_builtin_program/` subdirectories for `tool_manifest.json` files at startup — no manual editing of centralized configuration files is needed.

**Create `tool_manifest.json`** in your tool directory:

```json
{
    "tool_ident": "MyTool",
    "tool_title": {
        "en": "My Tool",
        "zh": "我的工具",
        "fr": "Mon Outil",
        "ru": "Мой Инструмент",
        "es": "Mi Herramienta",
        "ar": "أداتي"
    },
    "tool_type": "BuiltinProgram",
    "tool_version": "1.0.0",
    "tool_description": {
        "en": "Description of my tool",
        "zh": "我的工具描述",
        "fr": "Description de mon outil",
        "ru": "Описание моего инструмента",
        "es": "Descripción de mi herramienta",
        "ar": "وصف أداتي"
    },
    "tool_is_free": true,
    "tool_is_open_source": true,
    "tool_is_local": true,
    "tool_need_ai": false,
    "tool_folder_path": "tools_builtin_program/MyTool",
    "tool_need_version": "1.0.0",
    "tool_dependencies": [],
    "tool_window_width": 800,
    "tool_window_height": 600,
    "tool_icon_path": "app_icon.ico",
    "tool_author": "Your Name",
    "tool_license": "AGPL-3.0",
    "tool_tags": ["my-tag"],
    "tool_min_frontend_version": "1.0.0"
}
```

**Field Descriptions**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tool_ident` | string | ✅ | Unique tool identifier, consistent with class name |
| `tool_title` | object | ✅ | Multilingual title, must include at least `en` and `zh` |
| `tool_type` | string | ✅ | Fixed as `"BuiltinProgram"` |
| `tool_version` | string | ✅ | Semantic version number |
| `tool_description` | object | ✅ | Multilingual description |
| `tool_is_free` | bool | ✅ | Whether free (BuiltinProgram is always `true`) |
| `tool_is_open_source` | bool | ✅ | Whether open source (BuiltinProgram is always `true`) |
| `tool_is_local` | bool | ✅ | Whether local tool (BuiltinProgram is always `true`) |
| `tool_need_ai` | bool | ✅ | Whether AI functionality is needed |
| `tool_folder_path` | string | ✅ | Tool directory path (relative to `tools_fe/`) |
| `tool_need_version` | string | ✅ | Required tool version |
| `tool_dependencies` | string[] | ✅ | Additional pip dependency list |
| `tool_window_width` | int | ✅ | Default window width (pixels) |
| `tool_window_height` | int | ✅ | Default window height (pixels) |
| `tool_icon_path` | string | ✅ | Icon file path (relative to tool directory) |
| `tool_author` | string | ✅ | Author/team name |
| `tool_license` | string | ✅ | License (BuiltinProgram is always `"AGPL-3.0"`) |
| `tool_tags` | string[] | ✅ | Tag list for categorization and search |
| `tool_min_frontend_version` | string | ✅ | Minimum required frontend version |

> **Note**: The main program scans tool directories at startup. If a `tool_manifest.json` is not found, it falls back to `config/tool_list_builtin.json`. There is no need to register in `menu_config.json` for tool display; the tool cards are generated automatically from the tool list.

**Quick scaffold**: You can also use the scaffold generator to create the entire tool directory structure:

```bash
cd tools_fe
python scaffold_builtin.py MyTool "我的工具" "My Tool"
```

---

## 3. Core API

### 3.1 TFP_BuiltinProgramTool Base Class

All BuiltinProgram tools must inherit from `tfp_toolkit.tfp_base_tool.TFP_BuiltinProgramTool` (the dual-licensed SDK package; `tfp_utils.tfp_base_tool` is the main-program-internal copy and is not for tool development).

```python
from tfp_toolkit.tfp_base_tool import TFP_BuiltinProgramTool
```

**Required properties and methods**:

| Member | Type | Description |
|--------|------|-------------|
| `tool_ident` | property → str | Unique tool identifier |
| `tool_name` | property → str | Tool display name |
| `create_embedded_interface(parent_panel, parent_sizer)` | method → wx.Panel | Create embedded interface |

> **Note**: `show_interface()` has a default implementation in `TFP_BuiltinProgramTool` that calls `self.panel.Show()`. Only override if you need custom behavior.

**Optional override methods**:

| Method | Description |
|--------|-------------|
| `on_before_show()` | Called before the tool is shown |
| `on_after_show()` | Called after the tool is shown |
| `on_before_close()` → bool | Called before the tool is closed; return False to prevent closing |
| `on_after_close()` | Called after the tool is closed |

**Convenience methods** (provided by the base class, can be called directly):

| Method | Return | Description |
|--------|--------|-------------|
| `get_context()` | TFP_ToolContext | Get full context |
| `set_context(context)` | - | Set context |
| `get_language()` | str | Get current language code |
| `get_backend_url()` | str | Get backend base URL |
| `is_user_logged_in()` | bool | Whether the user is logged in |
| `has_permission(permission)` | bool | Whether the user has the specified permission |
| `get_user_id()` | int \| None | Get user ID |
| `get_user_type()` | str | Get user type (`"free"` / `"premium"` / `"enterprise"`) |
| `get_tool_param(key, default)` | any | Get tool startup parameter |
| `set_tool_param(key, value)` | - | Set tool parameter |
| `get_window_size()` | tuple | Get window size (read from metadata) |
| `is_standalone()` | bool | Whether in standalone window mode |

### 3.2 Context Data (TFP_ToolContext)

Tools obtain context data via `self.get_context()`, which returns a `TFP_ToolContext` object:

```python
from tfp_toolkit.tfp_base_tool import TFP_ToolContext, TFP_AuthContext, TFP_SettingsContext
```

**TFP_AuthContext (Authentication Context)**:

| Property | Type | Description |
|----------|------|-------------|
| `user_id` | int \| None | User ID (None when not logged in) |
| `user_type` | str | User type: `"free"` / `"premium"` / `"enterprise"` |
| `permissions` | list[str] | Permission list |
| `expires_at` | str \| None | Token expiration time (ISO 8601 format) |
| `machine_id` | str \| None | Machine identifier (set by the main program) |
| `can_request_api` | bool | Whether the user can make API requests (default `False`) |

**Methods**:

| Method | Return | Description |
|--------|--------|-------------|
| `is_logged_in()` | bool | Whether the user is logged in |
| `has_permission(permission)` | bool | Whether the user has the specified permission |
| `is_expired()` | bool | Whether the token has expired |

> **Security Note**: Do not access `session_token` or `refresh_token` directly. Use `is_user_logged_in()` and `has_permission()` methods for authentication checks. The framework handles token management internally.

**TFP_SettingsContext (Settings Context)**:

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `language` | str | `"zh"` | Current language code |
| `theme` | str | `"light"` | Current theme |
| `backend_url` | str | `""` | Backend base URL |
| `debug_mode` | bool | `False` | Whether debug mode is enabled |

### 3.3 Resource File Access

Resource files in the tool directory (e.g., files in the `assets/` directory) can be accessed via standard Python path methods:

```python
import os

class MyTool(TFP_BuiltinProgramTool):
    def get_asset_path(self, filename):
        tool_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(tool_dir, "assets", filename)
```

> **Note**: After packaging as an EXE, `__file__` behavior may differ. In PyInstaller environments, use `sys._MEIPASS` to get the resource path.

---

## 4. Using Context Data

### 4.1 Getting Authentication Information

> **Commercial Edition note**: this subsection applies only to builds that connect to the TabulexFlow backend (Commercial Edition / backend-connected builds). In the Community Edition (no backend) this code path is never reached and unauthenticated users can use the tool freely.

```python
class MyTool(TFP_BuiltinProgramTool):
    def create_embedded_interface(self, parent_panel, parent_sizer):
        context = self.get_context()

        if context.auth.is_logged_in():
            user_id = context.auth.user_id
            user_type = context.auth.user_type
        else:
            # Unauthenticated users can still view the tool interface
            # Permission checks happen at the backend API level when executing features
            pass
```

### 4.2 Getting Frontend Configuration

```python
class MyTool(TFP_BuiltinProgramTool):
    def create_embedded_interface(self, parent_panel, parent_sizer):
        # Get current language
        lang = self.get_language()

        # Get backend URL
        backend_url = self.get_backend_url()

        # Get full settings
        context = self.get_context()
        theme = context.settings.theme
        debug = context.settings.debug_mode
```

### 4.3 Calling Backend API

> **Commercial Edition note**: this subsection applies only to builds that connect to the TabulexFlow backend (Commercial Edition / backend-connected builds); the Community Edition has no backend to call.

BuiltinProgram tools run in the same process as the main program and can access the authentication manager directly. Use `auth_manager.get_auth_headers()` to obtain authenticated request headers:

```python
import requests
from tfp_auth import auth_manager

class MyTool(TFP_BuiltinProgramTool):
    def call_backend_api(self):
        # Get authenticated headers from the framework's auth manager
        # This automatically includes the Bearer token and user ID
        headers = auth_manager.get_auth_headers()

        response = requests.get(
            f"{self.get_backend_url()}/api/v1/my-endpoint",
            headers=headers
        )
        return response.json()
```

> **Security Note**: Always use `auth_manager.get_auth_headers()` for authenticated API calls. Do not manually construct `Authorization: Bearer` headers or access `session_token` directly. The auth manager handles token refresh and expiry automatically.

### 4.4 Permission Error Handling

> **Commercial Edition note**: this subsection applies only to builds that connect to the TabulexFlow backend (Commercial Edition / backend-connected builds); the Community Edition has no paid features and no permission errors to handle.

When calling backend APIs for paid features, handle 401/403 responses:

```python
def _handle_api_response(self, response):
    if response.status_code == 401:
        # Not logged in - login dialog will be shown by the framework
        return
    elif response.status_code == 403:
        # Insufficient permissions - upgrade dialog will be shown by the framework
        return
    # Process successful response
```

> **Design Principle**: The frontend does not pre-check permissions. All permission validation is done by the backend API. The frontend only handles the backend's 401/403 responses.

---

## 5. Internationalization (i18n)

### 5.1 Loading Translation Files

```python
from pathlib import Path
from tfp_toolkit.tfp_i18n_manager import TFP_I18nManager as I18nManager, translate_list as _base_translate_list

_TOOL_DIR = Path(__file__).parent

DEFAULT_TRANSLATIONS = {
    "en": {"hello": "Hello", "settings": "Settings", "export": "Export"},
    "zh": {"hello": "你好", "settings": "设置", "export": "导出"}
}

class MyTool_I18nManager(I18nManager):
    def __init__(self, default_language='en'):
        super().__init__(default_language=default_language, default_translations=DEFAULT_TRANSLATIONS)
    def _find_locales_dir(self):
        return str(_TOOL_DIR / 'locales') if (_TOOL_DIR / 'locales').exists() else None
    def _load_main_app_translations(self):
        pass  # Handled by SDK base class
    def _find_language_config_file(self):
        return None

i18n = MyTool_I18nManager()
translate = i18n.get
```

### 5.2 Translation File Format

**locales/zh.json**:
```json
{
    "hello": "你好",
    "settings": "设置",
    "export": "导出"
}
```

**locales/en.json**:
```json
{
    "hello": "Hello",
    "settings": "Settings",
    "export": "Export"
}
```

### 5.3 Responding to Language Changes

Language switching in the main program requires a restart to take effect. If your tool needs to handle language changes at runtime, you can reload translations when the tool is shown.

---

## 6. Integration with the Main Program

### 6.1 Loading Mechanism

BuiltinProgram tools are dynamically loaded via `importlib`, running in the same process as the main program:

1. The main program scans `tools_fe/tools_builtin_program/` subdirectories for `tool_manifest.json` files (falls back to `config/tool_list_builtin.json` if no manifests found)
2. When the user clicks a tool card, the main program loads `tool_main.py` via `importlib`
3. Calls `create_tool(parent, user_setting_base_dir)` factory function to create a tool instance
4. Calls `create_embedded_interface()` to embed the tool panel into the main window

BuiltinProgram runs in the same process as the main program and can directly access all context data.

### 6.2 Tool Factory Function

Each tool must export a `create_tool()` function:

```python
def create_tool(parent, user_setting_base_dir=None):
    """Tool factory function - called by the main program

    Args:
        parent: wxPython parent window object (the main window instance)
        user_setting_base_dir: User settings directory path (optional)
    """
    return MyTool(parent)
```

Parameter descriptions:
- `parent`: wxPython parent window object (the main window instance, passed as `self` by the main program)
- `user_setting_base_dir`: User settings base directory path string (optional). The main program passes `self.user_setting_dir` for this parameter. Your tool can use it to store per-user configuration files.

> **Note**: The main program calls `create_tool(self, user_setting_base_dir=user_setting_base_dir)`. The `context` (TFP_ToolContext) is NOT passed via `create_tool()` — it is set internally by the base class after instantiation. Use `self.get_context()` to access context data within your tool.

### 6.3 Lifecycle

```
User clicks tool card → Main program importlib loads tool module
  → Calls create_tool() to create instance
  → Calls create_embedded_interface() to embed panel
  → [User uses tool]
  → User returns to home (Ctrl+H)
  → Tool panel is hidden (not destroyed)
```

> **Important**: Since the tool panel is hidden rather than destroyed when the user returns to the home page, the tool instance persists in memory. When the user clicks the tool card again, the main program simply shows the existing panel (no re-creation). If your tool needs to refresh data when re-shown, override `on_before_show()` to update the UI state.

---

## 7. DPI Awareness

### 7.1 DPI Scaling

All BuiltinProgram tools must support DPI awareness. The main program provides the `spx_calc()` method for pixel scaling:

```python
from tfp_toolkit.tfp_dpi import spx_calc

class MyTool(TFP_BuiltinProgramTool):
    def create_embedded_interface(self, parent_panel, parent_sizer):
        # Use self.spx_calc() (from base class) or spx_calc() (standalone SDK) for all fixed pixel values
        button = wx.Button(self.panel, size=(self.spx_calc(100), self.spx_calc(30)))
        sizer.Add(button, 0, wx.ALL, spx_calc(10))
```

> **Note**: The `spx_calc()` method is available both as `self.spx_calc()` from the base class and as a standalone function from `tfp_toolkit.tfp_dpi`.

**Elements that need scaling**: Window/dialog sizes, control sizes, min/max sizes, icon/image sizes, Grid column widths, Sizer borders, separator sizes.

**Elements that do NOT need scaling**: Values of -1 (wx auto-calculated), proportion values in sizers, font point sizes (wxPython handles DPI scaling automatically).

---

## 8. Packaging and Release

### 8.1 Packaging Process

BuiltinProgram tools are packaged together with the main frontend program as an EXE; no separate release is needed.

Packaging steps:
1. Ensure the tool directory is under `tools_fe/tools_builtin_program/`
2. Ensure `tool_manifest.json` exists in the tool directory
3. Add the `--add-data` parameter in the PyInstaller build script (`scripts/tfpdesktop_build.bat` on Windows, `scripts/tfpdesktop_build.sh` on Linux) to include the tool directory. Format:
   ```bash
   --add-data "tools_fe/tools_builtin_program/MyTool;tools_fe/tools_builtin_program/MyTool"
   ```
   (Use `;` as separator on Windows, `:` on Linux/macOS)
4. Run the build script to generate the EXE

### 8.2 Version Management

- Follow Semantic Versioning
- Update `tool_version` in `tool_manifest.json`
- Record changes in `CHANGELOG.md`

---

## 9. Best Practices

### 9.1 Code Standards

- Follow PEP 8 Python code conventions
- Use type annotations to improve code readability
- Add appropriate docstrings
- Use `tfp_` prefix for module names, `TFP_` prefix for class names
- All `.py` source files must include the AGPL v3 SPDX header:
  ```python
  # Copyright (C) 2024-present TabulexFlow Team
  # SPDX-License-Identifier: AGPL-3.0-or-later
  ```

### 9.2 Error Handling

For user-facing errors, use `wx.MessageBox` to display error messages. For internal errors, use the `logging` module:

```python
import logging

logger = logging.getLogger(__name__)

class MyTool(TFP_BuiltinProgramTool):
    def safe_operation(self):
        try:
            result = self.risky_call()
        except Exception as e:
            logger.error("Operation failed: %s", e)
            wx.MessageBox(f"Error: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)
            return None
        return result
```

> **Tip**: Use `wx.MessageBox` for critical errors that require user attention, and `logger.info`/`logger.warning` for non-critical status messages. Avoid using `print()` for any output.

### 9.3 Thread Safety

```python
import threading
import wx

class MyTool(TFP_BuiltinProgramTool):
    def long_running_task(self):
        def task():
            result = self.do_heavy_work()
            wx.CallAfter(self.update_ui, result)

        thread = threading.Thread(target=task)
        thread.daemon = True
        thread.start()
```

### 9.4 Security

- Do not hardcode API keys or sensitive information
- Use HTTPS for backend API calls
- Do not print tokens in logs
- Handle 401/403 responses from backend API for permission checks (Commercial Edition backend-connected builds only)
- Use `send2trash` for file deletion (no permanent delete)

---

## 10. Debugging Tips

### 10.1 Logging

```python
import logging

logger = logging.getLogger(__name__)
logger.propagate = False  # Prevent duplicate log output

logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
```

### 10.2 Standalone Testing with Mock Context

```python
from tfp_toolkit.tfp_base_tool import TFP_ToolContext, TFP_AuthContext, TFP_SettingsContext

mock_context = TFP_ToolContext(
    auth=TFP_AuthContext(
        user_id=1,
        user_type="premium"
    ),
    settings=TFP_SettingsContext(
        language="zh",
        backend_url="http://127.0.0.1:8080"
    )
)

# Note: create_tool takes parent and user_setting_base_dir, not context.
# For standalone testing, create the tool instance and set context manually:
tool = create_tool(parent=None)
tool.set_context(mock_context)
```

### 10.3 Running in Development Mode

Run the main program directly in the development environment for debugging:

```bash
cd TabulexFlowDesktop
python main.py
```

Set `TFP_DEV_MODE=development` for development mode. After modifying tool code, click the tool card again to load the latest code (no need to restart the main program).

---

## 11. Contributing

1. Ensure your code complies with the standards in this guide
2. Sign the Contributor License Agreement ([CLA.md](CLA.md))
3. Submit a Pull Request to the main repository
4. Describe the tool functionality and testing status in the PR description

For the detailed contribution process, please refer to [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 12. SDK Reference (tfp_toolkit)

The `tfp_toolkit` package provides shared components used by BuiltinProgram tools:

### 12.1 Available Modules

| Module | Description |
|--------|-------------|
| `tfp_toolkit.tfp_base_tool` | Base classes: `TFP_BaseTool`, `TFP_BuiltinProgramTool` |
| `tfp_toolkit.tfp_i18n_manager` | I18n manager base class `TFP_I18nManager` |
| `tfp_toolkit.tfp_dpi` | DPI scaling: `spx_calc()`, `get_dpi_scale_factor()`, `set_dpi_scale_factor()` |
| `tfp_toolkit.tfp_base_grid` | Grid base class `TFP_BaseGrid` with keyboard shortcuts, undo/redo, copy/paste |
| `tfp_toolkit.tfp_auth` | Auth helpers: `is_user_logged_in()`, `has_permission()`, `is_premium_user()` |
| `tfp_toolkit.tfp_constants` | Constants: tool types, supported languages, and other defaults |

### 12.2 Using the Grid Base Class

For tools that use wx.grid.Grid, inherit from `TFP_BaseGrid`:

```python
from tfp_toolkit.tfp_base_grid import TFP_BaseGrid

class MyGrid(TFP_BaseGrid):
    MAX_UNDO = 20  # Customize undo stack size

    def __init__(self, parent, **kwargs):
        kwargs.setdefault('max_undo', self.MAX_UNDO)
        super().__init__(parent, **kwargs)
```

`TFP_BaseGrid` provides: Delete/Ctrl+C/V/A/Z/Y, copy/paste (Excel-compatible), undo/redo, right-click menus, read-only mode, and hook methods (`on_cells_cleared`, `on_cells_pasted`, `on_rows_added`, `on_rows_deleted`).

### 12.3 Scaffold Generators

| Generator | Location | Usage |
|-----------|----------|-------|
| BuiltinProgram | `tools_fe/scaffold_builtin.py` | `python scaffold_builtin.py <ident> <title_zh> <title_en>` |

---

> **Document Version**: 5.1.0
> **Last Updated**: 2026-10-12

---
---

## 中文版

# TabulexFlow BuiltinProgram 开源工具开发指南

> **文档版本**: 5.1.0
> **最后更新**: 2026-10-12
> **适用版本**: TabulexFlow v1.0.0
> **目标读者**: 开源贡献者

本指南面向开源贡献者，介绍如何为 TabulexFlow 前端工程开发 **BuiltinProgram** 类型的开源子工具。

BuiltinProgram 工具以 AGPL v3 协议开源，代码随前端主程序一起发布。工具通过 `importlib` 动态加载，运行在主程序的同一进程中，以嵌入式面板（wx.Panel）形式集成到主窗口。

### 1.1 前置知识

- Python 3.12.3+ 和 wxPython 4.2+
- 已阅读贡献指南（见 [CONTRIBUTING.md](CONTRIBUTING.md)）
- 已签署贡献者许可协议（见 [CLA.md](CLA.md)）

---

## 2. 快速开始

### 2.1 目录结构

在 `tools_fe/tools_builtin_program/` 下创建工具目录：

```
tools_fe/tools_builtin_program/{ToolIdent}/
├── tool_main.py          # 工具入口文件（必须）
├── tool_manifest.json    # 工具清单（必须，自动发现）
├── app_icon.ico          # 工具图标（必须）
├── locales/              # 国际化文件目录（可选）
│   ├── en.json
│   └── zh.json
├── assets/               # 资源文件目录（可选）
└── requirements.txt      # 额外依赖文件（可选）
```

### 2.2 最小示例

**tool_main.py**：

```python
import wx
from tfp_toolkit.tfp_base_tool import TFP_BuiltinProgramTool
from tfp_toolkit.tfp_dpi import spx_calc


class MyTool(TFP_BuiltinProgramTool):

    @property
    def tool_ident(self) -> str:
        return "MyTool"

    @property
    def tool_name(self) -> str:
        return "My Tool"

    def create_embedded_interface(self, parent_panel, parent_sizer):
        self.panel = wx.Panel(parent_panel)
        sizer = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(self.panel, label="Hello, TabulexFlow!")
        sizer.Add(label, 0, wx.ALL, spx_calc(10))

        self.panel.SetSizer(sizer)
        parent_sizer.Add(self.panel, 1, wx.EXPAND)
        return self.panel


def create_tool(parent, user_setting_base_dir=None):
    return MyTool(parent)
```

### 2.3 注册工具

BuiltinProgram 工具通过工具目录下的 `tool_manifest.json` 注册。主程序启动时自动扫描 `tools_fe/tools_builtin_program/` 子目录下的 `tool_manifest.json` 文件，无需手动编辑集中式配置文件。

**在工具目录下创建 `tool_manifest.json`**：

```json
{
    "tool_ident": "MyTool",
    "tool_title": {
        "en": "My Tool",
        "zh": "我的工具",
        "fr": "Mon Outil",
        "ru": "Мой Инструмент",
        "es": "Mi Herramienta",
        "ar": "أداتي"
    },
    "tool_type": "BuiltinProgram",
    "tool_version": "1.0.0",
    "tool_description": {
        "en": "Description of my tool",
        "zh": "我的工具描述",
        "fr": "Description de mon outil",
        "ru": "Описание моего инструмента",
        "es": "Descripción de mi herramienta",
        "ar": "وصف أداتي"
    },
    "tool_is_free": true,
    "tool_is_open_source": true,
    "tool_is_local": true,
    "tool_need_ai": false,
    "tool_folder_path": "tools_builtin_program/MyTool",
    "tool_need_version": "1.0.0",
    "tool_dependencies": [],
    "tool_window_width": 800,
    "tool_window_height": 600,
    "tool_icon_path": "app_icon.ico",
    "tool_author": "Your Name",
    "tool_license": "AGPL-3.0",
    "tool_tags": ["my-tag"],
    "tool_min_frontend_version": "1.0.0"
}
```

**字段说明**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `tool_ident` | string | ✅ | 工具唯一标识符，与类名一致 |
| `tool_title` | object | ✅ | 多语言标题，至少包含 `en` 和 `zh` |
| `tool_type` | string | ✅ | 固定为 `"BuiltinProgram"` |
| `tool_version` | string | ✅ | 语义化版本号 |
| `tool_description` | object | ✅ | 多语言描述 |
| `tool_is_free` | bool | ✅ | 是否免费（BuiltinProgram 固定为 `true`） |
| `tool_is_open_source` | bool | ✅ | 是否开源（BuiltinProgram 固定为 `true`） |
| `tool_is_local` | bool | ✅ | 是否本地工具（BuiltinProgram 固定为 `true`） |
| `tool_need_ai` | bool | ✅ | 是否需要 AI 功能 |
| `tool_folder_path` | string | ✅ | 工具目录路径（相对于 `tools_fe/`） |
| `tool_need_version` | string | ✅ | 要求的工具版本 |
| `tool_dependencies` | string[] | ✅ | 额外 pip 依赖列表 |
| `tool_window_width` | int | ✅ | 默认窗口宽度（像素） |
| `tool_window_height` | int | ✅ | 默认窗口高度（像素） |
| `tool_icon_path` | string | ✅ | 图标文件路径（相对于工具目录） |
| `tool_author` | string | ✅ | 作者/团队名称 |
| `tool_license` | string | ✅ | 许可证（BuiltinProgram 固定为 `"AGPL-3.0"`） |
| `tool_tags` | string[] | ✅ | 标签列表，用于分类和搜索 |
| `tool_min_frontend_version` | string | ✅ | 要求的最低前端版本 |

> **注意**：主程序启动时自动扫描工具目录。如果未找到 `tool_manifest.json`，会回退到 `config/tool_list_builtin.json`。无需在 `menu_config.json` 中注册工具显示项，工具卡片由工具列表自动生成。

**快速脚手架**：也可以使用脚手架生成器创建完整的工具目录结构：

```bash
cd tools_fe
python scaffold_builtin.py MyTool "我的工具" "My Tool"
```

---

## 3. 核心 API

### 3.1 TFP_BuiltinProgramTool 基类

所有 BuiltinProgram 工具必须继承 `tfp_toolkit.tfp_base_tool.TFP_BuiltinProgramTool`（双许可 SDK 包；`tfp_utils.tfp_base_tool` 仅供主程序内部使用，不用于工具开发）。

```python
from tfp_toolkit.tfp_base_tool import TFP_BuiltinProgramTool
```

**必须实现的属性和方法**：

| 成员 | 类型 | 说明 |
|------|------|------|
| `tool_ident` | property → str | 工具唯一标识符 |
| `tool_name` | property → str | 工具显示名称 |
| `create_embedded_interface(parent_panel, parent_sizer)` | method → wx.Panel | 创建嵌入式界面 |

> **注意**：`show_interface()` 在 `TFP_BuiltinProgramTool` 中有默认实现，调用 `self.panel.Show()`。仅在需要自定义行为时才重写。

**可选重写的方法**：

| 方法 | 说明 |
|------|------|
| `on_before_show()` | 工具显示前调用 |
| `on_after_show()` | 工具显示后调用 |
| `on_before_close()` → bool | 工具关闭前调用，返回 False 可阻止关闭 |
| `on_after_close()` | 工具关闭后调用 |

**便捷方法**（由基类提供，可直接调用）：

| 方法 | 返回 | 说明 |
|------|------|------|
| `get_context()` | TFP_ToolContext | 获取完整上下文 |
| `set_context(context)` | - | 设置上下文 |
| `get_language()` | str | 获取当前语言代码 |
| `get_backend_url()` | str | 获取后端基础 URL |
| `is_user_logged_in()` | bool | 用户是否已登录 |
| `has_permission(permission)` | bool | 是否拥有指定权限 |
| `get_user_id()` | int \| None | 获取用户 ID |
| `get_user_type()` | str | 获取用户类型（`"free"` / `"premium"` / `"enterprise"`） |
| `get_tool_param(key, default)` | any | 获取工具启动参数 |
| `set_tool_param(key, value)` | - | 设置工具参数 |
| `get_window_size()` | tuple | 获取窗口尺寸（从 metadata 读取） |
| `is_standalone()` | bool | 是否为独立窗口模式 |

### 3.2 上下文数据 (TFP_ToolContext)

工具通过 `self.get_context()` 获取上下文数据，返回 `TFP_ToolContext` 对象：

```python
from tfp_toolkit.tfp_base_tool import TFP_ToolContext, TFP_AuthContext, TFP_SettingsContext
```

**TFP_AuthContext（认证上下文）**：

| 属性 | 类型 | 说明 |
|------|------|------|
| `user_id` | int \| None | 用户 ID（未登录时为 None） |
| `user_type` | str | 用户类型：`"free"` / `"premium"` / `"enterprise"` |
| `permissions` | list[str] | 权限列表 |
| `expires_at` | str \| None | 令牌过期时间（ISO 8601 格式） |
| `machine_id` | str \| None | 机器标识（由主程序设置） |
| `can_request_api` | bool | 用户是否可以发起 API 请求（默认 `False`） |

**方法**：

| 方法 | 返回 | 说明 |
|------|------|------|
| `is_logged_in()` | bool | 用户是否已登录 |
| `has_permission(permission)` | bool | 是否拥有指定权限 |
| `is_expired()` | bool | 令牌是否已过期 |

> **安全提示**：不要直接访问 `session_token` 或 `refresh_token`。请使用 `is_user_logged_in()` 和 `has_permission()` 方法进行认证检查，框架内部处理令牌管理。

**TFP_SettingsContext（设置上下文）**：

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `language` | str | `"zh"` | 当前语言代码 |
| `theme` | str | `"light"` | 当前主题 |
| `backend_url` | str | `""` | 后端基础 URL |
| `debug_mode` | bool | `False` | 是否调试模式 |

### 3.3 资源文件访问

工具目录下的资源文件（如 `assets/` 目录中的文件），可通过 Python 标准方式获取路径：

```python
import os

class MyTool(TFP_BuiltinProgramTool):
    def get_asset_path(self, filename):
        tool_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(tool_dir, "assets", filename)
```

> **注意**：打包为 EXE 后，`__file__` 的行为可能不同。PyInstaller 环境下应使用 `sys._MEIPASS` 获取资源路径。

---

## 4. 使用上下文数据

### 4.1 获取认证信息

> **商业版说明**：本小节仅适用于连接 TabulexFlow 后端的构建（商业版/连接后端版本）。开源社区版无后端，该代码路径不会执行，未登录用户可自由使用工具。

```python
class MyTool(TFP_BuiltinProgramTool):
    def create_embedded_interface(self, parent_panel, parent_sizer):
        context = self.get_context()

        if context.auth.is_logged_in():
            user_id = context.auth.user_id
            user_type = context.auth.user_type
        else:
            # 未登录用户仍可查看工具界面
            # 权限检查在执行功能时由后端API验证
            pass
```

### 4.2 获取前端配置

```python
class MyTool(TFP_BuiltinProgramTool):
    def create_embedded_interface(self, parent_panel, parent_sizer):
        # 获取当前语言
        lang = self.get_language()

        # 获取后端 URL
        backend_url = self.get_backend_url()

        # 获取完整设置
        context = self.get_context()
        theme = context.settings.theme
        debug = context.settings.debug_mode
```

### 4.3 调用后端 API

> **商业版说明**：本小节仅适用于连接 TabulexFlow 后端的构建（商业版/连接后端版本）；开源社区版无后端可调用。

BuiltinProgram 工具与主程序运行在同一进程中，可以直接访问认证管理器。使用 `auth_manager.get_auth_headers()` 获取带认证的请求头：

```python
import requests
from tfp_auth import auth_manager

class MyTool(TFP_BuiltinProgramTool):
    def call_backend_api(self):
        # 从框架的认证管理器获取认证头
        # 自动包含 Bearer token 和用户 ID
        headers = auth_manager.get_auth_headers()

        response = requests.get(
            f"{self.get_backend_url()}/api/v1/my-endpoint",
            headers=headers
        )
        return response.json()
```

> **安全提示**：请始终使用 `auth_manager.get_auth_headers()` 进行需要认证的 API 调用。不要手动构造 `Authorization: Bearer` 请求头或直接访问 `session_token`。认证管理器会自动处理令牌刷新和过期。

### 4.4 权限错误处理

> **商业版说明**：本小节仅适用于连接 TabulexFlow 后端的构建（商业版/连接后端版本）；开源社区版无收费功能，也无权限错误需要处理。

调用后端API的收费功能时，需处理401/403响应：

```python
def _handle_api_response(self, response):
    if response.status_code == 401:
        # 未登录 - 框架会弹出登录对话框
        return
    elif response.status_code == 403:
        # 权限不足 - 框架会弹出升级提示对话框
        return
    # 处理成功响应
```

> **设计原则**：前端不预先检查权限，所有权限验证由后端API完成，前端仅处理后端返回的401/403响应。

---

## 5. 国际化

### 5.1 加载翻译文件

```python
from pathlib import Path
from tfp_toolkit.tfp_i18n_manager import TFP_I18nManager as I18nManager, translate_list as _base_translate_list

_TOOL_DIR = Path(__file__).parent

DEFAULT_TRANSLATIONS = {
    "en": {"hello": "Hello", "settings": "Settings", "export": "Export"},
    "zh": {"hello": "你好", "settings": "设置", "export": "导出"}
}

class MyTool_I18nManager(I18nManager):
    def __init__(self, default_language='en'):
        super().__init__(default_language=default_language, default_translations=DEFAULT_TRANSLATIONS)
    def _find_locales_dir(self):
        return str(_TOOL_DIR / 'locales') if (_TOOL_DIR / 'locales').exists() else None
    def _load_main_app_translations(self):
        pass  # Handled by SDK base class
    def _find_language_config_file(self):
        return None

i18n = MyTool_I18nManager()
translate = i18n.get
```

### 5.2 翻译文件格式

**locales/zh.json**：
```json
{
    "hello": "你好",
    "settings": "设置",
    "export": "导出"
}
```

**locales/en.json**：
```json
{
    "hello": "Hello",
    "settings": "Settings",
    "export": "Export"
}
```

### 5.3 响应语言切换

主程序语言切换需要重启才生效。如果工具需要在运行时处理语言变更，可以在工具显示时重新加载翻译。

---

## 6. 与主程序集成

### 6.1 加载机制

BuiltinProgram 工具通过 `importlib` 动态加载，运行在主程序的同一进程中：

1. 主程序扫描 `tools_fe/tools_builtin_program/` 子目录下的 `tool_manifest.json` 文件（若未找到清单则回退到 `config/tool_list_builtin.json`）
2. 用户点击工具卡片时，主程序通过 `importlib` 加载 `tool_main.py`
3. 调用 `create_tool(parent, user_setting_base_dir)` 工厂函数创建工具实例
4. 调用 `create_embedded_interface()` 将工具面板嵌入主窗口

BuiltinProgram 与主程序运行在同一进程中，可以直接访问所有上下文数据。

### 6.2 工厂函数

每个工具必须导出 `create_tool()` 函数：

```python
def create_tool(parent, user_setting_base_dir=None):
    """工具工厂函数 - 由主程序调用

    Args:
        parent: wxPython 父窗口对象（主窗口实例）
        user_setting_base_dir: 用户设置目录路径（可选）
    """
    return MyTool(parent)
```

参数说明：
- `parent`: wxPython 父窗口对象（主窗口实例，主程序传入 `self`）
- `user_setting_base_dir`: 用户设置基础目录路径字符串（可选）。主程序传入 `self.user_setting_dir`，工具可使用此目录存储用户配置文件。

> **注意**：主程序调用方式为 `create_tool(self, user_setting_base_dir=user_setting_base_dir)`。`context`（TFP_ToolContext）**不是**通过 `create_tool()` 传入的——它在实例化后由基类内部设置。在工具内请使用 `self.get_context()` 访问上下文数据。

### 6.3 生命周期

```
用户点击工具卡片 → 主程序 importlib 加载工具模块
  → 调用 create_tool() 创建实例
  → 调用 create_embedded_interface() 嵌入面板
  → [用户使用工具]
  → 用户返回主页（Ctrl+H）
  → 工具面板隐藏（而非销毁）
```

> **重要**：用户返回主页时工具面板是隐藏而非销毁，工具实例会一直保留在内存中。用户再次点击工具卡片时，主程序只是显示已有的面板（不会重新创建）。如果工具需要在重新显示时刷新数据，请重写 `on_before_show()` 方法来更新 UI 状态。

---

## 7. DPI 适配

### 7.1 DPI 缩放

所有 BuiltinProgram 工具必须支持 DPI 感知。主程序提供 `spx_calc()` 方法用于像素缩放：

```python
from tfp_toolkit.tfp_dpi import spx_calc

class MyTool(TFP_BuiltinProgramTool):
    def create_embedded_interface(self, parent_panel, parent_sizer):
        # 对所有固定像素值使用 self.spx_calc()（基类方法）或 spx_calc()（独立 SDK 函数）
        button = wx.Button(self.panel, size=(self.spx_calc(100), self.spx_calc(30)))
        sizer.Add(button, 0, wx.ALL, spx_calc(10))
```

> **注意**：`spx_calc()` 方法既可通过基类的 `self.spx_calc()` 调用，也可通过 `tfp_toolkit.tfp_dpi` 的独立函数调用。

**需要缩放的元素**：窗口/对话框尺寸、控件尺寸、最小/最大尺寸、图标/图片尺寸、Grid列宽、Sizer边距、分隔线尺寸。

**不需要缩放的元素**：值为-1（wx自动计算）、Sizer中的比例值、字体pt值（wxPython自动处理DPI缩放）。

---

## 8. 打包与发布

### 8.1 打包流程

BuiltinProgram 工具随前端主程序一起打包为 EXE，无需单独发布。

打包步骤：
1. 确保工具目录在 `tools_fe/tools_builtin_program/` 下
2. 确保工具目录下存在 `tool_manifest.json`
3. 在 PyInstaller 构建脚本（Windows 为 `scripts/tfpdesktop_build.bat`，Linux 为 `scripts/tfpdesktop_build.sh`）中添加 `--add-data` 参数包含工具目录。格式：
   ```bash
   --add-data "tools_fe/tools_builtin_program/MyTool;tools_fe/tools_builtin_program/MyTool"
   ```
   （Windows 使用 `;` 分隔，Linux/macOS 使用 `:` 分隔）
4. 运行构建脚本生成 EXE

### 8.2 版本管理

- 遵循语义化版本 (Semantic Versioning)
- 在 `tool_manifest.json` 中更新 `tool_version`
- 在 `CHANGELOG.md` 中记录变更

---

## 9. 最佳实践

### 9.1 代码规范

- 遵循 PEP 8 Python 代码规范
- 使用类型注解提高代码可读性
- 添加适当的文档字符串
- 模块名使用 `tfp_` 前缀，类名使用 `TFP_` 前缀
- 所有 `.py` 源文件必须包含 AGPL v3 SPDX 头：
  ```python
  # Copyright (C) 2024-present TabulexFlow Team
  # SPDX-License-Identifier: AGPL-3.0-or-later
  ```

### 9.2 错误处理

面向用户的错误使用 `wx.MessageBox` 显示错误信息，内部错误使用 `logging` 模块记录：

```python
import logging

logger = logging.getLogger(__name__)

class MyTool(TFP_BuiltinProgramTool):
    def safe_operation(self):
        try:
            result = self.risky_call()
        except Exception as e:
            logger.error("操作失败: %s", e)
            wx.MessageBox(f"错误: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
            return None
        return result
```

> **提示**：关键错误使用 `wx.MessageBox` 提示用户，非关键状态信息使用 `logger.info`/`logger.warning` 记录。避免使用 `print()` 输出任何信息。

### 9.3 线程安全

```python
import threading
import wx

class MyTool(TFP_BuiltinProgramTool):
    def long_running_task(self):
        def task():
            result = self.do_heavy_work()
            wx.CallAfter(self.update_ui, result)

        thread = threading.Thread(target=task)
        thread.daemon = True
        thread.start()
```

### 9.4 安全性

- 不要在代码中硬编码 API 密钥或敏感信息
- 所有后端 API 调用使用 HTTPS
- 不要在日志中打印令牌
- 处理后端API的401/403响应进行权限检查（仅限商业版连接后端的构建）
- 文件删除使用 `send2trash`（禁止永久删除）

---

## 10. 调试技巧

### 10.1 日志记录

```python
import logging

logger = logging.getLogger(__name__)
logger.propagate = False  # 防止重复日志输出

logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
```

### 10.2 模拟上下文独立测试

```python
from tfp_toolkit.tfp_base_tool import TFP_ToolContext, TFP_AuthContext, TFP_SettingsContext

mock_context = TFP_ToolContext(
    auth=TFP_AuthContext(
        user_id=1,
        user_type="premium"
    ),
    settings=TFP_SettingsContext(
        language="zh",
        backend_url="http://127.0.0.1:8080"
    )
)

# 注意：create_tool 接受 parent 和 user_setting_base_dir，不接受 context。
# 独立测试时，先创建工具实例，再手动设置上下文：
tool = create_tool(parent=None)
tool.set_context(mock_context)
```

### 10.3 开发模式运行

在开发环境中直接运行主程序进行调试：

```bash
cd TabulexFlowDesktop
python main.py
```

设置 `TFP_DEV_MODE=development` 启用开发模式。工具代码修改后，重新点击工具卡片即可加载最新代码（无需重启主程序）。

---

## 11. 提交贡献

1. 确保代码符合本指南的规范
2. 签署贡献者许可协议（[CLA.md](CLA.md)）
3. 提交 Pull Request 到主仓库
4. 在 PR 描述中说明工具功能和测试情况

详细的贡献流程请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 12. SDK 参考（tfp_toolkit）

`tfp_toolkit` 包为 BuiltinProgram 工具提供共享组件：

### 12.1 可用模块

| 模块 | 说明 |
|------|------|
| `tfp_toolkit.tfp_base_tool` | 基类：`TFP_BaseTool`、`TFP_BuiltinProgramTool` |
| `tfp_toolkit.tfp_i18n_manager` | 国际化管理器基类 `TFP_I18nManager` |
| `tfp_toolkit.tfp_dpi` | DPI 缩放：`spx_calc()`、`get_dpi_scale_factor()`、`set_dpi_scale_factor()` |
| `tfp_toolkit.tfp_base_grid` | Grid 基类 `TFP_BaseGrid`，含键盘快捷键、撤销/重做、复制/粘贴 |
| `tfp_toolkit.tfp_auth` | 认证辅助：`is_user_logged_in()`、`has_permission()`、`is_premium_user()` |
| `tfp_toolkit.tfp_constants` | 常量：工具类型、支持的语言及其他默认值 |

### 12.2 使用 Grid 基类

使用 wx.grid.Grid 的工具可继承 `TFP_BaseGrid`：

```python
from tfp_toolkit.tfp_base_grid import TFP_BaseGrid

class MyGrid(TFP_BaseGrid):
    MAX_UNDO = 20  # 自定义撤销栈大小

    def __init__(self, parent, **kwargs):
        kwargs.setdefault('max_undo', self.MAX_UNDO)
        super().__init__(parent, **kwargs)
```

`TFP_BaseGrid` 提供：Delete/Ctrl+C/V/A/Z/Y、复制/粘贴（兼容Excel）、撤销/重做、右键菜单、只读模式，以及钩子方法（`on_cells_cleared`、`on_cells_pasted`、`on_rows_added`、`on_rows_deleted`）。

### 12.3 脚手架生成器

| 生成器 | 位置 | 用法 |
|--------|------|------|
| BuiltinProgram | `tools_fe/scaffold_builtin.py` | `python scaffold_builtin.py <ident> <title_zh> <title_en>` |

---

> **文档版本**: 5.1.0
> **最后更新**: 2026-10-12
