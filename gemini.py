import os
import time
import traceback
import logging
import asyncio
import itertools
from io import BytesIO

import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

import PIL.Image
from google import genai
from google.genai import types
from google.api_core import exceptions as google_exceptions
from google.genai import errors as genai_errors
import yt_dlp
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch

from config import GOOGLE_API_KEYS, default_system_instruction
from history import append_history, load_and_deserialize_history_for_model
from group_history import get_combined_group_history
from telethon import TelegramClient
import re
import instruction_manager
import user_session_manager as usm
from localization import loc
import model_manager

logger = logging.getLogger("Gemini")

OFF_FLAG_VIDEO = True

try:
    clients = [genai.Client(api_key=key) for key in GOOGLE_API_KEYS]
    client_cycler = itertools.cycle(clients)
    logger.info(loc.get_string("logs.gemini_clients_loaded", count=len(clients)))
except Exception as e:
    logger.critical(loc.get_string("logs.gemini_clients_failed", error=e))
    clients = []

def get_next_client():
    if not clients: return None
    return next(client_cycler)

GLOBAL_TELETHON_CLIENT = None
def set_telethon_client(telethon_client: TelegramClient):
    global GLOBAL_TELETHON_CLIENT
    GLOBAL_TELETHON_CLIENT = telethon_client

tools = []
tools.append(Tool(url_context=types.UrlContext))
tools.append(Tool(google_search=types.GoogleSearch))


async def get_chat_history_tool_async(group_names: list[str] = [], num_messages: int = 100):
    if not GLOBAL_TELETHON_CLIENT: return loc.get_string("errors.telegram_client_not_initialized")
    return await get_combined_group_history(GLOBAL_TELETHON_CLIENT, group_names, num_messages)

def _extract_youtube_url(text: str) -> str | None:
    """Extracts the first YouTube link from the text."""
    regex = r"(https?://(?:www\.)?(?:youtube\.com/watch\?v=[\w-]+|youtu\.be/[\w-]+|youtube\.com/shorts/[\w-]+))"
    match = re.search(regex, text)
    return match.group(0) if match else None


async def view_youtube_video(video_url: str, user_query: str) -> str:
    """Analyzes the content of a YouTube video by link and answers the user's question."""
    logger.info(loc.get_string("logs.youtube_analysis_request", url=video_url, query=user_query))
    client = get_next_client()
    if not client: return loc.get_string("errors.gemini_no_available_clients")
    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model_manager.get_current_model("chat"),
            contents=[
                user_query,
                types.Part(file_data=types.FileData(mime_type="video/mp4", file_uri=video_url))
            ]
        )
        return "".join(part.text for part in response.candidates[0].content.parts if part.text)
    except Exception as e:
        logger.error(loc.get_string("logs.youtube_analysis_error", error=e))
        return loc.get_string("errors.youtube_analysis_failed", error=e)

async def download_youtube_video(video_url_or_text: str, quality: str = 'best', audio_only: bool = False) -> str:
    """Downloads video or audio from YouTube by link."""
    video_url = _extract_youtube_url(video_url_or_text)
    if not video_url:
        return loc.get_string("errors.youtube_url_not_found")

    logger.info(loc.get_string("logs.youtube_download_request", url=video_url, audio_only=audio_only))
    try:
        download_dir = "downloads"
        os.makedirs(download_dir, exist_ok=True)
        
        ydl_opts = {'outtmpl': os.path.join(download_dir, '%(title)s - %(id)s.%(ext)s'), 'noplaylist': True}
        if audio_only:
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]
        else:
            quality_map = {'best': '1080', '1080p': '1080', '720p': '720', '480p': '480', '360p': '360', '240p': '240', '144p': '144'}
            res = quality_map.get(quality.lower(), '720')
            ydl_opts['format'] = f'bestvideo[height<=?{res}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            filename = ydl.prepare_filename(info)
            if not os.path.exists(filename): ydl.download([video_url])
            base, _ = os.path.splitext(filename)
            if audio_only and os.path.exists(base + ".mp3"): filename = base + ".mp3"
        
        if not os.path.exists(filename): return loc.get_string("logs.youtube_download_file_not_found", url=video_url)
        
        file_size = os.path.getsize(filename) / (1024*1024)
        caption = loc.get_string("replies.youtube_download_success", title=info.get('title', 'N/A'), size_mb=f"{file_size:.2f}")
        return f"ACTION_SEND_FILE|{filename}|{caption}"
    except Exception as e:
        logger.error(loc.get_string("logs.youtube_download_error", error=e))
        return loc.get_string("errors.youtube_download_failed", error=e)
    
