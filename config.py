import os
import sys
from dotenv import load_dotenv

load_dotenv()

api_keys_str = os.environ.get('GOOGLE_API_KEYS')
if not api_keys_str:
    print("CRITICAL ERROR: GOOGLE_API_KEYS not found in environment variables.")
    sys.exit(1)

GOOGLE_API_KEYS = [key.strip() for key in api_keys_str.split(',') if key.strip()]
if not GOOGLE_API_KEYS:
    print("CRITICAL ERROR: GOOGLE_API_KEYS list is empty.")
    sys.exit(1)

API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
PHONE = os.environ['PHONE']

ADMIN_USER_IDS = [int(uid.strip()) for uid in os.environ.get('ADMIN_USER_IDS', '').split(',') if uid.strip()]

ALLOWED_GROUPS = [int(x.strip()) for x in os.environ.get('ALLOWED_GROUPS', '').split(',') if x.strip()]

AUTHORIZED_USER_IDS = [int(uid.strip()) for uid in os.environ.get('AUTHORIZED_USER_IDS', '').split(',') if uid.strip()]


default_system_instruction = (
    """
    You are a tool for completing tasks and for entertainment.
    """
)

HISTORY_SOURCE_GROUPS = [int(x.strip()) for x in os.environ.get('HISTORY_SOURCE_GROUPS', '').split(',') if x.strip()]
DEFAULT_GEMINI_MODEL = "gemini-2.5-pro"
DEFAULT_IMAGEN_MODEL = "imagen-4.0-generate-preview-06-06" 
DEFAULT_VIDEO_MODEL = "veo-3.0-generate-preview"

AVAILABLE_LANGUAGES = {
    "en_US": "English",
    "ru_RU": "Русский"
}
