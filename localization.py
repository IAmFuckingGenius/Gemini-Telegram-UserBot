import json
import os
import logging
from typing import Dict, Any, List

logger = logging.getLogger("Localization")

class LocalizationManager:
    """
    Manages loading and accessing localized strings with English fallback.
    """
    def __init__(self, locales_dir: str = "locales", default_lang: str = "ru_RU", fallback_lang: str = "en_US"):
        self.locales_dir = locales_dir
        self.strings = {}
        self.fallback_strings = {}
        
        if not os.path.exists(self.locales_dir):
            logger.error(f"Localization directory '{self.locales_dir}' not found!")
            return

        self._load_lang_file(fallback_lang, is_fallback=True)

        if default_lang != fallback_lang:
            self._load_lang_file(default_lang)
        else:
            self.strings = self.fallback_strings

    def _load_lang_file(self, lang_code: str, is_fallback: bool = False):
        """Internal function to load a language file."""
        file_path = os.path.join(self.locales_dir, f"{lang_code}.json")
        if not os.path.exists(file_path):
            logger.error(f"Localization file '{file_path}' not found.")
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if is_fallback:
                    self.fallback_strings = data
                else:
                    self.strings = data
            logger.info(f"Language '{lang_code}' successfully loaded {'as fallback' if is_fallback else ''}.")
        except Exception as e:
            logger.error(f"Error reading or parsing file '{file_path}': {e}")
    
    def _get_value(self, keys: List[str], dictionary: Dict) -> Any:
        """Recursively searches for a value by a list of keys."""
        key = keys[0]
        if key not in dictionary:
            raise KeyError
        
        value = dictionary[key]
        if len(keys) == 1:
            return value
        
        return self._get_value(keys[1:], value)

    def get_string(self, key: str, **kwargs) -> str:
        """
        Retrieves a string by key. If the key is not found in the primary language,
        it searches for it in the fallback (English) language.
        """
        keys = key.split('.')
        value = None
        try:
            value = self._get_value(keys, self.strings)
        except (KeyError, TypeError):
            try:
                value = self._get_value(keys, self.fallback_strings)
            except (KeyError, TypeError):
                logger.warning(f"Localization key not found in any language: '{key}'")
                return f"[missing_key: {key}]"
        
        if isinstance(value, str) and kwargs:
            return value.format(**kwargs)
        
        return value if isinstance(value, str) else f"[invalid_key_type: {key}]"

    def get_section(self, key: str) -> Any:
        """
        Retrieves a section (dictionary) or value (list, string) by key.
        It first searches in the primary language, then in the fallback.
        """
        keys = key.split('.')
        try:
            value = self.strings
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            try:
                value = self.fallback_strings
                for k in keys:
                    value = value[k]
                return value
            except (KeyError, TypeError):
                logger.warning(f"Localization section/key not found in any language: '{key}'")
                return {}

loc = LocalizationManager(default_lang="en_US")