def run_search_specialist(search_query: str) -> str:
    """
    Invokes a "one-off" Gemini assistant that has access
    to the GoogleSearch tool to perform a search query.
    Can browse URLs.
    """
    logger.info(loc.get_string("logs.search_specialist_request", query=search_query))

    if len(GOOGLE_API_KEYS) < 2:
        return loc.get_string("errors.search_specialist_requires_2_keys")
    
    specialist_api_key = GOOGLE_API_KEYS[-1]

    try:
        search_client = genai.Client(api_key=specialist_api_key)

        search_config = types.GenerateContentConfig(
            tools=tools,
            temperature=0.0
        )

        prompt = loc.get_string("prompts.search_specialist", search_query=search_query)
        
        response = search_client.models.generate_content(
            model=model_manager.get_current_model("chat"),
            contents=prompt,
            config=search_config
        )

        logger.info(loc.get_string("logs.search_specialist_success"))
        return response.text

    except Exception as e:
        logger.error(loc.get_string("logs.search_specialist_error", error=e))
        return loc.get_string("errors.search_specialist_error", error=e)

def generate_video_from_prompt(prompt: str, aspect_ratio: str = '16:9') -> str:
    """
    Creates a video based on a text description (prompt) using the Veo model.
    Returns the file path for sending.
    """
    if OFF_FLAG_VIDEO == True:
        return loc.get_string("errors.video_generation_disabled")
    logger.info(loc.get_string("logs.video_generation_request", prompt=prompt))
    client = get_next_client()
    if not client: return loc.get_string("errors.gemini_no_available_clients_for_video")

    try:
        video_config = types.GenerateVideosConfig(
            person_generation="allow_all",
            aspect_ratio=aspect_ratio,
        )

        operation = client.models.generate_videos(
            model=model_manager.get_current_model("video"),
            prompt=prompt,
            config=video_config,
        )

        logger.info(loc.get_string("logs.video_generation_started", name=operation.name))

        while not operation.done:
            time.sleep(20)
            operation = client.operations.get(operation)
            logger.info(loc.get_string("logs.video_generation_status_check", name=operation.name))
        logger.info(loc.get_string("logs.video_generation_complete"))

        generated_video = operation.response.generated_videos[0]
        
        download_dir = "downloads"
        os.makedirs(download_dir, exist_ok=True)
        
        timestamp = int(time.time())
        filename = f"generated_video_{timestamp}.mp4"
        filepath = os.path.join(download_dir, filename)

        client.files.download(file=generated_video.video)
        generated_video.video.save(filepath)
        
        file_size = os.path.getsize(filepath) / (1024*1024)
        
        logger.info(loc.get_string("logs.video_saved", path=filepath, size_mb=f"{file_size:.2f}"))
        
        caption = loc.get_string("replies.video_generation_success", prompt=prompt, size_mb=f"{file_size:.2f}")
        return f"ACTION_SEND_FILE|{filepath}|{caption}"

    except Exception as e:
        logger.error(loc.get_string("logs.video_generation_error", error=e, traceback=traceback.format_exc()))
        return loc.get_string("errors.video_generation_failed", error=e)

def generate_photo_from_prompt(prompt: str, aspect_ratio: str = '1:1') -> str:
    """
    Creates an image based on a text description (prompt) using the Imagen model.
    Returns the file path for sending.
    """
    logger.info(loc.get_string("logs.photo_generation_request", prompt=prompt))
    client = get_next_client()
    if not client: return loc.get_string("errors.gemini_no_available_clients_for_image")

    try:
        image_config = types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio=aspect_ratio
        )

        response = client.models.generate_images(
            model=model_manager.get_current_model("image"),
            prompt=prompt,
            config=image_config,
        )
        
        if not hasattr(response, 'generated_images') or not response.generated_images:
            logger.error(loc.get_string("logs.photo_generation_no_images"))
            return loc.get_string("errors.image_generation_no_images_returned")

        generated_image = response.generated_images[0]
        
        image_bytes = generated_image.image.image_bytes

        images_dir = "images"
        os.makedirs(images_dir, exist_ok=True)
        
        timestamp = int(time.time())
        filename = f"gen_photo_{timestamp}.png"
        filepath = os.path.join(images_dir, filename)

        with open(filepath, 'wb') as f:
            f.write(image_bytes)

        file_size = os.path.getsize(filepath) / (1024*1024)
        logger.info(loc.get_string("logs.photo_saved", path=filepath, size_mb=f"{file_size:.2f}"))
        
        caption = loc.get_string("replies.photo_generation_success", prompt=prompt)
        return f"ACTION_SEND_FILE|{filepath}|{caption}"

    except Exception as e:
        logger.error(loc.get_string("logs.photo_generation_error", error=e, traceback=traceback.format_exc()))
        return loc.get_string("errors.image_generation_failed", error=e)

