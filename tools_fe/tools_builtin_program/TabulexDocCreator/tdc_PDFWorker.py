# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import sys
import os
_tool_dir = os.path.dirname(os.path.abspath(__file__))
if _tool_dir not in sys.path:
    sys.path.insert(0, _tool_dir)

import re
import math
import shutil
import tempfile
import time
import wx
from collections import defaultdict
from tdc_i18n_manager import translate, translate_list
from tdc_logger import log_info, log_error, log_warning, log_debug
from tdc_BaseDocWorker import tdc_BaseDocWorker, check_source_file_size

try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

class tdc_PDFWorker(tdc_BaseDocWorker):
    FRAME_MIN_RATIO = 0.7
    worker_type = 'pdf'
    # 插入文本模式的文字颜色（蓝色）
    INSERT_TEXT_COLOR = (0.0, 0.0, 1.0)
    # 插入表格模式的边框颜色（蓝色）；删除表格模式按此颜色识别需删除的边框线
    INSERT_TABLE_BORDER_COLOR = (4 / 255, 98 / 255, 225 / 255)
    
    def __init__(self, tool_instance, data, operation_mode, fill_method, params=None):
        super().__init__(tool_instance, data, operation_mode, fill_method, params)
        self._frame_cache = {}
        self._current_source_file = ''
    
    def _get_pixmap_scale(self, page_width, page_height, max_dimension=1200):
        if page_width <= max_dimension and page_height <= max_dimension:
            return 1.0
        scale = max_dimension / max(page_width, page_height)
        return scale
    
    def _detect_frame_inner_box(self, page, page_num=0, source_file=''):
        page_rect = page.rect
        page_width = page_rect.width
        page_height = page_rect.height
        
        cache_key = (source_file, page_num, page_width, page_height)
        if cache_key in self._frame_cache:
            return self._frame_cache[cache_key]
        
        result = self._detect_frame_opencv(page, page_width, page_height)
        if result is None:
            result = self._detect_frame_pixel_scan(page, page_width, page_height)
        
        self._frame_cache[cache_key] = result
        return result
    
    def _detect_frame_opencv(self, page, page_width, page_height):
        try:
            import cv2
            import numpy as np
        except ImportError:
            return None
        
        scale = self._get_pixmap_scale(page_width, page_height)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
        img_width = pix.width
        img_height = pix.height
        
        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(img_height, img_width, pix.n)
        if pix.n == 4:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGBA2GRAY)
        elif pix.n == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array
        
        _, binary = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
        edges = cv2.Canny(binary, 50, 150)
        
        min_horizontal_length = int(0.7 * img_width)
        min_vertical_length = int(0.7 * img_height)
        
        horizontal_lines = []
        for y in range(img_height):
            row = edges[y, :]
            runs = []
            start = -1
            for x in range(img_width):
                if row[x] > 0:
                    if start == -1:
                        start = x
                else:
                    if start != -1 and x - start >= min_horizontal_length:
                        runs.append((start, x - 1, y))
                    start = -1
            if start != -1 and img_width - start >= min_horizontal_length:
                runs.append((start, img_width - 1, y))
            horizontal_lines.extend(runs)
        
        vertical_lines = []
        for x in range(img_width):
            col = edges[:, x]
            start = -1
            for y in range(img_height):
                if col[y] > 0:
                    if start == -1:
                        start = y
                else:
                    if start != -1 and y - start >= min_vertical_length:
                        vertical_lines.append((x, start, y - 1))
                    start = -1
            if start != -1 and img_height - start >= min_vertical_length:
                vertical_lines.append((x, start, img_height - 1))
        
        if not horizontal_lines or not vertical_lines:
            return None
        
        best_frame = None
        best_score = float('inf')
        
        for h_start, h_end, top_y in horizontal_lines:
            left_candidates = [v for v in vertical_lines if v[1] <= top_y <= v[2]]
            if not left_candidates:
                continue
            left_x = min(v[0] for v in left_candidates)
            
            bottom_candidates = [h for h in horizontal_lines if h[2] > top_y + 50]
            for b_start, b_end, bottom_y in bottom_candidates:
                right_candidates = [v for v in vertical_lines
                                    if v[0] > left_x + 50 and v[1] <= top_y and v[2] >= bottom_y]
                if not right_candidates:
                    continue
                right_x = max(v[0] for v in right_candidates)
                
                frame_left = left_x + 2
                frame_right = right_x - 2
                frame_top = top_y + 2
                frame_bottom = bottom_y - 2
                
                if frame_right > frame_left + 50 and frame_bottom > frame_top + 50:
                    score = frame_left + frame_top
                    if score < best_score:
                        best_score = score
                        best_frame = {
                            'left': frame_left / scale,
                            'top': frame_top / scale,
                            'right': frame_right / scale,
                            'bottom': frame_bottom / scale
                        }
        
        return best_frame
    
    def _detect_frame_pixel_scan(self, page, page_width, page_height):
        scale = self._get_pixmap_scale(page_width, page_height)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
        img_width = pix.width
        img_height = pix.height
        pixels = pix.samples
        stride = pix.stride
        n = pix.n
        
        binary = [0] * (img_width * img_height)
        threshold = 240
        for y in range(img_height):
            row_start = y * stride
            for x in range(img_width):
                idx = row_start + x * n
                if n >= 3:
                    r = pixels[idx]
                    g = pixels[idx + 1]
                    b = pixels[idx + 2]
                    gray_val = int(0.299 * r + 0.587 * g + 0.114 * b)
                else:
                    gray_val = pixels[idx]
                binary[y * img_width + x] = 0 if gray_val > threshold else 1
        
        def get_pixel(x, y):
            if 0 <= x < img_width and 0 <= y < img_height:
                return binary[y * img_width + x]
            return 0
        
        def find_horizontal_line(y, min_length, search_left, search_right):
            line_start = -1
            line_end = -1
            x = search_left
            while x < search_right:
                if get_pixel(x, y) == 1:
                    if line_start == -1:
                        line_start = x
                    line_end = x
                else:
                    if line_start != -1 and line_end - line_start + 1 >= min_length:
                        return line_start, line_end
                    line_start = -1
                x += 1
            if line_start != -1 and line_end - line_start + 1 >= min_length:
                return line_start, line_end
            return None, None
        
        def find_vertical_line(x, min_length, search_top, search_bottom):
            line_start = -1
            line_end = -1
            y = search_top
            while y < search_bottom:
                if get_pixel(x, y) == 1:
                    if line_start == -1:
                        line_start = y
                    line_end = y
                else:
                    if line_start != -1 and line_end - line_start + 1 >= min_length:
                        return line_start, line_end
                    line_start = -1
                y += 1
            if line_start != -1 and line_end - line_start + 1 >= min_length:
                return line_start, line_end
            return None, None
        
        total_width = img_width
        total_height = img_height
        min_horizontal_length = int(0.7 * total_width)
        min_vertical_length = int(0.7 * total_height)
        
        log_debug(f'Frame detection (pixel scan fallback): size: {total_width}x{total_height}, min_h={min_horizontal_length}, min_v={min_vertical_length}')
        
        best_frame = None
        best_score = float('inf')
        
        for top_y in range(10, img_height - 50):
            top_start, top_end = find_horizontal_line(top_y, min_horizontal_length, 0, img_width)
            if top_start is None:
                continue
            
            left_x_start = None
            for x in range(10, img_width - 10):
                v_start, v_end = find_vertical_line(x, min_vertical_length, top_y, img_height)
                if v_start is not None:
                    left_x_start = x
                    break
            
            if left_x_start is None:
                continue
            
            for bottom_y in range(top_y + 50, img_height - 10):
                bottom_start, bottom_end = find_horizontal_line(bottom_y, min_horizontal_length, 0, img_width)
                if bottom_start is None:
                    continue
                
                right_x_start = None
                for x in range(left_x_start + 50, img_width - 10):
                    v_start, v_end = find_vertical_line(x, min_vertical_length, top_y, bottom_y)
                    if v_start is not None:
                        right_x_start = x
                        break
                
                if right_x_start is None:
                    continue
                
                left_intersects = False
                for y in range(top_y, bottom_y + 1):
                    if get_pixel(left_x_start, y) == 1:
                        left_intersects = True
                        break
                
                if not left_intersects:
                    continue
                
                right_intersects = False
                for y in range(top_y, bottom_y + 1):
                    if get_pixel(right_x_start, y) == 1:
                        right_intersects = True
                        break
                
                if not right_intersects:
                    continue
                
                frame_left = left_x_start + 2
                frame_right = right_x_start - 2
                frame_top = top_y + 2
                frame_bottom = bottom_y - 2
                
                if frame_right > frame_left + 50 and frame_bottom > frame_top + 50:
                    score = frame_left + frame_top
                    if score < best_score:
                        best_score = score
                        best_frame = {
                            'left': frame_left / scale,
                            'top': frame_top / scale,
                            'right': frame_right / scale,
                            'bottom': frame_bottom / scale
                        }
        
        if best_frame is not None:
            return best_frame
        
        return {'left': 0, 'top': 0, 'right': page_width, 'bottom': page_height}
    
    def execute(self):
        if not HAS_FITZ:
            self._show_error('PyMuPDF (fitz) library not installed')
            return False
        total_start = time.time()
        log_info(f'PDF processing started')
        is_table_mode = self.fill_method == 'add_table'
        is_delete_table_mode = self.fill_method == 'delete_table'
        is_get_file_info_mode = self.operation_mode == 'get_file_info'
        log_debug(f'PDFWorker: fill_method={self.fill_method}, operation_mode={self.operation_mode}, is_table_mode={is_table_mode}, is_delete_table_mode={is_delete_table_mode}, is_get_file_info_mode={is_get_file_info_mode}, data_count={len(self.data) if self.data else 0}')
        
        if is_get_file_info_mode:
            return self._execute_get_file_info()
        
        if is_table_mode or is_delete_table_mode:
            all_rows = []
            for row in self.data:
                if row.get('data'):
                    all_rows.append(row)
            if not all_rows:
                mode_name = 'delete table' if is_delete_table_mode else 'insert'
                self._show_error(f'No data to {mode_name}')
                return False
            save_files = {}
            current_save_file = None
            current_source_file = None
            for row in all_rows:
                save_file = row.get('save_file', '')
                source_file = row.get('source_file', '')
                data_items = row.get('data', [])
                has_data1 = False
                if data_items and len(data_items) > 0:
                    first_data = data_items[0].get('value', '')
                    has_data1 = bool(first_data and first_data.strip())
                if is_delete_table_mode:
                    if save_file and save_file.strip() and source_file and source_file.strip():
                        if not os.path.dirname(save_file) and source_file:
                            source_dir = os.path.dirname(source_file)
                            if source_dir:
                                save_file = os.path.join(source_dir, save_file)
                        if save_file not in save_files:
                            save_files[save_file] = {'source': source_file, 'rows': []}
                        save_files[save_file]['rows'].append(row)
                else:
                    if save_file and save_file.strip():
                        if not os.path.dirname(save_file) and source_file:
                            source_dir = os.path.dirname(source_file)
                            if source_dir:
                                save_file = os.path.join(source_dir, save_file)
                        current_save_file = save_file
                        current_source_file = source_file
                    elif has_data1 and current_save_file:
                        row['save_file'] = current_save_file
                        row['source_file'] = current_source_file
                    if row.get('save_file'):
                        target_save = row.get('save_file')
                        if target_save not in save_files:
                            save_files[target_save] = {'source': current_source_file, 'rows': []}
                        save_files[target_save]['rows'].append(row)
            file_count = len(save_files)
            self._total_groups = file_count
            self._skipped_success = 0
            self._skipped_error = 0
            mode_name = 'Table delete' if is_delete_table_mode else 'Table insert'
            log_info(f'Starting {mode_name.lower()} for {file_count} files')
            skipped_count = 0
            for idx, (save_file, file_info) in enumerate(save_files.items()):
                if self.cancelled:
                    break
                self._update_progress(idx + 1, file_count, os.path.basename(save_file))
                file_start = time.time()
                rows = file_info['rows']
                source_file = file_info['source']
                should_skip, has_error = self._get_group_result_state(rows)
                if should_skip:
                    log_info(f'PDFWorker: Skipping {save_file} - Result column is not empty')
                    self._record_skip(has_error)
                    skipped_count += 1
                    continue
                if not source_file or not os.path.exists(source_file):
                    log_error(f'Source file not found: {source_file}')
                    self.log_group_result(save_file, rows, False, error='Source file not found')
                    self.results.append({'file': save_file, 'success': False, 'error': 'Source file not found'})
                    continue
                # B3-2：解析前限制源文件大小（防资源耗尽）
                if not check_source_file_size(source_file):
                    log_error(f'Source file too large (>200 MB), skip: {source_file}')
                    self.log_group_result(save_file, rows, False, error='Source file too large (>200 MB)')
                    self.results.append({'file': save_file, 'success': False, 'error': translate('msg_file_too_large', size='200 MB'), 'raw_error': True})
                    continue
                # B6-2：异常路径清理临时文件（先初始化，避免异常时 NameError）
                temp_path = None
                try:
                    open_start = time.time()
                    temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
                    temp_path = temp_file.name
                    temp_file.close()
                    shutil.copy2(source_file, temp_path)
                    doc = fitz.open(temp_path)
                    if doc.is_encrypted:
                        doc.close()
                        if os.path.exists(temp_path):
                            try:
                                os.remove(temp_path)
                            except Exception:
                                pass
                        log_error(f'PDF file is encrypted: {save_file}')
                        self.log_group_result(save_file, rows, False, error='PDF file is encrypted')
                        self.results.append({'file': save_file, 'success': False, 'error': translate('msg_pdf_encrypted'), 'raw_error': True})
                        continue
                    open_time = time.time() - open_start
                    
                    insert_position = self._get_insert_position()
                    process_start = time.time()
                    inserted = False
                    if is_delete_table_mode:
                        self._process_delete_table_mode(doc, rows)
                        inserted = True
                    else:
                        inserted = self._process_insert_table_mode(doc, rows, insert_position)
                    process_time = time.time() - process_start
                    
                    save_start = time.time()
                    doc.save(save_file)
                    doc.close()
                    save_time = time.time() - save_start
                    
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass
                    
                    file_time = time.time() - file_start
                    log_info(f'File {idx+1}/{file_count} completed in {file_time:.2f}s (open: {open_time:.2f}s, process: {process_time:.2f}s, save: {save_time:.2f}s)')
                    
                    if inserted:
                        self.log_group_result(save_file, rows, True)
                        self.results.append({'file': save_file, 'success': True})
                    else:
                        self.log_group_result(save_file, rows, False, error=translate('result_no_valid_position'))
                        self.results.append({'file': save_file, 'success': False, 'error': translate('result_no_valid_position'), 'raw_error': True})
                except Exception as e:
                    log_error(f'Error processing table for {save_file}: {e}')
                    self.log_group_result(save_file, rows, False, error=str(e))
                    # B6-2：异常路径清理临时 PDF 副本（防止文档残留系统临时目录）
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass
                    self.results.append({'file': save_file, 'success': False, 'error': str(e)})
            self._clear_progress()
            total_time = time.time() - total_start
            mode_name = 'Table delete' if is_delete_table_mode else 'Table insert'
            log_info(f'{mode_name} completed: {file_count} files in {total_time:.2f}s, skipped: {skipped_count}')
            if not self.cancelled:
                self._show_results()
            return True
        grouped_data = self._group_data_by_save_file()
        file_count = len(grouped_data)
        self._total_groups = file_count
        self._skipped_success = 0
        self._skipped_error = 0
        skipped_count = 0
        for idx, (save_file, rows) in enumerate(grouped_data.items()):
            if self.cancelled:
                break
            self._update_progress(idx + 1, file_count, os.path.basename(save_file))
            should_skip, has_error = self._get_group_result_state(rows)
            if should_skip:
                log_info(f'PDFWorker: Skipping {save_file} - Result column is not empty')
                self._record_skip(has_error)
                skipped_count += 1
                continue
            try:
                result = self._process_file_group(save_file, rows)
                self.log_group_result(save_file, rows, result is True,
                                      error=None if result is True else str(result))
                if result is True:
                    self.results.append({'file': save_file, 'success': True})
                elif result is False:
                    self.results.append({'file': save_file, 'success': False, 'error': ''})
                else:
                    # 加密/无可用位置等已本地化的失败信息：按失败计入，“执行结果”原样显示
                    self.results.append({'file': save_file, 'success': False, 'error': str(result), 'raw_error': True})
            except Exception as e:
                log_error(f'Error processing {save_file}: {e}')
                self.log_group_result(save_file, rows, False, error=str(e))
                self.results.append({'file': save_file, 'success': False, 'error': str(e)})
        self._clear_progress()
        total_time = time.time() - total_start
        log_info(f'PDF processing completed in {total_time:.2f}s, skipped: {skipped_count}')
        if not self.cancelled:
            self._show_results()
        return True
    
    def _process_file_group(self, save_file, rows):
        if not rows:
            return False
        source_file = rows[0].get('source_file', '')
        if not source_file or not os.path.exists(source_file):
            log_error(f'Source file not found: {source_file}')
            return False
        # B3-2：解析前限制源文件大小（防资源耗尽）
        if not check_source_file_size(source_file):
            log_error(f'Source file too large (>200 MB), skip: {source_file}')
            return False
        self._current_source_file = source_file
        self._frame_cache = {k: v for k, v in self._frame_cache.items() if k[0] == source_file}
        save_dir = os.path.dirname(save_file)
        if save_dir and not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)
        temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        temp_path = temp_file.name
        temp_file.close()
        shutil.copy2(source_file, temp_path)
        doc = fitz.open(temp_path)
        if doc.is_encrypted:
            doc.close()
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            log_error(f'PDF file is encrypted: {source_file}')
            return translate('msg_pdf_encrypted')
        try:
            inserted = False
            error_msg = None
            if self.fill_method == 'placeholder':
                self._process_placeholder_mode(doc, rows)
                inserted = True
            elif self.fill_method == 'add_text':
                insert_position = self._get_insert_position()
                inserted = self._process_insert_text_mode(doc, rows, insert_position)
                if not inserted:
                    error_msg = translate('result_no_space_text')
            elif self.fill_method == 'add_table':
                insert_position = self._get_insert_position()
                result = self._process_insert_table_mode(doc, rows, insert_position)
                if result is True:
                    inserted = True
                else:
                    error_msg = result
            elif self.fill_method == 'add_image':
                insert_position = self._get_insert_position()
                inserted = self._process_insert_image_mode(doc, rows, insert_position)
                if not inserted:
                    error_msg = translate('result_no_space_image')
            elif self.fill_method == 'delete_table':
                self._process_delete_table_mode(doc, rows)
                inserted = True
            else:
                insert_position = self._get_insert_position()
                inserted = self._process_insert_text_mode(doc, rows, insert_position)
                if not inserted:
                    error_msg = translate('result_no_space_text')
            
            if not inserted:
                return error_msg if error_msg else translate('result_no_valid_position')
            
            doc.save(save_file)
            return True
        finally:
            doc.close()
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
    
    def _is_page_bitmap_only(self, page):
        text = page.get_text()
        if text and text.strip():
            return False
        return True
    
    def _process_placeholder_mode(self, doc, rows):
        column_target_pages = {}
        for row in rows:
            for item_idx, item in enumerate(row.get('data', [])):
                target_page = item.get('target_page', '')
                if item_idx not in column_target_pages and target_page:
                    column_target_pages[item_idx] = target_page.strip()
        
        all_target_pages = set(column_target_pages.values())
        if not all_target_pages:
            all_target_pages = {''}
        
        # 规格7.2.1：多值索引跨页保持，避免每页都从第一个值重新开始
        multi_value_consumed = {}
        for target_page in all_target_pages:
            page_range = self._parse_page_range(target_page, len(doc))
            for page_num in page_range:
                page = doc[page_num]
                if self._is_page_bitmap_only(page):
                    log_info(f'Page {page_num + 1} is bitmap only, skipping placeholder replacement')
                    continue
                self._process_page_placeholders(doc, page, rows, page_num, target_page, column_target_pages, multi_value_consumed)
    
    def _parse_page_range(self, target_page, total_pages):
        if not target_page:
            return range(total_pages)
        if target_page.isdigit():
            page_num = int(target_page)
            if 1 <= page_num <= total_pages:
                return range(page_num - 1, page_num)
            return range(0)
        # 非法目标页不再回退为“所有页”，返回空范围表示跳过
        return range(0)
    
    def _process_page_placeholders(self, doc, page, rows, page_num, current_target_page='', column_target_pages=None, multi_value_consumed=None):
        if multi_value_consumed is None:
            multi_value_consumed = {}
        column_info = {}
        for row in rows:
            for item_idx, item in enumerate(row.get('data', [])):
                placeholder = item.get('placeholder', '')
                if not placeholder or not placeholder.strip():
                    continue
                if column_target_pages and item_idx in column_target_pages:
                    if column_target_pages[item_idx] != current_target_page:
                        continue
                value = item.get('value', '')
                value_count = item.get('value_count', '')
                direction = item.get('direction', '')
                is_single = '单值' in value_count or 'single' in value_count.lower()
                is_multi = '多值' in value_count or 'multi' in value_count.lower()
                is_image = '图片' in value_count or 'image' in value_count.lower()
                if not (is_single or is_multi or is_image):
                    # 规格7.2.1：填写数量未设置时按“单值”处理，与其它 Tab 保持一致
                    is_single = True
                if item_idx not in column_info:
                    column_info[item_idx] = {
                        'placeholder': placeholder,
                        'values': [],
                        'value_count': value_count,
                        'direction': direction,
                        'is_single': is_single,
                        'is_multi': is_multi,
                        'is_image': is_image
                    }
                if is_single:
                    if value and value.strip() and not column_info[item_idx]['values']:
                        column_info[item_idx]['values'] = [value]
                elif is_multi:
                    if value and value.strip():
                        column_info[item_idx]['values'].append(value)
                elif is_image:
                    if value and value.strip():
                        column_info[item_idx]['values'] = [value]
        for item_idx, info in column_info.items():
            if not info['values']:
                continue
            placeholder = info['placeholder']
            values = info['values']
            is_single = info['is_single']
            is_multi = info['is_multi']
            is_image = info['is_image']
            total_width = self._get_total_width()
            areas = page.search_for(placeholder)
            if not areas:
                continue
            if is_image:
                self._replace_with_image(page, areas, values)
            elif is_single:
                self._replace_with_single_value(page, areas, values[0])
            elif is_multi:
                start_index = multi_value_consumed.get(item_idx, 0)
                multi_value_consumed[item_idx] = self._replace_with_multi_values(page, areas, values, start_index)
    
    def _replace_with_single_value(self, page, areas, value):
        for area in areas:
            self._replace_text_in_area(page, area, value)
    
    def _replace_with_multi_values(self, page, areas, values, start_index=0):
        value_idx = start_index
        for area in areas:
            if value_idx >= len(values):
                break
            self._replace_text_in_area(page, area, values[value_idx])
            value_idx += 1
        return value_idx
    
    def _replace_with_image(self, page, areas, values):
        if not values or not HAS_PIL:
            return
        img_path = values[0]
        if not os.path.exists(img_path):
            log_error(f'Image file not found: {img_path}')
            return
        # B3-2：解析前限制源文件大小（防资源耗尽）
        if not check_source_file_size(img_path):
            log_error(f'Image file too large (>200 MB), skip insert: {img_path}')
            return
        try:
            pil_img = Image.open(img_path)
            orig_width, orig_height = pil_img.size
            img_params = self.params.get('image_params', {}) or {'width': 200, 'height': 200}
            max_pixel_width = img_params.get('width', 200)
            max_pixel_height = img_params.get('height', 200)
            scale = min(max_pixel_width / orig_width, max_pixel_height / orig_height, 1.0)
            new_width = int(orig_width * scale)
            new_height = int(orig_height * scale)
            for area in areas:
                # 占位符可能因页面 /Rotate 或自身旋转而带方向，插入图片时需用相同
                # 旋转角，否则图片会相对页面内容被错误地横竖颠倒
                style = self._get_placeholder_style(page, area)
                angle = style['angle']
                # 图片矩形按“显示坐标系中左上角对准占位符首字符左上角”反算，
                # 再覆盖占位符（白底）后插入图片，保证图片图层在占位符之上
                rect = self._get_image_rect_for_area(page, area, angle, new_width, new_height)
                self._clear_placeholder(page, area, style)
                page.insert_image(rect, filename=img_path, rotate=angle)
                break
        except Exception as e:
            log_error(f'Failed to insert image: {e}')
    
    def _process_delete_table_mode(self, doc, rows):
        if not rows:
            log_debug('_process_delete_table_mode: no rows')
            return
        
        search_texts = []
        seen_texts = set()
        for row in rows:
            for item in row.get('data', []):
                value = item.get('value', '')
                if value and value.strip():
                    text = value.strip()
                    if text not in seen_texts:
                        seen_texts.add(text)
                        search_texts.append(text)
        
        if not search_texts:
            log_info('No search texts provided for table deletion')
            return
        
        log_debug(f'Searching for cell texts: {search_texts}')
        
        column_target_pages = {}
        for row in rows:
            for item_idx, item in enumerate(row.get('data', [])):
                target_page = item.get('target_page', '')
                if item_idx not in column_target_pages and target_page:
                    column_target_pages[item_idx] = target_page.strip()
        
        target_page = ''
        if column_target_pages:
            target_page = list(column_target_pages.values())[0]
        target_page = target_page.strip() if target_page else ''
        page_range = self._parse_page_range(target_page, len(doc))
        
        total_deleted = 0
        for page_num in page_range:
            page = doc[page_num]
            # 用文本搜索定位待删除区域
            text_rects = []
            for text in search_texts:
                text_rects.extend(page.search_for(text))
            if not text_rects:
                continue

            # 统一在显示坐标系（考虑页面 /Rotate）内做表格区域分析，避免旋转页上
            # 横纵关系错乱；最终经 derotation 矩阵换回未旋转坐标再做 redaction
            rot_matrix = page.rotation_matrix
            display_hits = [fitz.Rect(r) * rot_matrix for r in text_rects]
            table_disp, row_pitch = self._locate_table_display_region(display_hits)

            if row_pitch > 0:
                margin_side = max(4.0, 0.05 * row_pitch)
                margin_top = 0.15 * row_pitch
                margin_bottom = 0.25 * row_pitch
            else:
                margin_side = 4.0
                margin_top = max(5.0, 0.15 * table_disp.height)
                margin_bottom = max(10.0, 0.3 * table_disp.height)
            delete_disp = fitz.Rect(table_disp.x0 - margin_side, table_disp.y0 - margin_top,
                                    table_disp.x1 + margin_side, table_disp.y1 + margin_bottom)
            # redaction 必须使用未旋转坐标系下的矩形（与 add_redact_annot 一致），
            # 此前与 page.rect（已旋转）求交曾把坐标整体裁空，导致一页都没删
            target_rect = fitz.Rect(delete_disp * page.derotation_matrix) & page.mediabox
            if target_rect.is_empty or target_rect.width <= 0 or target_rect.height <= 0:
                continue
            # 第一遍：只按命中文本包围盒删除文字（不动页面其它线稿/图片）。
            # 不能像旧实现那样对 find_tables 的结果或 union 大矩形做
            # REMOVE_IF_TOUCHED：图纸自身互相接触的大量线稿会被连带清空
            page.add_redact_annot(target_rect)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                                  graphics=fitz.PDF_REDACT_LINE_ART_NONE)
            # 第二遍：目标区域原本是空白（插入时经过空白检测），删除文字后残余的
            # 仅剩表格边框线；按边框绘制颜色（工具插入表格的蓝色）收集边界框与
            # 目标区域相交的线稿，得到精确表格外框后整框删除
            disp_rect = fitz.Rect(target_rect * rot_matrix)
            border_union = None
            for drawing in page.get_drawings():
                stroke = drawing.get('color')
                if stroke is None or drawing.get('type') not in ('s', 'fs'):
                    continue
                if any(abs(c - v) > 0.02 for c, v in zip(stroke, self.INSERT_TABLE_BORDER_COLOR)):
                    continue
                dbox = fitz.Rect(drawing['rect']) * rot_matrix
                if dbox.intersects(disp_rect):
                    border_union = dbox if border_union is None else fitz.Rect(border_union | dbox)
            if border_union is not None:
                border_rect = fitz.Rect(border_union.x0 - 1, border_union.y0 - 1,
                                        border_union.x1 + 1, border_union.y1 + 1)
                border_rect = fitz.Rect(border_rect * page.derotation_matrix) & page.mediabox
                if not border_rect.is_empty and border_rect.width > 0 and border_rect.height > 0:
                    page.add_redact_annot(border_rect)
                    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                                          graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED)
            total_deleted += 1

        log_info(f'Deleted {total_deleted} table region(s) across {len(doc)} pages')
        log_info('Table deletion completed')

    def _locate_table_display_region(self, display_hits):
        """在显示坐标系的命中矩形里定位插入表格的外框。

        返回 (表格文本包围盒, 行距)；认为命中文本按"行带"组织：先按 y 重叠聚类
        成行带（加入时要求x方向间距不超过平均字宽的3倍，防止横向远离的无关文字
        被并入同一行带），再把 x 范围相近、上下相邻的行带合并成表格候选组，取
        命中数最多的一组作为表格（工程图纸上的散落同名文字行带通常远小于表格）。
        行距取该组内相邻行带顶部间距的中位数，用于估算外扩边距。
        """
        def _median(values):
            sorted_v = sorted(values)
            n = len(sorted_v)
            if n % 2:
                return sorted_v[n // 2]
            return (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2.0

        med_width = _median([r.width for r in display_hits])
        items = sorted(display_hits, key=lambda r: r.y0)
        rows = []  # [rect, hits]
        for rect in items:
            placed = False
            for band in rows:
                band_rect = band[0]
                y_overlap = min(band_rect.y1, rect.y1) - rect.y0
                x_gap = max(band_rect.x0 - rect.x1, rect.x0 - band_rect.x1)
                if y_overlap > 0 and y_overlap >= 0.5 * min(band_rect.height, rect.height) \
                        and x_gap <= 3 * med_width:
                    band[0] |= rect
                    band[1].append(rect)
                    placed = True
                    break
            if not placed:
                rows.append([fitz.Rect(rect), [rect]])

        rows.sort(key=lambda b: b[0].y0)
        groups = []  # [rect, hits]
        for row_rect, row_hits in rows:
            merged = False
            for group in groups:
                group_rect = group[0]
                x_overlap = min(group_rect.x1, row_rect.x1) - max(group_rect.x0, row_rect.x0)
                y_gap = row_rect.y0 - group_rect.y1
                if x_overlap > 0 and x_overlap >= 0.6 * min(group_rect.width, row_rect.width) \
                        and y_gap <= 1.5 * min(group_rect.height, row_rect.height):
                    group[0] |= row_rect
                    group[1].extend(row_hits)
                    merged = True
                    break
            if not merged:
                groups.append([fitz.Rect(row_rect), list(row_hits)])

        best = max(groups, key=lambda g: len(g[1]))
        region = fitz.Rect(best[0])
        tops = sorted(set(round(r.y0, 1) for r in best[1]))
        pitch = 0.0
        if len(tops) >= 2:
            diffs = [b - a for a, b in zip(tops[:-1], tops[1:]) if b - a > 0.5]
            if diffs:
                pitch = _median(diffs)
        return region, pitch
    
    def _get_placeholder_style(self, page, area):
        """获取占位符所在文本的字号、颜色、基线起点和方向，用于替换后保持与原占位符一致。"""
        default_style = {
            'size': 11.0,
            'color': (0, 0, 0),
            'baseline_x': area.x0,
            'baseline_y': area.y1,
            'angle': 0,
        }
        try:
            best_overlap = 0.0
            best_style = None
            text_dict = page.get_text('dict')
            for block in text_dict.get('blocks', []):
                for line in block.get('lines', []):
                    for span in line.get('spans', []):
                        inter = fitz.Rect(span['bbox']) & area
                        if inter.is_empty:
                            continue
                        overlap = inter.get_area()
                        if overlap <= best_overlap:
                            continue
                        best_overlap = overlap
                        size = float(span.get('size') or default_style['size'])
                        color = fitz.sRGB_to_pdf(int(span.get('color') or 0))
                        origin = span.get('origin')
                        baseline_x = float(origin[0]) if origin else area.x0
                        baseline_y = float(origin[1]) if origin else area.y1
                        # 文本可能随页面 /Rotate 或自身旋转而不再是水平方向，
                        # 由 line 的 dir 向量换算出插入所需的旋转角（仅支持 90 的倍数）
                        dir_vec = line.get('dir', (1.0, 0.0))
                        angle = int(round(math.degrees(math.atan2(-dir_vec[1], dir_vec[0])) / 90.0) * 90) % 360
                        best_style = {
                            'size': size,
                            'color': color,
                            'baseline_x': baseline_x,
                            'baseline_y': baseline_y,
                            'angle': angle,
                        }
            if best_style:
                return best_style
        except Exception as e:
            log_debug(f'Failed to detect placeholder style: {e}')
        return default_style

    def _get_text_insert_point(self, area, style):
        """按文本方向计算占位符首字符的基线起点（与原占位符起点一致）。"""
        angle = style['angle']
        if angle == 90:
            return fitz.Point(style['baseline_x'], area.y1)
        if angle == 180:
            return fitz.Point(area.x1, style['baseline_y'])
        if angle == 270:
            return fitz.Point(style['baseline_x'], area.y0)
        return fitz.Point(area.x0, style['baseline_y'])

    def _insert_rotated_text(self, page, area, new_text, style):
        """按原占位符的旋转方向插入文本（单行，超出页面可用长度时缩小字号）。"""
        angle = style['angle']
        font_size = style['size']
        color = style['color']
        lines = new_text.split('\n')
        text_width = max((fitz.get_text_length(line, fontname='helv', fontsize=font_size)
                          for line in lines), default=0.0)
        start = self._get_text_insert_point(area, style)
        bounds = page.mediabox
        if angle == 90:
            available = start.y - bounds.y0 - 2
        elif angle == 180:
            available = start.x - bounds.x0 - 2
        elif angle == 270:
            available = bounds.y1 - start.y - 2
        else:
            available = bounds.x1 - start.x - 2
        draw_size = font_size
        if available > 0 and text_width > available:
            draw_size = max(1.0, font_size * available / text_width)
        line_height = draw_size * 1.25
        # 旋转后多行的堆叠方向（垂直于文本前进方向）
        perp_x = math.sin(math.radians(angle))
        perp_y = math.cos(math.radians(angle))
        for idx, line in enumerate(lines):
            point = fitz.Point(start.x + perp_x * line_height * idx,
                               start.y + perp_y * line_height * idx)
            page.insert_text(point, line, fontsize=draw_size, color=color, rotate=angle)

    def _cover_placeholder(self, page, area, style):
        """用白色矩形覆盖占位符。
        字符 bbox 为字宽单元格，花括号等字形墨迹会略微超出，因此沿“垂直文本方向”
        （即字号方向）外扩一点；不外扩文本前进方向，避免遮住相邻字符。
        """
        margin = max(1.0, style['size'] * 0.25)
        if style['angle'] in (90, 270):
            cover = fitz.Rect(area.x0 - margin, area.y0, area.x1 + margin, area.y1)
        else:
            cover = fitz.Rect(area.x0, area.y0 - margin, area.x1, area.y1 + margin)
        page.draw_rect(cover, color=None, fill=(1, 1, 1), overlay=True)

    def _clear_placeholder(self, page, area, style):
        """清除占位符内容。
        水平文本且页面未旋转时用 redaction 真正删除占位符字符；
        其余情况（页面 /Rotate 或文字自身旋转）改用白底遮盖：实测 apply_redactions
        会重排旋转文本，把后续无关文本整体位移（偏移量等于被删占位符的字宽），
        遮盖可保持页面其余内容位置不变。
        """
        if page.rotation == 0 and style['angle'] == 0:
            page.add_redact_annot(area, fill=(1, 1, 1))
            page.apply_redactions()
        else:
            self._cover_placeholder(page, area, style)

    def _get_image_rect_for_area(self, page, area, angle, new_width, new_height):
        """按页面旋转换算图片插入矩形，使其显示时左上角与原占位符首字符左上角对齐。"""
        if angle in (90, 270):
            unrot_w, unrot_h = new_height, new_width
        else:
            unrot_w, unrot_h = new_width, new_height
        if page.rotation in (90, 270):
            disp_w, disp_h = unrot_h, unrot_w
        else:
            disp_w, disp_h = unrot_w, unrot_h
        disp = fitz.Rect(area) * page.rotation_matrix
        disp_rect = fitz.Rect(disp.x0, disp.y0, disp.x0 + disp_w, disp.y0 + disp_h)
        return fitz.Rect(disp_rect * page.derotation_matrix)

    def _replace_text_in_area(self, page, area, new_text):
        try:
            new_text = str(new_text)
            style = self._get_placeholder_style(page, area)
            font_size = style['size']
            color = style['color']
            angle = style['angle']
            self._clear_placeholder(page, area, style)
            if angle != 0:
                self._insert_rotated_text(page, area, new_text, style)
                return
            # 页面坐标系（未旋转）边界，用于计算可用宽度/高度
            bounds = page.mediabox
            line_height = font_size * 1.25
            # 文本框宽度至少容纳整段文本单行显示，避免按原占位符字号替换后
            # 在窄框内被强制换行（换行出的下一行可能落入相邻占位符的 redaction
            # 区域而被误删，造成值被截断）；过宽时再按页面可用宽度换行
            available_width = max(1.0, bounds.x1 - area.x0 - 2)
            text_width = max((fitz.get_text_length(line, fontname='helv', fontsize=font_size)
                              for line in new_text.split('\n')), default=0.0)
            rect_width = min(max(area.width, text_width), available_width)
            # 以原占位符矩形为起点，向下预留多行高度以容纳换行后的长值
            max_height = max(line_height, bounds.y1 - area.y0 - 2)
            height = min(max_height, max(area.height, line_height * 10))
            text_rect = fitz.Rect(area.x0, area.y0, area.x0 + rect_width, area.y0 + height)
            rc = page.insert_textbox(text_rect, new_text, fontsize=font_size, color=color, align=0)
            if rc < 0:
                # 矩形内无法排版（如超长不可断词）时退化为单行插入；
                # 仍超出页面可用宽度时同步缩小字号，避免占位符被删而值丢失
                fallback_size = font_size
                if text_width > available_width:
                    fallback_size = max(1.0, font_size * available_width / text_width)
                point = self._get_text_insert_point(area, style)
                page.insert_text(point, new_text, fontsize=fallback_size, color=color)
        except Exception as e:
            log_error(f'Failed to replace text: {e}')
    
    def _process_insert_text_mode(self, doc, rows, insert_position):
        if not rows:
            return False
        column_target_pages = {}
        for row in rows:
            for item_idx, item in enumerate(row.get('data', [])):
                target_page = item.get('target_page', '')
                if item_idx not in column_target_pages and target_page:
                    column_target_pages[item_idx] = target_page.strip()
        target_page = ''
        if column_target_pages:
            target_page = list(column_target_pages.values())[0]
        target_page = target_page.strip() if target_page else ''
        page_range = self._parse_page_range(target_page, len(doc))
        
        # 规格7.3：行高比例参数（默认0.015）用于确定行高，插入宽度独立取整页可用宽度
        row_height_ratio = self._get_total_width()
        text_lines = []
        for row in rows:
            for item in row.get('data', []):
                value = item.get('value', '')
                if value and value.strip():
                    text_lines.append(value)
        if not text_lines:
            return False
        
        text = '\n'.join(text_lines)
        inserted = False
        
        for page_num in page_range:
            page = doc[page_num]
            if self._is_page_bitmap_only(page):
                log_info(f'Page {page_num + 1} is bitmap only, will insert text anyway')
            
            page_rect = page.rect
            line_height = page_rect.height * row_height_ratio
            if line_height <= 0:
                line_height = 12.0
            fontsize = max(4.0, min(72.0, line_height / 1.2))
            # 插入宽度取待插入内容的实际行宽（上限为页面可用宽度）：若固定取整页宽的
            # 90%，在密集图纸上几乎找不到如此宽的空白带，会误判“无可用位置”而插入失败
            text_width = max(
                (fitz.get_text_length(line, fontname='helv', fontsize=fontsize) for line in text_lines),
                default=0
            )
            max_width = min(page_rect.width * 0.9, text_width + 2)
            # insert_textbox 单行所需高度约为 (ascender-descender)*字号*1.25，
            # 比排版的 line_height 大；框高不足会让 insert_textbox 返回负值而误判放不下
            font = fitz.Font('helv')
            line_box_height = max(line_height, fontsize * (font.ascender - font.descender) * 1.25)
            max_height = len(text_lines) * line_box_height + 10
            position_index = self._get_insert_position_index()
            position = self._calculate_insert_position(page, max_width, max_height, position_index, page_num=page_num, source_file=self._current_source_file)
            if position is None:
                log_warning(f'No valid position found on page {page_num + 1}, skipping text insertion')
                continue
            # position 来自按显示方向渲染的位图，为显示坐标；须经逆旋转矩阵换回未旋转
            # 坐标，并以页面旋转角插入，否则带 /Rotate 的页面上文字方向会被转 90°
            disp_rect = fitz.Rect(
                position[0],
                position[1],
                position[0] + max_width,
                position[1] + max_height
            )
            text_rect = fitz.Rect(disp_rect * page.derotation_matrix)
            rc = page.insert_textbox(text_rect, text, fontsize=fontsize, align=0,
                                     color=self.INSERT_TEXT_COLOR, rotate=page.rotation)
            if rc < 0:
                # 仍放不下（如边距过窄）时缩小字号重试一次
                retry_size = max(4.0, fontsize * 0.85)
                rc = page.insert_textbox(text_rect, text, fontsize=retry_size, align=0,
                                         color=self.INSERT_TEXT_COLOR, rotate=page.rotation)
            if rc < 0:
                log_warning(f'Text does not fit in available space on page {page_num + 1}, skipping insertion')
                continue
            inserted = True
        
        return inserted
    
    def _process_insert_table_mode(self, doc, rows, insert_position):
        if not rows:
            return False
        
        column_target_pages = {}
        for row in rows:
            for item_idx, item in enumerate(row.get('data', [])):
                target_page = item.get('target_page', '')
                if item_idx not in column_target_pages and target_page:
                    column_target_pages[item_idx] = target_page.strip()
        target_page = ''
        if column_target_pages:
            target_page = list(column_target_pages.values())[0]
        target_page = target_page.strip() if target_page else ''
        page_range = self._parse_page_range(target_page, len(doc))
        
        table_params_start = time.time()
        total_width = self._get_total_width()
        table_params = self._get_table_params()
        num_cols_setting = table_params.get('cols', 3)
        num_rows = len(rows)
        tight = table_params.get('tight', False)
        buffer_factor = 1.0 if tight else 1.15
        column_widths = self._get_column_widths()
        original_row_height = self._get_row_height()
        
        if num_cols_setting == 'auto':
            num_cols = self._detect_table_columns(rows)
            log_debug(f'Auto-detected table columns: {num_cols}')
        else:
            num_cols = num_cols_setting if isinstance(num_cols_setting, int) else 3
        
        table_data = []
        for row in rows:
            data_items = row.get('data', [])
            row_data = []
            for col_idx in range(num_cols):
                if col_idx < len(data_items):
                    value = data_items[col_idx].get('value', '')
                    row_data.append(value if value else '')
                else:
                    row_data.append('')
            table_data.append(row_data)
        
        row_height_attempts = []
        if original_row_height >= 0.015:
            row_height_attempts = [original_row_height, 0.01, 0.005]
        elif original_row_height >= 0.01:
            row_height_attempts = [original_row_height, 0.005]
        else:
            row_height_attempts = [original_row_height]
        
        inserted = False
        tried_smaller = False
        
        for row_height in row_height_attempts:
            if row_height != original_row_height:
                tried_smaller = True
                log_debug(f'Retrying with smaller row height: {row_height}')
            
            inserted = self._try_insert_table_with_height(
                doc, page_range, table_data, num_rows, num_cols,
                total_width, row_height, column_widths, insert_position, buffer_factor
            )
            
            if inserted:
                break
        
        table_params_time = time.time() - table_params_start
        log_info(f'Table insert completed for {len(doc)} pages: params: {table_params_time:.3f}s')
        
        if not inserted:
            if tried_smaller:
                return translate('result_no_space_table_retry')
            else:
                return translate('result_no_space_table')
        
        return True
    
    def _try_insert_table_with_height(self, doc, page_range, table_data, num_rows, num_cols,
                                       total_width, row_height, column_widths, insert_position, buffer_factor):
        inserted = False
        
        for page_num in page_range:
            page = doc[page_num]
            if self._is_page_bitmap_only(page):
                log_info(f'Page {page_num + 1} is bitmap only, will insert table anyway')
            
            page_rect = page.rect
            is_portrait = page_rect.height > page_rect.width
            height_percentage = total_width
            if is_portrait: height_percentage = height_percentage * 0.45
            cell_height = (page_rect.height * height_percentage) if height_percentage > 0 else 21
            if column_widths and row_height and row_height > 0:
                width_multiplier = (cell_height / row_height) * 1.22
                cell_widths = [w * width_multiplier for w in column_widths[:num_cols]]
            else:
                cell_widths = [cell_height] * num_cols
            
            max_width = sum(cell_widths)
            max_height = cell_height * num_rows
            
            position_index = self._get_insert_position_index()
            position = self._calculate_insert_position(page, max_width, max_height, position_index, buffer_factor, page_num=page_num, source_file=self._current_source_file)
            if position is None:
                log_warning(f'No valid position found on page {page_num + 1} with row_height {row_height}')
                continue
            self._draw_table(page, table_data, position, cell_widths, cell_height)
            inserted = True
        
        return inserted
    
    def _detect_table_columns(self, rows):
        max_col_index = 0
        for row in rows:
            data_items = row.get('data', [])
            for col_idx in range(len(data_items) - 1, -1, -1):
                value = data_items[col_idx].get('value', '')
                if value and value.strip():
                    if col_idx > max_col_index:
                        max_col_index = col_idx
                    break
        return max_col_index + 1 if max_col_index >= 0 else 1
    
    def _process_insert_image_mode(self, doc, rows, insert_position):
        if not rows:
            return False
        column_target_pages = {}
        for row in rows:
            for item_idx, item in enumerate(row.get('data', [])):
                target_page = item.get('target_page', '')
                if item_idx not in column_target_pages and target_page:
                    column_target_pages[item_idx] = target_page.strip()
        target_page = ''
        if column_target_pages:
            target_page = list(column_target_pages.values())[0]
        target_page = target_page.strip() if target_page else ''
        page_range = self._parse_page_range(target_page, len(doc))
        
        # 规格7.3：插入图片使用“宽度”（占页宽比例），非法值回退为默认0.06
        total_width = self._get_total_width()
        if total_width <= 0 or total_width > 1:
            total_width = 0.06
        image_path = None
        for row in rows:
            for item in row.get('data', []):
                value = item.get('value', '')
                if value and os.path.exists(value):
                    image_path = value
                    break
            if image_path:
                break
        if not image_path:
            return False
        # B3-2：解析前限制源文件大小（防资源耗尽）
        if not check_source_file_size(image_path):
            log_error(f'Image file too large (>200 MB), skip insert: {image_path}')
            return False
        inserted = False
        
        try:
            pil_img = Image.open(image_path)
            orig_width, orig_height = pil_img.size
            pil_img.close()
            
            for page_num in page_range:
                page = doc[page_num]
                if self._is_page_bitmap_only(page):
                    log_info(f'Page {page_num + 1} is bitmap only, will insert image anyway')
                
                page_rect = page.rect
                max_width = page_rect.width * total_width
                ratio = max_width / orig_width
                new_width = int(orig_width * ratio)
                new_height = int(orig_height * ratio)
                position_index = self._get_insert_position_index()
                position = self._calculate_insert_position(page, new_width, new_height, position_index, page_num=page_num, source_file=self._current_source_file)
                if position is None:
                    log_warning(f'No valid position found on page {page_num + 1}, skipping image insertion')
                    continue
                # position 来自按显示方向渲染的位图，为显示坐标；须经逆旋转矩阵换回未旋转
                # 坐标，并以页面旋转角插入，否则带 /Rotate 的页面上图片会偏移并转 90°，
                # 从而错误覆盖图档已有元素
                disp_rect = fitz.Rect(
                    position[0],
                    position[1],
                    position[0] + new_width,
                    position[1] + new_height
                )
                rect = fitz.Rect(disp_rect * page.derotation_matrix)
                page.insert_image(rect, filename=image_path, rotate=page.rotation)
                inserted = True
        except Exception as e:
            log_error(f'Failed to insert image: {e}')
        
        return inserted
    
    def _draw_table(self, page, table_data, position, cell_widths, cell_height):
        if not table_data:
            return
        start_x, start_y = position
        fontsize = cell_height * 0.65
        color = self.INSERT_TABLE_BORDER_COLOR
        # position 为显示坐标；页面带 /Rotate 时须经逆旋转矩阵换回未旋转坐标，
        # 并让表格边框与文字按页面旋转角绘制，否则表格会偏移/超出页面且被转 90°
        derot = page.derotation_matrix
        rotate = page.rotation

        def to_unrot(u, v):
            return fitz.Point(u, v) * derot

        for row_idx, row_data in enumerate(table_data):
            x = start_x
            for col_idx, cell_value in enumerate(row_data):
                cell_width = cell_widths[col_idx] if col_idx < len(cell_widths) else cell_widths[0]
                y = start_y + row_idx * cell_height
                page.draw_polyline(
                    [to_unrot(x, y),
                     to_unrot(x + cell_width, y),
                     to_unrot(x + cell_width, y + cell_height),
                     to_unrot(x, y + cell_height)],
                    color=color, width=0.20, closePath=True
                )
                if cell_value:
                    text_pt = to_unrot(x + 3, y + cell_height / 2 + fontsize / 3)
                    page.insert_text(text_pt, str(cell_value), fontsize=fontsize, rotate=rotate)
                x += cell_width
    
    def _calculate_insert_position(self, page, max_width, max_height, position_index=None, buffer_factor=1.05, page_num=0, source_file=''):
        page_rect = page.rect
        page_width = page_rect.width
        page_height = page_rect.height
        margin = 2
        
        pix_start = time.time()
        scale = self._get_pixmap_scale(page_width, page_height)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
        img_width = pix.width
        img_height = pix.height
        pixels = pix.samples
        stride = pix.stride
        n = pix.n
        
        binary = [0] * (img_width * img_height)
        threshold = 240
        for y in range(img_height):
            row_start = y * stride
            for x in range(img_width):
                idx = row_start + x * n
                if n >= 3:
                    r = pixels[idx]
                    g = pixels[idx + 1]
                    b = pixels[idx + 2]
                    gray_val = int(0.299 * r + 0.587 * g + 0.114 * b)
                else:
                    gray_val = pixels[idx]
                binary[y * img_width + x] = 0 if gray_val > threshold else 1
        pix_time = time.time() - pix_start
        
        def get_pixel(x, y):
            if 0 <= x < img_width and 0 <= y < img_height:
                return binary[y * img_width + x]
            return 0
        
        pos_type = (position_index - 5) % 5 if position_index is not None and position_index >= 5 else position_index
        use_frame = position_index is not None and position_index >= 5
        
        log_debug(f'PDF size: {page_width}x{page_height}, scale: {scale}, img size: {img_width}x{img_height}')
        
        frame_start = time.time()
        if use_frame:
            frame = self._detect_frame_inner_box(page, page_num, source_file)
            frame_left = max(0, frame['left'])
            frame_top = max(0, frame['top'])
            frame_right = min(page_width, frame['right'])
            frame_bottom = min(page_height, frame['bottom'])
            log_debug(f'Frame detected: left={frame_left:.1f}, top={frame_top:.1f}, right={frame_right:.1f}, bottom={frame_bottom:.1f}')
        else:
            frame_left = 0
            frame_top = 0
            frame_right = page_width
            frame_bottom = page_height
        frame_time = time.time() - frame_start
        
        search_start = time.time()
        result = self._find_position_grid(
            get_pixel, img_width, img_height,
            max_width, max_height,
            frame_left, frame_top, frame_right, frame_bottom,
            pos_type, buffer_factor, scale
        )
        search_time = time.time() - search_start
        
        log_info(f'Position calc breakdown: pixmap: {pix_time:.3f}s, frame: {frame_time:.3f}s, search: {search_time:.3f}s')
        if result is None:
            # 未找到可用位置属正常结果，返回 None 由调用方处理（此前直接取下标会抛
            # TypeError: 'NoneType' object is not subscriptable，导致预览/执行报错）
            log_debug(f'Insert position result: none, content size: {max_width}x{max_height}')
            return None
        log_debug(f'Insert position result: x={result[0]:.1f}, y={result[1]:.1f}, content size: {max_width}x{max_height}')
        
        return result
    
    def _find_position_grid(self, get_pixel, img_width, img_height, max_width, max_height,
                           frame_left, frame_top, frame_right, frame_bottom,
                           pos_type, buffer_factor, scale):
        frame_left_s = int(frame_left * scale)
        frame_top_s = int(frame_top * scale)
        frame_right_s = int(frame_right * scale)
        frame_bottom_s = int(frame_bottom * scale)
        
        inner_margin = 2
        search_left = frame_left_s + inner_margin
        search_top = frame_top_s + inner_margin
        search_right = frame_right_s - inner_margin
        search_bottom = frame_bottom_s - inner_margin
        
        search_width = search_right - search_left
        search_height = search_bottom - search_top
        
        Lv = max(1, int(max_height * scale / 10))
        Lh = max(1, int(max_width * scale / 10))
        
        num_horizontal_lines = max(2, search_height // Lv)
        num_vertical_lines = max(2, search_width // Lh)
        
        log_debug(f'Grid: search area=({search_left},{search_top})-({search_right},{search_bottom}), lines={num_horizontal_lines}x{num_vertical_lines}, pos_type={pos_type}')
        
        horizontal_lines = []
        for i in range(num_horizontal_lines):
            y = search_top + int(i * search_height / max(1, num_horizontal_lines - 1))
            horizontal_lines.append(y)
        
        vertical_lines = []
        for i in range(num_vertical_lines):
            x = search_left + int(i * search_width / max(1, num_vertical_lines - 1))
            vertical_lines.append(x)
        
        segment_h = max(1, Lh)
        segment_v = max(1, Lv)
        
        grid = [[0] * num_vertical_lines for _ in range(num_horizontal_lines)]
        
        for hi, h_y in enumerate(horizontal_lines):
            for vi, v_x in enumerate(vertical_lines):
                all_white_h = True
                for sx in range(v_x - segment_h // 2, v_x + segment_h // 2 + 1):
                    if get_pixel(sx, h_y) == 1:
                        all_white_h = False
                        break
                
                all_white_v = True
                for sy in range(h_y - segment_v // 2, h_y + segment_v // 2 + 1):
                    if get_pixel(v_x, sy) == 1:
                        all_white_v = False
                        break
                
                if all_white_h and all_white_v:
                    grid[hi][vi] = 1
        
        required_lines = 2
        found_position = None
        
        search_order_h = list(range(num_horizontal_lines - required_lines + 1))
        search_order_v = list(range(num_vertical_lines - required_lines + 1))
        
        if pos_type == 1:
            search_order_h = list(range(num_horizontal_lines - required_lines, -1, -1))
        elif pos_type == 2:
            search_order_h = list(range(num_horizontal_lines - required_lines, -1, -1))
            search_order_v = list(range(num_vertical_lines - required_lines, -1, -1))
        elif pos_type == 4:
            search_order_v = list(range(num_vertical_lines - required_lines, -1, -1))
        
        for start_v in search_order_v:
            for start_h in search_order_h:
                can_place = True
                for hi in range(start_h, start_h + required_lines):
                    for vi in range(start_v, start_v + required_lines):
                        if grid[hi][vi] == 0:
                            can_place = False
                            break
                    if not can_place:
                        break
                
                if can_place:
                    h_idx = start_h
                    v_idx = start_v
                    
                    if pos_type == 1:
                        h_idx = start_h + required_lines - 1
                        v_idx = start_v
                    elif pos_type == 2:
                        v_idx = start_v + required_lines - 1
                        h_idx = start_h + required_lines - 1
                    elif pos_type == 3:
                        v_idx = start_v
                        h_idx = start_h
                    elif pos_type == 4:
                        v_idx = start_v + required_lines - 1
                        h_idx = start_h
                    
                    best_x = vertical_lines[v_idx]
                    best_y = horizontal_lines[h_idx]
                    
                    if pos_type == 1:
                        best_x = max(search_left, min(search_right - max_width * scale, best_x))
                        best_y = max(search_top, min(search_bottom - max_height * scale, best_y - max_height * scale))
                    elif pos_type == 2:
                        best_x = max(search_left, min(search_right - max_width * scale, best_x - max_width * scale))
                        best_y = max(search_top, min(search_bottom - max_height * scale, best_y - max_height * scale))
                    elif pos_type == 3:
                        best_x = max(search_left, min(search_right - max_width * scale, best_x))
                        best_y = max(search_top, min(search_bottom - max_height * scale, best_y))
                    elif pos_type == 4:
                        best_x = max(search_left, min(search_right - max_width * scale, best_x - max_width * scale))
                        best_y = max(search_top, min(search_bottom - max_height * scale, best_y))
                    else:
                        best_x = max(search_left, min(search_right - max_width * scale, best_x - int(max_width * scale / 2)))
                        best_y = max(search_top, min(search_bottom - max_height * scale, best_y - int(max_height * scale / 2)))
                    
                    area_empty = True
                    buffer_w = int(max_width * scale * buffer_factor)
                    buffer_h = int(max_height * scale * buffer_factor)
                    for check_y in range(int(best_y), int(best_y + buffer_h)):
                        for check_x in range(int(best_x), int(best_x + buffer_w)):
                            if check_y < img_height and check_x < img_width:
                                if get_pixel(check_x, check_y) == 1:
                                    area_empty = False
                                    break
                        if not area_empty:
                            break
                    
                    if area_empty:
                        found_position = (best_x / scale, best_y / scale)
                        log_debug(f'Position found: x={best_x/scale:.1f}, y={best_y/scale:.1f}, area={buffer_w}x{buffer_h}')
                        break
            if found_position:
                break
        
        if found_position:
            return found_position
        
        log_debug('No valid insert position found')
        return None
    
    def _is_area_empty(self, occupied, x, y, width, height, buffer_factor=1.05):
        if x < 0 or y < 0:
            return False
        buffer_width = int(width * buffer_factor)
        buffer_height = int(height * buffer_factor)
        if x + buffer_width > len(occupied[0]) or y + buffer_height > len(occupied):
            return False
        for row in range(y, y + buffer_height):
            for col in range(x, x + buffer_width):
                if row < len(occupied) and col < len(occupied[0]) and occupied[row][col]:
                    return False
        return True
    
    def _find_position_any(self, occupied, img_width, img_height, max_width, max_height, margin, half_width, scale, frame_left=0, frame_top=0, frame_right=None, frame_bottom=None, buffer_factor=1.05):
        if frame_right is None:
            frame_right = img_width
        if frame_bottom is None:
            frame_bottom = img_height
        frame_left_scaled = int(frame_left * scale)
        frame_top_scaled = int(frame_top * scale)
        frame_right_scaled = int(frame_right * scale)
        frame_bottom_scaled = int(frame_bottom * scale)
        limit_line = frame_left + (frame_right - frame_left) * 0.5
        limit_line_scaled = int(limit_line * scale)
        
        pos = self._find_position_bitmap_bottom_left(occupied, img_width, img_height, max_width, max_height, margin, half_width, scale, frame_left, frame_top, frame_right, frame_bottom, limit_line, buffer_factor)
        x, y = int(pos[0] * scale), int(pos[1] * scale)
        if self._is_area_empty(occupied, x, y, max_width, max_height, buffer_factor):
            return pos
        
        pos = self._find_position_bitmap_bottom_right(occupied, img_width, img_height, max_width, max_height, margin, half_width, scale, frame_left, frame_top, frame_right, frame_bottom, limit_line_scaled, buffer_factor)
        x, y = int(pos[0] * scale), int(pos[1] * scale)
        if self._is_area_empty(occupied, x, y, max_width, max_height, buffer_factor):
            return pos
        
        pos = self._find_position_bitmap_top_left(occupied, img_width, img_height, max_width, max_height, margin, half_width, scale, frame_left, frame_top, frame_right, frame_bottom, limit_line, buffer_factor)
        x, y = int(pos[0] * scale), int(pos[1] * scale)
        if self._is_area_empty(occupied, x, y, max_width, max_height, buffer_factor):
            return pos
        
        pos = self._find_position_bitmap_top_right(occupied, img_width, img_height, max_width, max_height, margin, half_width, scale, frame_left, frame_top, frame_right, frame_bottom, limit_line_scaled, buffer_factor)
        x, y = int(pos[0] * scale), int(pos[1] * scale)
        if self._is_area_empty(occupied, x, y, max_width, max_height, buffer_factor):
            return pos
        
        for y in range(frame_top_scaled + int(margin), frame_bottom_scaled - max_height - int(margin)):
            for x in range(frame_left_scaled + int(margin), frame_right_scaled - max_width - int(margin)):
                if self._is_area_empty(occupied, x, y, max_width, max_height, buffer_factor):
                    return (x / scale, y / scale)
        
        return (frame_left_scaled / scale + margin / scale, frame_top_scaled / scale + margin / scale)
    
    def _find_position_bitmap_top_left(self, occupied, img_width, img_height, max_width, max_height, margin, half_width, scale, frame_left=0, frame_top=0, frame_right=None, frame_bottom=None, limit_line=0, buffer_factor=1.05):
        if frame_right is None:
            frame_right = img_width
        if frame_bottom is None:
            frame_bottom = img_height
        frame_left_scaled = int(frame_left * scale)
        frame_top_scaled = int(frame_top * scale)
        frame_right_scaled = int(frame_right * scale)
        frame_bottom_scaled = int(frame_bottom * scale)
        limit_line_scaled = int(limit_line * scale) if limit_line > 0 else frame_left_scaled + (frame_right_scaled - frame_left_scaled) // 2
        start_y = frame_top_scaled + int(margin)
        end_y = min(frame_bottom_scaled - max_height - int(margin), img_height - int(margin))
        start_x = max(frame_left_scaled + int(margin), int(margin))
        end_x = min(limit_line_scaled - int(margin), frame_right_scaled - max_width - int(margin))
        for y in range(start_y, end_y):
            for x in range(start_x, end_x):
                if self._is_area_empty(occupied, x, y, max_width, max_height, buffer_factor):
                    return (x / scale, y / scale)
        return (frame_left_scaled / scale + margin / scale, frame_top_scaled / scale + margin / scale)
    
    def _find_position_bitmap_top_right(self, occupied, img_width, img_height, max_width, max_height, margin, half_width, scale, frame_left=0, frame_top=0, frame_right=None, frame_bottom=None, limit_line=0, buffer_factor=1.05):
        if frame_right is None:
            frame_right = img_width
        if frame_bottom is None:
            frame_bottom = img_height
        frame_left_scaled = int(frame_left * scale)
        frame_top_scaled = int(frame_top * scale)
        frame_right_scaled = int(frame_right * scale)
        frame_bottom_scaled = int(frame_bottom * scale)
        limit_line_scaled = int(limit_line * scale) if limit_line > 0 else frame_left_scaled + (frame_right_scaled - frame_left_scaled) // 2
        start_y = frame_top_scaled + int(margin)
        end_y = min(frame_bottom_scaled - max_height - int(margin), img_height - int(margin))
        start_x = max(limit_line_scaled + int(margin), frame_left_scaled + int(margin))
        end_x = frame_right_scaled - max_width - int(margin)
        for y in range(start_y, end_y):
            for x in range(end_x, start_x, -1):
                if self._is_area_empty(occupied, x, y, max_width, max_height, buffer_factor):
                    return (x / scale, y / scale)
        return ((frame_right_scaled - max_width - margin) / scale, frame_top_scaled / scale + margin / scale)
    
    def _find_position_bitmap_bottom_left(self, occupied, img_width, img_height, max_width, max_height, margin, half_width, scale, frame_left=0, frame_top=0, frame_right=None, frame_bottom=None, limit_line=0, buffer_factor=1.05):
        if frame_right is None:
            frame_right = img_width
        if frame_bottom is None:
            frame_bottom = img_height
        frame_left_scaled = int(frame_left * scale)
        frame_top_scaled = int(frame_top * scale)
        frame_right_scaled = int(frame_right * scale)
        frame_bottom_scaled = int(frame_bottom * scale)
        limit_line_scaled = int(limit_line * scale) if limit_line > 0 else frame_left_scaled + (frame_right_scaled - frame_left_scaled) // 2
        start_y = max(frame_bottom_scaled - max_height - int(margin), frame_top_scaled + int(margin))
        end_y = frame_bottom_scaled - int(margin)
        start_x = max(frame_left_scaled + int(margin), int(margin))
        end_x = min(limit_line_scaled - int(margin), frame_right_scaled - max_width - int(margin))
        for y in range(start_y, end_y, -1):
            for x in range(start_x, end_x):
                if self._is_area_empty(occupied, x, y, max_width, max_height, buffer_factor):
                    return (x / scale, y / scale)
        return (frame_left_scaled / scale + margin / scale, (frame_bottom_scaled - max_height - margin) / scale)
    
    def _find_position_bitmap_bottom_right(self, occupied, img_width, img_height, max_width, max_height, margin, half_width, scale, frame_left=0, frame_top=0, frame_right=None, frame_bottom=None, limit_line=0, buffer_factor=1.05):
        if frame_right is None:
            frame_right = img_width
        if frame_bottom is None:
            frame_bottom = img_height
        frame_left_scaled = int(frame_left * scale)
        frame_top_scaled = int(frame_top * scale)
        frame_right_scaled = int(frame_right * scale)
        frame_bottom_scaled = int(frame_bottom * scale)
        limit_line_scaled = int(limit_line * scale) if limit_line > 0 else frame_left_scaled + (frame_right_scaled - frame_left_scaled) // 2
        start_y = max(frame_bottom_scaled - max_height - int(margin), frame_top_scaled + int(margin))
        end_y = frame_bottom_scaled - int(margin)
        start_x = max(limit_line_scaled + int(margin), frame_left_scaled + int(margin))
        end_x = frame_right_scaled - max_width - int(margin)
        for y in range(start_y, end_y, -1):
            for x in range(end_x, start_x, -1):
                if self._is_area_empty(occupied, x, y, max_width, max_height, buffer_factor):
                    return (x / scale, y / scale)
        return ((frame_right_scaled - max_width - margin) / scale, (frame_bottom_scaled - max_height - margin) / scale)
    
    def _get_total_width(self):
        return self.params.get('total_width', 0.2)
    
    def _get_insert_position(self):
        positions = translate_list('combo_insert_positions')
        default_position = positions[3] if len(positions) > 3 else '左上'
        return self.params.get('insert_position', default_position)
    
    def _get_insert_position_index(self):
        return self.params.get('insert_position_index', 0)
    
    def _get_column_widths(self):
        return self.params.get('table_column_widths')
    
    def _get_row_height(self):
        return self.params.get('table_row_height')
    
    def _get_table_params(self):
        return self.params.get('table_params', {'cols': 3, 'rows': 3})
    
    def _show_results(self):
        success_count = sum(1 for r in self.results if r.get('success'))
        total_count = len(self.results)
        if self.tool_instance and hasattr(self.tool_instance, 'grids'):
            grid = self.tool_instance.grids.get('pdf')
            if grid:
                for r in self.results:
                    if r.get('success'):
                        grid.set_result(r['file'], translate('result_success'))
                    elif r.get('raw_error'):
                        # 已本地化的失败信息（如加密、无可用位置）原样显示
                        grid.set_result(r['file'], r.get('error', ''))
                    else:
                        error_msg = r.get('error', '')
                        short_error = self._get_short_error(error_msg)
                        grid.set_result(r['file'], f'{translate("result_failed")}: {short_error}')
        message = self._build_completion_message(success_count, total_count)
        def _do_show():
            wx.MessageBox(message, translate('tool_name'), wx.OK | wx.ICON_INFORMATION)
        wx.CallAfter(_do_show)
    
    def _execute_get_file_info(self):
        if not self.data:
            self._show_error(translate('msg_no_data'))
            return False
        
        grid = None
        if self.tool_instance and hasattr(self.tool_instance, 'grids'):
            grid = self.tool_instance.grids.get('pdf')
        
        pdf_info_keys = [
            'pdf_info_page_count', 'pdf_info_file_size', 'pdf_info_orientation',
            'pdf_info_page_size', 'pdf_info_title', 'pdf_info_author',
            'pdf_info_creation_date', 'pdf_info_modification_date', 'pdf_info_encrypted'
        ]
        
        success_count = 0
        error_count = 0
        
        for idx, row_data in enumerate(self.data):
            source_file = row_data.get('source_file', '')
            if not source_file or not source_file.strip():
                continue
            
            if not os.path.exists(source_file):
                log_warning(f'File not found: {source_file}')
                self.log_info_row_failure(row_data, 'file not found')
                error_count += 1
                continue
            # B3-2：解析前限制源文件大小（防资源耗尽）
            if not check_source_file_size(source_file):
                log_warning(f'Source file too large (>200 MB): {source_file}')
                self.log_info_row_failure(row_data, 'file too large (>200 MB)')
                error_count += 1
                continue
            try:
                doc = fitz.open(source_file)
                
                page_count = doc.page_count
                
                file_size = os.path.getsize(source_file)
                if file_size < 1024:
                    file_size_str = f'{file_size} B'
                elif file_size < 1024 * 1024:
                    file_size_str = f'{file_size / 1024:.1f} KB'
                else:
                    file_size_str = f'{file_size / (1024 * 1024):.1f} MB'
                
                orientations = set()
                page_sizes = set()
                for page_num in range(page_count):
                    page = doc.load_page(page_num)
                    rect = page.rect
                    width = rect.width
                    height = rect.height
                    if width > height:
                        orientations.add('landscape')
                    else:
                        orientations.add('portrait')
                    page_sizes.add((width, height))
                
                if len(orientations) == 1:
                    orientation = orientations.pop()
                    if orientation == 'landscape':
                        orientation_str = translate('pdf_info_landscape')
                    else:
                        orientation_str = translate('pdf_info_portrait')
                else:
                    orientation_str = translate('pdf_info_mixed')
                
                if len(page_sizes) == 1:
                    width, height = list(page_sizes)[0]
                    page_size_str = f'{width:.0f} x {height:.0f}'
                else:
                    page_size_str = translate('pdf_info_not_available')
                
                metadata = doc.metadata
                title = metadata.get('title', '')
                author = metadata.get('author', '')
                creation_date = metadata.get('creationDate', '')
                mod_date = metadata.get('modDate', '')
                
                if not title:
                    title = os.path.splitext(os.path.basename(source_file))[0]
                if not author:
                    author = translate('pdf_info_not_available')
                
                file_stat = os.stat(source_file)
                file_created = file_stat.st_ctime
                file_modified = file_stat.st_mtime
                
                creation_date_str = translate('pdf_info_not_available')
                if creation_date:
                    try:
                        if 'D:' in creation_date:
                            date_part = creation_date[2:10]
                            year = date_part[:4]
                            month = date_part[4:6]
                            day = date_part[6:8]
                            creation_date_str = f'{year}-{month}-{day}'
                    except Exception:
                        pass
                if creation_date_str == translate('pdf_info_not_available'):
                    try:
                        from datetime import datetime
                        creation_date_str = datetime.fromtimestamp(file_created).strftime('%Y-%m-%d')
                    except (ValueError, AttributeError):
                        pass
                
                mod_date_str = translate('pdf_info_not_available')
                if mod_date:
                    try:
                        if 'D:' in mod_date:
                            date_part = mod_date[2:10]
                            year = date_part[:4]
                            month = date_part[4:6]
                            day = date_part[6:8]
                            mod_date_str = f'{year}-{month}-{day}'
                    except Exception:
                        pass
                if mod_date_str == translate('pdf_info_not_available'):
                    try:
                        from datetime import datetime
                        mod_date_str = datetime.fromtimestamp(file_modified).strftime('%Y-%m-%d')
                    except (ValueError, AttributeError):
                        pass
                
                encrypted = doc.is_encrypted
                encrypted_str = translate('pdf_info_yes') if encrypted else translate('pdf_info_no')
                
                doc.close()
                
                pdf_info_values = [
                    str(page_count),
                    file_size_str,
                    orientation_str,
                    page_size_str,
                    title,
                    author,
                    creation_date_str,
                    mod_date_str,
                    encrypted_str
                ]
                
                if grid:
                    row_index = row_data.get('row_index', 0)
                    for col_idx, value in enumerate(pdf_info_values):
                        grid.SetCellValue(row_index, grid.COL_DATA_START + col_idx, value)
                
                log_info(f'PDF info extracted: {source_file}')
                success_count += 1
                
            except Exception as e:
                log_error(f'Error extracting PDF info from {source_file}: {e}')
                self.log_info_row_failure(row_data, str(e))
                error_count += 1
                if grid:
                    row_index = row_data.get('row_index', 0)
                    for col_idx in range(len(pdf_info_keys)):
                        grid.SetCellValue(row_index, grid.COL_DATA_START + col_idx, str(e))
        
        log_info(f'Get PDF Info completed: {success_count} success, {error_count} errors')
        
        # 获取文档信息：仅在存在未成功的行时弹窗提示，全部成功时静默完成
        if error_count > 0:
            message = translate('msg_info_failed_rows', count=error_count)
            wx.MessageBox(message, translate('msg_warning'), wx.OK | wx.ICON_WARNING)
        
        return True
    
    def _get_short_error(self, error_msg):
        if not error_msg:
            return translate('result_error_unknown')
        error_lower = error_msg.lower()
        if 'permission' in error_lower or '权限' in error_msg:
            return translate('result_error_permission')
        if 'not found' in error_lower or '不存在' in error_msg:
            return translate('result_error_not_found')
        if 'invalid' in error_lower or '无效' in error_msg:
            return translate('result_error_invalid')
        if 'timeout' in error_lower or '超时' in error_msg:
            return translate('result_error_timeout')
        if 'memory' in error_lower or '内存' in error_msg:
            return translate('result_error_memory')
        return translate('result_error_other')
    
    def preview(self, rows_data):
        if not HAS_FITZ:
            return None
        if not rows_data:
            return None
        if isinstance(rows_data, dict):
            rows_data = [rows_data]
        source_file = rows_data[0].get('source_file', '')
        save_file = rows_data[0].get('save_file', '')
        if not source_file or not os.path.exists(source_file):
            self.log_group_result(save_file, rows_data, False, error='Source file not found')
            return None
        # B3-2：解析前限制源文件大小（防资源耗尽）
        if not check_source_file_size(source_file):
            log_error(f'Source file too large (>200 MB), skip preview: {source_file}')
            self.log_group_result(save_file, rows_data, False, error='Source file too large (>200 MB)')
            return None
        try:
            temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
            temp_path = temp_file.name
            temp_file.close()
            shutil.copy2(source_file, temp_path)
            doc = fitz.open(temp_path)
            try:
                if self.fill_method == 'placeholder':
                    self._process_placeholder_mode(doc, rows_data)
                elif self.fill_method == 'add_text':
                    insert_position = self._get_insert_position()
                    self._process_insert_text_mode(doc, rows_data, insert_position)
                elif self.fill_method == 'add_table':
                    insert_position = self._get_insert_position()
                    self._process_insert_table_mode(doc, rows_data, insert_position)
                elif self.fill_method == 'add_image':
                    insert_position = self._get_insert_position()
                    self._process_insert_image_mode(doc, rows_data, insert_position)
                elif self.fill_method == 'delete_table':
                    self._process_delete_table_mode(doc, rows_data)
                else:
                    insert_position = self._get_insert_position()
                    self._process_insert_text_mode(doc, rows_data, insert_position)
                images = []
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    mat = fitz.Matrix(2, 2)
                    pix = page.get_pixmap(matrix=mat)
                    img_data = pix.tobytes('png')
                    images.append(img_data)
                self.log_group_result(save_file, rows_data, True)
                return {'type': 'pdf', 'images': images, 'page_count': len(images)}
            finally:
                doc.close()
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
        except Exception as e:
            log_error(f'Preview failed: {e}')
            self.log_group_result(save_file, rows_data, False, error=str(e))
            return None
    
    def render_page_to_image(self, source_file, page_num=0, zoom=2):
        if not HAS_FITZ:
            return None
        if not source_file or not os.path.exists(source_file):
            return None
        # B3-2：解析前限制源文件大小（防资源耗尽）
        if not check_source_file_size(source_file):
            log_error(f'Source file too large (>200 MB), skip render: {source_file}')
            return None
        try:
            doc = fitz.open(source_file)
            if page_num < len(doc):
                page = doc[page_num]
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes('png')
                doc.close()
                return img_data
            doc.close()
        except Exception as e:
            log_error(f'Render page failed: {e}')
        return None
