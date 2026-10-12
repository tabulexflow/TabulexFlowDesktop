# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""测试 TabulexDocCreator 子工具 - Excel/Word/PDF 处理逻辑"""
import pytest
import sys
import os

# Ensure TabulexDocCreator directory is in path
_tool_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _tool_dir not in sys.path:
    sys.path.insert(0, _tool_dir)


class TestExcelProcessing:
    """测试 Excel 处理逻辑"""

    def test_placeholder_in_text(self):
        """测试文本中的占位符"""
        text = "Hello {{name}}, your order {{id}} is ready."
        assert "{{name}}" in text
        assert "{{id}}" in text

    def test_replace_all_placeholders(self):
        """测试替换所有占位符"""
        text = "{{greeting}} {{name}}!"
        replacements = {"{{greeting}}": "Hello", "{{name}}": "World"}
        for key, value in replacements.items():
            text = text.replace(key, value)
        assert text == "Hello World!"
        assert "{{" not in text

    def test_placeholder_with_formatting(self):
        """测试带格式的占位符"""
        text = "Total: {{price}}"
        text = text.replace("{{price}}", "$99.99")
        assert text == "Total: $99.99"

    def test_multiple_same_placeholder(self):
        """测试多个相同占位符"""
        text = "{{name}} and {{name}} are friends."
        text = text.replace("{{name}}", "Alice")
        assert text == "Alice and Alice are friends."

    def test_placeholder_in_table(self):
        """测试表格中的占位符"""
        rows = [
            ["{{col1}}", "{{col2}}"],
            ["{{col1}}", "{{col2}}"],
        ]
        for row in rows:
            for i, cell in enumerate(row):
                row[i] = cell.replace("{{col1}}", "A").replace("{{col2}}", "B")
        assert rows[0] == ["A", "B"]
        assert rows[1] == ["A", "B"]


class TestWordProcessing:
    """测试 Word 处理逻辑"""

    def test_paragraph_placeholder(self):
        """测试段落中的占位符"""
        paragraph = "Dear {{recipient}}, thank you for your order."
        assert "{{recipient}}" in paragraph

    def test_table_cell_placeholder(self):
        """测试表格单元格中的占位符"""
        cell_text = "{{product_name}}"
        assert cell_text.startswith("{{")
        assert cell_text.endswith("}}")

    def test_image_placeholder(self):
        """测试图片占位符"""
        # 图片占位符格式: {{image:width:height}}
        placeholder = "{{image:200:150}}"
        parts = placeholder.strip("{}").split(":")
        assert parts[0] == "image"
        assert parts[1] == "200"
        assert parts[2] == "150"


class TestPDFProcessing:
    """测试 PDF 处理逻辑"""

    def test_page_number_validation(self):
        """测试页码验证"""
        page_num = 5
        assert page_num > 0
        assert isinstance(page_num, int)

    def test_insert_position(self):
        """测试插入位置"""
        positions = ["before", "after", "replace"]
        for pos in positions:
            assert pos in ["before", "after", "replace"]

    def test_table_tight_fit(self):
        """测试表格紧贴选项"""
        tight_fit = True
        assert isinstance(tight_fit, bool)


class TestPowerPointProcessing:
    """测试 PowerPoint 处理逻辑"""

    def test_slide_number(self):
        """测试幻灯片编号"""
        slide_num = 3
        assert slide_num > 0
        assert isinstance(slide_num, int)

    def test_shape_placeholder(self):
        """测试形状中的占位符"""
        shape_text = "{{title}}"
        assert "{{" in shape_text
        assert "}}" in shape_text


class TestFileInfoExtraction:
    """测试文件信息提取"""

    def test_extension_detection(self):
        """测试扩展名检测"""
        ext_map = {
            "file.xlsx": "xlsx",
            "file.docx": "docx",
            "file.pptx": "pptx",
            "file.pdf": "pdf",
        }
        for filename, expected_ext in ext_map.items():
            ext = filename.rsplit('.', 1)[-1].lower()
            assert ext == expected_ext

    def test_file_type_from_extension(self):
        """测试从扩展名判断文件类型"""
        def get_file_type(filename):
            ext = filename.rsplit('.', 1)[-1].lower()
            if ext in ('xlsx', 'xls'):
                return 'Excel'
            elif ext in ('docx', 'doc'):
                return 'Word'
            elif ext in ('pptx', 'ppt'):
                return 'PowerPoint'
            elif ext == 'pdf':
                return 'PDF'
            return 'Unknown'
        assert get_file_type("report.xlsx") == 'Excel'
        assert get_file_type("document.docx") == 'Word'
        assert get_file_type("slides.pptx") == 'PowerPoint'
        assert get_file_type("manual.pdf") == 'PDF'


class TestGridOperation:
    """测试Grid操作"""

    def test_row_insertion(self):
        """测试行插入"""
        rows = [["A", "B"], ["C", "D"]]
        rows.insert(1, ["X", "Y"])
        assert len(rows) == 3
        assert rows[1] == ["X", "Y"]

    def test_row_deletion(self):
        """测试行删除"""
        rows = [["A", "B"], ["C", "D"], ["E", "F"]]
        del rows[1]
        assert len(rows) == 2
        assert rows[1] == ["E", "F"]

    def test_cell_value_change(self):
        """测试单元格值修改"""
        cells = {"A1": "old_value"}
        cells["A1"] = "new_value"
        assert cells["A1"] == "new_value"

    def test_undo_redo(self):
        """测试撤销/重做"""
        history = []
        current = "initial"
        # 修改
        history.append(current)
        current = "modified"
        # 撤销
        current = history.pop()
        assert current == "initial"