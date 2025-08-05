import json
import os
import logging
from typing import Dict, Any

from config import AVAILABLE_LANGUAGES

logger = logging.getLogger("Localization")
LANG_CONFIG_FILE = ".lang"

class LocalizationManager:
    """
    Manages loading and accessing localized strings with a fallback to English.
    Handles language selection on the first run.
    """
    def __init__(self):
        self.locales_dir = "locales"
        self.fallback_lang = "en_US"
        self.strings = {}
        self.fallback_strings = {}
        self.selected_lang = None
        self._initialized = False

    def initialize(self):
        """
        This method performs the actual setup. It's called once from main.py
        after the instance is created.
        """
        if self._initialized:
            return
            
        if not os.path.exists(self.locales_dir):
            logger.error(f"Localization directory '{self.locales_dir}' not found!")
            return

        self._load_lang_file(self.fallback_lang, is_fallback=True)

        self.selected_lang = self._get_or_select_language()

        if self.selected_lang and self.selected_lang != self.fallback_lang:
            self._load_lang_file(self.selected_lang)
        else:
            self.strings = self.fallback_strings
            
        self._initialized = True


    def _get_or_select_language(self) -> str:
        """
        Gets the language from .lang file or prompts the user to select one if the file doesn't exist.
        """
        if os.path.exists(LANG_CONFIG_FILE):
            try:
                with open(LANG_CONFIG_FILE, "r") as f:
                    lang_code = f.read().strip()
                if lang_code in AVAILABLE_LANGUAGES:
                    logger.info(f"Language loaded from .lang file: {lang_code}")
                    return lang_code
                else:
                    logger.warning(f"Invalid language code '{lang_code}' in .lang file. Prompting for selection.")
            except Exception as e:
                logger.error(f"Error reading .lang file: {e}. Prompting for selection.")
        
        print("--- Language Selection ---")
        print("Please select your preferred language for the bot interface and logs.")
        
        lang_options = list(AVAILABLE_LANGUAGES.items())
        
        for i, (code, name) in enumerate(lang_options):
            print(f"  {i + 1}. {name} ({code})")
            
        while True:
            try:
                choice = int(input("Enter the number of your choice: ")) - 1
                if 0 <= choice < len(lang_options):
                    selected_code = lang_options[choice][0]
                    with open(LANG_CONFIG_FILE, "w") as f:
                        f.write(selected_code)
                    print(f"Language set to {AVAILABLE_LANGUAGES[selected_code]}. The bot will now start.")
                    print("You can change the language later by editing or deleting the '.lang' file.")
                    return selected_code
                else:
                    print("Invalid number. Please try again.")
            except ValueError:
                print("Invalid input. Please enter a number.")


    def _load_lang_file(self, lang_code: str, is_fallback: bool = False):
        """Internal function to load a language file."""
        file_path = os.path.join(self.locales_dir, f"{lang_code}.json")
        if not os.path.exists(file_path):
            logger.error(f"Localization file '{file_path}' not found.")
            if not is_fallback:
                logger.warning(f"Falling back to {self.fallback_lang} because {lang_code}.json is missing.")
                self.strings = self.fallback_strings
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if is_fallback:
                    self.fallback_strings = data
                else:
                    self.strings = data
            logger.info(f"Language '{lang_code}' loaded successfully {'as fallback' if is_fallback else ''}.")
        except Exception as e:
            logger.error(f"Error reading or parsing file '{file_path}': {e}")
    
    def _get_value(self, keys: list[str], dictionary: Dict) -> Any:
        """Recursively finds a value by a list of keys."""
        key = keys[0]
        if key not in dictionary:
            raise KeyError
        
        value = dictionary[key]
        if len(keys) == 1:
            return value
        
        return self._get_value(keys[1:], value)

    def get_string(self, key: str, **kwargs) -> str:
        """
        Gets a string by key. If the key is not found in the main language,
        it searches for it in the fallback (English).
        """
        if not self._initialized:
            return f"[loc_uninitialized: {key}]"

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
            try:
                return value.format(**kwargs)
            except KeyError as e:
                logger.error(f"Missing format key {e} for localization key '{key}'")
                return value
        
        return value if isinstance(value, str) else f"[invalid_key_type: {key}]"

    def get_section(self, key: str) -> Any:
        """
        Gets a section (dict) or a value (list, string) by key.
        Searches in the main language first, then in the fallback.
        """
        if not self._initialized:
            return {} 

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

loc = LocalizationManager()