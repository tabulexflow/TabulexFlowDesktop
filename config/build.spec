# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later
# -*- mode: python ; coding: utf-8 -*-
import os
import re
import sys
import tempfile
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_all

spec_file_path = sys.argv[0] if len(sys.argv) > 0 else __file__
spec_dir = os.path.dirname(os.path.abspath(spec_file_path))
project_root = os.path.dirname(spec_dir)

# ===== Linux 构建启用 strip（体积优化，2026-10）=====
# Linux 构建环境的 wxPython 为源码编译且未 strip，扩展模块带大量 .debug_* 调试符号
# （实测 wx/_core.cpython-312...so 解压后约 195MB，strip 后约 13MB），PyInstaller 默认
# 不 strip 会把符号原样打包（Linux 单文件产物因此达 ~300MB，而 Windows 仅 ~68MB）。
# Linux 下开启 strip，由 PyInstaller 调用系统 strip 命令剔除符号；Windows 下 strip 不适用
# （PyInstaller 官方不推荐在 Windows 使用 strip），保持关闭。
_strip_binaries = (sys.platform == 'linux')
print(f"[spec] strip binaries: {_strip_binaries}")

# ===== 社区发布版（OSS）判断 =====
# tfpdesktop_build 编译前会将 build_mode.IS_OSS_COMMUNITY_BUILD 临时置 True（见 build_mode.py 注释）。
# OSS 社区版不含远程/网页工具，因此**不打包** RemoteWebpage 回退引擎（PyWebView + PyGObject/WebKitGTK），
# 可省去数百 MB 体积。
_is_oss = False
_build_mode_path = os.path.join(project_root, 'build_mode.py')
try:
    with open(_build_mode_path, 'r', encoding='utf-8') as _f:
        _bmtxt = _f.read()
    _is_oss = re.search(r'^\s*IS_OSS_COMMUNITY_BUILD\s*=\s*True\s*$', _bmtxt, re.MULTILINE) is not None
except Exception:
    _is_oss = False
print(f"[spec] IS_OSS_COMMUNITY_BUILD={_is_oss} -> RemoteWebpage fallback engine {'SKIPPED (not bundled)' if _is_oss else 'collected'}")

wx_hiddenimports = collect_submodules('wx')
# OSS 社区版不含 RemoteWebpage（wx.html2 仅被该工具使用），排除 wx.html2 子模块：
# 其链接的系统 libwebkit2gtk 等会被 gtk hook 连带打进产物（约 40MB+）。OSS 版运行时
# main.py / tfp_tool_runner_mixin.py 对 `import wx.html2` 已是可选导入（失败置 None），
# 排除后行为与"系统 wxPython 无 html2 子模块"一致，功能不受影响。
if _is_oss:
    _wx_before = len(wx_hiddenimports)
    wx_hiddenimports = [m for m in wx_hiddenimports if m != 'wx.html2']
    print(f"[spec] OSS: excluded wx.html2 from hiddenimports ({_wx_before} -> {len(wx_hiddenimports)})")
print(f"Collected {len(wx_hiddenimports)} wx submodules for hiddenimports")


# ===== BuiltinProgram 打包模型（重要，勿改）=====
# 1) 工具代码本身（如 TabulexDocCreator/tool_main.py）作为 **datas 明文分发**（见 datas_list），
#    运行时由 tfp_mixins/tfp_tool_runner_mixin.py 经 importlib.util.spec_from_file_location
#    动态加载 —— 不编译进 PYZ 归档（AGPL 开源，明文分发是特性）。
# 2) 工具的第三方依赖（fitz/PyMuPDF、numpy、docx、pptx、PIL、xlrd、mutagen、send2trash、
#    regex 等）通过下方 hiddenimports **编译打包进二进制**。
#    注意：PyMuPDF 1.24+ 包名已改为 pymupdf（fitz 仅为兼容别名），且 PYZ 为 zlib 压缩，
#    用 strings 扫描单文件二进制看不到纯 Python 模块名 —— 不要据此误判依赖未打包。
#    合规要求：这些依赖必须全部在 docs/NOTICE.txt 中披露（见 NOTICE "TabulexDocCreator
#    Dependencies" 章节，其中 PyMuPDF 为 AGPL-3.0）。

