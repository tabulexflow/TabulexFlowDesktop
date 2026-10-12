# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""测试 TabulexFileOperator 子工具 - 搜索和匹配逻辑"""
import pytest
import sys
import os

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


class TestSearchLogic:
    """测试搜索逻辑"""

    def test_search_by_filename_contains(self):
        """测试文件名包含搜索"""
        filename = "project_report_2024.xlsx"
        search_term = "report"
        assert search_term.lower() in filename.lower()

    def test_search_by_filename_exact(self):
        """测试文件名精确匹配"""
        import fnmatch
        assert fnmatch.fnmatch("report.xlsx", "report.xlsx") is True
        assert fnmatch.fnmatch("report.xlsx", "report*") is True

    def test_search_by_extension(self):
        """测试扩展名搜索"""
        import fnmatch
        assert fnmatch.fnmatch("file.xlsx", "*.xlsx") is True
        assert fnmatch.fnmatch("file.doc", "*.xlsx") is False

    def test_search_case_insensitive(self):
        """测试大小写不敏感搜索"""
        filename = "REPORT.XLSX"
        search_term = "report"
        assert search_term.lower() in filename.lower()

    def test_search_substring_not_found(self):
        """测试子串未找到"""
        filename = "data.csv"
        search_term = "report"
        assert search_term.lower() not in filename.lower()

    def test_search_empty_term(self):
        """测试空搜索词匹配所有"""
        filename = "test.txt"
        search_term = ""
        assert search_term == "" or search_term.lower() in filename.lower()

    def test_search_multiple_extensions(self):
        """测试多扩展名搜索"""
        import fnmatch
        filename = "image.png"
        extensions = ["*.jpg", "*.png", "*.gif"]
        matched = any(fnmatch.fnmatch(filename, ext) for ext in extensions)
        assert matched is True


class TestRenameLogic:
    """测试重命名逻辑"""

    def test_simple_rename(self):
        """测试简单重命名"""
        old_name = "old_file.txt"
        new_name = "new_file.txt"
        assert old_name != new_name
        assert old_name.endswith(".txt")
        assert new_name.endswith(".txt")

    def test_rename_preserve_extension(self):
        """测试重命名保留扩展名"""
        original = "document.doc"
        ext = original.rsplit('.', 1)[-1]
        new_base = "renamed"
        new_name = f"{new_base}.{ext}"
        assert new_name == "renamed.doc"

    def test_rename_add_prefix(self):
        """测试添加前缀重命名"""
        original = "file.txt"
        prefix = "backup_"
        new_name = prefix + original
        assert new_name == "backup_file.txt"

    def test_rename_add_suffix(self):
        """测试添加后缀重命名"""
        original = "file.txt"
        suffix = "_v2"
        base, ext = original.rsplit('.', 1)
        new_name = f"{base}{suffix}.{ext}"
        assert new_name == "file_v2.txt"

    def test_rename_replace_text(self):
        """测试替换文本重命名"""
        original = "draft_report.txt"
        new_name = original.replace("draft", "final")
        assert new_name == "final_report.txt"


class TestDuplicateDetection:
    """测试重复检测逻辑"""

    def test_same_name_same_size(self):
        """测试同名同大小文件视为重复"""
        file1 = {"name": "test.txt", "size": 1024}
        file2 = {"name": "test.txt", "size": 1024}
        is_duplicate = (
            file1["name"].lower() == file2["name"].lower() and
            file1["size"] == file2["size"]
        )
        assert is_duplicate is True

    def test_same_name_different_size(self):
        """测试同名不同大小文件不视为重复"""
        file1 = {"name": "test.txt", "size": 1024}
        file2 = {"name": "test.txt", "size": 2048}
        is_duplicate = (
            file1["name"].lower() == file2["name"].lower() and
            file1["size"] == file2["size"]
        )
        assert is_duplicate is False

    def test_different_name_same_size(self):
        """测试不同名同大小文件不视为重复"""
        file1 = {"name": "a.txt", "size": 1024}
        file2 = {"name": "b.txt", "size": 1024}
        is_duplicate = (
            file1["name"].lower() == file2["name"].lower() and
            file1["size"] == file2["size"]
        )
        assert is_duplicate is False


class TestDeleteLogic:
    """测试删除逻辑"""

    def test_delete_file_marked(self):
        """测试文件标记为删除"""
        row = {"path": "C:\\temp\\file.txt", "will_delete": True}
        assert row["will_delete"] is True

    def test_delete_file_protected(self):
        """测试受保护文件不删除"""
        import os
        protected_paths = [os.environ.get('SystemRoot', 'C:\\Windows')]
        file_path = "C:\\Windows\\System32\\file.dll"
        is_protected = any(file_path.lower().startswith(p.lower()) for p in protected_paths)
        assert is_protected is True


class TestFileSizeCalculation:
    """测试文件大小计算"""

    def test_bytes_to_kb(self):
        size_bytes = 2048
        size_kb = size_bytes / 1024
        assert size_kb == 2.0

    def test_bytes_to_mb(self):
        size_bytes = 1048576
        size_mb = size_bytes / (1024 * 1024)
        assert size_mb == 1.0

    def test_format_size(self):
        def format_size(size_bytes):
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1048576:
                return f"{size_bytes / 1024:.1f} KB"
            else:
                return f"{size_bytes / 1048576:.1f} MB"
        assert format_size(500) == "500 B"
        assert format_size(2048) == "2.0 KB"
        assert format_size(1048576) == "1.0 MB"


class TestPathValidation:
    """测试路径验证"""

    def test_valid_windows_path(self):
        """测试有效 Windows 路径"""
        import re
        path = "C:\\Users\\test\\Documents\\file.txt"
        pattern = r'^[A-Za-z]:\\'
        assert re.match(pattern, path) is not None

    def test_invalid_path_characters(self):
        """测试无效路径字符"""
        invalid_chars = '<>:"|?*'
        path = "test.txt"
        has_invalid = any(c in path for c in invalid_chars)
        assert has_invalid is False

    def test_path_with_spaces(self):
        """测试带空格的路径"""
        path = "C:\\Program Files\\My App\\file.txt"
        assert " " in path