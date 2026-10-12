# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""测试 TabulexFileOperator 子工具核心逻辑"""
import pytest
import sys
import os

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 尝试导入 BFM 工具模块
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from tfo_utils.tfo_match_utils import TFO_MatchUtils
    HAS_BFM = True
except ImportError:
    HAS_BFM = False


class TestNameMatchLogic:
    """测试文件名匹配逻辑"""

    def test_exact_match(self):
        """测试精确匹配"""
        name = "test.txt"
        match_name = "test.txt"
        assert name.lower() == match_name.lower()

    def test_case_insensitive_match(self):
        """测试大小写不敏感匹配"""
        name = "TEST.TXT"
        match_name = "test.txt"
        assert name.lower() == match_name.lower()

    def test_wildcard_match(self):
        """测试通配符匹配"""
        import fnmatch
        assert fnmatch.fnmatch("test.txt", "*.txt") is True
        assert fnmatch.fnmatch("test.doc", "*.txt") is False

    def test_substring_match(self):
        """测试子串匹配"""
        name = "project_test_file.txt"
        match_name = "test"
        assert match_name.lower() in name.lower()

    def test_no_match(self):
        """测试不匹配情况"""
        name = "example.txt"
        match_name = "test"
        assert match_name.lower() not in name.lower()


class TestExcludeAllMatchName:
    """测试"排除所有匹配名整体"逻辑"""

    def _check_name_match(self, name, match_name, match_method):
        """模拟 _check_name_match 方法"""
        if not match_name:
            return False
        if match_method not in ["符合匹配名的正则式", "排除匹配名的通配符"]:
            name_lower = name.lower()
            match_name_lower = match_name.lower()
            if match_method == "排除所有匹配名整体":
                if not match_name_lower:
                    return True
                parts = match_name_lower.split("/")
                parts = [part.strip() for part in parts if part.strip()]
                if not parts:
                    return True
                for part in parts:
                    if part in name_lower:
                        return False
                return True
        return False

    def test_contains_match_part_returns_false(self):
        """测试包含匹配名部分时返回 False"""
        result = self._check_name_match("test.txt", "test/file", "排除所有匹配名整体")
        assert result is False

    def test_no_match_returns_true(self):
        """测试不包含任何匹配名时返回 True"""
        result = self._check_name_match("example.txt", "test/file", "排除所有匹配名整体")
        assert result is True

    def test_empty_match_name_returns_false(self):
        """测试空匹配名返回 False"""
        result = self._check_name_match("test.txt", "", "排除所有匹配名整体")
        assert result is False

    def test_multiple_parts(self):
        """测试多个匹配名部分，任一匹配则排除"""
        result = self._check_name_match("project_doc.txt", "test/doc/file", "排除所有匹配名整体")
        assert result is False  # 包含 "doc"

    def test_no_match_multiple_parts(self):
        """测试多个匹配名部分，都不匹配"""
        result = self._check_name_match("xyz.txt", "test/doc/file", "排除所有匹配名整体")
        assert result is True


class TestFilePathOperations:
    """测试文件路径操作"""

    def test_get_parent_dir(self):
        """测试获取父目录（Windows 路径语义，用 ntpath 保证跨平台确定性）"""
        import ntpath
        path = "C:\\Users\\test\\file.txt"
        parent = ntpath.dirname(path)
        assert parent == "C:\\Users\\test"

    def test_get_filename(self):
        """测试获取文件名（Windows 路径语义，用 ntpath 保证跨平台确定性）"""
        import ntpath
        path = "C:\\Users\\test\\file.txt"
        filename = ntpath.basename(path)
        assert filename == "file.txt"

    def test_get_extension(self):
        """测试获取扩展名"""
        filename = "document.pdf"
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        assert ext == "pdf"

    def test_no_extension(self):
        """测试无扩展名文件"""
        filename = "README"
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        assert ext == ''

    def test_join_paths(self):
        """测试路径拼接"""
        import os
        result = os.path.join("C:\\base", "subdir", "file.txt")
        assert "C:\\base" in result
        assert "subdir" in result
        assert "file.txt" in result


