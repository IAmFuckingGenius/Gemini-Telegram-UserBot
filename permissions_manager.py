import json
import os
import logging
from typing import List
from localization import loc

logger = logging.getLogger("PermissionsManager")
PERMISSIONS_FILE = "permissions.json"

def _load_permissions() -> dict:
    """Loads permissions from the permissions.json file."""
    if not os.path.exists(PERMISSIONS_FILE):
        return {}
    try:
        with open(PERMISSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(loc.get_string("logs.permissions_file_error", file=PERMISSIONS_FILE, error=e))
        return {}

def get_disallowed_tools_for_user(user_id: int) -> List[str]:
    """
    Returns a list of tool names that are disallowed for the user.
    """
    permissions = _load_permissions()
    user_id_str = str(user_id)
    return permissions.get(user_id_str, [])