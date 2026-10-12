# Copyright (C) 2024-present TabulexFlow Team
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import sys
import json
from pathlib import Path

SUPPORTED_LANGUAGES = ['en', 'zh', 'fr', 'ru', 'es', 'ar']


class TFP_I18nManager:

    def __init__(self, default_language='en', default_translations=None):
        self.default_language = default_language
        self.current_language = default_language
        self.translations = {}
        self.locales_dir = None
        self._default_translations = default_translations or {}
        self._initialized = False
        self.load_translations()
        self.load_saved_language_setting()
        self._initialized = True

    def load_translations(self):
        for lang in SUPPORTED_LANGUAGES:
            self.translations[lang] = {}
            if lang in self._default_translations:
                self.translations[lang] = self._default_translations[lang].copy()

        locales_dir = self._find_locales_dir()
        if locales_dir:
            self.locales_dir = locales_dir
            for lang in SUPPORTED_LANGUAGES:
                lang_file = os.path.join(locales_dir, f'{lang}.json')
                if os.path.exists(lang_file):
                    try:
                        with open(lang_file, 'r', encoding='utf-8') as f:
                            loaded_translations = json.load(f)
                            if lang in self.translations:
                                self.translations[lang].update(loaded_translations)
                            else:
                                self.translations[lang] = loaded_translations
                    except Exception as e:
                        print(f"Error loading {lang}.json: {e}")

        self._load_main_app_translations()

    def _find_locales_dir(self):
        # 与 tfp_toolkit/tfp_i18n_manager.py（SDK 权威源）保持实现一致（T3.2）：
        # 同步 SDK 版的 Nuitka --standalone 分支（主程序经 PyInstaller 打包时
        # '__compiled__' 不存在，该分支不触发，无行为影响）
        if '__compiled__' in globals():
            exe_dir = Path(sys.executable).parent
            locales = exe_dir / 'locales'
            if locales.exists():
                return str(locales)
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base = Path(sys._MEIPASS)
            locales = base / 'locales'
            if locales.exists():
                return str(locales)
        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            locales = exe_dir / 'locales'
            if locales.exists():
                return str(locales)
        try:
            base = Path(__file__).parent
            locales = base.parent / 'locales'
            if locales.exists():
                return str(locales)
        except OSError:
            pass
        return None

    def _load_main_app_translations(self):
        possible_paths = []
        # 与 tfp_toolkit/tfp_i18n_manager.py（SDK 权威源）保持实现一致（T3.2）：
        # 同步 SDK 版的 Nuitka --standalone 分支（PyInstaller 打包下不触发，无行为影响）
        if '__compiled__' in globals():
            exe_dir = Path(sys.executable).parent
            possible_paths.append(exe_dir / 'locales')
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base = Path(sys._MEIPASS)
            possible_paths.append(base / 'locales')
        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            possible_paths.append(exe_dir / 'locales')
        try:
            base = Path(__file__).parent.parent
            possible_paths.append(base / 'locales')
        except OSError:
            pass
        for locales_dir in possible_paths:
            if locales_dir and locales_dir.exists():
                for lang in SUPPORTED_LANGUAGES:
                    lang_file = locales_dir / f'{lang}.json'
                    if lang_file.exists():
                        try:
                            with open(lang_file, 'r', encoding='utf-8') as f:
                                main_app_translations = json.load(f)
                                if lang not in self.translations:
                                    self.translations[lang] = {}
                                self.translations[lang].update(main_app_translations)
                        except Exception as e:
                            print(f"Error loading main app {lang}.json: {e}")
                break

    def load_saved_language_setting(self):
        try:
            config_file = self._find_language_config_file()
            if config_file and config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                saved_lang = config.get('language', self.default_language)
                if saved_lang in self.translations:
                    self.current_language = saved_lang
        except Exception as e:
            print(f"Error loading saved language setting: {e}")

    def _find_language_config_file(self):
        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            config_file = exe_dir / 'config' / 'language_settings.json'
            if config_file.exists():
                return config_file
        try:
            base = Path(__file__).parent.parent
            config_file = base / 'config' / 'language_settings.json'
            if config_file.exists():
                return config_file
        except OSError:
            pass
        return None

    def set_language(self, language):
        if language in self.translations:
            self.current_language = language
            return True
        return False

    def get(self, key, **kwargs):
        if self.current_language in self.translations and key in self.translations[self.current_language]:
            text = self.translations[self.current_language][key]
        elif self.default_language in self.translations and key in self.translations[self.default_language]:
            text = self.translations[self.default_language][key]
        else:
            return key
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                return text
        return text

    def apply_remote_overrides(self, overrides):
        # T8.3.2 远程覆盖层合并入口（覆盖式、保离线）：
        # 后端有&本地有→后端值覆盖；后端有&本地无→补充新增；后端无&本地有→保留本地。
        # 仅接受 SUPPORTED_LANGUAGES 内 locale；非字典/非字符串值忽略。返回实际合并键数。
        # 注意：本方法为 tfp_utils/tfp_toolkit 双源文件，两侧实现必须保持一致
        #（tests/test_tfp_dual_source_consistency.py 守护）。
        if not isinstance(overrides, dict):
            return 0
        applied = 0
        for locale, entries in overrides.items():
            if str(locale) not in SUPPORTED_LANGUAGES or not isinstance(entries, dict):
                continue
            bucket = self.translations.setdefault(str(locale), {})
            for key, text in entries.items():
                if not isinstance(text, str):
                    continue
                bucket[str(key)] = text
                applied += 1
        return applied

    def get_language_code(self):
        return self.current_language

    def get_available_languages(self):
        return list(self.translations.keys())


def translate_list(i18n_instance, key):
    result = i18n_instance.get(key)
    if isinstance(result, list):
        return result
    elif isinstance(result, str):
        return [result]
    else:
        return []


i18n = TFP_I18nManager()


def translate(key, **kwargs):
    return i18n.get(key, **kwargs)