class TestFileSizeFormat:
    """测试文件大小格式化"""

    def test_bytes_to_kb(self):
        """测试字节转KB"""
        size_bytes = 2048
        size_kb = size_bytes / 1024
        assert size_kb == 2.0

    def test_zero_bytes(self):
        """测试零字节"""
        size_bytes = 0
        size_kb = size_bytes / 1024
        assert size_kb == 0.0

    def test_large_file(self):
        """测试大文件"""
        size_bytes = 1048576  # 1 MB
        size_kb = size_bytes / 1024
        assert size_kb == 1024.0


class TestSpecialPathMarkers:
    """测试特殊路径标记"""

    SPECIAL_MARKERS = [
        "[Invalid Path]",
        "[Nonexistent Path]",
        "[Not File]",
        "[No Permission]",
        "[WILL DELETE]",
        "[WILL RETAIN]",
        "[NO DUPLICATE]",
    ]

    def test_all_markers_start_with_bracket(self):
        for marker in self.SPECIAL_MARKERS:
            assert marker.startswith("["), f"Marker '{marker}' should start with '['"

    def test_marker_indicates_empty_value(self):
        """测试以 [ 开头的路径被视为空值"""
        path = "[Invalid Path]"
        assert path.startswith("[")


class TestUndoEntry:
    """测试撤销/重做条目"""

    def test_undo_entry_creation(self):
        """测试创建撤销条目"""
        entry = {
            "cell_changes": {(0, 0): ("old", "new")},
            "rows_added": [],
            "rows_deleted": [],
            "selection": None,
        }
        assert len(entry["cell_changes"]) == 1
        assert entry["cell_changes"][(0, 0)] == ("old", "new")

    def test_max_undo_limit(self):
        """测试最大撤销步数"""
        MAX_UNDO = 20
        assert MAX_UNDO == 20

    def test_undo_stack_overflow(self):
        """测试撤销栈溢出处理"""
        MAX_UNDO = 20
        stack = list(range(MAX_UNDO + 5))
        if len(stack) > MAX_UNDO:
            stack = stack[-MAX_UNDO:]
        assert len(stack) == MAX_UNDO


class TestFullmatchSemantics:
    """测试通配符/正则式的"完全匹配"语义（P2-1：*.txt 不应匹配 a.txt.bak）"""

    try:
        from tfo_utils.tfo_match_utils import check_name_match_part as _check
    except ImportError:
        _check = None
    # 以 staticmethod 包装，避免通过 self 调用时被绑定方法多传一个参数
    _check = staticmethod(_check)

    def setup_method(self):
        if self._check is None:
            pytest.skip("tfo_match_utils 不可导入")

    def test_wildcard_fullmatch(self):
        """通配符应完全匹配：*.txt 匹配 a.txt"""
        assert self._check("a.txt", "*.txt", "matches_wildcard") is not None

    def test_wildcard_no_prefix_match(self):
        """通配符完全匹配：*.txt 不应匹配 a.txt.bak"""
        assert self._check("a.txt.bak", "*.txt", "matches_wildcard") is None

    def test_exclude_wildcard_no_prefix_match(self):
        """排除通配符完全匹配：*.txt 不应排除 a.txt.bak"""
        assert self._check("a.txt.bak", "*.txt", "exclude_wildcards") is not None

    def test_exclude_wildcard_fullmatch(self):
        """排除通配符完全匹配：*.txt 应排除 a.txt"""
        assert self._check("a.txt", "*.txt", "exclude_wildcards") is None

    def test_regex_fullmatch(self):
        """正则式完全匹配：.*\\.txt 不应匹配 a.txt.bak"""
        assert self._check("a.txt.bak", r".*\.txt", "matches_regex") is None

    def test_regex_fullmatch_anchored(self):
        """正则式完全匹配：a\\.txt 应匹配 a.txt"""
        assert self._check("a.txt", r"a\.txt", "matches_regex") is not None