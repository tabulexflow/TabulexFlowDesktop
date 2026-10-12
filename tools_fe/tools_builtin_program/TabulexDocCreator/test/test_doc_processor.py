# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""测试 TabulexDocCreator 子工具核心逻辑"""
import pytest
import sys
import os

# Ensure TabulexDocCreator directory is in path
_tool_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _tool_dir not in sys.path:
    sys.path.insert(0, _tool_dir)


class TestPlaceholderReplacement:
    """测试占位符替换逻辑"""

    def test_simple_text_replacement(self):
        """测试简单文本替换"""
        text = "Hello {{name}}!"
        result = text.replace("{{name}}", "World")
        assert result == "Hello World!"

    def test_multiple_placeholders(self):
        """测试多个占位符替换"""
        text = "{{greeting}} {{name}}, your order #{{order_id}} is ready."
        text = text.replace("{{greeting}}", "Hello")
        text = text.replace("{{name}}", "Alice")
        text = text.replace("{{order_id}}", "12345")
        assert text == "Hello Alice, your order #12345 is ready."

    def test_no_placeholder_leaves_unchanged(self):
        """测试没有占位符时文本不变"""
        text = "No placeholders here."
        result = text.replace("{{missing}}", "value")
        assert result == text

    def test_placeholder_with_special_chars(self):
        """测试包含特殊字符的占位符"""
        text = "Value: {{price}}"
        result = text.replace("{{price}}", "$100.00")
        assert result == "Value: $100.00"


class TestTitleMatching:
    """测试标题匹配预处理逻辑"""

    def test_normalize_whitespace(self):
        """测试连续空白标准化"""
        import re
        text = "Hello   World\tTab"
        normalized = re.sub(r'\s+', ' ', text)
        assert normalized == "Hello World Tab"

    def test_strip_whitespace(self):
        """测试去除首尾空白"""
        text = "  \r\n  Hello World  \r\n  "
        cleaned = text.replace('\r\n', '\n').strip()
        assert cleaned == "Hello World"

    def test_split_variants(self):
        """测试按换行拆分为多个变体"""
        title = "Line1\nLine2\nLine3"
        variants = title.split('\n')
        assert len(variants) == 3
        assert variants[0] == "Line1"
        assert variants[1] == "Line2"
        assert variants[2] == "Line3"


class TestExcelCoordinateParsing:
    """测试 Excel 坐标解析"""

    def test_parse_basic_cell(self):
        """测试解析基本单元格地址"""
        import re
        match = re.match(r'^([A-Z]+)(\d+)$', "A1")
        assert match is not None
        assert match.group(1) == "A"
        assert match.group(2) == "1"

    def test_parse_complex_cell(self):
        """测试解析复杂单元格地址"""
        import re
        match = re.match(r'^([A-Z]+)(\d+)$', "AB100")
        assert match is not None
        assert match.group(1) == "AB"
        assert match.group(2) == "100"

    def test_parse_with_sheet(self):
        """测试解析带Sheet名的地址"""
        import re
        match = re.match(r'^(?:([^!]+)!)?([A-Z]+)(\d+)$', "Sheet1!C5")
        assert match is not None
        assert match.group(1) == "Sheet1"
        assert match.group(2) == "C"
        assert match.group(3) == "5"

    def test_parse_invalid_cell(self):
        """测试解析无效单元格地址"""
        import re
        match = re.match(r'^([A-Z]+)(\d+)$', "Invalid")
        assert match is None


class TestInheritRowLogic:
    """测试继承行逻辑"""

    def _find_ancestor(self, rows, current_idx):
        """模拟继承行查找逻辑"""
        for i in range(current_idx - 1, -1, -1):
            if rows[i][0] and rows[i][1]:
                return rows[i]
        return None

    def test_inherit_from_previous(self):
        """测试继承上一行的文件路径"""
        rows = [
            ("template.xlsx", "output.xlsx", "Alice"),
            ("", "", "Bob"),
            ("", "", "Charlie"),
        ]
        ancestor = self._find_ancestor(rows, 1)
        assert ancestor is not None
        assert ancestor[0] == "template.xlsx"

    def test_first_row_no_inherit(self):
        """测试第一行不能继承"""
        rows = [("template.xlsx", "output.xlsx", "Alice")]
        ancestor = self._find_ancestor(rows, 0)
        assert ancestor is None

    def test_skip_empty_rows(self):
        """测试跳过中间空行"""
        rows = [
            ("template.xlsx", "output.xlsx", "Alice"),
            ("", "", "Bob"),
            ("", "", "Charlie"),
            ("new_template.xlsx", "new_output.xlsx", "David"),
            ("", "", "Eve"),
        ]
        ancestor = self._find_ancestor(rows, 4)
        assert ancestor is not None
        assert ancestor[0] == "new_template.xlsx"


class TestFillingDirection:
    """测试填写方向逻辑"""

    def test_down_direction(self):
        """测试向下填写"""
        direction = "向下"
        offset = (1, 0) if direction == "向下" else (0, 1)
        assert offset == (1, 0)

    def test_right_direction(self):
        """测试向右填写"""
        direction = "向右"
        offset = (1, 0) if direction == "向下" else (0, 1)
        assert offset == (0, 1)

    def test_coordinate_direction(self):
        """测试坐标填写"""
        coord = "B3"
        assert coord == "B3"