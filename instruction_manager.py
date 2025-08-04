import os
import json
import logging
from typing import Optional
from datetime import datetime

from localization import loc
from config import default_system_instruction

logger = logging.getLogger("InstructionManager")

INSTRUCTIONS_DIR = "instructions"
DEFAULT_INSTRUCTION_FILE = "default_instruction.json"

def ensure_instructions_dir():
    if not os.path.exists(INSTRUCTIONS_DIR):
        os.makedirs(INSTRUCTIONS_DIR)

def get_user_instruction_path(user_id: int) -> str:
    ensure_instructions_dir()
    return os.path.join(INSTRUCTIONS_DIR, f"user_{user_id}.json")

def get_default_instruction_path() -> str:
    ensure_instructions_dir()
    return os.path.join(INSTRUCTIONS_DIR, DEFAULT_INSTRUCTION_FILE)

def save_instruction(filepath: str, instruction: str, title: str = ""):
    try:
        data = {
            "instruction": instruction,
            "title": title,
            "created_at": datetime.now().isoformat()
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(loc.get_string("logs.instruction_saved", path=filepath))
    except Exception as e:
        logger.error(loc.get_string("logs.instruction_save_error", path=filepath, error=e))

def load_instruction(filepath: str) -> Optional[dict]:
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(loc.get_string("logs.instruction_load_error", path=filepath, error=e))
        return None

def get_user_instruction(user_id: int) -> str:
    user_data = load_instruction(get_user_instruction_path(user_id))
    if user_data:
        return user_data["instruction"]
    
    default_data = load_instruction(get_default_instruction_path())
    if default_data:
        return default_data["instruction"]
    
    return default_system_instruction

def set_user_instruction(user_id: int, instruction: str, title: str = "") -> str:
    if not instruction.strip():
        return loc.get_string("replies.instruction_cannot_be_empty")
    
    filepath = get_user_instruction_path(user_id)
    save_instruction(filepath, instruction, title)
    return loc.get_string("replies.instruction_personal_set", title=title or loc.get_string("replies.instruction_no_title"))

def set_default_instruction(instruction: str, title: str = "") -> str:
    if not instruction.strip():
        return loc.get_string("replies.instruction_cannot_be_empty")
    
    filepath = get_default_instruction_path()
    save_instruction(filepath, instruction, title)
    return loc.get_string("replies.instruction_global_set", title=title or loc.get_string("replies.instruction_no_title"))

def delete_user_instruction(user_id: int) -> str:
    filepath = get_user_instruction_path(user_id)
    if not os.path.exists(filepath):
        return loc.get_string("replies.instruction_personal_not_found")
    
    try:
        os.remove(filepath)
        return loc.get_string("replies.instruction_personal_deleted")
    except Exception as e:
        logger.error(loc.get_string("logs.instruction_delete_error", path=filepath, error=e))
        return loc.get_string("replies.instruction_delete_failed")

def get_instruction_info(user_id: int) -> str:
    user_data = load_instruction(get_user_instruction_path(user_id))
    default_data = load_instruction(get_default_instruction_path())
    
    info = loc.get_string("replies.instruction_info_header")
    
    def format_date(iso_date_str):
        if not iso_date_str: return "N/A"
        return datetime.fromisoformat(iso_date_str).strftime('%d.%m.%Y %H:%M')

    if user_data:
        info += loc.get_string("replies.instruction_info_personal_section",
                               title=user_data.get('title') or loc.get_string("replies.instruction_no_title"),
                               length=len(user_data['instruction']),
                               created_at=format_date(user_data.get('created_at')))
    else:
        info += loc.get_string("replies.instruction_info_personal_none")
    
    if default_data:
        info += loc.get_string("replies.instruction_info_global_section",
                               title=default_data.get('title') or loc.get_string("replies.instruction_no_title"),
                               length=len(default_data['instruction']),
                               created_at=format_date(default_data.get('created_at')))
    else:
        info += loc.get_string("replies.instruction_info_global_fallback")
    
    current_instruction = get_user_instruction(user_id)
    info += loc.get_string("replies.instruction_info_active_section",
                           length=len(current_instruction),
                           preview=f"{current_instruction[:200]}{'...' if len(current_instruction) > 200 else ''}")
    
    return info