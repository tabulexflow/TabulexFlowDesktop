# TabulexFileOperator User Manual

> **Document Version**: 1.0.0
> **Last Updated**: 2026-09-17
> **Applies to**: TabulexFileOperator 1.0.0 (BuiltinProgram, AGPL v3, works offline)
> **Target Audience**: End users

> **中文版请翻到后半部分 / Chinese version below** ↓

TabulexFileOperator is a built-in tool of TabulexFlow. It performs batch operations on files and folders through a spreadsheet-like grid: **Search, Rename, Move, Copy, Compress, Decompress, Delete, Deduplicate**. It never operates on anything until you click **Execute**, and every executed operation can be undone.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Quick Start (5 minutes)](#2-quick-start-5-minutes)
3. [Interface Reference](#3-interface-reference)
4. [Core Concepts and Common Operations](#4-core-concepts-and-common-operations)
5. [Tab Reference](#5-tab-reference)
6. [Safety and Recovery](#6-safety-and-recovery)
7. [Tips and Best Practices](#7-tips-and-best-practices)
8. [FAQ / Troubleshooting](#8-faq--troubleshooting)
9. [Appendix](#9-appendix)

---

## 1. Introduction

### 1.1 What TabulexFileOperator Can Do

| Tab | What it does | Touches disk only on Execute |
|-----|--------------|------------------------------|
| Search | Find files/folders by name, extension, wildcard or regular expression and add them to the grid | No |
| Rename | Batch rename with 10 methods (text, position, prefix/suffix, case, regex, numbering, placeholders, MP3 tags) | Yes |
| Move | Move files/folders to a target folder, with folder-layout and conflict options | Yes |
| Copy | Batch copy files/folders, with the same options as Move | Yes |
| Compress | Group grid rows and create one ZIP per group | Yes |
| Decompress | Extract `.zip` / `.tar` / `.tar.gz` / `.tar.bz2` / `.tar.xz` / `.7z` archives | Yes |
| Delete | Batch delete by file-name/size/date filters, to the Recycle Bin | Yes |
| Deduplicate | Find duplicate files by name, size, fingerprint or hash, and delete the redundant ones | Yes |
| About | Version, developer, license, feedback and recommended tools | No |

- All processing is done locally. No account, no network, no upload.
- The interface has 6 languages: 简体中文, English, Français, Русский, Español, العربية.

### 1.2 Key Concepts

- **Grid (the table)**: one row = one file or folder to be processed. Only the first three columns — **Old Path**, **New Path**, **Match Name** — can be edited; the rest are information and results.
- **Old Path**: the existing file/folder on disk.
- **New Path**: the destination path the operation will produce. It can be computed automatically (by Apply or by Preview/Execute) or typed/pasted/imported by you.
- **Result column**: shows what will happen (preview) or what did happen (execute) for each row.
- **Apply / Preview / Execute** (see [4.1](#41-apply--preview--execute)):
  - **Apply** computes results and writes them into the grid. It never touches disk.
  - **Preview** predicts the outcome without touching disk.
  - **Execute** performs the real operation on disk (after a confirmation dialog).
- **Undo / Redo**: the **Edit** menu of the main window lets you undo or redo a whole Apply/Preview/Execute operation, including the real files on disk.

### 1.3 Safety First

- **Delete and Deduplicate move files to the Recycle Bin**, not permanent deletion, so you can still restore them from the system trash.
- **Execute is the only action that changes your files.** Editing the grid, Apply and Preview never do.
- Every Execute asks for confirmation and shows the current conflict settings.
- Every executed operation is undoable from the **Edit** menu (up to 20 steps, per session). Conflicting files are backed up automatically to a temporary folder before being overwritten/replaced/deleted.

---

## 2. Quick Start (5 minutes)

Goal: rename every `.jpg` image in a folder by adding a `Trip_` prefix.

1. **Open the tool**: in the main window tool grid, click the **Tabulex File Operator** card.
2. **Collect the files** — go to the **Search** tab:
   - **Search Path**: click **Browse..** and choose your folder.
   - **Match**: choose **Images (Preset)**. The Match Name box is filled with the image extensions automatically.
   - Keep **Recursive** checked if you also want files in sub-folders.
   - Click **Apply & Add**. Matching files are appended to the grid.
3. **Check the grid**: the Old Path column now lists the files. Fix or remove any unwanted rows.
4. **Rename** — go to the **Rename** tab:
   - **Naming Method**: choose **Add prefix or suffix**.
   - Select **Prefix** and type `Trip_` in the Prefix box.
   - Click **Apply**. The New Path column now shows the renamed paths.
5. **Preview**: click **Preview** and read the Result column (e.g. `Preview: Will be renamed`). Nothing on disk has changed yet.
6. **Execute**: click **Execute**, confirm the dialog. The files are renamed.
7. **Made a mistake?** Open the main window menu **Edit → Undo** to restore both the grid and the files.

> Tip: you can do the whole job with several rule passes (for example prefix first, then numbering) before a single Execute.

---

## 3. Interface Reference

### 3.1 Tabs

Across the top there are 9 tabs:

**Search · Rename · Move · Copy · Compress · Decompress · Delete · Deduplicate · About**

The first eight share the same grid; switching tabs keeps the grid content in place. The **About** tab replaces the grid area with version/license information and recommended-tool cards.

### 3.2 Toolbar

Each tab has its own toolbar above the grid:

- Row 1 usually holds the **inputs and the Apply button**.
- Row 2 usually holds the **conflict handling + Preview + Execute buttons**, and a **Stop** function while an operation is running.
- A **❔** help icon next to some dropdowns shows the full explanation of that option.

### 3.3 Grid Columns

| # | Column | Editable | Meaning |
|---|--------|----------|---------|
| 1 | Old Path | Yes | Source file/folder absolute path |
| 2 | New Path | Yes | Destination path |
| 3 | Match Name | Yes | The match name that found this row (used for grouping) |
| 4 | Result | No | Preview/execute status |
| 5 | Parent Dir | No | Parent folder name of Old Path |
| 6 | File Name | No | File/folder name of Old Path |
| 7 | Level | No | Depth relative to the search folder |
| 8 | Type | No | File or Directory |
| 9 | Size (KB) | No | File size |
| 10 | Created | No | Creation time |
| 11 | Modified | No | Modification time |
| 12 | Hidden | No | Yes/No |
| 13 | Read-Only | No | Read Only / Writable |

> **Paths must be absolute** (e.g. `/home/user/a.txt`, `D:\data\a.txt`). Relative paths and UNC paths (`\\server\share`) are not supported.

### 3.4 Grid Right-Click Menus and Shortcuts

Right-click a **cell**:

| Item | Shortcut | Item | Shortcut |
|------|----------|------|----------|
| Select All | Ctrl+A | Open Item | — |
| Deselect All | Esc | Open Containing Directory | — |
| Delete | Del | Copy Path | — |
| Copy | Ctrl+C | Import Table | Ctrl+I |
| Paste | Ctrl+V | Export Table | Ctrl+E |
| Undo Paste | Ctrl+Z | Search Content | Ctrl+F |
| Redo Paste | Ctrl+Shift+Z | | |

Right-click a **column header**: Sort Ascending / Sort Descending / Copy Data / Delete Data (editable columns only).
Right-click a **row header**: Insert Row / Delete Row / Copy Data / Delete Data.

- **Open Item** asks for confirmation before opening executable/script files (`.exe`, `.bat`, `.cmd`, `.ps1`, ...).
- **Search Content** (Ctrl+F) searches only the first three columns and offers Previous/Next navigation.
- **Undo/Redo Paste** here is cell-level editing undo; it does not undo file operations. Use the **Edit** menu for operation-level undo (see [4.5](#45-undo--redo--reset)).

### 3.5 Status Bar

- **Left**: progress and status of the current operation; when you select a cell it shows that cell's value (`Value: xxx` / `Value: (empty)`).
- **Right**: number of match names found.

### 3.6 Row Behavior

- The grid keeps at least 20 rows; after the last non-empty row it always keeps about 5 blank rows for new input.
- Rows added by Search are appended, not overwritten. Importing a table replaces everything (see [4.4](#44-import-and-export)).
- Drag & drop: you can drop files/folders from the file manager onto the grid, and drop a folder onto a path input box.

---

## 4. Core Concepts and Common Operations

### 4.1 Apply / Preview / Execute

The standard workflow for every operation is:

```
fill inputs → Apply → Preview → Execute
```

| Button | Changes the grid? | Changes disk? | Purpose |
|--------|-------------------|---------------|---------|
| **Apply** | Yes (writes New Path / Result) | No | Compute the result for all rows |
| **Preview** | Yes (writes Result only) | No | Predict the outcome row by row |
| **Execute** | Yes (after the fact) | **Yes** | Really perform the operation |

Rules that apply to all tabs:

- **Only Execute touches disk.**
- **Non-empty New Path is respected.** Preview and Execute always use the New Path you already have; they never overwrite it. They only fill in the New Path when it is empty, by computing it from the current settings.
- **Preview never writes into the New Path column** — it only writes the Result column.
- **Apply and Import are the only actions that may overwrite an existing New Path.**
- You may skip Apply and click Preview/Execute directly; empty New Path cells are computed automatically.
- While Preview/Execute is running, the button becomes **Stop**; click it to interrupt. The rows already processed stay recorded and can be undone.
- Result-column values you may see:
  - Preview texts: `Preview: Will be renamed / moved / copied / extracted / added to zip`, `Will be skipped / merged / replaced / overwritten`.
  - Deduplicate markers: `[NO DUPLICATE]`, `[WILL RETAIN]`, `[WILL DELETE]`.
  - Delete/dedup markers: `[WILL DELETE]`.
  - Problem markers: `[Invalid Path]`, `[Nonexistent Path]`, `[Not File]`, `[No Permission]`, `[Error: ...]`.
  - Execution results: `Success: ...`, `Failed: ...`, `Notice: ...`.

### 4.2 Conflict Handling

Every file-creating/moving tab has two dropdowns:

- **File conflict**: **Skip Duplicates** (keep the first, skip later same-named files) or **Overwrite Duplicates** (keep the last).
- **Directory conflict**: **Skip Duplicates**, **Merge Duplicates** (merge source content into the target folder), or **Replace Duplicates** (replace the target folder).

> The conflict dropdowns are **linked across tabs**: changing one tab's setting changes the others too.

Before overwriting, replacing or merging, the existing target is backed up to a temporary folder; if the backup fails, the operation is aborted rather than destroying data.

### 4.3 Interrupting an Operation

While Preview/Execute runs, click **Stop**. The operation ends at the next row. Rows already processed are reflected in the Result column and can still be undone.

### 4.4 Import and Export

- **Import (Ctrl+I)**: loads an Excel file and **replaces all grid data**. The first row of the active sheet must contain at least one of the headers `Old Path` or `New Path`. The easiest way to get a valid file is to export a template first.
- **Export (Ctrl+E)**: a dialog offers three modes via radio buttons (default: **Export data table**):
  - **Export directory tree text** — writes the folder structure starting at the search path as a `.txt` tree.
  - **Export template table** — an empty Excel file containing only the editable columns.
  - **Export data table** — an Excel file with all columns.

### 4.5 Undo / Redo / Reset

When TabulexFileOperator is open, the main window's menu bar gains an **Edit** menu:

| Item | What it does |
|------|--------------|
| **Undo** | Undoes the last Apply/Preview/Execute operation, including disk changes for Execute |
| **Redo** | Redoes the last undone operation |
| **Reset** | Restores all inputs to their startup defaults and clears the grid (asks for confirmation) |

- The menu items show the operation name and a summary, e.g. `Undo (Rename/Execute — 5 operations)`.
- Up to **20** operations per session are remembered.
- Undo of an Execute restores the files from the temporary backup, then restores the grid. If files were modified externally after the operation, a dialog lets you **Force Restore** or **Cancel undo**.
- Undo/Redo restore the **grid and files** but **not the input controls** — after undoing an Execute, the status bar reminds you: *Control parameters not restored, please verify before operating*.
- These menu actions have no keyboard shortcut, because Ctrl+Z/Ctrl+Y are reserved for cell-level editing undo.
- Backups live in the system temporary folder (`TabulexFileOperator_undo_backup`) and are deleted after undo, when pushed out of the 20-step history, and at tool startup.

### 4.6 Linked Target Path

The **Target Path** input boxes of **Move**, **Copy**, **Compress** and **Decompress** are linked: typing in one updates the other three. This lets you set the destination once.

---

## 5. Tab Reference

### 5.1 Search

**Row 1**

| Control | Meaning |
|---------|---------|
| Recursive | Also search sub-folders (default on) |
| Hidden | Also include hidden files/folders (default off) |
| Directory / File | Include directories / files in the result (File is on by default) |
| Search Path | Root folder to search (**Browse..** or drag & drop a folder) |
| Apply & Add | Run the search and append results to the grid |

**Row 2**

| Control | Meaning |
|---------|---------|
| Match | 14 match methods (see below) |
| Match Name | One name, or several separated by `/`; click **Set...** to enter one per line |
| ❔ | Match-method help |
| Import / Export | Table import/export |

**Match methods**

| Method | Rule |
|--------|------|
| Contains Full Name | Name contains the whole match name |
| Contains All Fragments | Name contains every space-separated fragment |
| Contains Any Fragment | Name contains at least one fragment |
| Equals Name | Name equals the match name |
| Starts with Name / Ends with Name | Prefix/suffix match |
| Images (Preset) | Sets `.jpg/.jpeg/.png/.gif/.bmp/.tiff/.webp/.svg/.ico` |
| Documents (Preset) | Sets `.xls/.xlsx/.doc/.docx/.ppt/.pptx/.pdf/.csv/.rtf/.odt/.ods/.odp` |
| Compressed (Preset) | Sets `.zip/.rar/.7z/.tar/.gz/.bz2/.xz/.iso` |
| Text (Preset) | Sets `.txt` |
| Exclude Full Names | Name contains none of the match names |
| Exclude Wildcards | Name matches none of the wildcards |
| Matches Wildcard | Name matches the wildcard, e.g. `report_*.xlsx` |
| Matches Regex | Name matches the Python regular expression |

Notes:

- In wildcard/regex modes the match name is **not** split into fragments.
- Put quotes around a fragment that contains spaces, e.g. `"annual report"*.pdf`.
- Switching between preset and non-preset methods clears the Match Name box.
- Search depth is limited to 20 levels; already-present paths are not added twice.
- The current Search Path is copied into the Move tab's Source Path automatically the first time you run Apply & Add.
- Regex safety limits: max 200 characters, max 10 quantifiers, max 3 nested quantifiers, 2-second timeout.

After searching, the status bar reports counts of found/duplicate/new paths, and lists match names that found nothing.

### 5.2 Rename

**Row 1** — pick a **Naming Method** (10 methods). Depending on the method, sub-mode radio buttons and parameter boxes appear:

| Naming Method | Parameters |
|---------------|------------|
| Original Name | — (restores the original name) |
| Replace Text | Sub-mode **By text** (Old Text, New Text) or **By position** (Position, Length, New Text) |
| Insert by Position | Position, New Text |
| Delete by Position | Position, Length |
| Add prefix or suffix | Sub-mode **Prefix** or **Suffix**, plus Text |
| Change case | **All uppercase / All lowercase / Camel case / Capitalize First** |
| Regex replace | Regex pattern, Replace with (supports `\1` back-references) |
| Add Number | Check **Before** to put the number before the name; **Grouping By**: None / Parent directory / Match name |
| Convert by Placeholder | New Text using placeholders (see below) |
| Rename MP3 | **Artist-Title / Title-Artist / Title only** (reads MP3 tags; falls back to the original name if tags are missing) |

- Position and Length are 1-based positions within the file name.
- **Add Number** produces padded numbers (`_01`, `_02`, ...); re-applying removes the old numbers first, so it will not accumulate.
- The base for rename is the current New Path if it is non-empty, otherwise the Old Path — so you can combine several rule passes.
- Invalid characters in a match name (`<>:"/\|*`) are removed.

**Placeholders** for *Convert by Placeholder*:

| Placeholder | Value |
|-------------|-------|
| `{{SERIAL_NUMBER}}` | Incrementing number from 1 |
| `{{CREATE_DATE}}` / `{{CREATE_TIME}}` | Creation date / time |
| `{{MODIFY_DATE}}` / `{{MODIFY_TIME}}` | Modification date / time |
| `{{MATCH_NAME}}` | Match name |
| `{{OLD_PARENT}}` / `{{OLD_DIR}}` | Original parent folder name / path |
| `{{OLD_BASE}}` | Original file name |
| `{{NEW_DIR}}` | New parent folder path |
| `{{SONG_AUTHOR}}` / `{{SONG_TITLE}}` | MP3 artist / title |

**Row 2** — conflict handling, **Preview**, **Execute**.

Rename steps: choose method → **Apply** (writes New Path) → **Preview** → **Execute**.

### 5.3 Move

**Row 1**: **Source Path** (what the Old Path must be under) and **Target Path**, each with **Browse..**; click **Apply** to compute the New Path.

**Row 2**: conflict handling, **Folder** layout, **Preview**, **Execute**.

**Folder layout** options:

| Option | New Path |
|--------|----------|
| Keep Structure | `target/relative_path` |
| Match Subfolder | `target/match_name/name` |
| Match + Structure | `target/match_name/relative_path` |
| Remove Parent Folder | The row's New Path with one parent level removed |
| Flatten Files | `target/name` (everything into the target root) |

Notes:

- The Old Path must be under the Source Path; otherwise the row is reported as not under the source path.
- Remove Parent Folder and Flatten Files ignore match-name subfolders.
- Merging folders follows the **Directory conflict** setting and merges recursively.

### 5.4 Copy

The Copy tab is identical to Move (same layout, folder options and conflict settings); it copies instead of moving, and the source is left in place.

### 5.5 Compress

**Row 1**: **Compression Group** — **Group by Directory** or **Group by Name** — plus the ❔ help, **Target Path** and **Apply**.

**Row 2**: conflict handling, **Preview**, **Execute**.

Grouping and ZIP contents:

- **Group by Directory**: rows sharing a parent folder name go into `(folder_name).zip`. Files are stored as `group/file_name`; folders as `group/relative_path`.
- **Group by Name**: rows sharing a Match Name go into `(match_name).zip`. Files are stored as `match_name/file_name`; folders as `match_name/base_name/relative_path`. Empty match names fall back to the directory rule.
- When no Target Path is given, the ZIP location is auto-computed: the parent of the search folder if available, otherwise the most common parent of the grid paths, otherwise the current working directory.
- When a Target Path is given, it must be a directory; it is created on Execute if missing, and every ZIP is written there.
- If a ZIP already exists, the **Directory conflict** setting decides: Skip (leave it), Merge (append non-duplicate entries), or Replace (back up the old ZIP, then recreate). A failed backup aborts the operation.
- Limits: single file 2 GB, ZIP 4 GB. Empty folders produce a notice instead of an archive.

### 5.6 Decompress

**Row 1**: **Decompression Group** — **Group by Package** or **Group by Match** — the ❔ help, **Target Path** and **Apply**.

**Row 2**: conflict handling, **Preview**, **Execute**.

Supported formats: `.zip`; `.tar`; `.tar.gz`/`.tgz`; `.tar.bz2`/`.tbz2`/`.tbz`; `.tar.xz`/`.txz`; `.7z`. **`.rar` is not supported.**

Grouping:

- **Group by Package**: each archive is extracted into a sub-folder named after the archive file (without extension).
- **Group by Match**: each archive is extracted into a sub-folder named after the row's Match Name (falls back to the archive name when empty).
- Group names are sanitized; illegal characters are removed.
- **Single top-level folder is stripped**: if an archive's first level contains exactly one folder and no files, that folder is skipped, so you do not get a double folder.
- If no Target Path is given, each archive is extracted next to the archive itself (archive folder + group name).
- Conflict handling is at **file and directory detail level** (skip / merge / replace), the same as Compress.
- Unsupported files, folders and invalid/empty rows are marked as skipped in the Result column.

### 5.7 Delete

**Row 1**: **Delete Filter** plus the ❔ help; relevant inputs appear depending on the filter.

| Filter | Input |
|--------|-------|
| Delete All | none |
| Name Contains / Name Not Contains | Contains Text / Not Contains Text |
| Size Less Than / Greater Than / Between | Minimum and Maximum + unit (B / KB / MB / GB) |
| Created Before / After / Between | Start and End time |
| Modified Before / After / Between | Start and End time |

**Row 2**: **Delete Target** — **Old Path** or **New Path** — **Preview** and **Execute**.

- Apply marks matching rows with `[WILL DELETE]` and reports how many will be deleted.
- Execute moves the matched files/folders to the **Recycle Bin**.
- The same path is deleted only once even if it appears several times.

### 5.8 Deduplicate

**Row 1**: **Deduplication Algorithm** and **Deduplication Rule**, plus ❔ help and **Apply**.

| Algorithm | Duplicate definition |
|-----------|----------------------|
| By Name | Same file name |
| Name + Size | Same file name and size |
| File Fingerprint | Same size + same first/last 1024 bytes |
| File Hash | Same size + same MD5 (head + middle + tail) |

| Rule | Kept file |
|------|-----------|
| Keep Latest / Earliest Creation | Newest / oldest creation time |
| Keep Latest / Earliest Modification | Newest / oldest modification time |
| Keep Longest / Shortest Name | Longest / shortest file name |
| Keep Longest / Shortest Path | Longest / shortest full path |

**Row 2**: **Delete Method** (Delete to Recycle Bin), **Preview**, **Execute**.

- Apply analyzes the grid and marks rows: `[NO DUPLICATE]`, `[WILL RETAIN]`, `[WILL DELETE]`.
- Execute moves the `[WILL DELETE]` files to the Recycle Bin.
- Only files are processed; folders are marked `[Not File]`, and unreadable files `[No Permission]`.

### 5.9 About

Shows the tool version, developer, AGPL v3 license, the official website, a feedback link, and recommended-tool cards (TabulexDocCreator, TabulexBomComparator, PalletLayout, Get More Tools).

---

## 6. Safety and Recovery

| Protection | Detail |
|------------|--------|
| Recycle Bin | Delete and Deduplicate move items to the system trash, not permanent deletion |
| Confirmation | Every Execute shows a warning dialog with the current operation and conflict settings |
| Automatic backup | Files/folders that would be overwritten, replaced, merged or deleted are copied to a temp backup first; a failed backup aborts the operation |
| Undo / Redo | Up to 20 operations per session, restoring both grid and disk (Edit menu) |
| External-change detection | When undoing an Execute, files changed outside the tool are detected and you choose Force Restore or Cancel |
| Non-destructive defaults | Apply/Preview never change disk; editing the grid never changes disk |
| Safety limits | Refuses non-absolute paths, over-long paths, and over-size files; sanitizes archive member names (blocks `..`, absolute paths, links) |

---

## 7. Tips and Best Practices

1. **Do one rule at a time, then combine.** For rename, apply a prefix, check the New Path column, then apply numbering.
2. **Always Preview before Execute** on large batches, and read the Result column.
3. **Use the Search tab to fill the grid** instead of typing paths; it also fills info columns (size, time, level).
4. **New Path is respected** — edit it freely; Preview/Execute will use your value and only fill empty cells.
5. **Set Target Path once** on Move/Copy/Compress/Decompress; the four fields are linked.
6. **Use conflict settings carefully**: Skip protects existing files; Overwrite/Merge/Replace rely on the automatic backup for undo.
7. **Export a template first** if you plan to prepare data in Excel and then Import.
8. **Grouping needs a Match Name**: when you use "Group by Name" for Compress/Decompress, make sure the Match Name column is filled (it is filled automatically by Search).
9. **If unsure, run Execute on a small test folder first**, then use Edit → Undo to roll back.

---

## 8. FAQ / Troubleshooting

**Q: Apply/Preview/Execute does nothing, and I get "No items to ...".**
The grid has no usable rows. Search and Apply & Add first, type Old Path values, or Import a table.

**Q: The Apply button is greyed out (Move/Copy).**
Fill in both Source Path and Target Path. Apply stays disabled until both are valid.

**Q: The Execute button is greyed out.**
An operation is already running; all operation buttons are disabled until it finishes. Click **Stop** to interrupt it or wait for it to complete.

**Q: Search finds nothing.**
- Check the Search Path is correct and absolute.
- Check whether you need **Recursive** (sub-folders) or **Hidden**.
- Check the match method: "Contains Full Name" needs the whole string, "Contains Any Fragment" is more permissive.
- Preset methods fill the Match Name for you; if you switched from a preset, re-enter the match name.

**Q: "Preview: Will be skipped" appears for some rows.**
The target already exists and the **File/Directory conflict** is set to Skip. Change it to Overwrite/Merge/Replace if that is what you want.

**Q: "File is locked by another program, skipped" / "File is in use, please close it first".**
The file is open in another program (e.g. Excel/WPS). Close it there and run the operation again.

**Q: "Path too long (248 chars), skipped" on Windows.**
Windows path length limits. Shorten the target path or use the Flatten Files / Match Subfolder layout.

**Q: "File too large (2 GB), skipped" or a ZIP exceeds 4 GB.**
These are the built-in limits. Split the work into smaller batches.

**Q: "Permission denied" / "No permission".**
Windows: run TabulexFlow as administrator for protected folders. Linux: check folder ownership/permissions.

**Q: A `.7z` file fails with "py7zr library missing".**
Install the optional `py7zr` package so 7z archives can be extracted.

**Q: I clicked Execute by mistake.**
Open the main window **Edit → Undo**. The files are restored from the temporary backup and the grid returns to its previous state. Do not modify the files manually beforehand, or a conflict dialog will appear.

**Q: The Undo conflict dialog appeared.**
Some files were changed outside the tool after the operation. Choose **Force Restore** to overwrite them with the backup, or **Cancel undo** to keep the current state.

**Q: After undo, the result says "Control parameters not restored".**
This is expected. Undo/Redo restore the grid and files, not the input controls; verify the parameters before running another operation.

**Q: Import fails with "No importable columns found".**
The first row of the active sheet must contain a header `Old Path` or `New Path`. Export a template first and fill it in.

**Q: Export has no directory-tree or data-table option available.**
Those two require at least one Old Path in the grid; only the template export is always available.

**Q: A row shows `[Invalid Path]`, `[Nonexistent Path]`, `[Not File]` or `[No Permission]`.**
The path is invalid, does not exist, is a folder where a file is required, or is not readable. Correct the row before executing.

**Q: I accidentally deleted a row / cleared a cell.**
Use the grid right-click **Undo Paste (Ctrl+Z)** for cell-level edits. For whole operations, use Edit → Undo.

**Q: The interface is too small / too large on a high-DPI screen.**
The tool follows the main application's DPI scaling; change the display scale or the app's settings.

---

## 9. Appendix

### 9.1 Limits

| Item | Limit |
|------|-------|
| Single file size | 2 GB |
| ZIP size | 4 GB |
| Windows path length | 248 characters |
| Search depth | 20 levels |
| Regex length / quantifiers / nested quantifiers / timeout | 200 / 10 / 3 / 2 s |
| Undo history | 20 operations per session |

### 9.2 Path Type Markers

- `[WILL DELETE]`, `[WILL RETAIN]`, `[NO DUPLICATE]` — deduplicate/delete predictions.
- `[Invalid Path]`, `[Nonexistent Path]`, `[Not File]`, `[No Permission]` — row problems.
- `[Error: ...]` — processing error.

### 9.3 Shortcuts

| Shortcut | Function |
|----------|----------|
| Ctrl+A | Select all cells |
| Ctrl+C / Ctrl+V | Copy / Paste cells |
| Ctrl+Z / Ctrl+Shift+Z | Undo / Redo cell edit |
| Del | Clear selected cells |
| Esc | Deselect |
| Ctrl+I / Ctrl+E | Import / Export table |
| Ctrl+F | Search content in the first three columns |

### 9.4 Glossary

| Term | Meaning |
|------|---------|
| Grid | The spreadsheet-like table of files/folders |
| Old Path | Source path |
| New Path | Destination path |
| Match Name | The keyword/extension that found a row; also used as a grouping name |
| Apply / Preview / Execute | Three operation levels: compute / predict / perform |
| Recycle Bin | System trash (Windows Recycle Bin or Linux/macOS trash) |
| BuiltinProgram | Built-in tool shipped with TabulexFlow |

---

> **Document Version**: 1.0.0
> **Last Updated**: 2026-09-17

---
---

# 灵表文件处理（TabulexFileOperator）使用手册

> **文档版本**：1.0.0
> **最后更新**：2026-09-17
> **适用版本**：TabulexFileOperator 1.0.0（内置工具 BuiltinProgram，AGPL v3，可离线使用）
> **面向读者**：最终用户

TabulexFileOperator 是 TabulexFlow 的内置工具，通过一张类似电子表格的网格对文件和目录进行批量操作：**搜索、重命名、移动、复制、压缩、解压、删除、去重**。只有点击**执行**时才会真正改动硬盘，且每一次执行都可以撤销。

---

## 目录

1. [简介](#1-简介)
2. [快速上手（5 分钟）](#2-快速上手5-分钟)
3. [界面说明](#3-界面说明)
4. [核心概念与通用操作](#4-核心概念与通用操作)
5. [各标签页详解](#5-各标签页详解)
6. [安全与恢复](#6-安全与恢复)
7. [技巧与最佳实践](#7-技巧与最佳实践)
8. [常见问题 / 故障排查](#8-常见问题--故障排查)
9. [附录](#9-附录)

---

## 1. 简介

### 1.1 TabulexFileOperator 能做什么

| 标签页 | 功能 | 是否仅在“执行”时改动硬盘 |
|--------|------|--------------------------|
| 搜索 | 按文件名、扩展名、通配符或正则查找文件/目录并加入网格 | 否 |
| 重命名 | 10 种批量重命名方式（文本、位置、前后缀、大小写、正则、编号、占位符、MP3 标签） | 是 |
| 移动 | 把文件/目录移动到目标目录，支持目录结构与冲突选项 | 是 |
| 复制 | 批量复制文件/目录，选项与移动相同 | 是 |
| 压缩 | 按分组把网格各行压缩为一个 ZIP | 是 |
| 解压 | 解压 `.zip` / `.tar` / `.tar.gz` / `.tar.bz2` / `.tar.xz` / `.7z` | 是 |
| 删除 | 按文件名/体积/时间过滤批量删除（移入回收站） | 是 |
| 去重 | 按文件名、大小、指纹或哈希查找重复文件并删除多余项 | 是 |
| 关于 | 版本、开发者、许可证、反馈与推荐工具 | 否 |

- 全部在本地处理，无需账号、无需联网、不上传文件。
- 界面支持 6 种语言：简体中文、English、Français、Русский、Español、العربية。

### 1.2 核心概念

- **网格（表格）**：一行 = 一个待处理的文件或目录。仅前三列——**旧路径**、**新路径**、**匹配名**——可编辑，其余列为信息与结果。
- **旧路径**：硬盘上现有的文件/目录。
- **新路径**：操作后要生成的目标路径。可由“应用”或“预览/执行”自动计算，也可由你手动输入/粘贴/导入。
- **执行结果列**：逐行显示“将要发生什么”（预览）或“已经发生了什么”（执行）。
- **应用 / 预览 / 执行**（见 [4.1](#41-应用--预览--执行)）：
  - **应用**：计算并把结果写入网格，不改动硬盘。
  - **预览**：预测结果，不改动硬盘。
  - **执行**：真正在硬盘上执行（弹确认框后）。
- **撤销 / 重做**：主窗口的“编辑”菜单可撤销/重做整次“应用/预览/执行”操作，包含硬盘上实际改动的文件。

### 1.3 安全第一

- **删除与去重都是移入回收站**，不是永久删除，仍可从系统回收站找回。
- **只有“执行”会改动你的文件**；编辑网格、应用、预览都不会。
- 每次执行都会弹出确认框，并显示当前冲突设置。
- 每次执行都可在“编辑”菜单撤销（单次会话最多 20 步）。被覆盖/替换/删除的目标会先自动备份到临时目录。

---

## 2. 快速上手（5 分钟）

目标：把某个文件夹里的所有 `.jpg` 图片统一加上 `Trip_` 前缀。

1. **打开工具**：在主窗口工具网格中点击 **Tabulex File Operator（灵表文件处理）** 卡片。
2. **收集文件**——进入 **搜索** 标签页：
   - **搜索路径**：点 **浏览..** 选择文件夹。
   - **匹配**：选择 **图片文件(预置)**，匹配名会自动填入图片扩展名。
   - 若需要包含子目录，保持 **递归** 勾选。
   - 点击 **应用并添加**，匹配到的文件会追加到网格中。
3. **检查网格**：旧路径列已列出这些文件，删除或修正不需要的行。
4. **重命名**——进入 **重命名** 标签页：
   - **重命名方式**：选择 **添加前缀或后缀**。
   - 选择 **前缀**，在“前缀”输入框中输入 `Trip_`。
   - 点击 **应用**，新路径列显示改名后的路径。
5. **预览**：点击 **预览结果**，查看执行结果列（如“预览：将被重命名”）。此时硬盘尚未改变。
6. **执行**：点击 **执行**，在确认框中确认，文件被重命名。
7. **出错了？** 打开主窗口菜单 **编辑 → 撤销操作**，可同时还原网格和文件。

> 提示：可以先连续做多轮规则（例如先加前缀，再加编号），最后只执行一次。

---

## 3. 界面说明

### 3.1 标签页

顶部共有 9 个标签页：

**搜索 · 重命名 · 移动 · 复制 · 压缩 · 解压 · 删除 · 去重 · 关于**

前 8 个共用同一张网格，切换标签页时网格内容保持不变；**关于**标签页会把网格区域替换为版本/许可证信息与推荐工具卡片。

### 3.2 操作栏

每个标签页在网格上方都有自己的操作栏：

- 第一行通常是**输入控件与“应用”按钮**。
- 第二行通常是**冲突处理 + “预览结果” + “执行”按钮**；操作进行中会提供**中断执行**。
- 部分下拉框旁的 **❔** 帮助图标会显示该选项的完整说明。

### 3.3 网格列

| 序号 | 列 | 可编辑 | 含义 |
|------|----|--------|------|
| 1 | 旧路径 | 是 | 源文件/目录的绝对路径 |
| 2 | 新路径 | 是 | 目标路径 |
| 3 | 匹配名 | 是 | 找到该行的匹配名（用于分组） |
| 4 | 执行结果 | 否 | 预览/执行状态 |
| 5 | 父目录名 | 否 | 旧路径的父目录名 |
| 6 | 文件或目录名 | 否 | 旧路径的文件/目录名 |
| 7 | 层级 | 否 | 相对于搜索目录的深度 |
| 8 | 类型 | 否 | 文件 / 目录 |
| 9 | 大小KB | 否 | 文件大小 |
| 10 | 创建时间 | 否 | 创建时间 |
| 11 | 修改时间 | 否 | 修改时间 |
| 12 | 隐藏 | 否 | 是/否 |
| 13 | 读写 | 否 | 只读 / 可写 |

> **路径必须是绝对路径**（如 `/home/user/a.txt`、`D:\data\a.txt`）。不支持相对路径和 UNC 路径（`\\server\share`）。

### 3.4 网格右键菜单与快捷键

在**单元格**上右键：

| 菜单项 | 快捷键 | 菜单项 | 快捷键 |
|--------|--------|--------|--------|
| 选择全部 | Ctrl+A | 打开此项 | — |
| 取消选择 | Esc | 打开所在目录 | — |
| 删除 | Del | 复制路径 | — |
| 复制 | Ctrl+C | 导入表格 | Ctrl+I |
| 粘贴 | Ctrl+V | 导出表格 | Ctrl+E |
| 撤销粘贴 | Ctrl+Z | 搜索内容 | Ctrl+F |
| 重做粘贴 | Ctrl+Shift+Z | | |

在**列标题**上右键：升序排列 / 降序排列 / 复制数据 / 删除数据（仅可编辑列）。
在**行标题**上右键：插入行 / 删除行 / 复制数据 / 删除数据。

- **打开此项** 在打开可执行/脚本文件（`.exe`、`.bat`、`.cmd`、`.ps1` 等）前会弹出警告确认。
- **搜索内容**（Ctrl+F）只搜索前三列，并提供“上一个/下一个”导航。
- 此处的**撤销/重做粘贴**是单元格级编辑撤销，不会撤销文件操作；整次操作的撤销请用**编辑**菜单（见 [4.5](#45-撤销--重做--重置)）。

### 3.5 状态栏

- **左侧**：当前操作的进度与状态；选中单元格时显示该单元格内容（`内容：xxx` / `内容：(空)`）。
- **右侧**：匹配名数量。

### 3.6 行行为

- 网格至少保留 20 行，并在最后一个非空行后保留约 5 个空行以便新增输入。
- 搜索结果是**追加**而非覆盖；导入会替换整表（见 [4.4](#44-导入与导出)）。
- 拖放：可从文件管理器把文件/目录拖到网格，或把目录拖到路径输入框。

---

## 4. 核心概念与通用操作

### 4.1 应用 / 预览 / 执行

每种操作的标准流程：

```
填写参数 → 应用 → 预览 → 执行
```

| 按钮 | 改动网格？ | 改动硬盘？ | 作用 |
|------|-----------|-----------|------|
| **应用** | 是（写入新路径/结果） | 否 | 为所有行计算结果 |
| **预览** | 是（只写结果列） | 否 | 逐行预测结果 |
| **执行** | 是（事后） | **是** | 真正执行操作 |

适用于所有标签页的规则：

- **只有“执行”会改动硬盘。**
- **尊重非空“新路径”。** 预览与执行始终沿用你已有的新路径，绝不覆盖；仅当新路径为空时，才按当前设置自动计算并填入。
- **预览绝不写入“新路径”列**，只写“执行结果”列。
- **只有“应用”和“导入”可能修改已有的非空新路径。**
- 可以跳过“应用”直接“预览/执行”，空白新路径会自动计算。
- 预览/执行进行中，按钮变为 **中断执行**，点击即可中断；已处理的行会被记录，仍可撤销。
- 执行结果列可能出现的内容：
  - 预览文本：`预览：将被重命名 / 将被移动 / 将被复制 / 将被解压 / 将加入压缩包`，`将被跳过 / 将合并 / 将被替换 / 将被覆盖`。
  - 去重标记：`[NO DUPLICATE]`、`[WILL RETAIN]`、`[WILL DELETE]`。
  - 删除/去重标记：`[WILL DELETE]`。
  - 问题标记：`[Invalid Path]`、`[Nonexistent Path]`、`[Not File]`、`[No Permission]`、`[Error: ...]`。
  - 执行结果：`成功：...`、`失败：...`、`提醒：...`。

### 4.2 冲突处理

所有会新建/移动文件的标签页都有两个下拉框：

- **文件冲突**：**跳过重名文件**（保留第一个，后续同名文件跳过）或 **覆盖重名文件**（保留最后一个）。
- **目录冲突**：**跳过重名目录**、**合并重名目录**（把源目录内容合并进目标目录）或 **替换重名目录**。

> 冲突下拉框**在各标签页间联动**：修改一个标签页的设置，其他标签页同步改变。

在覆盖、替换或合并前，已存在的目标会先备份到临时目录；若备份失败则中止操作，而不会破坏数据。

### 4.3 中断操作

预览/执行进行中点击 **中断执行**，操作会在下一行处结束。已处理的行会反映在执行结果列，且仍可撤销。

### 4.4 导入与导出

- **导入（Ctrl+I）**：加载 Excel 文件并**替换全部网格数据**。活动工作表第一行必须至少包含 `旧路径` 或 `新路径` 表头。最稳妥的方式是先导出一份模板再填写。
- **导出（Ctrl+E）**：弹出对话框，通过单选按钮选择方式（默认**导出数据表格**）：
  - **导出目录树文本**：从搜索目录开始，把目录结构导出为 `.txt` 目录树。
  - **导出模板表格**：导出只含可编辑列的空白 Excel 模板。
  - **导出数据表格**：导出包含所有列的 Excel 数据表。

### 4.5 撤销 / 重做 / 重置

打开 TabulexFileOperator 后，主窗口菜单栏会多出一个 **编辑** 菜单：

| 菜单项 | 作用 |
|--------|------|
| **撤销操作** | 撤销最近一次“应用/预览/执行”，执行类操作会连同硬盘一起还原 |
| **重做操作** | 重做最近一次被撤销的操作 |
| **重置** | 把所有输入恢复为启动默认值并清空网格（会二次确认） |

- 菜单项会动态显示操作名和摘要，如 `撤销操作 (重命名/执行 — 5项操作)`。
- 单次会话最多记忆 **20** 步。
- 撤销执行类操作时，先从临时备份还原文件，再恢复网格。若文件在操作后被外部修改，会弹出对话框让你选择 **强制还原** 或 **取消撤销**。
- 撤销/重做恢复的是**网格与文件**，**不恢复输入控件**——撤销执行后状态栏会提示：*控件参数未还原，请确认参数后再操作*。
- 这两个菜单项没有快捷键，因为 Ctrl+Z/Ctrl+Y 属于单元格级编辑撤销。
- 备份位于系统临时目录（`TabulexFileOperator_undo_backup`），在撤销后、被挤出 20 步历史时、以及每次启动工具时自动清理。

### 4.6 目标路径联动

**移动**、**复制**、**压缩**、**解压** 的 **目标路径** 输入框相互联动：在任意一个中输入，其余三个同步更新，便于只设置一次目标目录。

---

## 5. 各标签页详解

### 5.1 搜索

**第一行**

| 控件 | 说明 |
|------|------|
| 递归 | 同时搜索子目录（默认勾选） |
| 隐藏的 | 同时包含隐藏文件/目录（默认不勾选） |
| 目录 / 文件 | 结果中是否包含目录 / 文件（默认含文件） |
| 搜索路径 | 要搜索的根目录（**浏览..** 或拖放目录） |
| 应用并添加 | 执行搜索并把结果追加到网格 |

**第二行**

| 控件 | 说明 |
|------|------|
| 匹配 | 14 种匹配方式（见下表） |
| 匹配名 | 单个匹配名，或用 `/` 分隔的多个匹配名；点 **设置...** 可分行输入 |
| ❔ | 匹配方式帮助 |
| 导入 / 导出 | 表格导入/导出 |

**匹配方式**

| 方式 | 规则 |
|------|------|
| 包含完整匹配名 | 名称包含整个匹配名 |
| 包含匹配名所有片段 | 名称包含空格分隔的全部片段 |
| 包含匹配名任意片段 | 名称包含任一片段 |
| 等于匹配名 | 名称等于匹配名 |
| 以匹配名开头 / 以匹配名结尾 | 前缀 / 后缀匹配 |
| 图片文件(预置) | 自动填入 `.jpg/.jpeg/.png/.gif/.bmp/.tiff/.webp/.svg/.ico` |
| 办公文档(预置) | 自动填入 `.xls/.xlsx/.doc/.docx/.ppt/.pptx/.pdf/.csv/.rtf/.odt/.ods/.odp` |
| 压缩文件(预置) | 自动填入 `.zip/.rar/.7z/.tar/.gz/.bz2/.xz/.iso` |
| 文本文件(预置) | 自动填入 `.txt` |
| 排除所有匹配名整体 | 名称不包含任何匹配名 |
| 排除所有通配符整体 | 名称不匹配任何通配符 |
| 符合匹配名的通配符 | 名称匹配通配符，如 `报表_*.xlsx` |
| 符合匹配名的正则式 | 名称匹配 Python 正则表达式 |

说明：

- 通配符/正则模式下匹配名**不**按空格拆分片段。
- 片段内含空格时，用引号包裹，如 `"年度报告"*.pdf`。
- 在预置与非预置方式之间切换时，匹配名输入框会被清空。
- 搜索深度最多 20 层；已存在于网格中的路径不会重复添加。
- 首次点击“应用并添加”时，搜索路径会自动填入“移动”标签页的来源路径。
- 正则安全限制：最长 200 字符、量词最多 10 个、嵌套量词最多 3 个、匹配超时 2 秒。

搜索完成后，状态栏会报告找到/重复/新增的路径数量，并列出没有找到结果的匹配名。

### 5.2 重命名

**第一行**——选择 **重命名方式**（共 10 种），根据方式显示子模式与参数输入框：

| 重命名方式 | 参数 |
|------------|------|
| 原来的名字 | —（恢复原文件名） |
| 替换文本 | 子模式 **按文本**（旧文本、新文本）或 **按位置**（位置、长度、新文本） |
| 按位置插入 | 位置、新文本 |
| 按位置删除 | 位置、长度 |
| 添加前缀或后缀 | 子模式 **前缀** 或 **后缀**，加“文本” |
| 改变大小写 | **全部大写 / 全部小写 / 驼峰形式 / 首字母大写** |
| 正则表达式替换 | 正则式、替换为（支持 `\1` 反向引用） |
| 添加编号 | 勾选 **前面** 把编号放在名称前；**分组**：不分组 / 父目录 / 匹配名 |
| 按占位符转换 | 使用占位符的新文本（见下表） |
| 对MP3重命名 | **歌手-歌名 / 歌名-歌手 / 仅歌名**（读取 MP3 标签；缺失时回退原名） |

- “位置”和“长度”均为文件名中从 1 开始的位置。
- **添加编号** 生成补零编号（`_01`、`_02`…）；重复点击“应用”会先移除旧编号再重编，不会累积。
- 重命名的基准：新路径非空时以新路径为准，否则以旧路径为准——因此可组合多次规则。
- 匹配名中的非法字符（`<>:"/\|*`）会被剔除。

**占位符**（用于“按占位符转换”）：

| 占位符 | 含义 |
|--------|------|
| `{{SERIAL_NUMBER}}` | 从 1 开始递增的序号 |
| `{{CREATE_DATE}}` / `{{CREATE_TIME}}` | 创建日期 / 时间 |
| `{{MODIFY_DATE}}` / `{{MODIFY_TIME}}` | 修改日期 / 时间 |
| `{{MATCH_NAME}}` | 匹配名 |
| `{{OLD_PARENT}}` / `{{OLD_DIR}}` | 原父目录名 / 原父目录路径 |
| `{{OLD_BASE}}` | 原文件名 |
| `{{NEW_DIR}}` | 变更后的父目录路径 |
| `{{SONG_AUTHOR}}` / `{{SONG_TITLE}}` | MP3 歌手 / 标题 |

**第二行**——冲突处理、**预览结果**、**执行**。

重命名步骤：选择方式 → **应用**（写入新路径）→ **预览结果** → **执行**。

### 5.3 移动

**第一行**：**来源路径**（旧路径必须位于其下）与 **目标路径**，各有 **浏览..**；点击 **应用** 计算新路径。

**第二行**：冲突处理、**目录**布局、**预览结果**、**执行**。

**目录布局**选项：

| 选项 | 新路径 |
|------|--------|
| 保留结构 | `目标/相对路径` |
| 匹配名子目录 | `目标/匹配名/名称` |
| 匹配名+原结构 | `目标/匹配名/相对路径` |
| 消除父目录 | 该行新路径去掉一层父目录 |
| 展平文件 | `目标/名称`（全部放到目标根目录） |

说明：

- 旧路径必须位于来源路径下，否则该行会提示“旧路径不在来源路径下”。
- “消除父目录”和“展平文件”忽略匹配名子目录。
- 目录合并遵循 **目录冲突** 设置，并递归合并。

### 5.4 复制

复制标签页与移动完全相同（布局、目录选项、冲突设置一致），区别是复制而非移动，源文件保留在原地。

### 5.5 压缩

**第一行**：**压缩分组**——**按父目录名分组** 或 **按匹配名分组**——以及 ❔ 帮助、**目标路径**、**应用**。

**第二行**：冲突处理、**预览结果**、**执行**。

分组与 ZIP 内容：

- **按父目录名分组**：父目录名相同的行进入 `(父目录名).zip`。文件以 `分组名/文件名` 存储，目录以 `分组名/相对路径` 存储。
- **按匹配名分组**：匹配名相同的行进入 `(匹配名).zip`。文件以 `匹配名/文件名` 存储，目录以 `匹配名/目录名/相对路径` 存储。匹配名为空时回退为按父目录名分组。
- 未指定目标路径时自动计算位置：优先搜索目录的父目录；否则取网格路径中最常见的父路径；再否则取当前工作目录。
- 指定目标路径时，该路径必须是目录；执行时若不存在会自动创建，所有 ZIP 都保存到该目录。
- ZIP 已存在时由 **目录冲突** 决定：跳过 / 合并（追加不重名条目）/ 替换（先备份旧 ZIP 再重建）。备份失败会中止操作。
- 限制：单文件 2 GB、ZIP 4 GB；空目录不会生成压缩包，只给出提醒。

### 5.6 解压

**第一行**：**解压分组**——**按压缩包分组** 或 **按匹配名分组**——❔ 帮助、**目标路径**、**应用**。

**第二行**：冲突处理、**预览结果**、**执行**。

支持的格式：`.zip`；`.tar`；`.tar.gz`/`.tgz`；`.tar.bz2`/`.tbz2`/`.tbz`；`.tar.xz`/`.txz`；`.7z`。**不支持 `.rar`。**

分组：

- **按压缩包分组**：每个压缩包解压到以压缩包文件名（不带扩展名）命名的子目录。
- **按匹配名分组**：每个压缩包解压到以该行匹配名命名的子目录（为空时回退为压缩包文件名）。
- 分组名会规整，剔除非法字符。
- **自动剥离首层单一目录**：若压缩包第一层只有一个目录且没有文件，则跳过该层，避免出现双层目录。
- 未指定目标路径时，每个压缩包解压到压缩包自身所在目录下的分组子目录。
- 冲突处理按**文件与目录明细粒度**（跳过 / 合并 / 替换），与压缩相同。
- 不支持的文件、目录以及非法/空行会在执行结果列标记为跳过。

### 5.7 删除

**第一行**：**删除过滤** 与 ❔ 帮助；根据过滤方式显示相应输入：

| 过滤方式 | 输入 |
|----------|------|
| 删除全部文件 | 无 |
| 文件名包含 / 文件名不含 | 包含文本 / 不含文本 |
| 体积小于 / 大于 / 介于 | 最小值与最大值 + 单位（B / KB / MB / GB） |
| 创建时间早于 / 晚于 / 介于 | 开始时间 / 结束时间 |
| 修改时间早于 / 晚于 / 介于 | 开始时间 / 结束时间 |

**第二行**：**删除目标**——**旧路径** 或 **新路径**——**预览结果**、**执行**。

- “应用”会把命中的行标记为 `[WILL DELETE]`，并报告将删除的数量。
- “执行”把命中的文件/目录**移入回收站**。
- 同一路径即使出现多次也只删除一次。

### 5.8 去重

**第一行**：**查重算法** 与 **去重规则**，以及 ❔ 帮助、**应用**。

| 算法 | 重复的判定 |
|------|-----------|
| 按文件名 | 文件名相同 |
| 文件名+大小 | 文件名与大小都相同 |
| 文件指纹法 | 大小相同 + 首尾各 1024 字节相同 |
| 文件哈希法 | 大小相同 + MD5 相同（头 + 中 + 尾） |

| 去重规则 | 保留的文件 |
|----------|-----------|
| 保留创建时间最晚 / 最早的 | 创建时间最新 / 最旧 |
| 保留修改时间最晚 / 最早的 | 修改时间最新 / 最旧 |
| 保留文件名最长 / 最短的 | 文件名最长 / 最短 |
| 保留路径最长 / 最短的 | 完整路径最长 / 最短 |

**第二行**：**删除方法**（删除到回收站）、**预览结果**、**执行**。

- “应用”分析网格并标记：`[NO DUPLICATE]`、`[WILL RETAIN]`、`[WILL DELETE]`。
- “执行”把 `[WILL DELETE]` 的文件移入回收站。
- 只处理文件；目录标记为 `[Not File]`，不可读文件标记为 `[No Permission]`。

### 5.9 关于

显示工具版本、开发者、AGPL v3 许可证、官方网站、问题与建议链接，以及推荐工具卡片（灵表文档创建、灵表BOM比对、装柜计算器、获取更多工具）。

---

## 6. 安全与恢复

| 保护机制 | 说明 |
|----------|------|
| 回收站 | 删除与去重都是移入系统回收站，而非永久删除 |
| 二次确认 | 每次“执行”都会弹出警告框，显示当前操作与冲突设置 |
| 自动备份 | 将被覆盖、替换、合并或删除的目标会先复制到临时备份；备份失败则中止操作 |
| 撤销 / 重做 | 单次会话最多 20 步，同时还原网格与硬盘（“编辑”菜单） |
| 外部修改检测 | 撤销执行类操作时会检测被工具之外修改的文件，由你选择强制还原或取消 |
| 非破坏性默认 | 应用/预览不改动硬盘；编辑网格不改动硬盘 |
| 安全限制 | 拒绝非绝对路径、过长路径、过大文件；规整压缩包成员名（拦截 `..`、绝对路径、链接） |

---

## 7. 技巧与最佳实践

1. **一次一条规则，再组合**：重命名时先加前缀、检查新路径列，再加编号。
2. **大批量务必先预览再执行**，并仔细阅读执行结果列。
3. **用搜索标签页填充网格**，而不是手动输入路径；它会顺便填好大小、时间、层级等信息列。
4. **新路径会被尊重**——可自由编辑；预览/执行会沿用你的值，只填空单元格。
5. **目标路径设置一次即可**：移动/复制/压缩/解压四个输入框联动。
6. **谨慎选择冲突策略**：跳过能保护已有文件；覆盖/合并/替换依赖自动备份来撤销。
7. **先在 Excel 准备数据的话，先导出模板**再导入。
8. **分组依赖匹配名**：压缩/解压使用“按匹配名分组”时，确保匹配名列已填（搜索会自动填）。
9. **不确定时，先在小测试目录执行一次**，再用 编辑 → 撤销操作 回滚。

---

## 8. 常见问题 / 故障排查

**问：点应用/预览/执行没反应，提示“没有需要…的项目”。**
网格里没有可用行。请先搜索并“应用并添加”，或手动输入旧路径，或导入表格。

**问：移动/复制的“应用”按钮是灰的。**
需要同时填写来源路径和目标路径。两者都有效前“应用”一直禁用。

**问：“执行”按钮是灰的。**
已有操作在执行中；操作期间所有按钮都会被禁用。可点击 **中断执行** 或等待其完成。

**问：搜索不到任何文件。**
- 确认搜索路径正确且为绝对路径。
- 确认是否需要勾选 **递归**（子目录）或 **隐藏的**。
- 检查匹配方式：“包含完整匹配名”要求完整字符串，“包含匹配名任意片段”更宽松。
- 预置方式会自动填入匹配名；若从预置切换出来，请重新输入匹配名。

**问：某些行显示“预览：将被跳过”。**
目标已存在，且 **文件/目录冲突** 设为“跳过”。如确实要处理，改为“覆盖/合并/替换”。

**问：提示“文件被其他程序占用，已跳过” / “文件正在使用中，请先关闭”。**
文件被其他程序打开（如 Excel/WPS）。请先在那里关闭文件，再重新执行。

**问：Windows 下提示“路径过长(248字符)，已跳过”。**
受 Windows 路径长度限制。请缩短目标路径，或使用“展平文件/匹配名子目录”布局。

**问：提示“文件过大(2GB)，已跳过”或 ZIP 超过 4GB。**
这是内置限制。请拆分成更小的批次。

**问：提示“无权…/权限不足”。**
Windows：对受保护目录请以管理员身份运行 TabulexFlow。Linux：检查目录归属与权限。

**问：`.7z` 提示“缺少 py7zr 库”。**
安装可选的 `py7zr` 包后即可解压 7z 文件。

**问：误点了“执行”，怎么恢复？**
打开主窗口 **编辑 → 撤销操作**，文件会从临时备份还原，网格也会回到之前状态。请先不要手动改动这些文件，否则会触发冲突对话框。

**问：撤销时弹出了冲突对话框。**
说明有些文件在操作后被工具之外修改。选择 **强制还原** 用备份覆盖它们，或 **取消撤销** 保持现状。

**问：撤销后提示“控件参数未还原”。**
这是正常现象。撤销/重做只恢复网格与文件，不恢复输入控件；请确认参数后再执行下一次操作。

**问：导入失败，提示“未找到可导入的列”。**
活动工作表第一行必须包含 `旧路径` 或 `新路径` 表头。建议先导出模板再填写。

**问：导出时“导出目录树文本/数据表格”不可选。**
这两项要求网格中至少有一个旧路径；只有模板导出始终可用。

**问：某行显示 `[Invalid Path]`、`[Nonexistent Path]`、`[Not File]` 或 `[No Permission]`。**
路径非法、不存在、本应是文件却是目录，或不可读。修正该行后再执行。

**问：误删了某行 / 清空了某单元格。**
单元格级编辑请用网格右键 **撤销粘贴 (Ctrl+Z)**；整次操作用 **编辑 → 撤销操作**。

**问：高分屏上界面太小 / 太大。**
工具会跟随主程序的 DPI 缩放；请调整系统缩放或应用设置。

---

## 9. 附录

### 9.1 限制

| 项目 | 限制 |
|------|------|
| 单文件大小 | 2 GB |
| ZIP 大小 | 4 GB |
| Windows 路径长度 | 248 字符 |
| 搜索深度 | 20 层 |
| 正则长度 / 量词数 / 嵌套量词 / 超时 | 200 / 10 / 3 / 2 秒 |
| 撤销历史 | 单次会话 20 步 |

### 9.2 路径类型标记

- `[WILL DELETE]`、`[WILL RETAIN]`、`[NO DUPLICATE]`——去重/删除的预测标记。
- `[Invalid Path]`、`[Nonexistent Path]`、`[Not File]`、`[No Permission]`——行的问题标记。
- `[Error: ...]`——处理出错。

### 9.3 快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl+A | 全选单元格 |
| Ctrl+C / Ctrl+V | 复制 / 粘贴单元格 |
| Ctrl+Z / Ctrl+Shift+Z | 撤销 / 重做单元格编辑 |
| Del | 清空选中单元格 |
| Esc | 取消选择 |
| Ctrl+I / Ctrl+E | 导入 / 导出表格 |
| Ctrl+F | 在前三列中搜索内容 |

### 9.4 术语表

| 术语 | 含义 |
|------|------|
| 网格 | 类电子表格的文件/目录表格 |
| 旧路径 | 源路径 |
| 新路径 | 目标路径 |
| 匹配名 | 找到该行的关键字/扩展名，也用作分组名 |
| 应用 / 预览 / 执行 | 三个操作层级：计算 / 预测 / 实际执行 |
| 回收站 | 系统回收站（Windows 回收站或 Linux/macOS 的废纸篓） |
| BuiltinProgram | 随 TabulexFlow 一起发布的内置工具 |

---

> **文档版本**：1.0.0
> **最后更新**：2026-09-17
