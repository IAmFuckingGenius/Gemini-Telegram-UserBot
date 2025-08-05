import os
import json
import logging
import time
from typing import Dict, Any, Tuple
from datetime import datetime
from localization import loc

SESSIONS_BASE_DIR = "histories"
if not os.path.exists(SESSIONS_BASE_DIR):
    os.makedirs(SESSIONS_BASE_DIR)

logger = logging.getLogger("SessionManager")

PRICES = {
    "gemini-2.5-pro": {
        "input": 2.50,
        "output": 10.00
    },
    "gemini-2.5-flash": {
        "input": 1.25,
        "output": 2.50
    }
}

def get_user_dir(user_id: int) -> str:
    return os.path.join(SESSIONS_BASE_DIR, str(user_id))

def get_profile_path(user_id: int) -> str:
    return os.path.join(get_user_dir(user_id), "user_profile.json")

def get_sessions_dir(user_id: int) -> str:
    return os.path.join(get_user_dir(user_id), "sessions")

def get_session_path(user_id: int, session_id: str) -> str:
    return os.path.join(get_sessions_dir(user_id), f"{session_id}.json")

def get_user_profile(user_id: int, username: str, first_name: str) -> Dict[str, Any]:
    profile_path = get_profile_path(user_id)
    if os.path.exists(profile_path):
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile = json.load(f)
        except json.JSONDecodeError:
            return _create_new_profile(user_id, username, first_name)
            
        if profile.get('username') != username or profile.get('first_name') != first_name:
            profile['username'] = username
            profile['first_name'] = first_name
            save_user_profile(user_id, profile)
        
        profile_was_modified = False
        if 'sessions' in profile and isinstance(profile['sessions'], dict):
            for session_id, session_data in list(profile['sessions'].items()):
                if isinstance(session_data, str):
                    logger.warning(loc.get_string("logs.session_old_format_found", data=session_data))
                    new_session_structure = {
                        "name": session_data,
                        "created_at": datetime.now().isoformat(),
                        "stats": {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0, "total_cost": 0.0}
                    }
                    profile['sessions'][session_id] = new_session_structure
                    profile_was_modified = True
        
        if profile_was_modified:
            logger.info(loc.get_string("logs.session_profile_updated", user_id=user_id))
            save_user_profile(user_id, profile)
        return profile

    return _create_new_profile(user_id, username, first_name)

def _create_new_profile(user_id: int, username: str, first_name: str) -> Dict[str, Any]:
    user_dir = get_user_dir(user_id)
    sessions_dir = get_sessions_dir(user_id)
    os.makedirs(user_dir, exist_ok=True)
    os.makedirs(sessions_dir, exist_ok=True)

    session_id = f"session_{int(time.time())}"
    profile = {
        "user_id": user_id,
        "username": username,
        "first_name": first_name,
        "active_session_id": session_id,
        "sessions": {
            session_id: {
                "name": loc.get_string("session_manager.default_chat_name"),
                "created_at": datetime.now().isoformat(),
                "stats": {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0, "total_cost": 0.0}
            }
        }
    }
    save_user_profile(user_id, profile)
    with open(get_session_path(user_id, session_id), 'w', encoding='utf-8') as f:
        json.dump([], f)
    return profile

def save_user_profile(user_id: int, profile: Dict[str, Any]):
    with open(get_profile_path(user_id), 'w', encoding='utf-8') as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

def get_active_session_path(user_id: int, username: str, first_name: str) -> str:
    profile = get_user_profile(user_id, username, first_name)
    active_id = profile.get('active_session_id')
    if not active_id or active_id not in profile['sessions']:
        active_id = next(iter(profile.get('sessions', {})))
        if not active_id: return None
        profile['active_session_id'] = active_id
        save_user_profile(user_id, profile)
    return get_session_path(user_id, active_id)

def create_session(user_id: int, username: str, first_name: str, session_name: str) -> Tuple[bool, str]:
    profile = get_user_profile(user_id, username, first_name)
    existing_names = [s.get('name', '').lower() for s in profile['sessions'].values() if isinstance(s, dict)]
    if session_name.lower() in existing_names:
        return False, loc.get_string("session_manager.session_exists", name=session_name)
    
    session_id = f"session_{int(time.time())}"
    profile['sessions'][session_id] = {
        "name": session_name,
        "created_at": datetime.now().isoformat(),
        "stats": {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0, "total_cost": 0.0}
    }
    profile['active_session_id'] = session_id
    save_user_profile(user_id, profile)
    with open(get_session_path(user_id, session_id), 'w', encoding='utf-8') as f:
        json.dump([], f)
    return True, loc.get_string("session_manager.session_created", name=session_name)
    
def switch_session(user_id: int, username: str, first_name: str, session_name: str) -> Tuple[bool, str]:
    profile = get_user_profile(user_id, username, first_name)
    target_id = next((sid for sid, sdata in profile['sessions'].items() if isinstance(sdata, dict) and sdata.get('name', '').lower() == session_name.lower()), None)
    if not target_id:
        return False, loc.get_string("session_manager.session_not_found", name=session_name)
    profile['active_session_id'] = target_id
    save_user_profile(user_id, profile)
    return True, loc.get_string("session_manager.session_switched", name=profile['sessions'][target_id]['name'])

