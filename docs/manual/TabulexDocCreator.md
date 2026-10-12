# TabulexDocCreator User Manual

> **Document Version**: 1.0.0
> **Last Updated**: 2026-09-17
> **Applies to**: TabulexDocCreator 1.0.0 (BuiltinProgram, AGPL v3, works offline)
> **Target Audience**: End users

> **中文版请翻到后半部分 / Chinese version below** ↓

TabulexDocCreator is a built-in tool of TabulexFlow for batch document work. It creates or modifies **Excel (.xlsx)**, **Word (.docx)**, **PowerPoint (.pptx)** and **PDF** files by filling a spreadsheet-like grid: one row of data produces one output document, and many rows can be produced in one click. It also has a **Get Doc Info** mode that reads document metadata into the grid.

Nothing on disk is written before you click **Execute**.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Quick Start (5 minutes)](#2-quick-start-5-minutes)
3. [Interface Reference](#3-interface-reference)
4. [Core Concepts and Common Operations](#4-core-concepts-and-common-operations)
5. [Tab Reference](#5-tab-reference)
6. [Safety and Limits](#6-safety-and-limits)
7. [Tips and Best Practices](#7-tips-and-best-practices)
8. [FAQ / Troubleshooting](#8-faq--troubleshooting)
9. [Appendix](#9-appendix)

---

## 1. Introduction

### 1.1 What TabulexDocCreator Can Do

The tool has five tabs: **Excel · Word · PowerPoint · PDF · About**. Each document tab has two operation modes:

| Mode | What it does |
|------|--------------|
| **Create Doc** | Uses a template file as the source, fills in data (placeholders or titles), and saves a new document to the Save File path |
| **Get Doc Info** | Reads metadata of the Source File (page count, file size, title, author, dates, ...) and writes it into the grid |

Per-tab fill methods:

| Tab | Fill methods |
|-----|--------------|
| Excel | **Placeholder** (replace placeholder text) and **Fill by Title** (write values below/right of a title cell, or at a coordinate) |
| Word | **Placeholder** |
| PowerPoint | **Placeholder** |
| PDF | **Placeholder**, **Insert Image**, **Insert Text**, **Insert Table**, **Delete Table** |

- All processing is local. No account, no network, no upload.
- Supported formats: `.xlsx`, `.docx`, `.pptx`, `.pdf`. Old binary formats `.xls/.doc/.ppt` are **not** supported — convert them to the OOXML format first.
- The interface has 6 languages: 简体中文, English, Français, Русский, Español, العربية.

### 1.2 Key Concepts

- **Source File** — the template (Create Doc) or the file to inspect (Get Doc Info). Required.
- **Save File** — the output file path (Create Doc). Required. A relative path is resolved against the Source File's folder. If it already exists, the tool asks before overwriting.
- **Grid** — the data table. fixed columns: **ID**, **Source File***, **Save File***, **Result**; then data columns **Data1, Data2, …**.
- **Header rows** — the first 4 rows describe the data columns: target page/sheet, the placeholder/title to find, fill direction, and value count. They are read-only and color-coded.
- **Data rows** — rows below the header rows; one row = one set of values. Rows that share the same Save File belong to the same output document.
- **Inherited row** — a row whose Source File (or Save File) is empty. It reuses both paths from the nearest row above that has both.
- **Result column** — shows `Success` / `Failed: …` after Execute, and is also the "already processed" marker that lets you re-run safely.
- **Preview** — renders the result in memory without saving anything.
- **Execute** — really creates the output files.

### 1.3 Before You Start

- Prepare a template with clear placeholder or title text.
- Make sure the Source File and Save File paths are correct, and that image paths (when using Image mode) exist.
- Convert legacy `.xls/.doc/.ppt` files to `.xlsx/.docx/.pptx` before using them.
- Files larger than **200 MB** cannot be processed.

---

## 2. Quick Start (5 minutes)

Goal: create one Excel file per person from a template that contains the placeholder `{{Name}}`.

1. **Open the tool**: in the main window tool grid, click the **Tabulex Doc Creator** card.
2. Go to the **Excel** tab. Set **Mode = Create Doc**, **Fill = Placeholder**.
3. **Fill the header rows** in a data column (e.g. the first data column, under "Data1"):
   - **Target Sheet**: leave empty (all sheets) or type a sheet name/number.
   - **Placeholder**: type the placeholder exactly as it appears in the template, e.g. `{{Name}}`.
   - **Direction**: leave as is (not needed for a plain replacement).
   - **Value Count**: choose **Single Value**.
4. **Fill the data row** (the first row below the header rows):
   - **ID**: `001` (optional, for your own reference)
   - **Source File**: `C:\templates\invite.xlsx`
   - **Save File**: `C:\out\invite_001.xlsx`
   - **Data1**: `Alice`
5. **Add more people**: either add more rows with their own Save File, or use multi-value inheritance (see [3.5](#35-inherited-rows)).
6. **Preview**: click **Preview**. The preview dialog shows how the first output file will look; use **Previous/Next** to switch files. Nothing is saved.
7. **Execute**: close the preview, click **Execute**. If the output file exists, confirm the overwrite prompt. The Result column shows `Success`, and a completion dialog reports the count.
8. **Check the Result column**: rows that already show a value are skipped on the next Execute, so you can safely re-run after adding rows.

---

## 3. Interface Reference

### 3.1 Tabs

**Excel · Word · PowerPoint · PDF · About**

The first four tabs share the same layout (toolbar + grid + status bar) and keep an independent grid. The **About** tab shows the version, developer, license, website, feedback link and recommended tools.

### 3.2 Toolbar

From left to right:

| Control | Meaning |
|---------|---------|
| **Mode** | **Create Doc** or **Get Doc Info** |
| **Fill** | The fill method of the current tab (see [1.1](#11-what-tabulexdoccreator-can-do)) |
| **Img Width / Img Height** | Maximum image size in pixels, default 200 (Placeholder mode when inserting images) |
| **Pos** (PDF only) | Insert position for Insert Text/Table/Image (10 options) |
| **Height / Width** (PDF only) | Row height or image width, used by the insert methods |
| **Tight** (PDF only) | Table row spacing (Insert Table) |
| **Preview** | Open the preview dialog. **Disabled in Get Doc Info mode.** |
| **Execute** | Run the batch operation. While running it becomes **Cancel**. |

In Get Doc Info mode the Fill dropdown and the PDF parameter controls are disabled, and the Preview button is greyed out.

### 3.3 Grid Columns

| Column | Editable | Meaning |
|--------|----------|---------|
| **ID** | Yes | Your own reference number (never processed by the tool) |
| **Source File*** | Yes | Template file (Create Doc) / file to inspect (Get Doc Info) |
| **Save File*** | Yes | Output file path (Create Doc). Hidden in Get Doc Info |
| **Result** | No | Execution result. Hidden in Get Doc Info |
| **Data1, Data2, …** | Yes | One column per placeholder/title (Create Doc); information fields (Get Doc Info) |

- `*` marks a required field.
- You can add as many data columns as you need (up to 50).
- In **Get Doc Info** mode, the data columns are the output: they are read-only and shown on a light-grey background. Only Source File is editable.
- Drag files from the file manager onto the **Source File** column to fill paths.

### 3.4 Header Rows

The first 4 rows are read-only headers that describe each data column. Their labels change with the tab and fill method.

**Excel (Placeholder / Fill by Title)**

| Row | Label | What to enter |
|-----|-------|---------------|
| 0 | Target Sheet | Sheet name (e.g. `Sheet1`) or sheet number. Empty = all sheets |
| 1 | Placeholder* / Title* | The placeholder or title text to find |
| 2 | Direction | Down / Right / Coordinate |
| 3 | Value Count | Single Value / Multi Value / Image |

**Word / PowerPoint / PDF (Placeholder)**

| Row | Label | What to enter |
|-----|-------|---------------|
| 0 | Target Page | Page number (Word/PDF) or slide number (PowerPoint). Empty = all pages/slides |
| 1 | Placeholder* | The placeholder text to find |
| 2 | Direction | Down / Right |
| 3 | Value Count | Single Value / Multi Value / Image |

**Hidden header rows**

- **PDF Insert Text / Insert Table / Insert Image / Delete Table**: all header rows are hidden; the insert position is chosen in the toolbar instead.
- **Get Doc Info**: all header rows are hidden and the data columns show the retrieved information.

### 3.5 Inherited Rows

If **either** Source File or Save File is empty on a row, that row inherits **both** paths from the nearest row above that has both. This is how **Multi Value** works: each inherited row contributes one more value to the same output file.

| ID | Source File | Save File | Data1 |
|----|-------------|-----------|-------|
| 001 | template.xlsx | output.xlsx | A |
| *(empty)* | *(empty)* | *(empty)* | B |
| *(empty)* | *(empty)* | *(empty)* | C |

- With **Single Value**, only the first non-inherited row is used (the placeholder disappears after the first replacement).
- With **Multi Value**, every inherited row's value is used in turn.
- If a row has its own Save File but no Source File, it still inherits both paths from above — so keep the Source File on the first row of the group.

### 3.6 Result Column and Re-running

- After Execute, every processed group gets a **Result**: `Success` or `Failed: …`.
- **If a group's Result is not empty, the next Execute skips that group.** This prevents accidental duplication.
- To regenerate a file, first select its Result cell(s) and press **Delete** to clear them, then Execute again.
- If all groups are skipped, the tool tells you why (previously succeeded vs. previously failed) and how to clear the cells.
- The success text is written in the current UI language and recognized across all languages.

### 3.7 Right-Click Menus and Shortcuts

Right-click a **cell**: **Import**, **Export**, **Copy**, **Paste**, **Clear Cells** (plus Undo/Redo/Delete Data from the base grid).

Right-click the **row header**: **Insert Row**, **Delete Row**, **Append 100 Rows**.

| Shortcut | Function |
|----------|----------|
| Ctrl+C / Ctrl+V | Copy / Paste cells (paste understands Excel/LibreOffice selections) |
| Ctrl+A | Select all |
| Delete | Clear selected cells |
| Ctrl+Z / Ctrl+Shift+Z | Undo / Redo a cell edit (right-click menu also offers Undo/Redo) |

Notes:

- Paste prefers the HTML clipboard flavor, so leading/trailing empty rows copied from Excel are preserved.
- When pasting data into the header rows (rows 0-3), only the data columns are writable; the fixed columns stay read-only. Pasting a full table (header + data) into the top-left cell works best.

### 3.8 Status Bar and Drag & Drop

- **Left**: the selected cell's value; during processing, `Processing: current/total - filename`.
- **Right**: progress percent; on completion the summary (e.g. `Completed: 5/5 (skipped: 2)` or `skipped: N`); on cancel, "Operation cancelled".
- **Drag & drop**: drop files onto the Source File column. Unsupported extensions are rejected with a message.

---

## 4. Core Concepts and Common Operations

### 4.1 Create Doc vs Get Doc Info

| | Create Doc | Get Doc Info |
|---|------------|--------------|
| Source File | Required (template) | Required (file to inspect) |
| Save File | Required | Hidden |
| Header rows | Shown (except PDF insert modes) | Hidden |
| Data columns | Input values | Read-only output fields |
| Preview | Available | Disabled |
| Completion | Popup with success/total (and skipped count) | Popup only if some rows failed |
| Result column | `Success` / error | Not used |

In Get Doc Info mode, clearing a row's Source File automatically clears that row's information fields, so stale data does not remain.

### 4.2 Fill Direction and Value Count

**Fill Direction**

- **Down**: write below the found title/position.
- **Right**: write to the right of the found title/position.
- **Coordinate** (Excel): treat the Placeholder/Title text itself as a cell address, e.g. `A1`, `B5`, `Sheet1!C5`.

Direction is used by Excel **Fill by Title**. For plain **Placeholder** replacement the text is replaced in place, so direction usually does not matter.

**Value Count**

| Value | Behavior |
|-------|----------|
| Single Value | All occurrences of the placeholder are replaced with the same value (first non-inherited row) |
| Multi Value | One occurrence is replaced per row, using each row's value in turn |
| Image | The placeholder is removed and an image is inserted in its place (Data value = image path) |

### 4.3 Target Page / Target Sheet

- **Excel — Target Sheet** (header row 0, per column): sheet name or 1-based number; empty = all sheets. With Direction = Coordinate, an address like `Sheet1!C5` overrides the header value. Invalid/out-of-range sheets are reported and that column is skipped.
- **Word — Target Page**: page number (digits only). Empty = all pages. Page boundaries are detected from hard page breaks and section breaks and may differ slightly from Word's on-screen pagination.
- **PowerPoint — Target Page**: slide number. Empty = all slides.
- **PDF — Target Page**: page number. Empty = all pages.
- **PDF insert/delete modes** do not use the header row; they use the **Pos** dropdown in the toolbar.

### 4.4 Preview

- Preview builds the result **in memory** and never saves.
- It opens with the file of the selected/active row (otherwise the first file).
- Use **Previous / Next** to switch between output files.
- There is no "confirm" button in the preview; close it and click **Execute** to actually generate.
- In Get Doc Info mode, Preview is disabled.

### 4.5 Execute

When you click **Execute**:

1. Data is validated (missing Source File, missing image files, unsafe paths).
2. If different source files write to the **same output file**, a conflict warning appears.
3. If an output file **already exists**, an overwrite confirmation appears (listing up to 5 files).
4. The batch runs in the background; the toolbar Preview button becomes **Cancel**.
5. On finishing, the Result column is filled and a completion dialog reports `success/processed` (plus skipped count if any). In Get Doc Info mode, a popup appears only if some rows failed.

Groups whose Result column already has a value are skipped, so you can re-run only the new rows.

### 4.6 Cancel

While processing, click **Cancel** (the renamed Preview button) to stop after the current file. The status bar shows "Operation cancelled".

### 4.7 Import and Export

- **Import** and **Export** are available from the cell right-click menu.
- **Export** writes the header rows and row labels, so a round-trip export → edit → import keeps the same structure.
- Import auto-detects the exported header row / label column; plain data tables are imported 1:1 without losing the first row or column.
- Imported files are also subject to the 200 MB limit.

---

## 5. Tab Reference

### 5.1 Excel

**Fill methods: Placeholder / Fill by Title**

**Placeholder**

- Searches the workbook for cells containing the placeholder text (substring match, braces like `{{ }}` are not required).
- Single Value replaces every occurrence with one value; Multi Value replaces one occurrence per row; Image removes the placeholder and inserts the image.
- Cells that contain a **formula** are never overwritten (formulas take priority).
- Template compatibility: if a template's document-properties XML is malformed and the file cannot be parsed, the tool repairs a temporary working copy. **The source file is never modified.**

**Fill by Title**

- Finds cells whose text equals the title (after trimming and normalizing whitespace/newlines) and writes the value:
  - **Down** → the cell below the title;
  - **Right** → the cell to the right;
  - **Coordinate** → the title itself is a cell address (`A1`, `Sheet1!C5`).
- **Merged cells / same-color framed areas**: the value goes below the last row (Down) or right of the last column (Right) of the region.
- For Multi Value, the Nth row is written N rows below / N columns to the right of the region.
- Formula cells are skipped.

### 5.2 Word

**Fill method: Placeholder**

- Replaces placeholder text in the whole document: body paragraphs, tables, headers and footers.
- **Target Page** limits the replacement to one page (page breaks/section breaks are used to approximate pages); empty = all pages.
- If an image value is given for an Image-type item, the placeholder is removed and the image is inserted.
- Legacy `.doc` (OLE2) files are not supported: Execute writes `Failed: .doc format is not supported, please use .docx`, Get Doc Info counts the row as failed, and Preview shows the same message. Convert to `.docx` first.

### 5.3 PowerPoint

**Fill method: Placeholder**

- Replaces placeholder text in the text frames of the slides.
- **Target Page** selects the slide number; empty = all slides.
- Image insertion uses a floating picture and removes only the placeholder itself, keeping the rest of the text frame intact.
- Legacy `.ppt` (OLE2) files are not supported (analogous to `.doc`). Convert to `.pptx` first.

### 5.4 PDF

**Fill methods: Placeholder / Insert Image / Insert Text / Insert Table / Delete Table**

**Placeholder**

- Searches the PDF text for the placeholder (image-only PDFs without a text layer cannot be processed) and replaces it.
- The new text inherits the placeholder's font size, color and writing direction.
- Value Count: Single Value / Multi Value / Image (Image removes the placeholder and inserts the image). **Img Width / Img Height** set the maximum image size in pixels (default 200).

**Insert Image / Insert Text / Insert Table**

- Header rows are hidden; the values in the data rows are the content to insert.
- Choose the **Pos** in the toolbar; the tool finds a free area at that position:

| Pos | Meaning |
|-----|---------|
| (All) Any Position | Anywhere on the page |
| (All) Bottom-Left / Bottom-Right / Top-Left / Top-Right | Search from that corner |
| (Inside) … | Restrict the search to inside a drawing frame |

- **Insert Text** — the **Height** parameter is the row height as a fraction of the page height (default 0.015). Inserted text is blue.
- **Insert Table** — rows sharing the same Save File form one table (row count = number of rows, column count = widest row). **Height** is the row height (default 0.015); **Tight** reduces row spacing.
- **Insert Image** — the **Width** parameter is the image width as a fraction of the page width (default 0.06); the height keeps the image's aspect ratio.
- The Height/Width box remembers a separate value per fill method.

**Delete Table** — detects and removes tables in the PDF. No extra parameters.

**Other notes**

- Insert methods report `Failed: No space to insert …` when no suitable free area exists; the file is skipped.
- Encrypted PDFs cannot be edited (`Failed: PDF is encrypted and cannot be edited`).
- Rotated pages (`/Rotate`) and vertical text are handled; replacement text and inserted content keep the correct direction.

### 5.5 About

Shows the tool version, developer, AGPL v3 license, the official website, a feedback link, and recommended-tool cards (TabulexFileOperator, TabulexBomComparator, PalletLayout, Get More Tools).

---

## 6. Safety and Limits

| Item | Detail |
|------|--------|
| Source files | Never modified by Create Doc (a working copy is used); Get Doc Info is read-only |
| Overwrite | Existing output files always require confirmation before being overwritten |
| Output conflict | Writing different sources to the same output file triggers a warning |
| Result column | Prevents accidental re-generation; clear it manually to regenerate |
| Size limit | A source file larger than 200 MB is rejected before parsing (anti zip-bomb) |
| Format safety | `.doc/.xls/.ppt` (OLE2) and wrong-tab files are reported clearly instead of crashing |
| Path safety | Paths containing `..` are rejected |
| Formula safety | Excel cells containing formulas are never overwritten |
| Optional libraries | Excel/Word/PPT/PDF processing needs `openpyxl`, `python-docx`, `python-pptx`, `PyMuPDF (fitz)`; image handling uses `Pillow` |

---

## 7. Tips and Best Practices

1. **Use clear placeholders** such as `{{Name}}`, `{{Date}}` in your templates; they are easier to spot and to fill.
2. **One data column per placeholder/title.** The header row is per column, so different columns can target different pages/sheets.
3. **Reuse the same Save File for multi-value rows** (inherited rows) — that is how one document gets several values.
4. **Use Save File relative paths** if you want outputs to land next to the template.
5. **Preview before Execute** for a new template, especially for PDF insert positions.
6. **Check the Result column** after running; clear it on purpose when you want to regenerate.
7. **Get Doc Info is a quick audit tool**: paste many paths into Source File, run, and export the grid to Excel.
8. **Keep templates under 200 MB** and convert legacy Office formats first.
9. **Set the target page/sheet per column**; leave it empty to process everything.

---

## 8. FAQ / Troubleshooting

**Q: The Preview button is greyed out.**
You are in **Get Doc Info** mode; that mode has no preview. Switch Mode to **Create Doc**.

**Q: Execute says "No data to process".**
The grid has no data rows with a Source File. Fill in Source File (and Save File in Create Doc mode) or import a table.

**Q: "Source file not found" / "Image file not found" appears before execution.**
One of the Source File or image paths does not exist. Correct the path (the message lists the row number).

**Q: "This is a Word document, please use the Word tab".**
The file type does not match the current tab. Switch to the correct tab (or convert the file). The same applies to Excel and PowerPoint.

**Q: "Failed: .doc format is not supported" (or `.ppt`).**
Old binary Office formats cannot be read. Open the file and save it as `.docx` / `.pptx`, then use it.

**Q: "Failed: PDF is encrypted".**
Password-protected PDFs cannot be edited. Remove the password first.

**Q: "Failed: file too large (max …)"**
The source file exceeds 200 MB. Split or compress it.

**Q: "File already exists. Overwrite?"**
The Save File already exists. Choose Yes to overwrite, No to abort and change the paths. Note that groups already showing a Result value do not trigger this prompt, because they will be skipped.

**Q: Nothing was generated and the tool says all rows were skipped.**
The Result column already has values for those groups. Select those Result cells and press **Delete**, then Execute again. For rows that failed last time, fix the error first.

**Q: Only part of the rows were processed after re-running.**
That is the skip behavior: rows with a non-empty Result are skipped. Use `Completed: x/y (skipped: n)` in the status bar to confirm.

**Q: "The following output files have conflicts (multiple rows writing to the same file)."**
Different Source Files map to the same Save File. Give each source its own output path, or confirm if sharing is intended (e.g. multi-value rows).

**Q: The placeholder was not replaced.**
- The placeholder text must match exactly (including braces and spaces).
- Check the **Target Sheet/Page** value; an invalid/out-of-range value skips that column.
- For Word/PDF, the placeholder must exist in the text layer (scanned image-only PDFs cannot be processed).
- In Excel, cells containing formulas are not overwritten.

**Q: In Excel Fill by Title, the value landed in the wrong cell.**
Check the **Direction**: Down writes below, Right writes to the right, Coordinate treats the title as an address. For merged cells or framed areas, the value goes after the whole region.

**Q: "Failed: No space to insert text/table/image".**
No suitable free area was found at the selected position. Try a different **Pos** (e.g. another corner or Any Position), a smaller Height/Width, or enable Tight.

**Q: The inserted PDF text is blue.**
This is by design; inserted text uses a fixed blue color.

**Q: The image is too large / too small.**
Set **Img Width / Img Height** (Placeholder image mode, in pixels) or the **Width** fraction (Insert Image mode).

**Q: I pasted from Excel and lost the first rows.**
Update to the current version; paste now reads the HTML clipboard flavor and keeps leading empty rows. If it still happens, paste into the first data row and check the selection.

**Q: Import lost the first row/column.**
The importer auto-detects the exported header row/label column. For a plain data table without headers, data maps 1:1. If needed, export first to get the canonical layout.

**Q: The Word page count shows "N/A (docx cannot get exact page count)".**
Word page breaks are computed by the rendering engine, which `python-docx` cannot read. This is expected; the Page Count info field may be unavailable.

**Q: The tool modified my template?**
No. Create Doc loads the template and writes the output to the Save File. Make sure the Save File is different from the Source File.

**Q: Can I run several tabs at the same time?**
No. Only one operation runs at a time; other buttons are disabled while it runs. Cancel or wait, then continue.

---

## 9. Appendix

### 9.1 Get Doc Info Fields

| Tab | Fields |
|-----|--------|
| Excel | File Size, Sheet Count, Row Count, Column Count, Title, Author, Creation Date, Modification Date, Last Modified By |
| Word | File Size, Page Count, Word Count, Character Count, Title, Author, Creation Date, Modification Date, Last Modified By |
| PowerPoint | File Size, Slide Count, Slide Size, Title, Author, Creation Date, Modification Date, Last Modified By |
| PDF | Page Count, File Size, Orientation, Page Size, Title, Author, Creation Date, Modification Date, Encrypted |

Unavailable values are shown as the localized "N/A".

### 9.2 Result Messages

- Success: `Success` / 成功.
- Failure: `Failed: <reason>`, where `<reason>` is one of: file not found, permission denied, invalid data, invalid target, timeout, memory error, `.doc/.ppt` format unsupported, no space to insert, no suitable position, encrypted PDF, file too large, unknown error.
- Invalid Sheet/Page values: `Invalid target: <value>`.

### 9.3 Limits

| Item | Limit |
|------|-------|
| Source file size | 200 MB per file |
| Data columns | 50 |
| Excel `DEFAULT` initial rows | 4 header rows + 50 data rows |
| Undo history | 50 cell-edit steps |

### 9.4 Shortcuts

| Shortcut | Function |
|----------|----------|
| Ctrl+C / Ctrl+V | Copy / Paste |
| Ctrl+A | Select all |
| Delete | Clear selected cells |
| Ctrl+Z / Ctrl+Shift+Z | Undo / Redo cell edit |

### 9.5 Glossary

| Term | Meaning |
|------|---------|
| Source File | Template (Create Doc) or file to inspect (Get Doc Info) |
| Save File | The generated output path |
| Placeholder | Text in the template that is replaced by data |
| Title | Text used as an anchor for Fill by Title |
| Inheritance row | A row without its own paths that reuses the paths above |
| Target Sheet / Page | The sheet / page / slide to operate on |
| Value Count | Single Value / Multi Value / Image |
| Get Doc Info | Read metadata instead of generating files |

---

> **Document Version**: 1.0.0
> **Last Updated**: 2026-09-17

---
---

# 灵表文档创建（TabulexDocCreator）使用手册

> **文档版本**：1.0.0
> **最后更新**：2026-09-17
> **适用版本**：TabulexDocCreator 1.0.0（内置工具 BuiltinProgram，AGPL v3，可离线使用）
> **面向读者**：最终用户

TabulexDocCreator 是 TabulexFlow 的内置工具，用于批量处理文档。它通过一张类似电子表格的网格，批量创建或修改 **Excel (.xlsx)**、**Word (.docx)**、**PowerPoint (.pptx)** 和 **PDF** 文件：一行数据生成一个文件，多行可一键成批生成。它还提供 **获取文档信息** 模式，把文档的元信息读入网格。

在你点击**执行**之前，工具不会在硬盘上写入任何文件。

---

## 目录

1. [简介](#1-简介)
2. [快速上手（5 分钟）](#2-快速上手5-分钟)
3. [界面说明](#3-界面说明)
4. [核心概念与通用操作](#4-核心概念与通用操作)
5. [各标签页详解](#5-各标签页详解)
6. [安全与限制](#6-安全与限制)
7. [技巧与最佳实践](#7-技巧与最佳实践)
8. [常见问题 / 故障排查](#8-常见问题--故障排查)
9. [附录](#9-附录)

---

## 1. 简介

### 1.1 TabulexDocCreator 能做什么

工具包含五个标签页：**Excel · Word · PowerPoint · PDF · 关于**。每个文档标签页都有两种操作方式：

| 操作方式 | 作用 |
|----------|------|
| **创建文档** | 以模板文件为来源，填入数据（占位符或标题），并把新文档保存到“保存文件”路径 |
| **获取文档信息** | 读取源文件的元信息（页数、大小、标题、作者、日期等）并写入网格 |

各标签页的填写方式：

| 标签页 | 填写方式 |
|--------|----------|
| Excel | **占位符替换**、**按标题填写**（在标题下方/右侧写入，或按坐标写入） |
| Word | **占位符替换** |
| PowerPoint | **占位符替换** |
| PDF | **占位符替换**、**插入图片**、**插入文本**、**插入表格**、**删除表格** |

- 全部本地处理，无需账号、无需联网、不上传文件。
- 支持格式：`.xlsx`、`.docx`、`.pptx`、`.pdf`。旧版二进制格式 `.xls/.doc/.ppt` **不支持**，请先另存为新格式。
- 界面支持 6 种语言：简体中文、English、Français、Русский、Español、العربية。

### 1.2 核心概念

- **待操作文件（来源文件）**——模板文件（创建文档）或待检查文件（获取文档信息）。必填。
- **保存文件（输出文件）**——输出路径（创建文档）。必填。相对路径会相对于来源文件所在目录解析。若文件已存在，执行前会询问是否覆盖。
- **网格**——数据表格。固定列为 **编号ID**、**待操作文件\***、**保存文件\***、**执行结果**；其后是数据列 **数据1、数据2、…**。
- **表头行**——最前面 4 行，用于描述各数据列：目标页/目标Sheet页、待查找的占位符/标题、填写方向、填写数量。只读并有底色区分。
- **数据行**——表头行下方的行；一行 = 一组值。拥有相同“保存文件”的行属于同一个输出文档。
- **继承行**——待操作文件或保存文件为空的行，会沿用上方最近的、两个字段都非空的行的**两个**路径。
- **执行结果列**——执行后显示“成功” / “失败：…”，同时作为“是否已处理”的标记，使重复执行更安全。
- **预览**——在内存中生成结果，不保存任何文件。
- **执行**——真正生成输出文件。

### 1.3 使用前提

- 准备带清晰占位符或标题文本的模板。
- 确认待操作文件、保存文件路径正确；使用“图片”模式时确认图片路径存在。
- 旧版 `.xls/.doc/.ppt` 请先转换为 `.xlsx/.docx/.pptx`。
- 超过 **200 MB** 的文件无法处理。

---

## 2. 快速上手（5 分钟）

目标：用含有占位符 `{{Name}}` 的模板，为每个人生成一个 Excel 文件。

1. **打开工具**：在主窗口工具网格中点击 **灵表文档创建** 卡片。
2. 进入 **Excel** 标签页，设置 **操作 = 创建文档**、**填写 = 占位符替换**。
3. **填写表头行**（在某个数据列，例如“数据1”下方）：
   - **目标Sheet页**：留空（所有工作表）或输入工作表名/编号。
   - **待查找占位符\***：输入与模板中完全一致的占位符，如 `{{Name}}`。
   - **填写方向**：保持默认（纯替换时不需要）。
   - **填写数量**：选择 **单值**。
4. **填写数据行**（表头行下方的第一行）：
   - **编号ID**：`001`（可选，仅供自己参考）
   - **待操作文件**：`C:\templates\invite.xlsx`
   - **保存文件**：`C:\out\invite_001.xlsx`
   - **数据1**：`Alice`
5. **添加更多人**：新增行并各自填写保存文件，或使用多值继承（见 [3.5](#35-继承行)）。
6. **预览**：点击 **预览**。预览窗口显示第一个输出文档的效果；用 **上一个/下一个** 切换文件。此时不保存任何内容。
7. **执行**：关闭预览，点击 **执行**。若输出文件已存在，确认覆盖提示。执行结果列显示“成功”，并弹出完成数量提示。
8. **查看执行结果列**：已有值的行在下次执行时会被跳过，因此你可以在新增行之后安全地再次执行。

---

## 3. 界面说明

### 3.1 标签页

**Excel · Word · PowerPoint · PDF · 关于**

前四个标签页布局相同（操作栏 + 网格 + 状态栏），各自维护独立的网格。**关于**标签页显示版本、开发者、许可证、官网、反馈链接和推荐工具。

### 3.2 操作栏

从左到右：

| 控件 | 说明 |
|------|------|
| **操作** | **创建文档** 或 **获取文档信息** |
| **填写** | 当前标签页的填写方式（见 [1.1](#11-tabulexdoccreator-能做什么)） |
| **图宽 / 图高** | 图片最大尺寸（像素），默认 200（占位符替换模式下插入图片时使用） |
| **位置**（仅 PDF） | 插入文本/表格/图片的插入位置（10 个选项） |
| **行高 / 宽度**（仅 PDF） | 插入方式使用的行高或图片宽度 |
| **紧贴**（仅 PDF） | 表格行距是否紧凑（插入表格） |
| **预览** | 打开预览窗口。**获取文档信息模式下不可用。** |
| **执行** | 执行批量操作。运行中按钮变为 **取消**。 |

获取文档信息模式下，填写方式下拉框与 PDF 参数控件被禁用，预览按钮置灰。

### 3.3 网格列

| 列 | 可编辑 | 说明 |
|----|--------|------|
| **编号ID** | 是 | 自定义参考编号，程序不处理 |
| **待操作文件\*** | 是 | 模板文件（创建文档）/ 待检查文件（获取文档信息） |
| **保存文件\*** | 是 | 输出路径（创建文档）。获取文档信息模式下隐藏 |
| **执行结果** | 否 | 执行结果。获取文档信息模式下隐藏 |
| **数据1、数据2、…** | 是 | 每个占位符/标题一列（创建文档）；信息字段（获取文档信息） |

- `*` 表示必填。
- 数据列可以按需增加（最多 50 列）。
- **获取文档信息**模式下，数据列就是输出结果：浅灰底、只读；只有“待操作文件”可编辑。
- 可从文件管理器把文件拖到 **待操作文件** 列填入路径。

### 3.4 表头行

最前面 4 行是只读表头，用于描述各数据列，其标签随标签页与填写方式变化。

**Excel（占位符替换 / 按标题填写）**

| 行 | 标签 | 填写内容 |
|----|------|----------|
| 0 | 目标Sheet页 | 工作表名（如 `Sheet1`）或页编号。留空 = 所有工作表 |
| 1 | 待查找占位符\* / 待查找标题\* | 要查找的占位符或标题文本 |
| 2 | 填写方向 | 向下 / 向右 / 坐标 |
| 3 | 填写数量 | 单值 / 多值 / 图片 |

**Word / PowerPoint / PDF（占位符替换）**

| 行 | 标签 | 填写内容 |
|----|------|----------|
| 0 | 目标页 | 页码（Word/PDF）或幻灯片编号（PowerPoint）。留空 = 所有页/幻灯片 |
| 1 | 待查找占位符\* | 要查找的占位符文本 |
| 2 | 填写方向 | 向下 / 向右 |
| 3 | 填写数量 | 单值 / 多值 / 图片 |

**表头隐藏的情况**

- **PDF 插入文本 / 插入表格 / 插入图片 / 删除表格**：所有表头行隐藏，插入位置在操作栏选择。
- **获取文档信息**：所有表头行隐藏，数据列显示获取到的信息。

### 3.5 继承行

若某行的 **待操作文件** 或 **保存文件** 为空，该行会沿用上方最近的、两个字段都非空的行的**两个**路径。这正是 **多值** 的实现方式：每条继承行为同一个输出文件提供一个值。

| 编号ID | 待操作文件 | 保存文件 | 数据1 |
|--------|-----------|---------|-------|
| 001 | template.xlsx | output.xlsx | A |
| *(空)* | *(空)* | *(空)* | B |
| *(空)* | *(空)* | *(空)* | C |

- **单值** 时只使用第一个非继承行的值（占位符第一次替换后就消失了）。
- **多值** 时依次使用每个继承行的值。
- 若某行有自己的保存文件但没有待操作文件，它仍会从上方继承**两个**路径——因此请把待操作文件保留在分组的首行。

### 3.6 执行结果列与重复执行

- 执行后，每个分组会得到 **执行结果**：`成功` 或 `失败：…`。
- **若某组的执行结果非空，下次执行会跳过该组**，避免重复生成。
- 如需重新生成，先选中这些“执行结果”单元格并按 **Delete** 清空，再执行。
- 若所有组都被跳过，工具会说明原因（上次成功 / 上次失败）以及如何清空后重试。
- 成功标记按当前界面语言写入，并能跨语言识别。

### 3.7 右键菜单与快捷键

在**单元格**上右键：**导入**、**导出**、**复制**、**粘贴**、**清空单元格**（以及基类提供的撤销/重做/删除数据）。

在**行标签**上右键：**插入行**、**删除行**、**追加100行**。

| 快捷键 | 功能 |
|--------|------|
| Ctrl+C / Ctrl+V | 复制 / 粘贴单元格（粘贴支持 Excel/LibreOffice 的选择区） |
| Ctrl+A | 全选 |
| Delete | 清空选中单元格 |
| Ctrl+Z / Ctrl+Shift+Z | 撤销 / 重做单元格编辑（右键菜单也有撤销/重做） |

说明：

- 粘贴优先读取 HTML 剪贴板格式，因此从 Excel 复制的选区首尾空行会被保留。
- 粘贴到表头行（0–3 行）时，只有数据列可写，固定列保持只读；建议把完整表格（含表头）粘贴到左上角单元格。

### 3.8 状态栏与拖放

- **左侧**：选中单元格的内容；处理中显示 `处理中: 当前/总数 - 文件名`。
- **右侧**：进度百分比；完成后显示摘要（如 `处理完成: 5/5 (已跳过: 2)` 或 `已跳过: N`）；取消时显示“操作已取消”。
- **拖放**：可把文件拖到“待操作文件”列；不支持的文件类型会被拒绝并提示。

---

## 4. 核心概念与通用操作

### 4.1 创建文档 vs 获取文档信息

| | 创建文档 | 获取文档信息 |
|---|----------|--------------|
| 待操作文件 | 必填（模板） | 必填（待检查文件） |
| 保存文件 | 必填 | 隐藏 |
| 表头行 | 显示（PDF 插入模式除外） | 隐藏 |
| 数据列 | 输入值 | 只读输出字段 |
| 预览 | 可用 | 不可用 |
| 完成提示 | 弹出成功/总数（含跳过数） | 仅当有行失败时弹出 |
| 执行结果列 | `成功` / 错误 | 不使用 |

获取文档信息模式下，清空某行的待操作文件会自动清空该行的信息列，避免残留过期数据。

**切换操作方式会清空数据列**：在任意标签页把“操作”从一种切换为另一种（创建文档 ⇄ 获取文档信息）时，除 **编号ID / 待操作文件 / 保存文件 / 执行结果** 四列之外的所有列内容（含表头行与数据行）会被全部清空——两种模式下数据列含义不同，切换后旧内容不再适用。由**创建文档切换为获取文档信息**时，若非空单元格（含表头行）**多于 3 个**，会先弹确认框（选择“否”则取消切换）；不超过 3 个则直接清空。反向切换不弹确认框。清空不可撤销。

### 4.2 填写方向与填写数量

**填写方向**

- **向下**：写在找到的标题/位置的下一行。
- **向右**：写在找到的标题/位置的下一列。
- **坐标**（Excel）：把占位符/标题本身当作单元格地址，如 `A1`、`B5`、`Sheet1!C5`。

方向主要用于 Excel 的 **按标题填写**。纯 **占位符替换** 是就地替换，通常不需要填写方向。

**填写数量**

| 选项 | 行为 |
|------|------|
| 单值 | 该占位符的所有出现位置都替换为同一个值（使用第一个非继承行） |
| 多值 | 每行依次替换一个出现位置，逐行消费各行的值 |
| 图片 | 删除占位符并在其位置插入图片（数据值 = 图片路径） |

### 4.3 目标页 / 目标Sheet页

- **Excel — 目标Sheet页**（第 0 行，按列）：工作表名或从 1 开始的编号；留空 = 所有工作表。方向为“坐标”时，地址如 `Sheet1!C5` 的页名优先级高于表头值。非法/超范围的工作表会被报告并跳过该列。
- **Word — 目标页**：页码（仅数字）。留空 = 所有页。页面边界通过硬分页符与分节符近似判定，可能与 Word 显示的分页略有差异。
- **PowerPoint — 目标页**：幻灯片编号。留空 = 所有幻灯片。
- **PDF — 目标页**：页码。留空 = 所有页。
- **PDF 插入/删除表格模式**不使用表头行，改用操作栏的 **位置** 下拉框。

### 4.4 预览

- 预览在**内存中**生成结果，绝不保存。
- 默认预览当前选中/活动行对应的文件（未选中则预览第一个文件）。
- 用 **上一个 / 下一个** 在输出文件间切换。
- 预览窗口没有“确认”按钮；关闭预览后点击 **执行** 才会真正生成。
- 获取文档信息模式下预览不可用。

### 4.5 执行

点击 **执行** 后：

1. 校验数据（缺少待操作文件、图片文件缺失、路径不安全等）。
2. 若不同来源文件写入 **同一个输出文件**，弹出冲突警告。
3. 若输出文件 **已存在**，弹出覆盖确认（最多列出 5 个文件）。
4. 后台批量运行；操作栏的预览按钮变为 **取消**。
5. 完成后填写执行结果列，并弹出 `成功数/处理数` 的完成提示（有跳过时附带跳过数）。获取文档信息模式下仅当有行失败时才弹窗。

执行结果列已有值的分组会被跳过，因此再次执行只处理新增行。

### 4.6 取消

处理中点击 **取消**（预览按钮改名而来），会在当前文件处理完后停止。状态栏显示“操作已取消”。

### 4.7 导入与导出

- **导入**、**导出** 在单元格右键菜单中。
- **导出** 会写出表头行与行标签，所以“导出→编辑→导入”往返能保持结构一致。
- 导入会自动识别导出的标题行/标签列；普通数据表按 1:1 导入，不会丢失首行或首列。
- 导入的文件同样受 200 MB 限制。

---

## 5. 各标签页详解

### 5.1 Excel

**填写方式：占位符替换 / 按标题填写**

**占位符替换**

- 在工作簿中查找包含占位符文本的单元格（子串匹配，不要求 `{{ }}` 花括号）。
- 单值：所有出现位置替换为同一个值；多值：每行替换一个出现位置；图片：删除占位符并插入图片。
- 含有**公式**的单元格不会被覆盖（公式优先级最高）。
- 模板兼容性：若模板的文档属性 XML 畸形导致无法解析，工具会修复一份临时副本；**源文件不会被修改**。

**按标题填写**

- 找到文本等于标题的单元格（会去除首尾空白、规范化换行与连续空白），再按方向写入：
  - **向下** → 标题下方单元格；
  - **向右** → 标题右侧单元格；
  - **坐标** → 标题本身作为单元格地址（`A1`、`Sheet1!C5`）。
- **合并单元格 / 相同背景色加共同外框区域**：值写到区域最后一行的下一行（向下）或最后一列的右一列（向右）。
- 多值时，第 N 行的值写到区域下方第 N 行 / 右侧第 N 列。
- 公式单元格会被跳过。

### 5.2 Word

**填写方式：占位符替换**

- 在整篇文档中替换占位符文本：正文段落、表格、页眉与页脚。
- **目标页** 把替换限制在某一页（通过分页符/分节符近似分页）；留空 = 所有页。
- 若某数据项为“图片”类型且提供了图片路径，则删除占位符并插入图片。
- 旧版 `.doc`（OLE2）不支持：执行时在执行结果列写入 `失败：不支持 .doc 格式，请使用 .docx`；获取文档信息计入失败行；预览显示同样提示。请先另存为 `.docx`。

### 5.3 PowerPoint

**填写方式：占位符替换**

- 在幻灯片的所有文本框中替换占位符文本。
- **目标页** 选择幻灯片编号；留空 = 所有幻灯片。
- 图片以浮动形状插入，只移除占位符本身，文本框内其他文字与其他占位符的替换结果都会保留。
- 旧版 `.ppt`（OLE2）不支持（与 `.doc` 类似）。请先另存为 `.pptx`。

### 5.4 PDF

**填写方式：占位符替换 / 插入图片 / 插入文本 / 插入表格 / 删除表格**

**占位符替换**

- 在 PDF 文本中搜索占位符并替换（纯位图、无文本层的 PDF 无法处理）。
- 替换后的文本继承原占位符的字号、颜色与书写方向。
- 填写数量：单值 / 多值 / 图片（图片：删除占位符并插入图片）。**图宽 / 图高** 设置图片最大尺寸（像素，默认 200）。

**插入图片 / 插入文本 / 插入表格**

- 表头行隐藏；数据行中的值就是要插入的内容。
- 在操作栏选择 **位置**，工具在该位置查找可用空白区域：

| 位置 | 说明 |
|------|------|
| (全部)任意位置 | 页面任意位置 |
| (全部)左下 / 右下 / 左上 / 右上 | 从该角落开始查找 |
| (图框内)… | 仅在图纸图框内查找 |

- **插入文本**：**行高** 为行高占页高的比例（默认 0.015）；插入的文本为蓝色。
- **插入表格**：具有相同“保存文件”的连续行组成一张表格（行数 = 行数，列数 = 最宽行的列数）。**行高** 为行高比例（默认 0.015）；**紧贴** 可减小行距。
- **插入图片**：**宽度** 为图片宽度占页宽的比例（默认 0.06）；高度按原图纵横比换算。
- “行高/宽度”输入框会按填写方式分别记忆各自的取值。

**删除表格**——检测并删除 PDF 中的表格，无额外参数。

**其他说明**

- 插入类操作找不到合适空白区域时，会在执行结果列写入“失败：无空间插入…”，该文件被跳过。
- 加密 PDF 无法编辑（`失败：PDF 文件已加密，无法编辑`）。
- 已适配旋转页面（`/Rotate`）与竖排文字，替换与插入内容的方向正确。

### 5.5 关于

显示工具版本、开发者、AGPL v3 许可证、官方网站、问题与建议链接，以及推荐工具卡片（灵表文件处理、灵表BOM比对、装柜计算器、获取更多工具）。

---

## 6. 安全与限制

| 项目 | 说明 |
|------|------|
| 源文件 | 创建文档不修改源文件（使用工作副本）；获取文档信息只读 |
| 覆盖 | 输出文件已存在时必须确认才会覆盖 |
| 输出冲突 | 不同来源写入同一输出文件时会警告 |
| 执行结果列 | 防止误重复生成；需手动清空才会重新生成 |
| 大小限制 | 源文件超过 200 MB 在解析前被拒绝（防 zip bomb） |
| 格式安全 | `.doc/.xls/.ppt`（OLE2）与放错标签页的文件会给出明确提示，而不是崩溃 |
| 路径安全 | 含 `..` 的路径会被拒绝 |
| 公式安全 | Excel 中含公式的单元格不会被覆盖 |
| 依赖库 | Excel/Word/PPT/PDF 处理需要 `openpyxl`、`python-docx`、`python-pptx`、`PyMuPDF (fitz)`；图片处理使用 `Pillow` |

---

## 7. 技巧与最佳实践

1. **使用清晰的占位符**（如 `{{Name}}`、`{{Date}}`），便于识别与填写。
2. **每个占位符/标题占一个数据列。** 表头按列设置，因此不同列可指向不同页/工作表。
3. **多值行复用同一个“保存文件”**（继承行），即可让一个文档填入多个值。
4. **保存文件用相对路径**时，输出会落在模板所在目录。
5. **新模板先预览再执行**，尤其是 PDF 的插入位置。
6. **执行后检查执行结果列**；需要重新生成时再手动清空。
7. **获取文档信息是快速的批量审查工具**：把大量路径粘贴到“待操作文件”，执行后把网格导出为 Excel。
8. **模板保持在 200 MB 以内**，并先把旧版 Office 格式转换为新格式。
9. **按列设置目标页/工作表**；留空则处理全部。

---

## 8. 常见问题 / 故障排查

**问：预览按钮是灰的。**
当前是 **获取文档信息** 模式，该模式没有预览。请把“操作”切回 **创建文档**。

**问：执行时提示“没有数据可处理”。**
网格里没有带“待操作文件”的数据行。请填写待操作文件（创建文档还需保存文件），或导入表格。

**问：执行前提示“源文件不存在” / “图片文件不存在”。**
某个待操作文件或图片路径不存在。按提示的行号修正路径。

**问：提示“这是 Word 文档，请在 Word 标签页操作”。**
文件类型与当前标签页不符。请切换到正确的标签页（或转换文件）。Excel、PowerPoint 同理。

**问：提示“失败：不支持 .doc 格式”（或 `.ppt`）。**
旧版二进制 Office 格式无法读取。请用 Office 打开后另存为 `.docx` / `.pptx` 再使用。

**问：提示“失败：PDF 文件已加密”。**
带密码的 PDF 无法编辑，请先取消密码保护。

**问：提示“失败：文件过大（最大 …）”。**
源文件超过 200 MB，请拆分或压缩后再处理。

**问：提示“文件已存在，是否覆盖？”。**
保存文件已存在。选择“是”覆盖，或“否”并修改路径。注意：执行结果列已有值的分组不会触发此提示，因为它们会被跳过。

**问：什么都没生成，提示全部被跳过。**
这些分组的执行结果列已有值。选中这些“执行结果”单元格按 **Delete** 清空后再执行；上次失败的请先修正错误。

**问：再次执行只处理了一部分行。**
这是跳过机制：执行结果列非空的行会被跳过。状态栏的 `处理完成: x/y (已跳过: n)` 可确认。

**问：提示“以下输出文件存在冲突（多行数据写入同一文件）”。**
不同的来源文件映射到了同一个保存文件。请为每个来源指定各自的输出路径；若是多值共用同一输出，确认即可。

**问：占位符没有被替换。**
- 占位符文本必须完全匹配（含花括号与空格）。
- 检查 **目标Sheet页/目标页**；非法或超范围的值会跳过该列。
- Word/PDF 中占位符必须存在于文本层（纯扫描图片的 PDF 无法处理）。
- Excel 中含公式的单元格不会被覆盖。

**问：Excel 按标题填写时值写到了错误的单元格。**
检查 **填写方向**：向下写在标题下方，向右写在右侧，“坐标”则把标题当作地址。合并单元格或外框区域会把值写在区域之后。

**问：提示“失败：无空间插入文本/表格/图片”。**
所选位置找不到足够的空白区域。可换一个 **位置**（其他角落或“任意位置”）、减小行高/宽度，或启用“紧贴”。

**问：PDF 插入的文本为什么是蓝色？**
这是固定设计，插入文本使用蓝色。

**问：图片太大 / 太小。**
占位符图片模式请设置 **图宽 / 图高**（像素）；插入图片模式请设置 **宽度** 比例。

**问：从 Excel 粘贴时丢失了前几行。**
请使用当前版本；粘贴现在读取 HTML 剪贴板格式，会保留选区首尾的空行。若仍出现，请粘贴到第一个数据行并检查选区。

**问：导入后丢失了首行/首列。**
导入器会自动识别导出的标题行/标签列；没有标题的普通数据表按 1:1 导入。必要时先“导出”获得规范布局。

**问：Word 页数显示“无(python-docx无法精确获取页数)”。**
Word 分页由渲染引擎决定，`python-docx` 无法读取，属正常现象，“页数”字段可能不可用。

**问：工具会修改我的模板吗？**
不会。创建文档会读取模板并把结果写入“保存文件”。请确保保存文件与来源文件不是同一个路径。

**问：可以同时跑多个标签页吗？**
不可以。同一时间只允许一个操作；运行期间其他按钮被禁用。请取消或等待完成后再继续。

---

## 9. 附录

### 9.1 获取文档信息字段

| 标签页 | 字段 |
|--------|------|
| Excel | 文件大小、工作表数、行数、列数、标题、作者、创建日期、修改日期、最后修改者 |
| Word | 文件大小、页数、字数、字符数、标题、作者、创建日期、修改日期、最后修改者 |
| PowerPoint | 文件大小、幻灯片数、幻灯片尺寸、标题、作者、创建日期、修改日期、最后修改者 |
| PDF | 页数、文件大小、页面方向、页面尺寸、标题、作者、创建日期、修改日期、加密状态 |

不可用的值显示为本地化的“无”。

### 9.2 执行结果提示

- 成功：`成功`。
- 失败：`失败：<原因>`，原因包括：文件不存在、权限不足、数据无效、无效的目标、超时、内存错误、不支持 `.doc/.ppt` 格式、无空间插入、未找到插入位置、PDF 已加密、文件过大、未知错误等。
- 无效的目标 Sheet/页：`无效的目标：<值>`。

### 9.3 限制

| 项目 | 限制 |
|------|------|
| 源文件大小 | 每个文件 200 MB |
| 数据列 | 50 |
| Excel 初始行 | 4 表头行 + 50 数据行 |
| 撤销步数 | 50 步单元格编辑 |

### 9.4 快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl+C / Ctrl+V | 复制 / 粘贴 |
| Ctrl+A | 全选 |
| Delete | 清空选中单元格 |
| Ctrl+Z / Ctrl+Shift+Z | 撤销 / 重做单元格编辑 |

### 9.5 术语表

| 术语 | 含义 |
|------|------|
| 待操作文件（来源文件） | 模板（创建文档）或待检查文件（获取文档信息） |
| 保存文件（输出文件） | 生成的输出路径 |
| 占位符 | 模板中将被数据替换的文本 |
| 标题 | 按标题填写的定位锚点 |
| 继承行 | 没有自己的路径、沿用上方路径的行 |
| 目标页 / 目标Sheet页 | 要操作的工作表 / 页 / 幻灯片 |
| 填写数量 | 单值 / 多值 / 图片 |
| 获取文档信息 | 读取元信息而不是生成文件 |

---

> **文档版本**：1.0.0
> **最后更新**：2026-09-17
