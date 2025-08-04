import logging
from config import DEFAULT_GEMINI_MODEL, DEFAULT_IMAGEN_MODEL, DEFAULT_VIDEO_MODEL

logger = logging.getLogger("ModelManager")

current_models = {
    "chat": DEFAULT_GEMINI_MODEL,
    "image": DEFAULT_IMAGEN_MODEL,
    "video": DEFAULT_VIDEO_MODEL
}

def get_current_model(model_type: str) -> str:
    """Returns the current model for the specified type ('chat' or 'image')."""
    return current_models.get(model_type, DEFAULT_GEMINI_MODEL)

def set_current_model(model_type: str, new_model_name: str) -> bool:
    """Sets a new model and returns True if successful."""
    if model_type not in current_models:
        return False
    
    logger.info(f"Changing {model_type} model from '{current_models[model_type]}' to '{new_model_name}'")
    current_models[model_type] = new_model_name
    return True