# Linux RemoteWebpage 回退引擎：pywebview（GTK WebKit2）+ PyGObject（gi）
# 仅当构建环境安装了这些依赖时才收集（Windows 构建无 gi/pywebview，不受影响）
# OSS 社区版直接跳过，避免把 WebKitGTK/GTK3 及其依赖链打进包
gi_datas, gi_binaries, gi_hiddenimports = [], [], []
webview_hiddenimports = []
if not _is_oss:
    try:
        gi_datas, gi_binaries, gi_hiddenimports = collect_all('gi')
        print(f"Collected gi: {len(gi_datas)} datas, {len(gi_binaries)} binaries, {len(gi_hiddenimports)} hiddenimports")
    except Exception as e:
        gi_datas, gi_binaries, gi_hiddenimports = [], [], []
        print(f"gi not collected (skip): {e}")

    try:
        webview_hiddenimports = collect_submodules('webview')
        _extra_web_hiddenimports = ['webview', 'webview.platforms.gtk']
        print(f"Collected {len(webview_hiddenimports)} webview submodules")
    except Exception as e:
        webview_hiddenimports = []
        _extra_web_hiddenimports = []
        print(f"webview not collected (skip): {e}")
else:
    _extra_web_hiddenimports = []

datas_list = [
    (os.path.join(project_root, 'tools_fe', 'tools_builtin_program'), 'tools_fe/tools_builtin_program'),
    (os.path.join(project_root, 'tfp_utils'), 'tfp_utils'),
    (os.path.join(project_root, 'config', 'tool_list_builtin.json'), 'config'),
    (os.path.join(project_root, 'config', 'language_settings.json'), 'config'),
    (os.path.join(project_root, 'config', 'default_icon.ico'), 'config'),
    (os.path.join(project_root, 'app_icon.ico'), '.'),
    (os.path.join(project_root, 'locales'), 'locales'),
    # version.txt 必须放到 config/：main.py::_read_frontend_version_from_file() 读取
    # base_path/config/version.txt（base_path 在冻结模式为 sys._MEIPASS）。此前放在 '.'
    # 导致冻结产物读不到版本文件、静默回退 "1.0.0"（2026-10 修复）。
    (os.path.join(spec_dir, 'version.txt'), 'config'),
    # ===== OSS 合规（AGPL §5(a) Object Form / §6 第三方声明，M-6）=====
    # 许可证与第三方声明文件必须随二进制分发，并可在 Help -> About 对话框中查看
    (os.path.join(project_root, 'LICENSE.txt'), '.'),
    (os.path.join(project_root, 'docs', 'NOTICE.txt'), 'docs'),
    (os.path.join(project_root, 'docs', 'CLA.md'), 'docs'),
    (os.path.join(project_root, 'docs', 'CONTRIBUTING.md'), 'docs'),
]

# Include _build_target.py if it exists (written by tfpdesktop_build.bat before packaging)
_build_target_file = os.path.join(project_root, '_build_target.py')
if os.path.exists(_build_target_file):
    datas_list.append((_build_target_file, '.'))
    print(f"Including build target marker: {_build_target_file}")

builtin_tools_dir = os.path.join(project_root, 'tools_fe', 'tools_builtin_program')
if os.path.exists(builtin_tools_dir):
    for tool_dir in os.listdir(builtin_tools_dir):
        tool_locales_dir = os.path.join(builtin_tools_dir, tool_dir, 'locales')
        if os.path.isdir(tool_locales_dir):
            for lang_file in os.listdir(tool_locales_dir):
                if lang_file.endswith('.json'):
                    source = os.path.join(tool_locales_dir, lang_file)
                    dest = os.path.join('tools_fe', 'tools_builtin_program', tool_dir, 'locales')
                    datas_list.append((source, dest))
                    print(f"Adding locale: {source} -> {dest}")

print(f"Total datas_list entries: {len(datas_list)}")

def read_default_tool():
    main_py_path = os.path.join(project_root, 'main.py')
    with open(main_py_path, 'r', encoding='utf-8') as f:
        content = f.read()
    match = re.search(r'DEFAULT_TOOL\s*=\s*["\']([^"\']*)["\']', content)
    if match:
        value = match.group(1)
        return value if value else "main"
    return "main"

