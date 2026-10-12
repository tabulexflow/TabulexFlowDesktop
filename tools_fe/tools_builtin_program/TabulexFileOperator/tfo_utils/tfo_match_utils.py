# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import re
import regex

from tfo_utils.tfo_i18n_manager import translate

_MAX_REGEX_LENGTH = 200
_MAX_REGEX_QUANTIFIERS = 10
_MAX_NESTED_QUANTIFIERS = 3
_REGEX_TIMEOUT_SECONDS = 2

PRESET_METHODS = {"images_preset", "documents_preset", "compressed_preset", "text_preset"}

EXCLUDE_METHODS = {"exclude_full_names", "exclude_wildcards"}

METHODS_USING_ENDSWITH = {"ends_with_name"} | PRESET_METHODS


def validate_regex_complexity(pattern: str) -> str:
    if len(pattern) > _MAX_REGEX_LENGTH:
        return translate("regex_complexity_too_long", length=len(pattern), max=_MAX_REGEX_LENGTH)
    quantifier_count = 0
    nesting_depth = 0
    max_nesting = 0
    nested_quantifier_count = 0
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == '\\' and i + 1 < len(pattern):
            i += 2
            continue
        if c in ('*', '+', '?'):
            quantifier_count += 1
            if nesting_depth > 0:
                nested_quantifier_count += 1
        elif c == '{':
            quantifier_count += 1
            if nesting_depth > 0:
                nested_quantifier_count += 1
        elif c == '(':
            nesting_depth += 1
            max_nesting = max(max_nesting, nesting_depth)
        elif c == ')':
            nesting_depth = max(0, nesting_depth - 1)
        i += 1
    if quantifier_count > _MAX_REGEX_QUANTIFIERS:
        return translate("regex_complexity_quantifiers", count=quantifier_count, max=_MAX_REGEX_QUANTIFIERS)
    if max_nesting > 5:
        return translate("regex_complexity_nesting", depth=max_nesting)
    if nested_quantifier_count > _MAX_NESTED_QUANTIFIERS:
        return translate("regex_complexity_nested_quantifiers", count=nested_quantifier_count, max=_MAX_NESTED_QUANTIFIERS)
    return ""


def regex_match_with_timeout(pattern: str, text: str) -> re.Match:
    try:
        return regex.match(pattern, text, timeout=_REGEX_TIMEOUT_SECONDS)
    except TimeoutError:
        return None
    except regex.error:
        return None


def regex_fullmatch_with_timeout(pattern: str, text: str) -> re.Match:
    """正则"完全匹配"语义（整个字符串必须匹配），供名称匹配场景使用"""
    try:
        return regex.fullmatch(pattern, text, timeout=_REGEX_TIMEOUT_SECONDS)
    except TimeoutError:
        return None
    except regex.error:
        return None


def wildcard_to_regex(wildcard: str) -> str:
    if not wildcard:
        return ''
    r = re.escape(wildcard)
    r = r.replace(r'\*', '.*')
    r = r.replace(r'\?', '.')
    return r


def split_match_name_with_quotes(match_name: str) -> list:
    parts = []
    i = 0
    length = len(match_name)
    while i < length:
        while i < length and match_name[i] == ' ':
            i += 1
        if i >= length:
            break
        if match_name[i] == '"':
            j = i + 1
            while j < length and match_name[j] != '"':
                j += 1
            if j < length:
                part = match_name[i + 1:j]
                if part:
                    parts.append(part)
                i = j + 1
            else:
                part = match_name[i:]
                if part:
                    parts.append(part)
                break
        else:
            j = i
            while j < length and match_name[j] != ' ':
                j += 1
            part = match_name[i:j]
            if part:
                parts.append(part)
            i = j
    return parts


def check_name_match_part(file_dir_name: str, match_name: str, match_method: str) -> str:
    if not match_name:
        return None
    file_dir_name_lower = file_dir_name.lower()
    match_name_lower = match_name.lower()
    current_method = match_method

    if current_method == "contains_full_name":
        if match_name_lower in file_dir_name_lower:
            return match_name
        return None

    elif current_method == "contains_all_fragments":
        match_parts = split_match_name_with_quotes(match_name)
        if not match_parts:
            return None
        for part in match_parts:
            if part.lower() not in file_dir_name_lower:
                return None
        return match_name

    elif current_method == "contains_any_fragment":
        match_parts = split_match_name_with_quotes(match_name)
        if not match_parts:
            return None
        for part in match_parts:
            if part.lower() in file_dir_name_lower:
                return part
        return None

    elif current_method == "starts_with_name":
        if file_dir_name_lower.startswith(match_name_lower):
            return match_name
        return None

    elif current_method == "equals_name":
        if file_dir_name_lower == match_name_lower:
            return match_name
        return None

    elif current_method in METHODS_USING_ENDSWITH:
        if file_dir_name_lower.endswith(match_name_lower):
            return match_name
        return None

    elif current_method == "exclude_full_names":
        if match_name and match_name_lower in file_dir_name_lower:
            return None
        return match_name

    elif current_method == "exclude_wildcards":
        match_regex = wildcard_to_regex(match_name)
        try:
            # fullmatch 完全匹配语义：*.txt 不应匹配 a.txt.bak
            if re.fullmatch(match_regex, file_dir_name, re.IGNORECASE) is not None:
                return None
        except re.error:
            pass
        return match_name

    elif current_method == "matches_wildcard":
        match_regex = wildcard_to_regex(match_name)
        try:
            # fullmatch 完全匹配语义：*.txt 不应匹配 a.txt.bak
            if re.fullmatch(match_regex, file_dir_name, re.IGNORECASE) is not None:
                return match_name
        except re.error:
            pass
        return None

    elif current_method == "matches_regex":
        try:
            complexity_error = validate_regex_complexity(match_name)
            if complexity_error:
                return None
            if regex_fullmatch_with_timeout(match_name, file_dir_name) is not None:
                return match_name
        except (re.error, TimeoutError):
            pass
        return None

    return None


def check_name_match_list(file_dir_name: str, match_names: list, match_method: str) -> str:
    if not match_names:
        return None
    current_method = match_method

    if current_method in EXCLUDE_METHODS:
        for match_name in match_names:
            if check_name_match_part(file_dir_name, match_name, match_method) is None:
                return None
        return "/".join(match_names)
    else:
        for match_name in match_names:
            result = check_name_match_part(file_dir_name, match_name, match_method)
            if result is not None:
                return result
        return None
