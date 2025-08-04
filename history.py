import base64
import os
import json
import logging
from google.genai.types import Part
from localization import loc

MAX_HISTORY_MESSAGES = 1000000
MAX_CONTENT_LENGTH = 150000

logger = logging.getLogger("History")

def load_history(history_filepath: str) -> list:
    """Loads history from a JSON file."""
    if os.path.exists(history_filepath):
        try:
            with open(history_filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return []
                history = json.loads(content)
                
                for entry in history:
                    if entry.get("role") == "assistant":
                        entry["role"] = "model"
                
                return history
        except Exception as e:
            logger.error(loc.get_string("logs.history_load_error", path=history_filepath, error=e))
            return []
    return []

def save_history(history_filepath: str, history: list):
    """Saves history to a JSON file."""
    try:
        with open(history_filepath, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(loc.get_string("logs.history_save_error", path=history_filepath, error=e))


def _serialize_part(part: Part) -> dict:
    """Transforms a Part object into a JSON-serializable dictionary, encoding media in Base64."""
    serialized = {}
    
    if hasattr(part, 'text') and part.text:
        text = part.text.strip()
        if len(text) > MAX_CONTENT_LENGTH:
            text = text[:MAX_CONTENT_LENGTH] + loc.get_string("logs.history_content_truncated")
        serialized['text'] = text
        
    if hasattr(part, 'function_call') and part.function_call:
        serialized['function_call'] = {
            'name': part.function_call.name,
            'args': dict(part.function_call.args)
        }
    if hasattr(part, 'function_response') and part.function_response:
        serialized['function_response'] = {
            'name': part.function_response.name,
            'response': dict(part.function_response.response)
        }

    if hasattr(part, 'inline_data') and part.inline_data and hasattr(part.inline_data, 'data'):
        data_b64 = base64.b64encode(part.inline_data.data).decode('utf-8')
        serialized['inline_data'] = {
            'mime_type': part.inline_data.mime_type,
            'data_base64': data_b64
        }
        
    return serialized

def append_history(history_filepath: str, role: str, parts: list[Part]):
    """Adds a new entry to the history, serializing its parts beforehand."""
    if role == "assistant":
        role = "model"
    
    history = load_history(history_filepath)
    
    serialized_parts = [_serialize_part(p) for p in parts if p]
    
    entry = {"role": role, "parts": serialized_parts}
    history.append(entry)

    if len(history) > MAX_HISTORY_MESSAGES:
        history = history[-MAX_HISTORY_MESSAGES:]
        
    save_history(history_filepath, history)

def load_and_deserialize_history_for_model(history_filepath: str) -> list:
    """
    Loads history from a file and transforms it into a format
    understood by genai.Client (with Part objects and bytes).
    """
    history_as_dicts = load_history(history_filepath)
    deserialized_history = []

    for entry in history_as_dicts:
        deserialized_parts = []
        for part_dict in entry.get("parts", []):
            try:
                part_data = part_dict.copy()
                
                if 'inline_data' in part_data and 'data_base64' in part_data['inline_data']:
                    encoded_data = part_data['inline_data'].pop('data_base64')
                    part_data['inline_data']['data'] = base64.b64decode(encoded_data)
                
                deserialized_parts.append(Part(**part_data))
                
            except Exception as e:
                logger.error(loc.get_string("logs.history_part_deserialize_error", part=part_dict, error=e))

        deserialized_history.append({
            "role": entry["role"],
            "parts": deserialized_parts
        })
    
    return deserialized_history