def get_exe_config():
    default_tool = read_default_tool()
    if default_tool == "main":
        return {
            'name': 'TabulexFlow',
            'icon': os.path.join(project_root, 'app_icon.ico')
        }
    tool_icon_path = os.path.join(project_root, 'tools_fe', 'tools_builtin_program', default_tool, 'app_icon.ico')
    if not os.path.exists(tool_icon_path):
        tool_icon_path = os.path.join(project_root, 'app_icon.ico')
    return {
        'name': default_tool,
        'icon': tool_icon_path
    }

exe_config = get_exe_config()
# 最终产物名由构建脚本经环境变量传入（形如 <Base>-<版本>-<OSS|Full>[-devtest]），
# 使 PyInstaller 直接产出带版本+形态的文件名，避免构建后重命名（见 tfpdesktop_build.bat/.sh）。
# 未设置时回退默认名，兼容手工直接运行 pyinstaller 的场景。
_tfp_exe_name = os.environ.get('TFP_EXE_NAME', '').strip()
if _tfp_exe_name:
    exe_config['name'] = _tfp_exe_name
print(f"Build config: exe name={exe_config['name']}, icon={exe_config['icon']}")


def derive_version_resource(src_path, exe_name):
    """从 config/version.txt 派生临时版本资源：仅把 OriginalFilename 换成实际产物名。

    config/version.txt 是版本单一来源，但其 OriginalFilename 是固定值；Windows 资源中的
    OriginalFilename 应与实际文件名一致，故构建期派生一份临时文件（其余字段含 ProductVersion
    保持不变）。该临时文件同时用于 EXE 的 version= 资源与打包数据，保证资源与运行时文件一致。
    派生失败（未找到字段）时回退原始文件路径。
    """
    with open(src_path, 'r', encoding='utf-8') as f:
        text = f.read()
    actual_name = f"{exe_name}.exe"
    new_text, count = re.subn(
        r"(StringStruct\(u?'OriginalFilename',\s*u?')[^']*('\))",
        lambda m: m.group(1) + actual_name + m.group(2),
        text,
    )
    if count == 0:
        print("[spec] WARN: OriginalFilename not found in version.txt; using original file")
        return src_path
    fd, tmp_path = tempfile.mkstemp(prefix='tfp_version_', suffix='.txt')
    with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
        f.write(new_text)
    print(f"[spec] Version resource OriginalFilename -> {actual_name}")
    return tmp_path


_version_txt_src = os.path.join(spec_dir, 'version.txt')
_version_resource_path = derive_version_resource(_version_txt_src, exe_config['name'])

# 派生成功（临时文件）时替换 datas_list 中的 version.txt 条目，使随包文件与资源一致
if _version_resource_path != _version_txt_src:
    datas_list = [
        (_version_resource_path, dest) if src == _version_txt_src and dest == 'config' else (src, dest)
        for (src, dest) in datas_list
    ]

block_cipher = None