get_chat_history_declaration = types.FunctionDeclaration(
    name='get_chat_history_tool_async',
    description=loc.get_string("tool_descriptions.get_chat_history"),
    parameters=types.Schema(type=types.Type.OBJECT, properties={'group_names': types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)), 'num_messages': types.Schema(type=types.Type.INTEGER)})
)
view_youtube_declaration = types.FunctionDeclaration(
    name='view_youtube_video',
    description=loc.get_string("tool_descriptions.view_youtube_video"),
    parameters=types.Schema(type=types.Type.OBJECT, properties={'video_url': types.Schema(type=types.Type.STRING), 'user_query': types.Schema(type=types.Type.STRING)}, required=['video_url', 'user_query'])
)
download_youtube_declaration = types.FunctionDeclaration(
    name='download_youtube_video',
    description=loc.get_string("tool_descriptions.download_youtube_video"),
    parameters=types.Schema(type=types.Type.OBJECT, properties={
        'video_url_or_text': types.Schema(type=types.Type.STRING, description=loc.get_string("tool_descriptions.param_video_url_or_text")),
        'quality': types.Schema(type=types.Type.STRING, description=loc.get_string("tool_descriptions.param_quality")),
        'audio_only': types.Schema(type=types.Type.BOOLEAN, description=loc.get_string("tool_descriptions.param_audio_only"))
    }, required=['video_url_or_text'])
)
run_search_specialist_declaration = types.FunctionDeclaration(
    name='run_search_specialist',
    description=loc.get_string("tool_descriptions.run_search_specialist"),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={'search_query': types.Schema(type=types.Type.STRING, description=loc.get_string("tool_descriptions.param_search_query"))},
        required=['search_query']
    )
)
generate_video_declaration = types.FunctionDeclaration(
    name='generate_video_from_prompt',
    description=loc.get_string("tool_descriptions.generate_video_from_prompt"),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            'prompt': types.Schema(type=types.Type.STRING, description=loc.get_string("tool_descriptions.param_video_prompt")),
            'aspect_ratio': types.Schema(type=types.Type.STRING, description=loc.get_string("tool_descriptions.param_video_aspect_ratio"))
        },
        required=['prompt']
    )
)
generate_photo_declaration = types.FunctionDeclaration(
    name='generate_photo_from_prompt',
    description=loc.get_string("tool_descriptions.generate_photo_from_prompt"),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            'prompt': types.Schema(type=types.Type.STRING, description=loc.get_string("tool_descriptions.param_photo_prompt")),
            'aspect_ratio': types.Schema(type=types.Type.STRING, description=loc.get_string("tool_descriptions.param_photo_aspect_ratio"))
        },
        required=['prompt']
    )
)
available_tools_for_chat = {
    "get_chat_history_tool_async": get_chat_history_tool_async,
    "view_youtube_video": view_youtube_video,
    "download_youtube_video": download_youtube_video,
    "run_search_specialist": run_search_specialist,
    "generate_video_from_prompt": generate_video_from_prompt,
    "generate_photo_from_prompt": generate_photo_from_prompt,
}