def delete_session(user_id: int, username: str, first_name: str, session_name: str) -> Tuple[bool, str]:
    profile = get_user_profile(user_id, username, first_name)
    target_id = next((sid for sid, sdata in profile['sessions'].items() if (isinstance(sdata, dict) and sdata.get('name', '').lower() == session_name.lower()) or (isinstance(sdata, str) and sdata.lower() == session_name.lower())), None)

    if not target_id: return False, loc.get_string("session_manager.session_not_found", name=session_name)
    if len(profile['sessions']) <= 1: return False, loc.get_string("session_manager.cannot_delete_last")

    was_active = (profile['active_session_id'] == target_id)
    deleted_data = profile['sessions'].pop(target_id)
    deleted_name = deleted_data.get('name') if isinstance(deleted_data, dict) else deleted_data
    
    if was_active:
        new_active_id = next(iter(profile['sessions']))
        profile['active_session_id'] = new_active_id
        new_active_data = profile['sessions'][new_active_id]
        new_active_name = new_active_data.get('name') if isinstance(new_active_data, dict) else new_active_data
        msg = loc.get_string("session_manager.session_deleted_and_switched", deleted_name=deleted_name, new_active_name=new_active_name)
    else:
        msg = loc.get_string("session_manager.session_deleted", name=deleted_name)

    save_user_profile(user_id, profile)
    session_file = get_session_path(user_id, target_id)
    if os.path.exists(session_file): os.remove(session_file)
    
    return True, msg

def rename_session(user_id: int, username: str, first_name: str, old_name: str, new_name: str) -> Tuple[bool, str]:
    profile = get_user_profile(user_id, username, first_name)
    existing_names = [s.get('name', '').lower() for s in profile['sessions'].values() if isinstance(s, dict)]
    if new_name.lower() in existing_names:
        return False, loc.get_string("session_manager.name_taken", name=new_name)

    target_id = next((sid for sid, sdata in profile['sessions'].items() if isinstance(sdata, dict) and sdata.get('name', '').lower() == old_name.lower()), None)
    if not target_id: return False, loc.get_string("session_manager.session_not_found", name=old_name)
    
    profile['sessions'][target_id]['name'] = new_name
    save_user_profile(user_id, profile)
    return True, loc.get_string("session_manager.renamed", old_name=old_name, new_name=new_name)

def get_active_session_display_name(user_id: int, username: str, first_name: str) -> str:
    profile = get_user_profile(user_id, username, first_name)
    if not profile:
        return loc.get_string("session_manager.default_chat_name")

    active_id = profile.get('active_session_id', 'default')
    session_object = profile.get('sessions', {}).get(active_id)
    
    if isinstance(session_object, dict):
        return session_object.get('name', f"ID: {active_id}")
    elif isinstance(session_object, str):
        return session_object
    else:
        return loc.get_string("session_manager.default_chat_name")

def get_all_sessions_info(user_id: int, username: str, first_name: str) -> list:
    profile = get_user_profile(user_id, username, first_name)
    active_id = profile.get('active_session_id')
    sessions_info = []

    for session_id, session_data in profile.get('sessions', {}).items():
        session_path = get_session_path(user_id, session_id)
        if not os.path.exists(session_path): continue

        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                history = json.loads(f.read().strip() or "[]")
            msg_count = sum(1 for msg in history if msg.get("role") != "tool")
            
            common_info = {
                "is_active": session_id == active_id,
                "msg_count": msg_count,
                "last_modified": datetime.fromtimestamp(os.path.getmtime(session_path))
            }
            if isinstance(session_data, dict):
                sessions_info.append({
                    "name": session_data.get('name', loc.get_string("session_manager.unnamed_session")),
                    "created_at": session_data.get('created_at'),
                    "stats": session_data.get('stats', {}),
                    **common_info
                })
            elif isinstance(session_data, str):
                sessions_info.append({
                    "name": session_data,
                    "created_at": None,
                    "stats": {},
                    **common_info
                })
        except (IOError, json.JSONDecodeError, OSError) as e:
            logger.warning(loc.get_string("logs.session_file_process_error", path=session_path, error=e))
            continue

    sessions_info.sort(key=lambda x: (not x["is_active"], x["last_modified"]), reverse=True)
    return sessions_info
    
def update_session_stats(user_id: int, username: str, first_name: str, prompt_tokens: int, output_tokens: int):
    profile = get_user_profile(user_id, username, first_name)
    active_id = profile.get('active_session_id')
    if not active_id or active_id not in profile['sessions']: return

    safe_prompt_tokens = prompt_tokens or 0
    safe_output_tokens = output_tokens or 0

    session_data = profile['sessions'][active_id]
    
    if not isinstance(session_data, dict):
        logger.warning(loc.get_string("logs.session_stats_update_failed_is_string", session_id=active_id))
        return

    if 'stats' not in session_data:
        session_data['stats'] = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0, "total_cost": 0.0}
    
    stats = session_data['stats']
    stats['prompt_tokens'] = safe_prompt_tokens
    stats['output_tokens'] = safe_output_tokens
    stats['total_tokens'] = safe_prompt_tokens + safe_output_tokens

    from model_manager import get_current_model
    price_model_key = get_current_model('chat')

    price_model = PRICES.get(price_model_key)
    if price_model:
        cost_input = (safe_prompt_tokens / 1_000_000) * price_model['input']
        cost_output = (safe_output_tokens / 1_000_000) * price_model['output']
        stats['total_cost'] = stats.get('total_cost', 0.0) + cost_input + cost_output
    else:
        logger.warning(loc.get_string("logs.price_model_not_found", model=price_model_key))

    save_user_profile(user_id, profile)