a = Analysis(
    [os.path.join(project_root, 'main.py')],
    pathex=[project_root],
    binaries=gi_binaries,
    datas=datas_list + gi_datas,
    hiddenimports=[
        *wx_hiddenimports,
        'importlib.util', 'pathlib', 'requests', 'json',
        'zipfile', 'subprocess', 'tempfile', 'shutil',
        'threading', 'importlib.resources',
        'os', 'sys', 'datetime', 'hashlib', 're',
        'collections', 'itertools', 'charset_normalizer',
        'openpyxl', 'openpyxl.styles', 'openpyxl.utils',
        'fitz', 'PIL', 'PIL.Image',
        'tfp_utils', 'tfp_utils.tfp_main_utils', 'tfp_utils.tfp_i18n_manager',
        'tfp_utils.tfp_webview_helper', 'tfp_utils.tfp_webview_fallback',
        'regex',
        'mutagen', 'mutagen.mp3', 'mutagen.id3',
        'send2trash',
        'py7zr', 'py7zr.helpers', 'py7zr.compressor', 'py7zr.decompressor',
        'py7zr.py7zr', 'py7zr.properties', 'py7zr.exceptions', 'py7zr.callbacks',
        'py7zr.compressor', 'py7zr.decompressor', 'py7zr.presets',
        'py7zr.archiveinfo', 'py7zr.utils', 'py7zr.worker',
        'pycryptodomex', 'pyppmd', 'pybcj', 'multivolumefile', 'texttable',
        'keyring', 'keyring.errors',
        'docx', 'docx.shared',
        'pptx', 'pptx.util',
        'xlrd',
        'pkg_resources',
        'platformdirs',
        'importlib_resources',
        'more_itertools',
        'jaraco.context', 'jaraco.functools', 'jaraco.classes',
        '_build_target',
        *gi_hiddenimports,
        *webview_hiddenimports,
        'webview', 'webview.platforms.gtk',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pythoncom', 'pywin32', 'win32com', 'win32api',
        'win32con', 'win32gui', 'win32pipe', 'win32process',
        'onnxruntime',
        'onnxruntime.tools', 'onnxruntime.test', 'onnxruntime.transformers',
        'onnxruntime.capi.onnxruntime_pybind11_state',
        'torch', 'tensorflow', 'keras', 'paddle',
        'cuda', 'cudnn', 'tensorrt', 'nvidia',
        'pandas', 'pygraphviz', 'pydot', 'joblib',
        'scipy', 'scipy.sparse', 'sklearn', 'matplotlib',
        # 体积瘦身（2026-09-07）：运行时不可达/无关依赖，排除后不损失功能
        # numpy：唯一引用在 tdc_PDFWorker._detect_frame_opencv，被 import cv2 门控，
        #   而 cv2(OpenCV) 未安装 → 运行时不加载 numpy（实测无其他 numpy 引用）
        # zstandard：仅 Nuitka onefile 压缩器引用（不属于前端产物）
        # gevent/greenlet：仅 gunicorn worker 与 Nuitka 插件引用（均不在前端产物）
        'numpy', 'zstandard', 'gevent', 'greenlet', 'gunicorn', 'nuitka',
    ] + (['gi', 'webview', 'pywebview', 'wx.html2'] if _is_oss else []),
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ===== 开源产物洁净（OSC-07）：剔除内置工具目录下的测试/字节码/日志 =====
# datas 以整目录收集 tools_fe/tools_builtin_program，会把 test/、__pycache__/*.pyc、
# logs/ 等非运行时内容一并打包；此处统一剔除，保证公开产物只含工具运行所需代码。
_TOOLS_DATA_PREFIX = 'tools_fe/tools_builtin_program/'
_tools_datas_kept, _tools_datas_dropped = [], []
for _item in a.datas:
    _dest = _item[0]
    if _dest.startswith(_TOOLS_DATA_PREFIX) and (
        '/test/' in _dest
        or '/__pycache__/' in _dest
        or '/logs/' in _dest
        or _dest.endswith(('.pyc', '.pyo'))
    ):
        _tools_datas_dropped.append(_dest)
    else:
        _tools_datas_kept.append(_item)
if _tools_datas_dropped:
    a.datas = _tools_datas_kept
    print(f"[spec] Dropped {len(_tools_datas_dropped)} non-runtime builtin-tool entries "
          f"(test/__pycache__/logs/*.pyc)")

# ===== 体积优化（v5.x，2026-09-07；OSS 版扩展 2026-10）：剔除系统级 WebView C 库 =====
# 打包时 PyInstaller 的 gi / gtk hook 会把构建机**整套系统** WebKitGTK / JavaScriptCore /
# GStreamer 共享库及其依赖链打进单文件二进制（Full 版产物可达 ~525MB）：
#   - Full 版：gi hook 收集 PyWebView + PyGObject(WebKitGTK) 回退引擎的依赖链；
#   - OSS 版：wxPython 的 wx.html2 链接的系统 libwebkit2gtk 等（OSS 不含 RemoteWebpage）。
# 这些 C 库**运行时从目标机系统加载**（如 Ubuntu 24.04 预装 libwebkit2gtk-4.1-0 +
# gir1.2-webkit2-4.1），无需打包进产物，仅保留 gi 纯 Python 绑定 / typelibs / pywebview。
# 注意：仅剔除 WebKit/JS/GStreamer/WPE/Soup 链；wxPython 自带的 GTK3 库
# （libgtk-3/libcairo/libglib 等）与 ICU（libxml2/lxml 依赖）是运行时必需，绝不在此过滤。
import fnmatch as _fnmatch
_SYSTEM_WEBVIEW_LIBS = (
    # WebKitGTK 渲染引擎 + JavaScriptCore JS 引擎（单文件 ~121MB）
    'libwebkit2gtk-*.so*', 'libjavascriptcoregtk-*.so*',
    # GStreamer 媒体播放链（WebKit 依赖）：核心库 + 全部插件。
    # 注意：Gst hook 把插件统一收集到 dest 目录 `gst_plugins/`，因此需单独匹配该目录
    'libgstreamer-1.0.so*', 'libgst*-1.0.so*', 'libgst*.so*',
    'gst_plugins/*',
    # WPE / Soup / Enchant（WebKit 的绘制后端、HTTP 栈、拼写检查）
    'libwpe*.so*', 'libsoup*.so*', 'libenchant*.so*',
)
_orig_binaries = list(a.binaries)
_kept, _dropped = [], []
for _item in _orig_binaries:
    _dest = _item[0]
    if any(_fnmatch.fnmatch(_dest, _pat) for _pat in _SYSTEM_WEBVIEW_LIBS):
        _dropped.append(_dest)
    else:
        _kept.append(_item)
if _dropped:
    a.binaries = _kept
    _dropped_bytes = 0
    for _it in _orig_binaries:
        if any(_fnmatch.fnmatch(_it[0], _p) for _p in _SYSTEM_WEBVIEW_LIBS):
            try:
                _dropped_bytes += os.path.getsize(_it[1])
            except OSError:
                pass
    print(f"[spec] Dropped {len(_dropped)} system WebView/GStreamer libs "
          f"(~{_dropped_bytes / 1048576:.0f} MB), loaded from system at runtime:")
    for _d in sorted(set(_dropped)):
        print(f"  - {_d}")
else:
    print("[spec] No system WebView/GStreamer libs found to drop")

# ===== 体积优化（v5.x，2026-09-07）：剔除 gi hook 收集的系统 GLib 数据（share/）=====
# gi/GTK hook 会通过 collect_glib_share_files('icons') 等把构建机**整套系统图标/
# 光标主题**（Bibata/Papirus/Mint-Y/Yaru 等，实测 ~338MB、27 万个文件）连同
# share/glib-2.0/schemas、share/gstreamer-1.0 等数据一并收进产物。这些同样是
# 目标机系统 GTK 自带的数据（运行时从系统加载），打包纯属体积浪费。
# 本项目自有 datas（tools_fe/tfp_utils/config/locales/docs/LICENSE 等）均不带
# `share/` 前缀，因此按 dest 前缀剔除 share/ 是安全的。
_orig_datas = list(a.datas)
_kept_datas, _dropped_datas = [], []
for _item in _orig_datas:
    _dest = _item[0]
    if _dest.startswith('share/'):
        _dropped_datas.append(_dest)
    else:
        _kept_datas.append(_item)
if _dropped_datas:
    a.datas = _kept_datas
    _dropped_data_bytes = 0
    for _it in _orig_datas:
        if _it[0].startswith('share/'):
            try:
                _dropped_data_bytes += os.path.getsize(_it[1])
            except OSError:
                pass
    print(f"[spec] Dropped {len(_dropped_datas)} system GLib shared data files "
          f"(~{_dropped_data_bytes / 1048576:.0f} MB), loaded from system at runtime")
else:
    print("[spec] No system GLib shared data files (share/) found to drop")

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Support onefile (default) or onedir mode via TFP_PACKAGE_MODE env var
# TFP_PACKAGE_MODE=onedir -> directory mode (faster startup, easier incremental update)
# TFP_PACKAGE_MODE=onefile or unset -> single-file mode (default, easier distribution)
package_mode = os.environ.get('TFP_PACKAGE_MODE', 'onefile')

if package_mode == 'onedir':
    # Directory mode: EXE + dependencies in a folder
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=exe_config['name'],
        debug=False,
        bootloader_ignore_signals=False,
        strip=_strip_binaries,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=exe_config['icon'],
        version=_version_resource_path,
        manifest=os.path.join(spec_dir, 'app.manifest'),
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=_strip_binaries,
        upx=True,
        upx_exclude=[],
        name=exe_config['name'],
    )
else:
    # Single-file mode (default): everything packed into one EXE
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name=exe_config['name'],
        debug=False,
        bootloader_ignore_signals=False,
        strip=_strip_binaries,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=exe_config['icon'],
        version=_version_resource_path,
        manifest=os.path.join(spec_dir, 'app.manifest'),
    )

# 清理临时版本资源文件（仅在派生成功时存在；此时已被 EXE/datas 消费完毕）
if _version_resource_path != _version_txt_src:
    try:
        os.remove(_version_resource_path)
    except OSError:
        pass