def create_chat_config(user_id: int = None) -> types.GenerateContentConfig:
    """Creates a chat configuration with a personalized user instruction."""
    system_instruction = instruction_manager.get_user_instruction(user_id) if user_id else default_system_instruction

    all_declarations = [
        get_chat_history_declaration,
        view_youtube_declaration,
        download_youtube_declaration,
        run_search_specialist_declaration,
        generate_video_declaration,
        generate_photo_declaration
    ]
    
    return types.GenerateContentConfig(
        temperature=0.8,
        tools=[types.Tool(function_declarations=all_declarations)],
        tool_config=types.ToolConfig(
             function_calling_config=types.FunctionCallingConfig(
                mode='AUTO'
             )
        ),
        system_instruction=types.Content(parts=[types.Part(text=system_instruction)]),
        safety_settings=[{"category": c, "threshold": "BLOCK_NONE"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
    )


search_config = types.GenerateContentConfig(
    temperature=0.7,
    max_output_tokens=8000,
    tools=tools,
    safety_settings=[
        {"category": c, "threshold": "BLOCK_NONE"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]
    ]
)

chat_sessions = {}

def get_chat_session(session_key: str, user_id: int = None):
    if session_key not in chat_sessions:
        client = get_next_client()
        if not client: raise RuntimeError(loc.get_string("errors.gemini_no_available_clients"))
        init_history = [msg for msg in load_and_deserialize_history_for_model(session_key) if msg.get("role") != "tool"]
        config = create_chat_config(user_id)
        
        model_name = model_manager.get_current_model("chat")
        
        chat_sessions[session_key] = client.chats.create(model=model_name, history=init_history, config=config)
    return chat_sessions[session_key]

async def _execute_tool_call(function_call):
    tool_function = available_tools_for_chat.get(function_call.name)
    if not tool_function: return loc.get_string("errors.unknown_function_call", name=function_call.name)
    args = dict(function_call.args)
    if asyncio.iscoroutinefunction(tool_function):
        return await tool_function(**args)
    else:
        return await asyncio.to_thread(tool_function, **args)

async def call_gemini(session_key: str, parts: list, user_id: int, username: str, first_name: str, status_callback=None) -> str:
    if not clients:
        return loc.get_string("errors.gemini_clients_not_initialized")
    try:
        chat_session = get_chat_session(session_key, user_id)
        append_history(session_key, "user", parts)
        current_parts = parts

        for _ in range(5):
            try:
                response = await asyncio.to_thread(chat_session.send_message, message=current_parts)

                if hasattr(response, 'usage_metadata'):
                    prompt_tokens = response.usage_metadata.prompt_token_count
                    output_tokens = response.usage_metadata.candidates_token_count
                    logger.info(loc.get_string("logs.gemini_token_stats", 
                                               session=os.path.basename(session_key), 
                                               prompt=prompt_tokens, 
                                               output=output_tokens))
                    usm.update_session_stats(user_id, username, first_name, prompt_tokens, output_tokens)

                if not response or not response.candidates or not response.candidates[0].content:
                    finish_reason_str = loc.get_string("errors.gemini_unknown_reason")
                    try:
                        finish_reason_str = response.candidates[0].finish_reason.name
                    except (AttributeError, IndexError):
                        pass
                    
                    logger.error(loc.get_string("logs.gemini_empty_response", reason=finish_reason_str))
                    
                    reason_text = ""
                    if finish_reason_str == 'SAFETY':
                        reason_text = loc.get_string("errors.gemini_safety_reason")
                    elif finish_reason_str == 'RECITATION':
                        reason_text = loc.get_string("errors.gemini_recitation_reason")
                    
                    return loc.get_string("errors.gemini_empty_or_blocked_response", reason=reason_text)

                response_parts = response.candidates[0].content.parts
                append_history(session_key, "model", response_parts)

                function_call = None
                for part in response_parts:
                    if part.function_call:
                        function_call = part.function_call
                        break

                if not function_call:
                    text_result = "".join(part.text for part in response_parts if part.text)
                    return text_result.replace("", "")

                logger.info(loc.get_string("logs.gemini_function_call", name=function_call.name, args=dict(function_call.args)))

                if status_callback and asyncio.iscoroutinefunction(status_callback):
                    try:
                        await status_callback(function_call.name)
                    except Exception as e:
                        logger.warning(loc.get_string("logs.gemini_status_callback_error", e=e))
                
                result = await _execute_tool_call(function_call)
                
                if isinstance(result, str) and result.startswith("ACTION_SEND_FILE|"):
                    return result
                
                response_part = types.Part.from_function_response(name=function_call.name, response={'result': result})
                append_history(session_key, "tool", [response_part])
                current_parts = [response_part]
            except (genai_errors.ServerError, google_exceptions.ResourceExhausted, google_exceptions.ServiceUnavailable) as e:
                logger.warning(loc.get_string("logs.gemini_api_error", error=e))
                new_client = get_next_client()
                if new_client:
                    chat_session._client = new_client
                else:
                    logger.error(loc.get_string("logs.gemini_all_keys_exhausted"))
                    return loc.get_string("errors.gemini_all_keys_failed")
        return loc.get_string("errors.gemini_server_fell")

    except Exception as e:
        error_msg = loc.get_string("logs.gemini_critical_error", error=e, traceback=traceback.format_exc())
        logger.error(error_msg)
        return loc.get_string("errors.gemini_unexpected_error")